import asyncio
import json

import pytest

from incident_lab import store
from incident_lab.agent import investigate, session, tool
from incident_lab.models import Proposal
from incident_lab.simulator import approve, cancel, propose, read_tool


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.sqlite")
    store.init(path)
    return path


def prepared(db):
    fixture = store.cases()[0]
    rid = store.create(fixture["id"], path=db)
    store.transition(rid, "investigating", path=db)
    result = read_tool(rid, "query_logs", {}, db)
    with store.transaction(db) as c:
        store.emit(c, rid, "tool_result", {"name": "query_logs", "result": result})
    p = {
        "diagnosis": "bad_deployment",
        "action": "rollback_release",
        "target": "orders-api",
        "summary": "Release change correlates with TypeError",
        "evidence_ids": ["log-001"],
        "uncertainty": "Synthetic test",
        "expected_effect": "API recovery",
    }
    pid = propose(rid, p, db)
    return rid, pid, p


def test_approval_single_execution_and_stale(db):
    rid, pid, _ = prepared(db)
    with pytest.raises(ValueError):
        approve(rid, {"proposal_id": pid, "revision": 1, "decision": "approve"}, db)
    body = {"proposal_id": pid, "revision": 0, "decision": "approve"}
    approve(rid, body, db)
    with pytest.raises(ValueError):
        approve(rid, body, db)
    assert store.get(rid, db)["executions"] == 1
    assert read_tool(rid, "get_service_health", {}, db)["status"] == "healthy"


def test_cross_run_and_reject(db):
    first, pid, _ = prepared(db)
    second, _, _ = prepared(db)
    with pytest.raises(ValueError):
        approve(second, {"proposal_id": pid, "revision": 0, "decision": "approve"}, db)
    approve(first, {"proposal_id": pid, "revision": 0, "decision": "reject"}, db)
    assert store.get(first, db)["executions"] == 0


def test_cancel_and_invalid_action(db):
    rid, pid, p = prepared(db)
    cancel(rid, db)
    with pytest.raises(ValueError):
        approve(rid, {"proposal_id": pid, "revision": 0, "decision": "approve"}, db)
    with pytest.raises(ValueError):
        Proposal.model_validate(p | {"action": "execute_shell"})
    with pytest.raises(ValueError):
        read_tool(rid, "query_logs", {"run_id": "other"}, db)


async def test_actual_mcp_is_scoped_and_read_only(db):
    rid = store.create(store.cases()[0]["id"], path=db)
    async with session(rid, db) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == {
            "get_service_health",
            "query_logs",
            "query_metrics",
            "list_changes",
            "search_runbooks",
        }
        result = await tool(client, rid, "query_logs", {}, db)
        assert "supports" not in json.dumps(result)
        assert result["items"][0]["id"] == "log-001"
        assert (await client.call_tool("execute_shell", {"command": "whoami"})).isError
        assert (await client.call_tool("query_logs", {"run_id": "other"})).isError
        assert (await client.call_tool("query_metrics", {"query": "extra"})).isError


async def test_unavailable_provider_fails_explicitly(db):
    class Unavailable:
        async def chat(self, *args, **kwargs):
            raise ConnectionError("Ollama unavailable")

    rid = store.create(store.cases()[0]["id"], path=db)
    await investigate(rid, db, Unavailable())
    assert store.get(rid, db)["state"] == "failed"


def test_split_frozen():
    import hashlib

    manifest = json.loads((store.ROOT / "cases/manifest.json").read_text())
    assert hashlib.sha256((store.ROOT / "cases/cases.json").read_bytes()).hexdigest() == manifest["sha256"]
    assert sum(c["split"] == "development" for c in store.cases()) == 12
    assert sum(c["split"] == "held_out" for c in store.cases()) == 18


def test_concurrent_approvals_execute_once(db):
    from concurrent.futures import ThreadPoolExecutor

    rid, pid, _ = prepared(db)

    def attempt(_):
        try:
            approve(rid, {"proposal_id": pid, "revision": 0, "decision": "approve"}, db)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(attempt, range(4))) == 1
    assert store.get(rid, db)["executions"] == 1


async def test_retry_is_bounded(db):
    from incident_lab.agent import read_with_retry

    fixture = next(c for c in store.cases() if c["variant"] == "tool_unavailable")
    rid = store.create(fixture["id"], path=db)
    async with session(rid, db) as client:
        assert (await read_with_retry(client, rid, "query_logs", {}, db))["unavailable"]
        assert (await read_with_retry(client, rid, "query_logs", {}, db))["unavailable"]
    assert sum(e["type"] == "tool_call" for e in store.get(rid, db)["events"]) == 2


async def test_cancellation_during_inference(db):
    started = asyncio.Event()

    class Slow:
        async def chat(self, *args, **kwargs):
            started.set()
            await asyncio.Event().wait()

    rid = store.create(store.cases()[0]["id"], path=db)
    task = asyncio.create_task(investigate(rid, db, Slow()))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store.get(rid, db)["state"] == "cancelled"
    assert store.get(rid, db)["executions"] == 0


async def test_execution_timeout_explicit(db, monkeypatch):
    import incident_lab.agent as agent

    monkeypatch.setattr(agent, "ACTIVE_SECONDS", 0.5)

    class Slow:
        async def chat(self, *args, **kwargs):
            await asyncio.sleep(1)

    rid = store.create(store.cases()[0]["id"], path=db)
    await investigate(rid, db, Slow())
    run = store.get(rid, db)
    assert run["state"] == "inconclusive"
    assert not run["executions"]


async def test_model_limit(db):
    class Invalid:
        async def chat(self, *args, **kwargs):
            return {"message": {"role": "assistant", "content": "not JSON"}}

    rid = store.create(store.cases()[0]["id"], path=db)
    await investigate(rid, db, Invalid())
    run = store.get(rid, db)
    assert run["state"] == "inconclusive"
    assert sum(e["type"] == "model_result" for e in run["events"]) == 6


async def test_missing_verification_never_recovers(db, monkeypatch):
    import incident_lab.agent as agent

    rid, pid, _ = prepared(db)
    approve(rid, {"proposal_id": pid, "revision": 0, "decision": "approve"}, db)

    async def unavailable(*args):
        return {"error": "telemetry unavailable"}

    monkeypatch.setattr(agent, "read_with_retry", unavailable)
    await agent.verify(rid, db)
    run = store.get(rid, db)
    assert run["state"] == "inconclusive"
    assert not any(e["type"] == "completed" for e in run["events"])


def test_api_restart_and_sse_reconnect(db, monkeypatch):
    from fastapi.testclient import TestClient

    from incident_lab import api

    monkeypatch.setattr(api, "DB", db)
    interrupted = store.create(store.cases()[0]["id"], path=db)
    store.transition(interrupted, "investigating", path=db)
    waiting, pid, _ = prepared(db)
    with TestClient(api.app) as client:
        run = client.get("/api/runs/" + interrupted).json()
        assert run["state"] == "inconclusive"
        assert client.get("/api/runs/" + waiting).json()["state"] == "awaiting_approval"
        cursor = run["events"][0]["seq"]
        response = client.get("/api/runs/" + interrupted + "/events", headers={"Last-Event-ID": str(cursor)})
        assert response.status_code == 200
        ids = [int(line[4:]) for line in response.text.splitlines() if line.startswith("id: ")]
        assert ids == sorted(ids) and min(ids) > cursor
        assert client.post("/api/runs", json={"case_id": store.cases()[0]["id"]}).status_code == 403
        assert (
            client.post(
                "/api/runs/" + waiting + "/approval",
                json={"proposal_id": pid, "revision": 0, "decision": "approve", "command": "shell"},
            ).status_code
            == 422
        )


def test_degraded_and_wrong_action(db):
    fixture = next(c for c in store.cases() if c["ground_truth"]["diagnosis"] == "upstream_outage")
    rid = store.create(fixture["id"], path=db)
    store.transition(rid, "investigating", path=db)
    with store.transaction(db) as c:
        store.emit(
            c, rid, "tool_result", {"name": "query_logs", "result": read_tool(rid, "query_logs", {}, db)}
        )
    p = {
        "diagnosis": "upstream_outage",
        "action": "enable_degraded_mode",
        "target": "upstream-client",
        "summary": "Provider failed",
        "evidence_ids": ["log-001"],
        "uncertainty": "Provider remains down",
        "expected_effect": "Degraded service",
    }
    pid = propose(rid, p, db)
    approve(rid, {"proposal_id": pid, "revision": 0, "decision": "approve"}, db)
    health = read_tool(rid, "get_service_health", {}, db)
    assert health["status"] == "degraded" and health["metrics"]["upstream_error_pct"] == 100


async def test_end_to_end_with_actual_mcp(db):
    from incident_lab.agent import verify

    class ScriptedTestProvider:
        def __init__(self):
            self.turn = 0

        async def chat(self, messages, tools=None):
            self.turn += 1
            if self.turn == 1:
                return {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"function": {"name": "query_logs", "arguments": {}}}],
                    }
                }
            if self.turn == 2:
                return {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "diagnosis": "bad_deployment",
                                "action": "rollback_release",
                                "target": "orders-api",
                                "summary": "Matched stack trace",
                                "evidence_ids": ["log-001"],
                                "uncertainty": "Test provider only",
                                "expected_effect": "Healthy API",
                            }
                        ),
                    }
                }
            return {
                "message": {
                    "role": "assistant",
                    "content": "Fresh health observation shows recovery in the simulator.",
                }
            }

    provider = ScriptedTestProvider()
    rid = store.create(store.cases()[0]["id"], path=db)
    await investigate(rid, db, provider)
    run = store.get(rid, db)
    assert run["state"] == "awaiting_approval" and run["executions"] == 0
    approve(rid, {"proposal_id": run["proposal_id"], "revision": run["revision"], "decision": "approve"}, db)
    await verify(rid, db, provider)
    run = store.get(rid, db)
    assert run["state"] == "completed" and run["executions"] == 1
    assert run["events"][-2]["payload"]["observed_status"] == "healthy"
