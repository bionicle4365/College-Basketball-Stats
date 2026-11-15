# College Basketball Stats — Product & Feature Roadmap

This document is the source of truth for the **Weekly New Feature / Feature Enhancement Automation** (`source:feature` / `source:roadmap`). Every proposed feature must be scoped as an atomic, single-PR enhancement with explicit `owned_paths`, `forbidden_paths`, `acceptance_criteria`, and deterministic `verification_commands`.

---

## Pillar 1: Pick'em & Group Leaderboards (`domain:groups-firestore`, `domain:site-ui`)

1. **Hot Streak & Consistency Badges on Group Leaderboard**
   - **Summary**: Compute and display each group member's active win streak (or 20+ VAL streak), season high single-game VAL pick, and consistency (StdDev / median VAL) in `site_ui/group/index.html` and `site_ui/helpers.js`.
   - **Owned Paths**: `site_ui/helpers.js`, `site_ui/group/index.html`, `site_ui/styles.css`, `tests/test_helpers_and_contracts.py`

2. **Head-to-Head Member Comparison Drawer in Groups**
   - **Summary**: Allow users in a group to select any two members in `site_ui/group/index.html` and view a head-to-head comparison card showing shared games, head-to-head record when picking different players, total VAL differential, and most-picked players.
   - **Owned Paths**: `site_ui/helpers.js`, `site_ui/group/index.html`, `site_ui/styles.css`, `tests/test_helpers_and_contracts.py`

3. **Pick Contrarian & Ownership Analytics ("Pick Distribution Bar")**
   - **Summary**: On live and completed games in `site_ui/group/index.html` and `site_ui/scoreboard/index.html`, show the percentage of group members who picked each player ("Chalk Pick" vs. "Lone Wolf Pick" badge when only 1 member selected a player).
   - **Owned Paths**: `site_ui/helpers.js`, `site_ui/group/index.html`, `site_ui/scoreboard/index.html`, `site_ui/styles.css`, `tests/test_helpers_and_contracts.py`

4. **Season Pick'em Recap & Monthly/Conference Splits Filter**
   - **Summary**: Add a filter toggle on the Group Leaderboard (`All Games`, `Conference Play Only`, `Last 5 Games`, `Quad 1–2 Games`) so groups can track mini-seasons and high-stakes matchup standings without changing Firestore schemas.
   - **Owned Paths**: `site_ui/helpers.js`, `site_ui/group/index.html`, `site_ui/styles.css`, `tests/test_helpers_and_contracts.py`

---

## Pillar 2: Live Game & Box Score UX (`domain:analytics`, `domain:site-ui`)

1. **Advanced Shooting & Efficiency Splits (`eFG%`, `TS%`, `AST/TO`, `VAL/MIN`)**
   - **Summary**: Add a pure helper `calculateAdvancedEfficiency(stats, labels)` in `site_ui/helpers.js` computing Effective FG% (`(FGM + 0.5 * 3PM) / FGA`), True Shooting % (`PTS / (2 * (FGA + 0.44 * FTA))`), and VAL-per-minute efficiency (`VAL / MIN`), and surface these pills in the Player VAL Breakdown Modal (`renderValBreakdownHtml`).
   - **Owned Paths**: `site_ui/helpers.js`, `site_ui/styles.css`, `docs/contracts/schemas_and_routes.json`, `tests/test_helpers_and_contracts.py`

2. **Live Box Score "Pick'em MVP Leader" & Pace-Adjusted VAL Projection**
   - **Summary**: During live (`state === 'in'`) and completed games on `site_ui/scoreboard/index.html`, highlight the current #1 VAL leader on each team with a crown/MVP pill and calculate pace-adjusted full-game projected VAL based on current minutes/game clock.
   - **Owned Paths**: `site_ui/helpers.js`, `site_ui/scoreboard/index.html`, `site_ui/styles.css`, `tests/test_helpers_and_contracts.py`

3. **Side-by-Side Player Pick'em Comparison Modal on Roster & Pre-Game Scoreboard**
   - **Summary**: Allow users researching their pre-game pick on `site_ui/roster/index.html` or `site_ui/scoreboard/index.html` to compare two teammates side-by-side (Season Avg VAL, L3 Avg VAL, Floor/Ceiling VAL, Usage/Minutes stability).
   - **Owned Paths**: `site_ui/helpers.js`, `site_ui/roster/index.html`, `site_ui/styles.css`, `tests/test_helpers_and_contracts.py`

4. **Team Box Score Summary Comparison Strip (Rebounding, Paint/3PT Scoring & Turnover Margin)**
   - **Summary**: Add a compact visual comparison bar above the player box scores in `site_ui/scoreboard/index.html` comparing both teams' Team VAL, FG%/3PT%/FT%, Rebound margin, Assist-to-Turnover ratio, and Steals+Blocks ("Stocks").
   - **Owned Paths**: `site_ui/helpers.js`, `site_ui/scoreboard/index.html`, `site_ui/styles.css`, `tests/test_helpers_and_contracts.py`

---

## Pillar 3: Team Resume, Standings & Bracketology (`domain:espn-api`, `domain:analytics`, `domain:site-ui`)

1. **Interactive Quadrant 1–4 Game List Drilldown in Standings & Schedule**
   - **Summary**: Enhance `calculateScheduleQuadSummary` in `site_ui/helpers.js` to retain the list of games in each Quadrant (`Q1`–`Q4`) so tapping a Quadrant card in `site_ui/standings/index.html` or `site_ui/schedule/index.html` reveals the exact wins, losses, and remaining games in that quadrant.
   - **Owned Paths**: `site_ui/helpers.js`, `site_ui/standings/index.html`, `site_ui/schedule/index.html`, `site_ui/styles.css`, `tests/test_helpers_and_contracts.py`

2. **NCAA Tournament Resume Summary Banner on Schedule Page**
   - **Summary**: Add a collapsible "Team Tournament Resume" header strip at the top of `site_ui/schedule/index.html` displaying current BPI/PWR Rank, SOR, SOS, Non-Conf SOS, Q1–Q4 records, and Best Win / Toughest Remaining Game.
   - **Owned Paths**: `site_ui/helpers.js`, `site_ui/schedule/index.html`, `site_ui/styles.css`, `tests/test_helpers_and_contracts.py`

3. **Conference Standings Sort & Filter Controls (Overall, Conf, BPI, SOR, Streak)**
   - **Summary**: Allow users on `site_ui/standings/index.html` to sort conference standings by Conference Seed, Overall Win %, BPI Rank, Strength of Record (SOR), or Point Differential, plus a conference selector dropdown to browse any Division I conference.
   - **Owned Paths**: `site_ui/standings/index.html`, `site_ui/helpers.js`, `site_ui/styles.css`, `tests/test_helpers_and_contracts.py`

---

## Pillar 4: PWA, Mobile & Performance Enhancements (`domain:pwa`, `domain:site-ui`)

1. **Offline Last-Known Snapshot Caching for Schedule & Standings**
   - **Summary**: Cache the most recent successful JSON responses for `fetchTeamSchedule` and `standings` in `localStorage`/`sessionStorage` with a timestamp banner ("Viewing cached data from ...") when offline or when ESPN API requests fail.
   - **Owned Paths**: `site_ui/helpers.js`, `site_ui/schedule/index.html`, `site_ui/standings/index.html`, `site_ui/styles.css`, `tests/test_helpers_and_contracts.py`

2. **Optional Browser Notification Opt-In for Unsubmitted Pre-Game Picks**
   - **Summary**: Add an opt-in toggle in `site_ui/settings/index.html` and helper check in `site_ui/_layouts/default.html` using the Web `Notification` API to alert logged-in users when their favorite team tips off within 2 hours and they haven't submitted a pick yet.
   - **Owned Paths**: `site_ui/helpers.js`, `site_ui/settings/index.html`, `site_ui/_layouts/default.html`, `tests/test_helpers_and_contracts.py`

3. **Keyboard Navigation & ARIA Accessibility Polish for Modals & Drawers**
   - **Summary**: Add `Escape`-key modal dismissal, `aria-expanded` / `role="dialog"` / `aria-modal="true"` attributes, and keyboard `Enter`/`Space` row expansion for `scoreboard`, `roster`, `standings`, and `group` modals/drawers.
   - **Owned Paths**: `site_ui/scoreboard/index.html`, `site_ui/roster/index.html`, `site_ui/standings/index.html`, `site_ui/group/index.html`, `tests/test_helpers_and_contracts.py`
