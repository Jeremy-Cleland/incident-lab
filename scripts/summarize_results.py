"""Summarize completed reports without filtering failures or modifying recordings."""

import json
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
reports = {
    name: json.loads((ROOT / "artifacts" / f"{name}.json").read_text())
    for name in ["development-agent", "held_out-agent", "held_out-baseline"]
}
assert all(r["complete"] for r in reports.values()), "Wait for complete reports"
assert len(reports["held_out-agent"]["results"]) == 54
assert len(reports["held_out-baseline"]["results"]) == 54
rows = []
summary = {}
for name, report in reports.items():
    results = report["results"]
    n = len(results)
    summary[name] = {
        "count": n,
        "correct": sum(r["correct"] for r in results),
        "evidence_exists": sum(r["citations_exist"] for r in results),
        "supported_task_claim": sum(r["evidence_support"] for r in results),
        "unsupported_task_claim_proxy": sum(r["unsupported_claim"] for r in results),
        "appropriate_abstentions": sum(r["appropriate_abstention"] for r in results),
        "unapproved_executions": sum(r["unapproved_execution"] for r in results),
        "duplicate_executions": sum(r["duplicate_execution"] for r in results),
        "false_verified_recovery": sum(r["false_verified_recovery"] for r in results),
        "mean_tool_calls": round(statistics.mean(r["tool_calls"] for r in results), 2),
        "tool_errors": sum(r["tool_errors"] for r in results),
        "median_active_seconds": round(statistics.median(r["seconds"] for r in results), 2),
        "mean_active_seconds": round(statistics.mean(r["seconds"] for r in results), 2),
        "input_tokens": sum(r["tokens_in"] for r in results),
        "output_tokens": sum(r["tokens_out"] for r in results),
        "observed_outcomes": dict(Counter(r["outcome"] for r in results)),
    }
    s = summary[name]
    rows.append(
        f"| {name} | {s['correct']}/{n} ({100 * s['correct'] / n:.1f}%) | {s['mean_tool_calls']} | {s['median_active_seconds']} s | {s['tool_errors']} | {s['input_tokens']:,} / {s['output_tokens']:,} |"
    )
meta = reports["held_out-agent"]["metadata"]
a = summary["held_out-agent"]
b = summary["held_out-baseline"]
text = (
    """# Measured results\n\nThese are completed local Qwen3 runs on synthetic fixtures. Every result, including failures, is available in the JSON reports and public replay. Earlier protocol measurements are retained under `artifacts/superseded/` and are excluded from this table. See [protocol and limitations](EVALUATION.md), including the disclosed exploratory held-out history.\n\n| Method | Diagnosis + action correct | Mean tool attempts | Median active time | Read errors | Input / output tokens |\n| --- | --- | --- | --- | --- | --- |\n"""
    + "\n".join(rows)
    + "\n\n"
)
text += f"The agent achieved {a['correct']}/54 correct held-out diagnosis/action outcomes; the fixed-packet baseline achieved {b['correct']}/54. "
text += (
    "These results do not show an accuracy advantage for iterative tool use on this small corpus. "
    if a["correct"] <= b["correct"]
    else "The observed difference is limited to this small, correlated synthetic test set. "
)
text += "The scenario templates often contain explicit causal clues; no production effectiveness claim follows.\n\n"
text += "## Execution controls and recovery\n\n"
for name in ["held_out-agent", "held_out-baseline"]:
    s = summary[name]
    text += f"- **{name}:** {s['unapproved_executions']} unapproved executions, {s['duplicate_executions']} duplicate executions, {s['false_verified_recovery']} false verified statuses. Outcomes: `{json.dumps(s['observed_outcomes'], sort_keys=True)}`. Appropriate abstentions: {s['appropriate_abstentions']}.\n"
text += "\nVerification status is derived from fresh simulator observations. The task-level unsupported-claim proxy is not a general hallucination rate; it flags incorrect diagnosis/action or missing evidence support. Free-text recovery summaries are not comprehensively graded by this rubric.\n\n## Failures\n\n"
for name, report in reports.items():
    for row in report["results"]:
        if not row["correct"]:
            text += f"- {name}, `{row['case_id']}`, {row['variant']}, repetition {row['repeat']}: {row['outcome']}; [full recording](../artifacts/runs/{row['run_id']}.json).\n"
text += (
    "\n## Provenance\n\n```json\n"
    + json.dumps(meta, indent=2)
    + "\n```\n\nThe baseline shares these model and scenario settings. Its mode field differs. Active time includes model and MCP work but excludes approval wait. Local OS load and model caching can affect latency; these measurements are descriptive, not a controlled systems benchmark.\n"
)
(ROOT / "docs/RESULTS.md").write_text(text)
(ROOT / "artifacts/summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
