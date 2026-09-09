# Release record — September 9, 2026

- Public replay: https://jeremy-incident-lab.netlify.app
- Public repository: https://github.com/Jeremy-Cleland/incident-lab
- Netlify site ID: `c726943c-a99c-49c6-8596-ad02113b7e66`
- Accepted replay deployment: `6aa1bd83b456013e847cb065`
- Immutable deployment: https://6aa1bd83b456013e847cb065--jeremy-incident-lab.netlify.app
- Application source at deployment: `f56eb42d2e45e528e445394fadab324c58513f60`
- Public inference: disabled; no backend or Ollama server is deployed.

The static release contains 126 genuine recordings and four complete reports: development, held-out agent, held-out baseline, and supplemental forced log exposure. The recording count includes three separate rejection investigations. A WebM walkthrough and desktop/mobile screenshots accompany the source.

Held-out diagnosis/action: agent **51/54 (94.4%)**, baseline **52/54 (96.3%)**. Both show zero unapproved/duplicate executions and zero false verified statuses. This is a synthetic, correlated benchmark with disclosed protocol corrections, not a production reliability claim or pristine blind evaluation.

Acceptance: 18 Python tests; TypeScript/Vite build; Ruff; Git diff checks; actual local Ollama workflow through browser refresh, approval, and verification; public replay approval/rejection/failure paths; all report downloads; zero axe findings or overflow at 390/768/1440 in both themes; zero new public console errors; no public localhost requests. Detailed checks are in [ACCEPTANCE.md](ACCEPTANCE.md).

The portfolio integration is in commit `9177228b845cb658ce56701d13ed54882057eb95` on `codex/portfolio-redesign`, PR https://github.com/Jeremy-Cleland/jeremycleland.com/pull/5. The existing portfolio production release is not merged; the user's earlier release plan requires preview review first.

To reproduce a static deployment, run `npm ci --prefix web`, `npm run build --prefix web`, then deploy `web/dist` to the separate Incident Lab site. Never deploy the Python API or expose the Ollama port publicly. Netlify's automatically enabled branding injection was disabled to preserve the application CSP.

## Portfolio preview acceptance

The Netlify deploy preview `6aa1bd2b48d9870008c57c3a` is ready for commit `9177228b845cb658ce56701d13ed54882057eb95`: https://deploy-preview-5--jeremycleland.netlify.app/portfolio/incident-lab.

The separate portfolio Performance Testing check remains failing on the homepage: LCP 3.5 seconds versus its 2.5-second threshold (run 34399423346). The preceding redesign commit also failed the same check at 3.8 seconds (run 34393156567). The Incident Lab application CI passes; this existing portfolio gate and requested preview review remain before merging that redesign. No performance threshold was relaxed.
