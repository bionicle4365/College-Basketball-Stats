---
name: autonomous-verifier
description: Verifies autonomous agent work against GitHub Issue task specifications, file ownership boundaries, contract schemas, and deterministic unit tests.
---

## Guidelines for Autonomous Verification

### Verification Checklist
1. **Load Issue Spec**: Run `python scripts/agent_backlog.py get <issue_number>` to retrieve `owned_paths`, `forbidden_paths`, `acceptance_criteria`, and `verification_commands`.
2. **Run Deterministic Gate**: Execute `python scripts/verify_task.py --cwd <worktree_path> --issue <issue_number>` to verify:
   - Active git branch is an isolated `agent/...` branch (never `main` or `master`).
   - Modified/untracked files stay strictly within `owned_paths` and never touch `forbidden_paths`.
   - `python -m pytest` (including Node-backed `site_ui/helpers.js` tests and contract checks) and all issue `verification_commands` exit `0`.
3. **Inspect Diff, Examples & Screenshots**:
   - Review `git -C <worktree_path> diff origin/main...HEAD` against every item in `acceptance_criteria`.
   - Confirm that any new top-level function in `site_ui/helpers.js` is listed in [schemas_and_routes.json](file:///d:/Git/College-Basketball-Stats/docs/contracts/schemas_and_routes.json) and tested in `tests/test_helpers_and_contracts.py`.
   - Confirm `site_ui/common.js` still contains `FIREBASE_*_PLACEHOLDER` tokens.
   - For UI-visible changes (`site_ui/`), capture Before (`origin/main`) and After (`HEAD`) Light & Dark mode screenshots via [capture_screenshots.py](file:///d:/Git/College-Basketball-Stats/scripts/capture_screenshots.py) into `scratch/screenshots/`, visually inspect them, and publish them to the isolated `agent-assets` branch (`python scripts/capture_screenshots.py publish ...`).
4. **Report Verdict**:
   - **Pass**: Transition the issue and open a detailed Pull Request using `python scripts/agent_backlog.py complete <issue_number> --cwd <worktree_path> --pr agent/issue-<issue_number> --push --open-pr --summary "<concise summary>" --examples "<concrete input/output & UI walkthrough>" --verification "<observed pytest & syntax check results>" --screenshot "After (Light Mode)=https://..." --screenshot "After (Dark Mode)=https://..."` (never push or merge to `main` and never merge the PR).
   - **Fail**: Fix the violation (up to 2 attempts) or mark the issue blocked via `python scripts/agent_backlog.py block <issue_number> --reason "<exact failure>"`.
