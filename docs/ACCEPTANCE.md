# Acceptance evidence

Implementation checks on September 9, 2026:

- Python 3.12 / `uv run pytest -q`: 17 passing tests. Includes actual MCP stdio, scoped arguments, unknown tools, concurrent and duplicate approvals, stale and cross-run approval, rejection, cancellation, execution timeout, retry limits, restart, SSE cursor replay, unavailable provider, incorrect recovery action, degraded outcome, missing verification evidence, and an end-to-end test provider flow.
- Ruff import/undefined-name checks and formatter; Vite TypeScript production build.
- Browser inspection of workspace at 390, 768, and 1440 pixels, dark and light. No horizontal overflow; axe WCAG A/AA checks returned zero violations for these views. Evidence and proposal controls were present during the checks.
- Keyboard Tab reaches the skip link, Enter moves focus to main; saved theme survives reload; reduced-motion preference recognized.
- The header initially overflowed under a 200% CSS scaling stress test. Wrapping was corrected; a repeat check returned no overflow. This is a scaling stress test, not a substitute for every browser's native zoom implementation.
- Replay paused at recorded approval and continued to the actual recorded healthy result. Evaluation tables exposed all development rows.
- Netlify candidate deployment: no live-agent control, no localhost network requests, no page errors, zero axe violations on Evaluation. The public Content Security Policy permits connections only to the same origin.
- Portfolio addition: Next.js production build via `npx next build` and lint passed. It is prepared in the existing redesign branch; production merge remains a separate review step.

Screenshots and browser automation output are under the local `output/playwright/` directory. Selected release screenshots and a recorded replay walkthrough are published separately with the final artifacts. Tests using a scripted provider are explicitly test-only; public inference recordings use the actual local model.

Warnings: the installed FastAPI/Starlette test adapter emits two deprecation warnings about its test transport. They do not fail the tests. No framework migration was made solely to remove them.

Final model evaluation and production replay verification are recorded in `RESULTS.md` and `RELEASE.md` after those runs finish. A high synthetic score does not establish production reliability.
