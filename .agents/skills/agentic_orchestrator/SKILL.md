---
name: agentic-orchestrator
description: Coordinates agentic flows across specialized domain skills (Site UI, ESPN & Analytics, Firestore & Groups, PWA) to deliver verified single-PR modifications in isolated git worktrees.
---

## Guidelines for Task Orchestration

### GitHub Issues Backlog Integration
Autonomous tasks are discovered via [task-generator](file:///d:/Git/College-Basketball-Stats/.agents/skills/task_generator/SKILL.md) ([audit_and_generate_tasks.py](file:///d:/Git/College-Basketball-Stats/scripts/audit_and_generate_tasks.py)), proposed weekly via [feature-enhancer](file:///d:/Git/College-Basketball-Stats/.agents/skills/feature_enhancer/SKILL.md) ([propose_feature_tasks.py](file:///d:/Git/College-Basketball-Stats/scripts/propose_feature_tasks.py)), queued as GitHub Issues via [agent_backlog.py](file:///d:/Git/College-Basketball-Stats/scripts/agent_backlog.py), and gated by [verify_task.py](file:///d:/Git/College-Basketball-Stats/scripts/verify_task.py):
- **Initialize repo labels**: `python scripts/agent_backlog.py init`
- **Audit codebase & telemetry (in isolated `origin/main` worktree)**: `python scripts/audit_and_generate_tasks.py --worktree --run-tests --espn --ci --publish`
- **Propose weekly features (in isolated `origin/main` worktree)**: `python scripts/propose_feature_tasks.py --worktree --publish`
- **List proposed issues**: `python scripts/agent_backlog.py list --status proposed`
- **Approve issue**: `python scripts/agent_backlog.py approve <issue_number>` (transitions `agent:proposed` -> `agent:ready`)
- **Claim next approved task & isolated worktree**: `python scripts/agent_backlog.py next --claim --worktree --reclaim-stale-hours 6 --agent scheduled-executor --json`
- **Verify task**: `python scripts/verify_task.py --cwd <worktree_path> --issue <issue_number>`
- **Capture & publish UI screenshots (for visual changes)**: `python scripts/capture_screenshots.py ...` and `python scripts/capture_screenshots.py publish ...` (publishes to isolated `agent-assets` branch)
- **Complete task & open rich PR**: `python scripts/agent_backlog.py complete <issue_number> --cwd <worktree_path> --pr agent/issue-<issue_number> --push --open-pr --summary "..." --examples "..." --verification "..." --screenshot "Caption=URL"`
- **Block stuck task**: `python scripts/agent_backlog.py block <issue_number> --reason "..."`

### Domain Identification
When an issue is claimed, load the matching domain skill(s):
- **UI templates, modals, dark mode, CSS (`domain:site-ui`, `domain:pwa`)**: [site-ui-expert](file:///d:/Git/College-Basketball-Stats/.agents/skills/site_ui_expert/SKILL.md)
- **ESPN API endpoints, VAL math, BPI/PWR rankings, Quadrant 1–4 & SOS (`domain:espn-api`, `domain:analytics`)**: [espn-analytics-expert](file:///d:/Git/College-Basketball-Stats/.agents/skills/espn_analytics_expert/SKILL.md)
- **Firebase Auth, Firestore rules, Pick'em collections, Groups & PBKDF2 privacy (`domain:groups-firestore`)**: [firestore-groups-expert](file:///d:/Git/College-Basketball-Stats/.agents/skills/firestore_groups_expert/SKILL.md)

### Execution Rules
1. Inspect [schemas_and_routes.json](file:///d:/Git/College-Basketball-Stats/docs/contracts/schemas_and_routes.json) before modifying `site_ui/helpers.js`, `site_ui/sw.js`, or `firestore.rules`.
2. Any new top-level function in `site_ui/helpers.js` **must** be added to `helper_functions` in `docs/contracts/schemas_and_routes.json` and tested in `tests/test_helpers_and_contracts.py`.
3. Modify only files within the issue's `owned_paths`, and never touch `forbidden_paths`.
4. Always run `python scripts/verify_task.py --cwd <worktree_path> --issue <issue_number>` before opening a PR.
