# Three-minute interview demonstration

[Recorded visual walkthrough](https://jeremy-incident-lab.netlify.app/media/incident-lab-walkthrough.webm) — shows replay playback, not live inference.

1. **0:00–0:30 — Establish scope.** “This is a recorded run of a local Qwen3 agent against a synthetic order-processing service. The tools and model calls actually ran; playback does not invoke a model.” Select a bad-deployment recording.
2. **0:30–1:15 — Follow the evidence.** Play the timeline, open a log or change-history result, and identify the stable evidence IDs. Explain that the model requests tools through a real MCP stdio session. Ground-truth labels stay outside its context.
3. **1:15–1:45 — Show the boundary.** At the proposal, explain target, fixed parameters, uncertainty, and evidence. The read-only MCP server cannot execute. Approval is tied to the exact proposal and revision; an application transaction applies the simulator action once. Select the recorded approval.
4. **1:45–2:15 — Verify.** Open the fresh health observation. The application derives status from this observation. Switch to an upstream recording to show degraded recovery while the provider remains down. A passing local API metric does not mean the dependency recovered.
5. **2:15–3:00 — Discuss evidence and limits.** Open Evaluation, show every case and the fixed-packet baseline, including misses. Explain synthetic template limitations, tool/retry budgets, and what you would measure with real integrations. Show a separately recorded rejection to demonstrate that no action runs.

For a live local demonstration, start the API and Ollama before the interview. Identify the screen as local live inference and let the interviewer approve or reject. If Ollama is unavailable, show the explicit failure and switch to the clearly labeled replay; never present replay as live inference.
