"""Publish only actual persisted local-model recordings; never synthesize event continuations."""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web/public/data"
OUT.mkdir(parents=True, exist_ok=True)
index = {
    "status": "Experimental synthetic benchmark. Evaluation in progress; no real-world recovery claim.",
    "recordings": [],
    "reports": [],
}
seen = set()
for name, title in [
    ("development-agent", "Development · agent"),
    ("held_out-agent", "Held-out · agent"),
    ("held_out-baseline", "Held-out · fixed-packet baseline"),
]:
    path = ROOT / "artifacts" / f"{name}.json"
    if not path.exists():
        continue
    report = json.loads(path.read_text())
    if not report.get("complete"):
        continue
    shutil.copyfile(path, OUT / path.name)
    report.update(
        title=title,
        file="/data/" + path.name,
        safety_violations=sum(
            r["unapproved_execution"] or r["duplicate_execution"] for r in report["results"]
        ),
    )
    index["reports"].append(report)
    for result in report["results"]:
        rid = result["run_id"]
        if rid in seen:
            continue
        seen.add(rid)
        source = ROOT / "artifacts/runs" / f"{rid}.json"
        shutil.copyfile(source, OUT / source.name)
        family = result["family"].replace("_", " ")
        index["recordings"].append(
            {
                "id": rid,
                "title": f"{family.capitalize()} · {result['variant'].replace('_', ' ')} · {'baseline' if 'baseline' in name else 'agent'} {result['repeat']}",
                "family": result["family"],
                "variant": result["variant"],
                "file": "/data/" + source.name,
                "state": result["state"],
                "correct": result["correct"],
                "branch": "approved",
            }
        )
for source in (
    sorted((ROOT / "artifacts/rejections").glob("*.json")) if (ROOT / "artifacts/rejections").exists() else []
):
    data = json.loads(source.read_text())
    run = data["run"]
    shutil.copyfile(source, OUT / source.name)
    index["recordings"].append(
        {
            "id": run["id"],
            "title": data["title"],
            "family": data["family"],
            "variant": "standard",
            "file": "/data/" + source.name,
            "state": "rejected",
            "correct": False,
            "branch": "rejected",
        }
    )
held = next((r for r in index["reports"] if r["title"] == "Held-out · agent"), None)
if held:
    index["status"] = (
        f"Experimental synthetic benchmark: {held['summary']['correct']}/{held['summary']['count']} held-out agent runs selected the expected diagnosis and action. Inspect all results and limitations in Evaluation."
    )
(OUT / "index.json").write_text(json.dumps(index, indent=2) + "\n")
print(
    f"Exported {len(index['recordings'])} genuine local recordings and {len(index['reports'])} completed reports."
)
