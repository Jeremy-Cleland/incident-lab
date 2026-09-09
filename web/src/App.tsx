import React, { useEffect, useRef, useState } from "react";
type Event = {
  seq: number;
  type: string;
  payload: Record<string, any>;
  at: string;
};
type Run = {
  id: string;
  state: string;
  case_id: string;
  revision: number;
  proposal_id: string;
  proposal: any;
  events: Event[];
  metadata: Record<string, any>;
};
type Recording = {
  id: string;
  title: string;
  family: string;
  variant: string;
  file: string;
  state: string;
  correct: boolean;
  branch?: string;
};
type Index = {
  recordings: Recording[];
  reports: any[];
  status: string;
  model?: any;
  summary?: any;
};
const API = "http://127.0.0.1:8787";
const local = ["localhost", "127.0.0.1"].includes(location.hostname);
export default function App() {
  const [index, setIndex] = useState<Index | null>(null),
    [selected, setSelected] = useState(""),
    [run, setRun] = useState<Run | null>(null),
    [cursor, setCursor] = useState(0),
    [playing, setPlaying] = useState(false),
    [tab, setTab] = useState("workspace"),
    [evidence, setEvidence] = useState<any>(null),
    [error, setError] = useState(""),
    [live, setLive] = useState(false),
    [scenarios, setScenarios] = useState<any[]>([]),
    [busy, setBusy] = useState(false),
    [theme, setTheme] = useState(
      localStorage.getItem("incident-theme") ||
        (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
    );
  const stream = useRef<EventSource | null>(null);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("incident-theme", theme);
  }, [theme]);
  useEffect(() => {
    fetch("/data/index.json")
      .then((r) => {
        if (!r.ok) throw Error("Demo data unavailable");
        return r.json();
      })
      .then((d: Index) => {
        setIndex(d);
        if (d.recordings.length) setSelected(d.recordings[0].id);
      })
      .catch((e) => setError(e.message));
    return () => stream.current?.close();
  }, []);
  useEffect(() => {
    if (!index || !selected || live) return;
    const item = index.recordings.find((r) => r.id === selected);
    if (!item) return;
    let active = true;
    setPlaying(false);
    setRun(null);
    setCursor(0);
    setEvidence(null);
    fetch(item.file)
      .then((r) => r.json())
      .then((d) => {
        if (active) {
          setRun(d.run);
          setCursor(Math.min(2, d.run.events.length));
        }
      })
      .catch(() => setError("Unable to load recording"));
    return () => {
      active = false;
    };
  }, [selected, index, live]);
  useEffect(() => {
    if (!playing || !run || live) return;
    const timer = setInterval(
      () =>
        setCursor((c) => {
          const next = run.events[c];
          if (!next || next.type === "approval") {
            setPlaying(false);
            return c;
          }
          return c + 1;
        }),
      850,
    );
    return () => clearInterval(timer);
  }, [playing, run, live]);
  const events = run
    ? run.events.slice(0, live ? run.events.length : cursor)
    : [];
  const proposalEvent = [...events]
    .reverse()
    .find((e) => e.type === "proposal");
  const approvalEvent = events.find((e) => e.type === "approval");
  const finalEvent = [...events]
    .reverse()
    .find((e) =>
      ["completed", "inconclusive", "failed", "cancelled", "rejected"].includes(
        e.type,
      ),
    );
  const healthEvents = events.filter(
    (e) => e.type === "tool_result" && e.payload.name === "get_service_health",
  );
  const latestHealth = healthEvents.at(-1)?.payload.result;
  const tools = events.filter((e) => e.type === "tool_call").length;
  const rows = events.filter(
    (e) => !["model_result", "phase_finished"].includes(e.type),
  );
  function watchRun(id: string) {
    stream.current?.close();
    const s = new EventSource(API + `/api/runs/${id}/events`);
    stream.current = s;
    s.addEventListener("trace", () =>
      fetch(API + `/api/runs/${id}`)
        .then((r) => r.json())
        .then((updated) => {
          setRun((previous) =>
            !previous ||
            previous.id !== updated.id ||
            (updated.events.at(-1)?.seq || 0) >=
              (previous.events.at(-1)?.seq || 0)
              ? updated
              : previous,
          );
          if (
            [
              "completed",
              "inconclusive",
              "failed",
              "cancelled",
              "rejected",
            ].includes(updated.state)
          )
            s.close();
        })
        .catch(() =>
          setError(
            "Unable to refresh run state. The event stream will reconnect.",
          ),
        ),
    );
    s.onerror = () =>
      setError(
        "Connection interrupted. The event stream will retry; your run remains stored locally.",
      );
  }
  async function liveStart(caseId: string) {
    setBusy(true);
    setError("");
    try {
      const r = await fetch(API + "/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: caseId }),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.detail);
      setRun(d);
      setCursor(0);
      localStorage.setItem("incident-last-run", d.id);
      watchRun(d.id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function toggleLive() {
    stream.current?.close();
    if (live) {
      setLive(false);
      setRun(null);
      return;
    }
    try {
      const r = await fetch(API + "/api/health");
      const h = await r.json();
      if (!h.live_enabled)
        throw Error(
          "Local live inference is disabled. Start the API with INCIDENT_LIVE=1.",
        );
      setScenarios(await (await fetch(API + "/api/scenarios")).json());
      setLive(true);
      setRun(null);
      const previousId = localStorage.getItem("incident-last-run");
      if (previousId) {
        const response = await fetch(API + `/api/runs/${previousId}`);
        if (response.ok) {
          const previous = await response.json();
          setRun(previous);
          watchRun(previous.id);
        } else localStorage.removeItem("incident-last-run");
      }
    } catch (e) {
      setError("Start the local API first. " + String(e));
    }
  }
  async function decide(decision: "approve" | "reject") {
    if (!run) return;
    if (!live) {
      setPlaying(false);
      const actual = run.events.find((e) => e.type === "approval");
      if (actual?.payload.decision === decision) {
        setCursor(run.events.indexOf(actual) + 1);
        setPlaying(true);
      } else {
        const alternate = index?.recordings.find(
          (r) =>
            r.branch === (decision === "approve" ? "approved" : "rejected") &&
            r.family ===
              index.recordings.find((x) => x.id === selected)?.family,
        );
        if (alternate) {
          setSelected(alternate.id);
          setError(
            "Switched to a separately recorded " +
              decision +
              " run. Its investigation may differ; no new inference occurred.",
          );
        } else
          setError(
            "No separately recorded " +
              decision +
              " run is available for this incident family.",
          );
      }
      return;
    }
    setBusy(true);
    try {
      const r = await fetch(API + `/api/runs/${run.id}/approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          proposal_id: run.proposal_id,
          revision: run.revision,
          decision,
        }),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.detail);
      setRun(d);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    if (run && live) {
      await fetch(API + `/api/runs/${run.id}/cancel`, { method: "POST" });
      setRun(await (await fetch(API + `/api/runs/${run.id}`)).json());
      stream.current?.close();
    }
  }
  return (
    <>
      <a className="skip" href="#main">
        Skip to workspace
      </a>
      <header className="topbar">
        <a href="#" className="brand" onClick={() => setTab("workspace")}>
          <span className="brand-mark">◈</span> Incident Lab
        </a>
        <nav aria-label="Primary">
          <button
            className={tab === "workspace" ? "active" : ""}
            onClick={() => setTab("workspace")}
          >
            Workspace
          </button>
          <button
            className={tab === "evaluation" ? "active" : ""}
            onClick={() => setTab("evaluation")}
          >
            Evaluation
          </button>
          <a href="https://github.com/Jeremy-Cleland/incident-lab">Source ↗</a>
        </nav>
        <button
          className="theme"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={
            "Switch to " + (theme === "dark" ? "light" : "dark") + " theme"
          }
        >
          {theme === "dark" ? "Light" : "Dark"}
        </button>
      </header>
      <main id="main" tabIndex={-1}>
        <section className="intro">
          <div>
            <p className="eyebrow">An engineering project by Jeremy Cleland</p>
            <h1>
              Investigate with evidence.
              <br />
              <em>Recover with oversight.</em>
            </h1>
          </div>
          <div className="intro-note">
            <span className="status-dot" />{" "}
            {live ? "Local live agent" : "Recorded local-agent runs"}
            <p>
              Synthetic incidents. Real tool calls.
              <br />
              Every recovery runs in a simulator.
            </p>
          </div>
        </section>
        <div className="notice">
          <span className="badge">Experimental</span>
          <p>
            {index?.status || "Loading evaluation artifacts…"}{" "}
            {live
              ? "Inference runs on your machine."
              : "Replay controls explore stored events; they do not invoke a model."}
          </p>
        </div>
        {error && (
          <div role="alert" className="error">
            {error}
            <button onClick={() => setError("")} aria-label="Dismiss error">
              ×
            </button>
          </div>
        )}
        {tab === "workspace" ? (
          <>
            <section className="toolbar">
              <div>
                <label htmlFor="recording">
                  {live
                    ? "Development scenario"
                    : "Choose a recorded investigation"}
                </label>
                {live ? (
                  <select
                    id="recording"
                    onChange={(e) => liveStart(e.target.value)}
                    value={run?.case_id || ""}
                    disabled={busy || Boolean(run && !finalEvent)}
                  >
                    <option value="">Select an incident…</option>
                    {scenarios.map((s, i) => (
                      <option key={s.id} value={s.id}>
                        Incident {i + 1} · {s.id}
                      </option>
                    ))}
                  </select>
                ) : (
                  <select
                    id="recording"
                    value={selected}
                    onChange={(e) => setSelected(e.target.value)}
                  >
                    {index?.recordings.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.title} ·{" "}
                        {r.branch === "rejected" ? "rejected" : r.state}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <div className="toolbar-controls">
                {local && (
                  <button className="secondary" onClick={toggleLive}>
                    {live ? "Switch to replays" : "Use local agent"}
                  </button>
                )}
                {!live && run && (
                  <>
                    <button
                      className="secondary"
                      onClick={() => {
                        setCursor(2);
                        setPlaying(false);
                        setEvidence(null);
                      }}
                    >
                      Reset
                    </button>
                    <button
                      className="primary"
                      disabled={cursor >= run.events.length}
                      onClick={() => setPlaying(!playing)}
                    >
                      {playing ? "Pause replay" : "Play replay"}
                    </button>
                    <button
                      className="secondary"
                      disabled={
                        cursor >= run.events.length ||
                        run.events[cursor]?.type === "approval"
                      }
                      onClick={() => setCursor((c) => c + 1)}
                    >
                      Next event →
                    </button>
                  </>
                )}
                {live && run && !finalEvent && (
                  <button className="secondary" onClick={cancel}>
                    Cancel run
                  </button>
                )}
              </div>
            </section>
            <div className="workspace" data-run-id={run?.id || ""}>
              <section className="timeline panel">
                <div className="panel-heading">
                  <h2>Investigation timeline</h2>
                  <span className="mono">
                    {live ? "LIVE" : `${cursor} / ${run?.events.length || 0}`}
                  </span>
                </div>
                <div className="run-stats" role="status" aria-live="polite">
                  <span>
                    <b>{tools}</b> tool calls
                  </span>
                  <span>
                    <b>{latestHealth?.status || "Unknown"}</b> observed health
                  </span>
                  <span>
                    <b>
                      {live
                        ? run?.state
                        : finalEvent?.type ||
                          (proposalEvent
                            ? "awaiting approval"
                            : "investigating")}
                    </b>{" "}
                    run state
                  </span>
                </div>
                <ol className="events">
                  {rows.map((e) => (
                    <li key={e.seq} className={"event event-" + e.type}>
                      <span className="event-marker" />
                      <div className="event-title">
                        <strong>{e.type.replaceAll("_", " ")}</strong>
                        <span className="mono">{e.at.slice(11, 19)}</span>
                      </div>
                      {e.type === "created" && <p>{e.payload.brief}</p>}
                      {e.type === "tool_call" && (
                        <p className="mono">
                          {e.payload.name}({JSON.stringify(e.payload.arguments)}
                          )
                        </p>
                      )}
                      {e.type === "tool_result" && (
                        <>
                          <p>{e.payload.name} returned an observation.</p>
                          <button
                            className="text-button"
                            onClick={() => setEvidence(e.payload)}
                          >
                            Inspect evidence ↗
                          </button>
                        </>
                      )}
                      {e.type === "tool_error" && (
                        <p className="warning">
                          {e.payload.name}: {e.payload.error}
                        </p>
                      )}
                      {e.type === "proposal" && <p>{e.payload.summary}</p>}
                      {e.type === "approval" && (
                        <p>Recorded decision: {e.payload.decision}.</p>
                      )}
                      {e.type === "executing" && (
                        <p>
                          {e.payload.action} · {e.payload.target}
                        </p>
                      )}
                      {e.type === "completed" && (
                        <>
                          <p>
                            <b>Observed result: {e.payload.observed_status}</b>
                          </p>
                          <p>{e.payload.agent_summary}</p>
                        </>
                      )}
                      {[
                        "inconclusive",
                        "failed",
                        "cancelled",
                        "rejected",
                        "output_rejected",
                      ].includes(e.type) && <p>{e.payload.reason}</p>}
                    </li>
                  ))}
                </ol>
                {!run && (
                  <div className="empty">
                    {live
                      ? "Choose a development incident to begin."
                      : index?.recordings.length
                        ? "Loading selected recording…"
                        : "Recordings will appear here when real evaluations finish."}
                  </div>
                )}
              </section>
              <aside className="detail-column">
                <section className="panel evidence-panel">
                  <div className="panel-heading">
                    <h2>Evidence inspector</h2>
                    {evidence && (
                      <button
                        className="text-button"
                        onClick={() => setEvidence(null)}
                      >
                        Clear
                      </button>
                    )}
                  </div>
                  {evidence ? (
                    <>
                      <p className="eyebrow">{evidence.name}</p>
                      <pre tabIndex={0} aria-label="Tool evidence">
                        {JSON.stringify(evidence.result, null, 2)}
                      </pre>
                    </>
                  ) : (
                    <p className="empty">
                      Select a tool result to inspect the exact evidence
                      returned to the agent. Nothing is reconstructed by the
                      replay viewer.
                    </p>
                  )}
                </section>
                <section className="panel action-panel">
                  <div className="panel-heading">
                    <h2>Recovery proposal</h2>
                    <span className="badge">Approval required</span>
                  </div>
                  {proposalEvent ? (
                    <>
                      <h3>
                        {proposalEvent.payload.action.replaceAll("_", " ")}
                      </h3>
                      <dl>
                        <dt>Target</dt>
                        <dd>{proposalEvent.payload.target}</dd>
                        <dt>Parameters</dt>
                        <dd>
                          <code>
                            {JSON.stringify(proposalEvent.payload.parameters)}
                          </code>
                        </dd>
                        <dt>Expected effect</dt>
                        <dd>{proposalEvent.payload.expected_effect}</dd>
                        <dt>Uncertainty</dt>
                        <dd>{proposalEvent.payload.uncertainty}</dd>
                        <dt>Evidence references</dt>
                        <dd>
                          {proposalEvent.payload.evidence_ids.length
                            ? proposalEvent.payload.evidence_ids.map(
                                (id: string) => (
                                  <button
                                    className="evidence-ref"
                                    key={id}
                                    onClick={() => {
                                      const found = events.find(
                                        (e) =>
                                          e.type === "tool_result" &&
                                          JSON.stringify(
                                            e.payload.result,
                                          ).includes('\"' + id + '\"'),
                                      );
                                      if (found) setEvidence(found.payload);
                                    }}
                                  >
                                    {id}
                                  </button>
                                ),
                              )
                            : "No evidence cited"}
                        </dd>
                      </dl>
                      {!approvalEvent && !finalEvent ? (
                        <div className="approval-actions">
                          <button
                            className="primary"
                            disabled={busy}
                            onClick={() => decide("approve")}
                          >
                            {live
                              ? "Approve simulation"
                              : run?.events.find((e) => e.type === "approval")
                                    ?.payload.decision === "approve"
                                ? "Play recorded approval"
                                : "View recorded approval"}
                          </button>
                          <button
                            className="secondary"
                            disabled={busy}
                            onClick={() => decide("reject")}
                          >
                            {live
                              ? "Reject proposal"
                              : run?.events.find((e) => e.type === "approval")
                                    ?.payload.decision === "reject"
                                ? "Play recorded rejection"
                                : "View recorded rejection"}
                          </button>
                        </div>
                      ) : (
                        <p className="muted">
                          {approvalEvent
                            ? "Decision recorded."
                            : "No action executed."}
                        </p>
                      )}
                      <p className="fine">
                        {live
                          ? "Approval is bound to this proposal and simulator revision."
                          : "Recorded decisions were made locally by the operator or evaluation harness, as identified in the export."}
                      </p>
                    </>
                  ) : (
                    <p className="empty">
                      The agent must gather evidence before proposing an action.
                      It can also abstain.
                    </p>
                  )}
                </section>
              </aside>
            </div>
            {run && (
              <section className="provenance">
                <p className="eyebrow">Run provenance</p>
                <p>
                  {run.metadata.model || "Local model"} ·{" "}
                  {run.metadata.mode || "agent"} · Scenario{" "}
                  {run.metadata.scenario_version || "Unknown"} · {run.case_id}
                </p>
                <code>
                  Model digest:{" "}
                  {run.metadata.digest || "Recorded in evaluation report"}
                </code>
                <p>
                  {run.metadata.hardware} ·{" "}
                  {run.metadata.hardware_model || run.metadata.machine}{" "}
                  {run.metadata.memory_bytes
                    ? "· " +
                      Math.round(run.metadata.memory_bytes / 2 ** 30) +
                      " GB memory"
                    : ""}
                </p>
                {!live && (
                  <a
                    href={
                      index?.recordings.find((r) => r.id === selected)?.file
                    }
                    download
                  >
                    Download complete run JSON ↓
                  </a>
                )}
                {live && (
                  <a href={API + `/api/runs/${run.id}/export`} download>
                    Export local run ↓
                  </a>
                )}
              </section>
            )}
          </>
        ) : (
          <section className="evaluation">
            <div className="section-title">
              <p className="eyebrow">Measure the full test set</p>
              <h2>
                Results, including <em>the misses.</em>
              </h2>
              <p>
                30 frozen synthetic cases: 12 development and 18 held-out.
                Held-out runs are repeated three times. The baseline receives a
                fixed evidence packet through the same read tools; it cannot
                choose an iterative investigation.
              </p>
            </div>
            {index?.reports.map((report) => (
              <Report
                key={report.file}
                report={report}
                onOpen={(id: string) => {
                  stream.current?.close();
                  setLive(false);
                  setSelected(id);
                  setTab("workspace");
                  setPlaying(false);
                }}
              />
            ))}
            <div className="panel">
              <h3>What these results establish</h3>
              <p>
                <a href="https://github.com/Jeremy-Cleland/incident-lab/blob/main/docs/EVALUATION.md">
                  Read the protocol and implementation corrections ↗
                </a>
                . Earlier measurements used permissive MCP argument handling and
                are retained separately. The final evaluation is not a pristine
                blind benchmark.
              </p>
              <p>
                Correctness is graded against synthetic scenario labels.
                Evidence support is a deterministic rubric, not a
                general-purpose factuality judge. Simulator recovery does not
                establish real-world operational effectiveness.
              </p>
              <p>
                The cases share templates and often contain explicit causal
                clues. Repeated runs are not independent evidence of production
                reliability.
              </p>
              <p>
                Targets: at least 80% correct held-out diagnosis/action
                outcomes, zero unapproved or duplicate executions, and no
                fabricated verified recovery. Missed targets remain visible and
                the project remains experimental.
              </p>
            </div>
          </section>
        )}
      </main>
      <footer>
        <span>Incident Lab / Jeremy Cleland</span>
        <a href="https://jeremycleland.com/portfolio">Back to portfolio ↗</a>
        <span>No production systems connected.</span>
      </footer>
    </>
  );
}
function Report({
  report,
  onOpen,
}: {
  report: any;
  onOpen: (id: string) => void;
}) {
  return (
    <article className="panel report">
      <div className="panel-heading">
        <h3>{report.title}</h3>
        <a href={report.file} download>
          Full results JSON ↓
        </a>
      </div>
      <div className="report-metrics">
        <div>
          <strong>
            {report.summary
              ? Math.round(report.summary.accuracy * 100) + "%"
              : "Pending"}
          </strong>
          <span>Diagnosis + action correct</span>
        </div>
        <div>
          <strong>{report.summary?.count || 0}</strong>
          <span>Runs evaluated</span>
        </div>
        <div>
          <strong>{report.safety_violations ?? "—"}</strong>
          <span>Execution-control violations</span>
        </div>
      </div>
      <details>
        <summary>Inspect every result</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Case</th>
                <th>Variant</th>
                <th>Repeat</th>
                <th>Correct</th>
                <th>Outcome</th>
                <th>Calls</th>
                <th>Seconds</th>
                <th>Recording</th>
              </tr>
            </thead>
            <tbody>
              {report.results?.map((r: any) => (
                <tr key={r.run_id}>
                  <td>{r.case_id}</td>
                  <td>{r.variant}</td>
                  <td>{r.repeat}</td>
                  <td>{r.correct ? "Yes" : "No"}</td>
                  <td>{r.outcome}</td>
                  <td>{r.tool_calls}</td>
                  <td>{r.seconds}</td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => onOpen(r.run_id)}
                      aria-label={
                        "Replay case " + r.case_id + " repetition " + r.repeat
                      }
                    >
                      Replay ↗
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </article>
  );
}
