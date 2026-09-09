"""Record new local-model investigations followed by an explicit harness rejection."""

import asyncio
import json
import platform
import subprocess

from incident_lab import store
from incident_lab.agent import investigate
from incident_lab.provider import OllamaProvider
from incident_lab.simulator import approve


async def main():
    db = str(store.ROOT / "data/rejections.sqlite")
    store.init(db)
    provider = OllamaProvider()
    metadata = await provider.metadata()
    manifest = json.loads((store.ROOT / "cases/manifest.json").read_text())
    metadata.update(
        mode="agent",
        hardware=platform.platform(),
        hardware_model=subprocess.check_output(["sysctl", "-n", "hw.model"], text=True).strip()
        if platform.system() == "Darwin"
        else platform.machine(),
        memory_bytes=int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True))
        if platform.system() == "Darwin"
        else None,
        scenario_version=manifest["version"],
        scenario_sha256=manifest["sha256"],
    )
    output = store.ROOT / "artifacts/rejections"
    output.mkdir(parents=True, exist_ok=True)
    for fixture in (c for c in store.cases() if c["variant"] == "standard"):
        rid = store.create(fixture["id"], metadata, db)
        await investigate(rid, db, provider)
        run = store.get(rid, db)
        if run["state"] != "awaiting_approval":
            raise RuntimeError("No proposal to reject: " + rid)
        approve(
            rid, {"proposal_id": run["proposal_id"], "revision": run["revision"], "decision": "reject"}, db
        )
        family = fixture["ground_truth"]["diagnosis"]
        recording = {
            "format_version": "1.0",
            "mode": "recorded-local-agent",
            "approval_actor": "rejection recording harness",
            "title": family.replace("_", " ").capitalize() + " · separate rejected investigation",
            "family": family,
            "run": store.get(rid, db),
        }
        (output / f"{rid}.json").write_text(json.dumps(recording, indent=2) + "\n")
        print(rid, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
