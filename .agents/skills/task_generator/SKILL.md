---
name: task-generator
description: Discovers actionable engineering tasks from contract drift, Firestore rules alignment, CSP/placeholder checks, unit test failures, live ESPN API telemetry, and GitHub Actions CI runs, publishing deduplicated GitHub Issues via agent_backlog.py.
---

## Guidelines for Autonomous Task Discovery (Every 8h)

### 1. Live Telemetry, CI & Codebase Audits
Run the deterministic audit script to inspect contract synchronization, Firestore rules alignment, Firebase placeholder safety, CSP headers, unit test suites, live ESPN API endpoints, and GitHub Actions CI on `main`:
```powershell
python scripts/audit_and_generate_tasks.py --run-tests --espn --ci --publish --max-new-issues 3 --max-open-proposed 5
```
What the deterministic audit covers:
- **Contract & Firestore Rules Drift (`source:data-drift`)**: Diffs [schemas_and_routes.json](file:///d:/Git/College-Basketball-Stats/docs/contracts/schemas_and_routes.json) against [firestore.rules](file:///d:/Git/College-Basketball-Stats/firestore.rules), top-level functions in [helpers.js](file:///d:/Git/College-Basketball-Stats/site_ui/helpers.js), precached assets in [sw.js](file:///d:/Git/College-Basketball-Stats/site_ui/sw.js), and declared page templates in `site_ui/`.
- **Frontend Security & Test Coverage (`source:data-drift`, `source:test-gap`)**: Verifies `FIREBASE_*_PLACEHOLDER` tokens in [common.js](file:///d:/Git/College-Basketball-Stats/site_ui/common.js), `Content-Security-Policy` headers in [default.html](file:///d:/Git/College-Basketball-Stats/site_ui/_layouts/default.html), and flags any pure helper functions in `site_ui/helpers.js` missing unit test coverage in `tests/test_helpers_and_contracts.py`.
- **Unit Test Suites & GitHub Actions CI (`source:test-gap`)**: Runs `python -m pytest -q` and checks `/actions/runs?branch=main` for recent workflow failures.
- **Live ESPN API Telemetry (`source:telemetry`)**: Probes ESPN Men's & Women's College Basketball scoreboard, standings, team schedule, and team roster endpoints for HTTP failures or schema drift.

### 2. Clean Separation from Feature Ideation
- Do **NOT** propose `source:feature` or `source:roadmap` enhancements during Task Discovery runs. New feature ideation and UX enhancements are owned exclusively by the **Weekly Feature Enhancer** automation ([feature-enhancer](file:///d:/Git/College-Basketball-Stats/.agents/skills/feature_enhancer/SKILL.md) / `scripts/propose_feature_tasks.py`).

### 3. Noise & Safety Guardrails
- **Human Approval Gate**: All newly published issues start as `agent:proposed` and require human approval (`agent:ready`) before execution.
- **Daily Cap & Zero Speculative Noise**: Publish at most **3 net-new audit issues per 24h** (`--max-new-issues 3`, capped at 5 open proposed audit issues). Never propose speculative refactors without a concrete bug, telemetry failure, contract drift, or test failure.
- **Rich Diagnostics & Examples**: Include concrete observed drift items, failing assertion excerpts, or expected-vs-actual contract examples in `context` and `examples` so reviewers can validate issues immediately.
- **Single-PR Scope**: Every generated task must be completable in one cohesive PR with explicit `owned_paths`, `firestore.rules` in `forbidden_paths` unless rules changes are explicitly required, and runnable CLI `verification_commands` (`python -m pytest -v`).
