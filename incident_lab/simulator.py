import re
import uuid

from . import store
from .models import Approval, Proposal

TARGETS = {
    "rollback_release": "orders-api",
    "restore_worker_concurrency": "orders-worker",
    "enable_degraded_mode": "upstream-client",
    "none": "none",
}
PARAMETERS = {
    "rollback_release": {"release": "2026.09.1"},
    "restore_worker_concurrency": {"concurrency": 8},
    "enable_degraded_mode": {"queue_shipping": True},
    "none": {},
}


def observed_health(run, fixture):
    metrics = dict(fixture["initial_metrics"])
    status = "unhealthy"
    if run["executions"] and run["outcome"] in ["healthy", "degraded"]:
        metrics.update(error_rate_pct=0.2, p95_ms=180)
        if run["outcome"] == "healthy":
            metrics.update(db_connections=35, worker_concurrency=8)
        if run["proposal"] and run["proposal"]["action"] == "rollback_release":
            metrics["release"] = "2026.09.1"
        status = run["outcome"]
    return {
        "id": f"health-r{run['revision']}",
        "revision": run["revision"],
        "status": status,
        "metrics": metrics,
        "note": "Provider remains unavailable; shipping queued."
        if status == "degraded"
        else "Synthetic service observation.",
    }


def public_items(items):
    return [{k: v for k, v in item.items() if k != "supports"} for item in items]


def read_tool(rid, name, args, path=None):
    run = store.get(rid, path)
    fixture = store.case(run["case_id"])
    if name not in ["get_service_health", "query_logs", "query_metrics", "list_changes", "search_runbooks"]:
        raise ValueError("Unknown tool")
    if set(args) - ({"query"} if name == "search_runbooks" else set()):
        raise ValueError("Unknown or cross-run arguments")
    fault = fixture.get("fault")
    if fault and fault["tool"] == name:
        with store.transaction(path) as c:
            c.execute(
                "INSERT INTO attempts VALUES(?,?,1) ON CONFLICT(run_id,tool) DO UPDATE SET count=count+1",
                (rid, name),
            )
            count = c.execute("SELECT count FROM attempts WHERE run_id=? AND tool=?", (rid, name)).fetchone()[
                0
            ]
        if fault["mode"] == "always" or count == 1:
            raise TimeoutError("Synthetic telemetry read timed out")
    if name == "get_service_health":
        return observed_health(run, fixture)
    if name == "query_logs":
        return {"items": public_items(fixture["logs"])}
    if name == "query_metrics":
        return {
            "items": [
                {
                    "id": f"metric-r{run['revision']}",
                    "window": "10:00–10:05 UTC",
                    "values": observed_health(run, fixture)["metrics"],
                }
            ]
        }
    if name == "list_changes":
        return {"items": public_items(fixture["changes"])}
    query = args.get("query", "incident")
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("Invalid search")
    terms = re.findall(r"[a-zA-Z0-9]+", query)[:12]
    with store.connect(path) as c:
        rows = c.execute(
            "SELECT id,body FROM runbooks WHERE runbooks MATCH ? ORDER BY rank LIMIT 3",
            (" OR ".join('"' + t + '"' for t in terms) or "incident",),
        ).fetchall()
    items = [dict(x) for x in rows]
    if fixture["stale"]:
        items.append(
            {
                "id": "runbook-archived",
                "body": "ARCHIVED v1, superseded: restart all workers for every order error. Do not use as current guidance.",
            }
        )
    return {"items": items}


def evidence_ids(run):
    found = set()

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("id"), str):
                found.add(x["id"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for e in run["events"]:
        if e["type"] == "tool_result":
            walk(e["payload"].get("result"))
    return found


def propose(rid, proposal, path=None):
    p = Proposal.model_validate(proposal)
    run = store.get(rid, path)
    if p.target != TARGETS[p.action]:
        raise ValueError("Action target mismatch")
    if p.action != "none" and (not p.evidence_ids or not set(p.evidence_ids) <= evidence_ids(run)):
        raise ValueError("Proposal cites unseen or missing evidence")
    if p.action == "none" and p.diagnosis != "insufficient_evidence":
        raise ValueError("No action requires explicit abstention")
    pid = str(uuid.uuid4())
    with store.transaction(path) as c:
        if c.execute("SELECT state FROM runs WHERE id=?", (rid,)).fetchone()["state"] != "investigating":
            raise ValueError("Run no longer investigating")
        state = "inconclusive" if p.action == "none" else "awaiting_approval"
        c.execute(
            "UPDATE runs SET state=?,proposal_id=?,proposal=? WHERE id=?",
            (state, pid, p.model_dump_json(), rid),
        )
        store.emit(
            c,
            rid,
            "proposal",
            {"id": pid, "revision": run["revision"], "parameters": PARAMETERS[p.action], **p.model_dump()},
        )
        if state == "inconclusive":
            store.emit(c, rid, "inconclusive", {"reason": "Agent abstained"})
    return pid


def approve(rid, approval, path=None):
    a = Approval.model_validate(approval)
    with store.transaction(path) as c:
        row = c.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        if row is None:
            raise KeyError(rid)
        run = dict(row)
        if (
            run["state"] != "awaiting_approval"
            or run["proposal_id"] != a.proposal_id
            or run["revision"] != a.revision
        ):
            raise ValueError("Stale, duplicate, or cross-run approval")
        c.execute(
            "INSERT INTO approvals VALUES(?,?,?,?,?)",
            (rid, a.proposal_id, a.revision, a.decision, store.now()),
        )
        store.emit(c, rid, "approval", a.model_dump())
        if a.decision == "reject":
            c.execute("UPDATE runs SET state='rejected' WHERE id=?", (rid,))
            store.emit(c, rid, "rejected", {"reason": "Human rejected proposal"})
            return
        p = Proposal.model_validate_json(run["proposal"])
        if p.target != TARGETS[p.action] or p.action == "none":
            raise ValueError("Invalid action")
        store.emit(
            c, rid, "executing", {"action": p.action, "target": p.target, "parameters": PARAMETERS[p.action]}
        )
        truth = store.case(run["case_id"])["ground_truth"]
        outcome = truth["outcome"] if p.action == truth["action"] else "unhealthy"
        c.execute(
            "UPDATE runs SET state='verifying',revision=revision+1,executions=executions+1,outcome=? WHERE id=?",
            (outcome, rid),
        )
        store.emit(c, rid, "verifying", {"revision": run["revision"] + 1})


def cancel(rid, path=None):
    return store.transition(rid, "cancelled", {"reason": "Operator cancelled"}, path)
