---
name: feature-enhancer
description: Weekly product and UX feature proposer that inspects docs/product_roadmap.md and open/closed GitHub Issues to propose up to 2 high-impact, single-PR feature enhancements across Pick'em/Groups, Live Box Score, Standings/Bracketology, and PWA/Mobile UX.
---

## Guidelines for Weekly Feature & Enhancement Proposals

### 1. Inspect Backlog, Reply to Issue Comments & Propose Balanced Roadmap Features
First check for any unanswered human comments on open GitHub Issues and respond (updating the issue spec/body/screenshots if requested):
```powershell
python scripts/agent_backlog.py comment-queue --json
python scripts/agent_backlog.py reply-issue <issue_number> --body "..." [--update-body-file <path>] [--status ready]
```
Then run the deterministic feature proposer script with `--worktree` (creating an isolated `agent/feature-proposer` worktree from the latest `origin/main`) to check open/closed `source:feature` and `source:roadmap` issues and publish up to 2 deduplicated feature proposals across underrepresented product pillars (automatically rendering and publishing Light & Dark mode preview screenshots to `agent-assets` for UI features):
```powershell
python scripts/propose_feature_tasks.py --worktree --publish --max-new-features 2 --max-open-features 4
```
When summarizing proposed features in chat, always display the published Light/Dark preview screenshots (`![Caption](https://raw.githubusercontent.com/...)`) inline whenever a proposal includes UI changes.

### 2. Four Core Product Pillars ([product_roadmap.md](file:///d:/Git/College-Basketball-Stats/docs/product_roadmap.md))
1. **Pick'em & Group Leaderboards (`domain:groups-firestore`, `domain:site-ui`)**:
   - Hot streak, season-high VAL, and consistency (StdDev) badges on Group Leaderboards.
   - Head-to-head member comparison drawers and contrarian/chalk pick distribution bars.
   - Group leaderboard filter modes (`All Games`, `Conference Play Only`, `Last 5 Games`, `Quad 1–2`).
2. **Live Game & Box Score UX (`domain:analytics`, `domain:site-ui`)**:
   - Advanced shooting efficiency metrics (`eFG%`, `TS%`, `AST/TO`, `VAL/MIN`) in the Player VAL Breakdown modal.
   - Live box score Pick'em MVP leader badges and pace-adjusted VAL projections.
   - Side-by-side teammate comparison modals and team box score summary strips.
3. **Team Resume, Standings & Bracketology (`domain:espn-api`, `domain:analytics`, `domain:site-ui`)**:
   - Interactive Quadrant 1–4 game list drilldowns in Standings and Schedule.
   - NCAA Tournament Resume summary banners (BPI/PWR, SOR, SOS, Non-Conf SOS, Q1–Q4 records).
   - Conference Standings sort controls (Seed, Overall, BPI, SOR) and conference switcher.
4. **PWA, Mobile & Performance Enhancements (`domain:pwa`, `domain:site-ui`)**:
   - Offline last-known `localStorage` snapshot caching for Schedule and Standings.
   - Browser `Notification` opt-in reminders for unsubmitted pre-game picks.
   - Keyboard `Escape`-key modal dismissal and ARIA dialog accessibility polish.

### 3. Custom Feature Ideation Rules
If all catalog items in `scripts/propose_feature_tasks.py` have already been proposed/completed (and fewer than 4 open `source:feature` / `source:roadmap` issues exist), read [product_roadmap.md](file:///d:/Git/College-Basketball-Stats/docs/product_roadmap.md) and propose 1–2 bounded, single-PR feature enhancements via:
```powershell
python scripts/agent_backlog.py create --title "..." --context "..." --objective "..." --examples "..." --screenshot "Light Mode Preview=https://..." --owned-paths ... --forbidden-paths firestore.rules .github/workflows/ --acceptance ... --verify "python -m pytest -v" --priority p2 --source feature --domain ...
```
- **Rich Issue Detail & Examples**: Always provide `--context` (user impact & motivation) and `--examples` (concrete helper input/output JSON, edge-case values, and UI badge/layout behavior). For UI-facing proposals, render a mockup screenshot in `scratch/screenshots/` using [capture_screenshots.py](file:///d:/Git/College-Basketball-Stats/scripts/capture_screenshots.py) and publish it to `agent-assets` so reviewers can preview the feature visually before approving.
- **Contract Registration**: Whenever a feature adds a new pure helper function in `site_ui/helpers.js`, include `docs/contracts/schemas_and_routes.json` and `tests/test_helpers_and_contracts.py` in `owned_paths` and require unit test coverage in `acceptance_criteria`.
- **Zero Firestore Breaking Changes**: Never propose features that break existing Firestore document schemas (`user_settings`, `groups`, `<teamId><m|w>` pick documents) or require manual Firebase Console intervention.
