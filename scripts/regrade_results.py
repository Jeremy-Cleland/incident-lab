"""Correct deterministic evidence attribution without changing inference or case labels."""

import json
import shutil
from pathlib import Path

from incident_lab.evaluate import grade

ROOT = Path(__file__).resolve().parents[1]
for name in ["development-agent", "held_out-agent", "held_out-baseline"]:
    path = ROOT / "artifacts" / f"{name}.json"
    report = json.loads(path.read_text())
    assert report["complete"], "Cannot regrade incomplete report"
    old = ROOT / "artifacts/superseded" / f"{name}-grader-1.0.json"
    if not old.exists():
        shutil.copyfile(path, old)
    for i, previous in enumerate(report["results"]):
        run_path = ROOT / "artifacts/runs" / f"{previous['run_id']}.json"
        recording = json.loads(run_path.read_text())
        current = grade(recording["run"]) | {"repeat": previous["repeat"], "mode": previous["mode"]}
        assert current["correct"] == previous["correct"] and current["outcome"] == previous["outcome"]
        recording["grade"] = current
        recording["grader_version"] = "1.1"
        run_path.write_text(json.dumps(recording, indent=2) + "\n")
        report["results"][i] = current
    report["grader_version"] = "1.1"
    path.write_text(json.dumps(report, indent=2) + "\n")
print("Regraded evidence support; no diagnosis/action or outcome changes.")
