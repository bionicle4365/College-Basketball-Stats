#!/usr/bin/env python3
"""Weekly New Feature & Feature Enhancement proposer for College-Basketball-Stats.

Inspects `docs/product_roadmap.md` and existing GitHub Issues (both open and closed)
to propose bounded, single-PR feature enhancements across the 4 product pillars:
1. Pick'em & Group Leaderboards (`domain:groups-firestore`, `domain:site-ui`)
2. Live Game & Box Score UX (`domain:analytics`, `domain:site-ui`)
3. Team Resume, Standings & Bracketology (`domain:espn-api`, `domain:analytics`, `domain:site-ui`)
4. PWA, Mobile & Performance Enhancements (`domain:pwa`, `domain:site-ui`)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Set

try:
    from scripts import agent_backlog, capture_screenshots
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import agent_backlog  # type: ignore[no-redef]
    import capture_screenshots  # type: ignore[no-redef]


FEATURE_CATALOG: List[Dict[str, Any]] = [
    {
        "pillar": "pickem-groups",
        "title": "Add hot streak, season high VAL, and consistency stats to Group Leaderboard",
        "context": (
            "Currently the Group Leaderboard (`site_ui/group/index.html`) shows Total VAL, Picks Made, "
            "Top Pick %, Avg VAL, and the last 4 games' trend pills, making it hard to tell whether a "
            "member's average comes from steady 20+ VAL picks or a single boom/bust game. Adding streak, "
            "season-high, and standard-deviation consistency badges rewards both hot hands and steady pickers "
            "without altering any Firestore document schema."
        ),
        "objective": (
            "Enhance the Group Leaderboard in `site_ui/group/index.html` and `site_ui/helpers.js` with "
            "a pure helper `calculateMemberStreakAndConsistency(gameVals)` that computes each member's "
            "active 20+ VAL streak, single-game season high VAL, and VAL consistency (standard deviation), "
            "rendering compact streak/high badges on the leaderboard."
        ),
        "examples": (
            "### Helper Input / Output Example\n"
            "```js\n"
            "// Ordered chronologically (oldest -> newest)\n"
            "calculateMemberStreakAndConsistency([18, 22, 27, 34, 24])\n"
            "// => {\n"
            "//   count: 5,\n"
            "//   seasonHigh: 34,\n"
            "//   avgVal: 25.0,\n"
            "//   stdDev: 5.3,\n"
            "//   activeHotStreak: 4,     // consecutive 20+ VAL games at tail\n"
            "//   consistencyLabel: \"Steady\"\n"
            "// }\n\n"
            "// Empty history edge case:\n"
            "calculateMemberStreakAndConsistency([])\n"
            "// => { count: 0, seasonHigh: null, avgVal: null, stdDev: null, activeHotStreak: 0, consistencyLabel: \"N/A\" }\n"
            "```\n\n"
            "### UI Badge Preview\n"
            "- Member cell / leaderboard columns display: `Best: +34` pill, `🔥 4G` active 20+ VAL streak badge (when `activeHotStreak >= 2`), and `±5.3` consistency indicator."
        ),
        "owned_paths": [
            "site_ui/helpers.js",
            "site_ui/group/index.html",
            "site_ui/styles.css",
            "docs/contracts/schemas_and_routes.json",
            "tests/test_helpers_and_contracts.py",
        ],
        "forbidden_paths": ["firestore.rules", ".github/workflows/"],
        "acceptance_criteria": [
            "Add `calculateMemberStreakAndConsistency(gameVals)` in `site_ui/helpers.js` and register it in `docs/contracts/schemas_and_routes.json`",
            "Display season-high VAL and active streak badges in the Group Leaderboard table in `site_ui/group/index.html`",
            "Add unit tests in `tests/test_helpers_and_contracts.py` verifying streak, season-high, and empty-history edge cases",
        ],
        "verification_commands": ["python -m pytest -v"],
        "priority": "p2",
        "source": "feature",
        "domains": ["groups-firestore", "site-ui", "analytics"],
    },
    {
        "pillar": "live-boxscore",
        "title": "Add advanced shooting efficiency metrics (eFG%, TS%, AST/TO) to Player VAL Breakdown modal",
        "context": (
            "The Player VAL Breakdown modal (`renderValBreakdownHtml` in `site_ui/helpers.js`) explains how a "
            "player's raw counting stats add up to their VAL score, but Pick'em users evaluating players also want "
            "modern basketball efficiency splits (`eFG%`, `TS%`, `AST/TO`) right inside the breakdown modal "
            "with full light/dark-mode parity."
        ),
        "objective": (
            "Add a pure helper `calculateAdvancedEfficiency(stats, labels)` in `site_ui/helpers.js` "
            "computing Effective FG% (`(FGM + 0.5 * 3PM) / FGA`), True Shooting % (`PTS / (2 * (FGA + 0.44 * FTA))`), "
            "and Assist-to-Turnover ratio, and render an efficiency summary strip inside `renderValBreakdownHtml`."
        ),
        "examples": (
            "### Helper Input / Output Example\n"
            "```js\n"
            "calculateAdvancedEfficiency({\n"
            "  pts: 26, fg: { m: 9, a: 17 }, threePt: { m: 4, a: 8 }, ft: { m: 4, a: 5 }, ast: 6, tov: 2\n"
            "})\n"
            "// => {\n"
            "//   efgPct: 64.7, tsPct: 67.7, astToRatio: 3.0,\n"
            "//   efgDisplay: \"64.7%\", tsDisplay: \"67.7%\", astToDisplay: \"3.0\"\n"
            "// }\n\n"
            "// Zero-attempt edge case (0 FGA, 0 FTA, 0 TO):\n"
            "calculateAdvancedEfficiency({ pts: 0, fg: { m: 0, a: 0 }, threePt: { m: 0, a: 0 }, ft: { m: 0, a: 0 }, ast: 2, tov: 0 })\n"
            "// => { efgPct: null, tsPct: null, astToRatio: null, efgDisplay: \"N/A\", tsDisplay: \"N/A\", astToDisplay: \"2.0\" }\n"
            "```"
        ),
        "owned_paths": [
            "site_ui/helpers.js",
            "site_ui/styles.css",
            "docs/contracts/schemas_and_routes.json",
            "tests/test_helpers_and_contracts.py",
        ],
        "forbidden_paths": ["firestore.rules", ".github/workflows/"],
        "acceptance_criteria": [
            "Add `calculateAdvancedEfficiency(stats, labels)` in `site_ui/helpers.js` and register it in `docs/contracts/schemas_and_routes.json`",
            "Surface eFG%, TS%, and AST/TO in `renderValBreakdownHtml` with clean zero-attempt handling",
            "Add unit tests in `tests/test_helpers_and_contracts.py` covering `calculateAdvancedEfficiency` and `renderValBreakdownHtml` output",
        ],
        "verification_commands": ["python -m pytest -v"],
        "priority": "p2",
        "source": "feature",
        "domains": ["analytics", "site-ui"],
    },
    {
        "pillar": "standings-resume",
        "title": "Add Quadrant 1-4 game list drilldown to calculateScheduleQuadSummary and Standings/Schedule UI",
        "context": (
            "Standings currently show aggregate `W-L` counts per Quadrant (Q1–Q4), so users researching bracketology "
            "cannot see which specific wins or upcoming games make up a team's Q1 or Q2 record without scrolling "
            "through the full season schedule."
        ),
        "objective": (
            "Extend `calculateScheduleQuadSummary(events, teamId, bpiMap)` in `site_ui/helpers.js` so each "
            "quadrant bucket (`1..4`) includes a `games` array (`id`, `opponentName`, `locationLabel`, `oppRank`, "
            "`completed`, `winner`, `score`), and allow users on `site_ui/standings/index.html` to inspect the "
            "games inside each Quadrant."
        ),
        "examples": (
            "### Helper Return Shape Example\n"
            "```js\n"
            "const summary = calculateScheduleQuadSummary(events, '152', bpiMap);\n"
            "// summary[1] => {\n"
            "//   w: 4, l: 3, rem: 2, pct: 57,\n"
            "//   games: [\n"
            "//     { id: '4017', opponentName: 'Duke', locationLabel: 'Away', oppRank: 6, completed: true, winner: true, score: '78-74' },\n"
            "//     { id: '4018', opponentName: 'North Carolina', locationLabel: 'Home', oppRank: 11, completed: false, winner: false, score: '' }\n"
            "//   ]\n"
            "// }\n"
            "```"
        ),
        "owned_paths": [
            "site_ui/helpers.js",
            "site_ui/standings/index.html",
            "site_ui/styles.css",
            "tests/test_helpers_and_contracts.py",
        ],
        "forbidden_paths": ["firestore.rules", ".github/workflows/"],
        "acceptance_criteria": [
            "Each quadrant bucket returned by `calculateScheduleQuadSummary` includes a structured `games` list while preserving backward-compatible `w`, `l`, `rem`, and `pct` fields",
            "Tapping a Quadrant card in the Standings team drawer toggles a compact list of that team's games in that quadrant",
            "Unit tests in `tests/test_helpers_and_contracts.py` verify quadrant game bucket classification",
        ],
        "verification_commands": ["python -m pytest -v"],
        "priority": "p2",
        "source": "feature",
        "domains": ["espn-api", "analytics", "site-ui"],
        "screenshot_caption": "Proposed Quadrant Game List Drilldown",
        "mockup_html": (
            '<div class="roster-drawer-inner standings-drawer-inner" style="border-radius:12px; border:1px solid #cbd5e1; padding:18px; max-width:760px;">'
            '<div>'
            '<div class="roster-section-header" style="margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">'
            '<span class="roster-section-title">Quadrant Win-Loss Breakdown — NC State Wolfpack</span>'
            '<span class="roster-minilog-hint">Tap a Quadrant card to inspect matchups · via ESPN BPI</span>'
            '</div>'
            '<div class="standings-quad-grid">'
            '<div class="standings-quad-card" style="outline:2px solid #2563eb; cursor:pointer;">'
            '<div class="standings-quad-top"><span class="quad-pill quad-pill-q1">Q1</span><span class="standings-quad-pct pill-sub-pos">57%</span></div>'
            '<div class="standings-quad-record">4-3</div>'
            '<div class="standings-quad-meta"><span>2 left · Expanded ▾</span><span class="standings-quad-cutoff">H 1–30 · N 1–50 · A 1–75</span></div>'
            '</div>'
            '<div class="standings-quad-card"><div class="standings-quad-top"><span class="quad-pill quad-pill-q2">Q2</span><span class="standings-quad-pct pill-sub-pos">67%</span></div><div class="standings-quad-record">4-2</div><div class="standings-quad-meta"><span>1 left · Tap to view ▸</span><span class="standings-quad-cutoff">H 31–75 · N 51–100 · A 76–135</span></div></div>'
            '<div class="standings-quad-card"><div class="standings-quad-top"><span class="quad-pill quad-pill-q3">Q3</span><span class="standings-quad-pct pill-sub-pos">83%</span></div><div class="standings-quad-record">5-1</div><div class="standings-quad-meta"><span>0 left · Tap to view ▸</span><span class="standings-quad-cutoff">H 76–160 · N 101–200 · A 136–240</span></div></div>'
            '<div class="standings-quad-card"><div class="standings-quad-top"><span class="quad-pill quad-pill-q4">Q4</span><span class="standings-quad-pct pill-sub-pos">100%</span></div><div class="standings-quad-record">6-0</div><div class="standings-quad-meta"><span>0 left · Tap to view ▸</span><span class="standings-quad-cutoff">H 161+ · N 201+ · A 241+</span></div></div>'
            '</div>'
            '<div style="margin-top:12px; border-radius:8px; border:1px solid rgba(148,163,184,0.35); padding:10px 12px; background:rgba(37,99,235,0.05);">'
            '<div style="font-size:0.78rem; font-weight:700; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:8px; display:flex; justify-content:space-between;">'
            '<span>Quadrant 1 Matchups (4-3, 2 Remaining)</span><span style="opacity:0.75;">H 1–30 · N 1–50 · A 1–75</span></div>'
            '<div style="display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:6px; font-size:0.82rem;">'
            '<div style="display:flex; justify-content:space-between; padding:6px 8px; border-radius:6px; background:rgba(16,185,129,0.12);"><span><strong>@ #6 Duke</strong> (Away)</span><span style="font-weight:700; color:#10b981;">W 78-74</span></div>'
            '<div style="display:flex; justify-content:space-between; padding:6px 8px; border-radius:6px; background:rgba(239,68,68,0.12);"><span><strong>vs #4 Kansas</strong> (Neutral)</span><span style="font-weight:700; color:#ef4444;">L 71-76</span></div>'
            '<div style="display:flex; justify-content:space-between; padding:6px 8px; border-radius:6px; background:rgba(16,185,129,0.12);"><span><strong>vs #11 North Carolina</strong> (Home)</span><span style="font-weight:700; color:#10b981;">W 82-76</span></div>'
            '<div style="display:flex; justify-content:space-between; padding:6px 8px; border-radius:6px; background:rgba(148,163,184,0.15);"><span><strong>@ #19 Virginia</strong> (Away)</span><span style="font-weight:600; opacity:0.8;">Upcoming · Feb 24</span></div>'
            '</div></div></div></div>'
        ),
    },
    {
        "pillar": "pwa-mobile",
        "title": "Add keyboard Escape-key dismissal and ARIA dialog semantics across all modals",
        "context": (
            "Desktop keyboard users and screen-reader users cannot currently press `Escape` to dismiss overlays "
            "on Scoreboard, Roster, and Group pages, and `.modal-overlay` containers lack `role=\"dialog\"` and "
            "`aria-modal=\"true\"` semantics."
        ),
        "objective": (
            "Improve keyboard accessibility and mobile/desktop UX by adding a shared Escape-key listener "
            "and `role=\"dialog\"` / `aria-modal=\"true\"` semantics to the VAL breakdown, VAL formula, "
            "member pick history, and group privacy modals across `site_ui/`."
        ),
        "examples": (
            "### HTML & Keyboard Behavior Example\n"
            "```html\n"
            "<div id=\"val-modal\" class=\"modal-overlay\" role=\"dialog\" aria-modal=\"true\" aria-labelledby=\"val-modal-title\">\n"
            "```\n"
            "- Pressing `Escape` while any `.modal-overlay` has `display: flex` (or `.open` class) closes only the active modal without navigating away."
        ),
        "owned_paths": [
            "site_ui/scoreboard/index.html",
            "site_ui/roster/index.html",
            "site_ui/group/index.html",
            "tests/test_helpers_and_contracts.py",
        ],
        "forbidden_paths": ["firestore.rules", ".github/workflows/"],
        "acceptance_criteria": [
            "All `.modal-overlay` containers in scoreboard, roster, and group pages include `role=\"dialog\"` and `aria-modal=\"true\"`",
            "Pressing the `Escape` key closes any active modal overlay on scoreboard, roster, and group pages",
            "Unit tests in `tests/test_helpers_and_contracts.py` verify modal ARIA attributes and Escape key handlers",
        ],
        "verification_commands": ["python -m pytest -v"],
        "priority": "p2",
        "source": "feature",
        "domains": ["pwa", "site-ui"],
    },
    {
        "pillar": "pickem-groups",
        "title": "Add Group Leaderboard filter modes (All Games, Conference Only, Last 5 Games, Quad 1-2)",
        "context": (
            "Long-season Pick'em groups often want to see who has been hottest lately (`Last 5 Games`) or "
            "who performs best in marquee matchups (`Quad 1-2`) without creating separate Firestore groups."
        ),
        "objective": (
            "Allow group members in `site_ui/group/index.html` to filter leaderboard standings and game matrices "
            "by game subset (`All Games`, `Last 5 Games`, `Quad 1-2 Matchups`) using a pure filter helper in "
            "`site_ui/helpers.js` without requiring any Firestore schema changes."
        ),
        "examples": (
            "### Filter Behavior Example\n"
            "```js\n"
            "filterGroupGamesByMode(games, 'last5', bpiMap, '152')   // => 5 most recent completed/active games\n"
            "filterGroupGamesByMode(games, 'quad1_2', bpiMap, '152') // => only games classified as Q1 or Q2 via getGameQuadrant()\n"
            "filterGroupGamesByMode(games, 'all', bpiMap, '152')     // => full season game list\n"
            "```"
        ),
        "owned_paths": [
            "site_ui/helpers.js",
            "site_ui/group/index.html",
            "site_ui/styles.css",
            "docs/contracts/schemas_and_routes.json",
            "tests/test_helpers_and_contracts.py",
        ],
        "forbidden_paths": ["firestore.rules", ".github/workflows/"],
        "acceptance_criteria": [
            "Add `filterGroupGamesByMode(games, mode, bpiMap, teamId)` in `site_ui/helpers.js` and register it in `docs/contracts/schemas_and_routes.json`",
            "Render filter pills above the Group Leaderboard in `site_ui/group/index.html` that recompute standings for the active filter",
            "Add unit tests in `tests/test_helpers_and_contracts.py` verifying `all`, `last5`, and `quad1_2` filtering",
        ],
        "verification_commands": ["python -m pytest -v"],
        "priority": "p2",
        "source": "feature",
        "domains": ["groups-firestore", "site-ui", "analytics"],
        "screenshot_caption": "Proposed Group Leaderboard Filter Modes",
        "mockup_html": (
            '<div class="card" style="padding:18px; border-radius:12px; max-width:740px;">'
            '<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:14px;">'
            '<h3 style="margin:0; font-size:1.05rem;">Group Standings · Wolfpack Pick\'em</h3>'
            '<div style="display:inline-flex; gap:6px; background:rgba(148,163,184,0.15); padding:4px; border-radius:999px; font-size:0.78rem; font-weight:600;">'
            '<span style="padding:4px 10px; border-radius:999px; opacity:0.75;">All Games (18)</span>'
            '<span style="padding:4px 10px; border-radius:999px; background:#2563eb; color:#fff;">Last 5 Games</span>'
            '<span style="padding:4px 10px; border-radius:999px; opacity:0.75;">Quad 1–2 Matchups (9)</span>'
            '</div></div>'
            '<table class="standings-table" style="width:100%; border-collapse:collapse; font-size:0.86rem;">'
            '<thead><tr style="text-align:left; border-bottom:1px solid rgba(148,163,184,0.3);">'
            '<th style="padding:8px;">Rank</th><th style="padding:8px;">Member</th><th style="padding:8px;">Filtered VAL (Last 5)</th><th style="padding:8px;">Avg VAL</th><th style="padding:8px;">Top Pick %</th>'
            '</tr></thead><tbody>'
            '<tr style="border-bottom:1px solid rgba(148,163,184,0.18);"><td style="padding:8px; font-weight:700;">#1</td><td style="padding:8px; font-weight:600;">Justin</td><td style="padding:8px; font-weight:700; color:#10b981;">+138</td><td style="padding:8px;">27.6</td><td style="padding:8px;">60%</td></tr>'
            '<tr><td style="padding:8px; font-weight:700;">#2</td><td style="padding:8px; font-weight:600;">Alex</td><td style="padding:8px; font-weight:700; color:#10b981;">+121</td><td style="padding:8px;">24.2</td><td style="padding:8px;">40%</td></tr>'
            '</tbody></table></div>'
        ),
    },
    {
        "pillar": "live-boxscore",
        "title": "Add Team Box Score comparison summary strip (Team VAL, Shooting Splits, Rebounds, Stocks)",
        "context": (
            "While individual player box scores show per-player VAL, Scoreboard users lack an at-a-glance "
            "team-level comparison strip showing which team is winning total VAL, shooting splits, rebounds, and stocks."
        ),
        "objective": (
            "Add a pure helper `calculateTeamBoxScoreSummary(players, labels)` in `site_ui/helpers.js` that aggregates "
            "team-wide Total VAL, FG%, 3PT%, FT%, Rebounds, Assist/TO ratio, and Stocks (STL+BLK), and render a "
            "head-to-head team comparison strip on `site_ui/scoreboard/index.html`."
        ),
        "examples": (
            "### Helper Output Example\n"
            "```js\n"
            "calculateTeamBoxScoreSummary(awayPlayers, labels)\n"
            "// => { totalVal: 148, fgPct: 48.4, threePtPct: 39.1, ftPct: 78.6, reb: 37, astToRatio: 1.8, stocks: 11 }\n"
            "```"
        ),
        "owned_paths": [
            "site_ui/helpers.js",
            "site_ui/scoreboard/index.html",
            "site_ui/styles.css",
            "docs/contracts/schemas_and_routes.json",
            "tests/test_helpers_and_contracts.py",
        ],
        "forbidden_paths": ["firestore.rules", ".github/workflows/"],
        "acceptance_criteria": [
            "Add `calculateTeamBoxScoreSummary(players, labels)` in `site_ui/helpers.js` and register it in `docs/contracts/schemas_and_routes.json`",
            "Render the head-to-head team comparison strip in `site_ui/scoreboard/index.html` when box score data is available",
            "Add unit tests in `tests/test_helpers_and_contracts.py` verifying `calculateTeamBoxScoreSummary` math",
        ],
        "verification_commands": ["python -m pytest -v"],
        "priority": "p2",
        "source": "feature",
        "domains": ["analytics", "site-ui"],
        "screenshot_caption": "Proposed Head-to-Head Team Box Score Comparison Strip",
        "mockup_html": (
            '<div class="card" style="padding:16px 18px; border-radius:12px; max-width:740px;">'
            '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; font-weight:700; font-size:0.9rem;">'
            '<span>NC State (Away)</span><span style="font-size:0.76rem; text-transform:uppercase; opacity:0.7;">Team Box Score Comparison</span><span>Duke (Home)</span>'
            '</div>'
            '<div class="roster-summary-strip" style="display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:8px;">'
            '<div class="roster-stat-pill"><span class="roster-pill-label">Team VAL</span><span class="roster-pill-value" style="font-size:0.98rem;"><strong style="color:#10b981;">148</strong> vs 134</span><span class="roster-pill-sub">Fantasy Total</span></div>'
            '<div class="roster-stat-pill"><span class="roster-pill-label">FG% / 3P%</span><span class="roster-pill-value" style="font-size:0.95rem;"><strong>48.4%</strong> vs 44.1%</span><span class="roster-pill-sub">3PT: 39.1% vs 33.3%</span></div>'
            '<div class="roster-stat-pill"><span class="roster-pill-label">Rebounds</span><span class="roster-pill-value" style="font-size:0.98rem;"><strong>37</strong> vs 33</span><span class="roster-pill-sub">+4 Margin</span></div>'
            '<div class="roster-stat-pill"><span class="roster-pill-label">AST / TO</span><span class="roster-pill-value" style="font-size:0.98rem;"><strong>1.8</strong> vs 1.3</span><span class="roster-pill-sub">16 AST · 9 TO</span></div>'
            '<div class="roster-stat-pill"><span class="roster-pill-label">Stocks</span><span class="roster-pill-value" style="font-size:0.98rem;"><strong>11</strong> vs 8</span><span class="roster-pill-sub">7 STL · 4 BLK</span></div>'
            '</div></div>'
        ),
    },
    {
        "pillar": "standings-resume",
        "title": "Add Conference Standings sort controls (Conf Seed, Overall Win%, BPI Rank, SOR) and conference switcher",
        "context": (
            "Standings currently lock users to their favorite team's conference in default seed order. Adding "
            "interactive sort pills and a conference dropdown makes the Standings page useful for comparing "
            "NCAA Tournament resumes across all Division I conferences."
        ),
        "objective": (
            "Enhance `site_ui/standings/index.html` and `site_ui/helpers.js` with a pure sorting helper "
            "`sortStandingsEntries(entries, sortBy, bpiMap)` and interactive column/pill sorting plus a conference "
            "selector dropdown so users can inspect any Division I conference and sort by Seed, Overall, BPI, or SOR."
        ),
        "examples": (
            "### Sorting Example\n"
            "```js\n"
            "sortStandingsEntries(entries, 'bpi', bpiMap)    // ascending BPI rank (1, 2, ...; unranked last)\n"
            "sortStandingsEntries(entries, 'winpct', bpiMap) // descending overall win percentage\n"
            "sortStandingsEntries(entries, 'seed', bpiMap)   // conference seed order\n"
            "```"
        ),
        "owned_paths": [
            "site_ui/helpers.js",
            "site_ui/standings/index.html",
            "site_ui/styles.css",
            "docs/contracts/schemas_and_routes.json",
            "tests/test_helpers_and_contracts.py",
        ],
        "forbidden_paths": ["firestore.rules", ".github/workflows/"],
        "acceptance_criteria": [
            "Add `sortStandingsEntries(entries, sortBy, bpiMap)` in `site_ui/helpers.js` and register it in `docs/contracts/schemas_and_routes.json`",
            "Add conference dropdown switcher and sortable column headers in `site_ui/standings/index.html`",
            "Add unit tests in `tests/test_helpers_and_contracts.py` verifying `sortStandingsEntries` across seed, winpct, bpi, and sor",
        ],
        "verification_commands": ["python -m pytest -v"],
        "priority": "p2",
        "source": "feature",
        "domains": ["espn-api", "analytics", "site-ui"],
        "screenshot_caption": "Proposed Conference Switcher & Standings Sort Controls",
        "mockup_html": (
            '<div class="card" style="padding:16px 18px; border-radius:12px; max-width:740px;">'
            '<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">'
            '<div style="display:flex; align-items:center; gap:8px;">'
            '<span style="font-weight:700; font-size:0.95rem;">Conference:</span>'
            '<select style="padding:5px 10px; border-radius:8px; border:1px solid rgba(148,163,184,0.4); font-weight:600;"><option>ACC (Atlantic Coast Conference)</option></select>'
            '</div>'
            '<div style="display:inline-flex; gap:6px; font-size:0.78rem; font-weight:600;">'
            '<span style="padding:4px 10px; border-radius:999px; background:rgba(148,163,184,0.18);">Conf Seed</span>'
            '<span style="padding:4px 10px; border-radius:999px; background:#2563eb; color:#fff;">BPI Rank ▲</span>'
            '<span style="padding:4px 10px; border-radius:999px; background:rgba(148,163,184,0.18);">SOR Rank</span>'
            '<span style="padding:4px 10px; border-radius:999px; background:rgba(148,163,184,0.18);">Overall Win%</span>'
            '</div></div>'
            '<table class="standings-table" style="width:100%; border-collapse:collapse; font-size:0.85rem;">'
            '<thead><tr style="text-align:left; border-bottom:1px solid rgba(148,163,184,0.3);">'
            '<th style="padding:7px;">Seed</th><th style="padding:7px;">Team</th><th style="padding:7px;">Conf</th><th style="padding:7px;">Overall</th><th style="padding:7px; color:#2563eb;">BPI ▲</th><th style="padding:7px;">SOR</th>'
            '</tr></thead><tbody>'
            '<tr style="border-bottom:1px solid rgba(148,163,184,0.18);"><td style="padding:7px;">#1</td><td style="padding:7px; font-weight:600;">Duke</td><td style="padding:7px;">14-2</td><td style="padding:7px;">23-4</td><td style="padding:7px; font-weight:700;">#3</td><td style="padding:7px;">#5</td></tr>'
            '<tr><td style="padding:7px;">#2</td><td style="padding:7px; font-weight:600;">NC State</td><td style="padding:7px;">13-3</td><td style="padding:7px;">22-5</td><td style="padding:7px; font-weight:700;">#9</td><td style="padding:7px;">#8</td></tr>'
            '</tbody></table></div>'
        ),
    },
    {
        "pillar": "pwa-mobile",
        "title": "Add offline last-known snapshot caching for Team Schedule and Conference Standings",
        "context": (
            "Mobile PWA users checking schedules or standings in arenas or on spotty cellular connections lose "
            "visibility when live ESPN API fetches fail. A lightweight `localStorage` snapshot cache provides "
            "graceful offline fallback."
        ),
        "objective": (
            "Enhance `fetchTeamSchedule` in `site_ui/helpers.js` with resilient `localStorage` snapshot caching "
            "(`saveCachedSnapshot` / `loadCachedSnapshot`) so users viewing Schedule or Standings on flaky mobile "
            "connections see the last fetched data instead of an empty error state."
        ),
        "examples": (
            "### Snapshot Round-Trip & TTL Example\n"
            "```js\n"
            "saveCachedSnapshot('schedule:152:mens', payload);\n"
            "loadCachedSnapshot('schedule:152:mens', 6 * 3600 * 1000); // => { data: payload, savedAt: 1731686400000 }\n"
            "loadCachedSnapshot('schedule:152:mens', 0);               // => null (expired)\n"
            "```"
        ),
        "owned_paths": [
            "site_ui/helpers.js",
            "docs/contracts/schemas_and_routes.json",
            "tests/test_helpers_and_contracts.py",
        ],
        "forbidden_paths": ["firestore.rules", ".github/workflows/"],
        "acceptance_criteria": [
            "Add `saveCachedSnapshot(key, data)` and `loadCachedSnapshot(key, maxAgeMs)` in `site_ui/helpers.js` and register them in `docs/contracts/schemas_and_routes.json`",
            "Use snapshot fallback in `fetchTeamSchedule` when network requests fail",
            "Add unit tests in `tests/test_helpers_and_contracts.py` verifying snapshot round-trip and TTL expiration",
        ],
        "verification_commands": ["python -m pytest -v"],
        "priority": "p2",
        "source": "feature",
        "domains": ["pwa", "espn-api"],
    },
]


def select_candidate_features(
    existing_titles: Set[str],
    limit: int = 2,
) -> List[Dict[str, Any]]:
    """Return up to `limit` unproposed feature specs balanced across product pillars."""
    normalized_existing = {t.strip().casefold() for t in existing_titles if t.strip()}
    available = [
        spec
        for spec in FEATURE_CATALOG
        if spec["title"].strip().casefold() not in normalized_existing
    ]
    selected: List[Dict[str, Any]] = []
    used_pillars: Set[str] = set()

    # Pass 1: pick at most 1 per pillar first for diversity
    for spec in available:
        if len(selected) >= limit:
            break
        if spec["pillar"] not in used_pillars:
            selected.append(spec)
            used_pillars.add(spec["pillar"])

    # Pass 2: fill remaining budget if needed
    for spec in available:
        if len(selected) >= limit:
            break
        if spec not in selected:
            selected.append(spec)

    return selected


def _render_and_attach_issue_screenshots(
    spec: Dict[str, Any],
    issue_obj: dict,
    repo: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Render Light/Dark mockup PNGs for a UI feature spec, publish to `agent-assets`, and update the issue body."""
    existing_screenshots = spec.get("screenshots")
    if existing_screenshots:
        return list(existing_screenshots)

    mockup_html = spec.get("mockup_html")
    if not mockup_html:
        return []

    issue_number = int(issue_obj.get("number") or 0)
    if not issue_number:
        return []

    try:
        repo_root = agent_backlog._get_canonical_repo_root()
        out_dir = os.path.join(repo_root, "scratch", "screenshots")
        css_text = capture_screenshots.read_file_from_ref("site_ui/styles.css", repo_root=repo_root)
        shots = capture_screenshots.capture_html_screenshots(
            body_html=mockup_html,
            output_dir=out_dir,
            name_prefix=f"issue-{issue_number}-mockup",
            css_text=css_text,
        )
        files_map: Dict[str, str] = {}
        for shot in shots:
            mode = shot["mode"]
            files_map[f"screenshots/issue-{issue_number}/mockup-{mode}.png"] = shot["path"]

        urls = capture_screenshots.publish_assets_to_branch(
            files_map=files_map,
            commit_message=f"chore: add issue #{issue_number} visual preview screenshots",
            repo=repo,
            repo_root=repo_root,
        )
        base_caption = spec.get("screenshot_caption") or "Proposed UI Preview"
        published_screenshots: List[Dict[str, str]] = []
        for mode_key, mode_label in (("light", "Light Mode"), ("dark", "Dark Mode")):
            rel_key = f"screenshots/issue-{issue_number}/mockup-{mode_key}.png"
            if rel_key in urls:
                published_screenshots.append(
                    {
                        "caption": f"{base_caption} ({mode_label})",
                        "url": urls[rel_key],
                    }
                )

        if published_screenshots:
            updated_body = agent_backlog.format_task_body(
                objective=spec["objective"],
                spec={
                    "owned_paths": spec["owned_paths"],
                    "forbidden_paths": spec["forbidden_paths"],
                    "acceptance_criteria": spec["acceptance_criteria"],
                    "verification_commands": spec["verification_commands"],
                },
                context=spec.get("context"),
                examples=spec.get("examples"),
                screenshots=published_screenshots,
            )
            agent_backlog.update_task_issue(issue_number, body=updated_body, repo=repo)
            issue_obj["body"] = updated_body
        return published_screenshots
    except Exception as exc:
        print(f"WARNING: Could not generate/publish screenshots for issue #{issue_number}: {exc}", file=sys.stderr)
        return []


def audit_and_propose_features(
    repo: Optional[str] = None,
    max_new_features: int = 2,
    max_open_features: int = 4,
    publish: bool = False,
) -> Dict[str, Any]:
    """Inspect open/closed feature issues and optionally publish up to `max_new_features` proposals."""
    existing_titles: Set[str] = set()
    open_feature_issues: List[dict] = []

    try:
        all_issues = agent_backlog.list_task_issues(status="all", state="all", repo=repo)
        for item in all_issues:
            title = (item.get("title") or "").strip()
            if title:
                existing_titles.add(title)
            if item.get("state") == "open":
                lbls = {l.get("name", "") for l in item.get("labels", [])}
                if "source:feature" in lbls or "source:roadmap" in lbls:
                    open_feature_issues.append(item)
    except Exception as exc:
        if publish:
            raise
        print(f"WARNING: Offline mode (could not query GitHub Issues): {exc}", file=sys.stderr)

    remaining_cap = max(0, max_open_features - len(open_feature_issues))
    budget = min(max_new_features, remaining_cap)
    candidates = select_candidate_features(existing_titles=existing_titles, limit=budget)

    published: List[Dict[str, Any]] = []
    if publish and candidates:
        for spec in candidates:
            res = agent_backlog.create_task_issue(
                title=spec["title"],
                objective=spec["objective"],
                owned_paths=spec["owned_paths"],
                forbidden_paths=spec["forbidden_paths"],
                acceptance_criteria=spec["acceptance_criteria"],
                verification_commands=spec["verification_commands"],
                priority=spec.get("priority", "p2"),
                source=spec.get("source", "feature"),
                domains=spec.get("domains", []),
                context=spec.get("context"),
                examples=spec.get("examples"),
                screenshots=spec.get("screenshots"),
                repo=repo,
            )
            if not res.get("deduplicated") and spec.get("mockup_html") and not spec.get("screenshots"):
                attached_shots = _render_and_attach_issue_screenshots(spec, res["issue"], repo=repo)
                res["screenshots"] = attached_shots
            else:
                res["screenshots"] = spec.get("screenshots") or []
            published.append(res)

    return {
        "open_feature_count": len(open_feature_issues),
        "max_open_features": max_open_features,
        "budget": budget,
        "candidates": candidates,
        "published": published,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Weekly New Feature / Feature Enhancement proposer for College-Basketball-Stats"
    )
    parser.add_argument("--repo-root", default=".", help="Path to repository root")
    parser.add_argument("--repo", default=None, help="GitHub repo slug owner/name")
    parser.add_argument("--worktree", action="store_true", help="Run inside an isolated agent/... worktree branched from latest origin/main")
    parser.add_argument("--base-branch", default="main", help="Base branch to fetch when --worktree is enabled (default: main)")
    parser.add_argument("--max-new-features", type=int, default=2, help="Max new feature issues per run")
    parser.add_argument("--max-open-features", type=int, default=4, help="Max open feature/roadmap issues allowed")
    parser.add_argument("--publish", action="store_true", help="Publish candidate feature specs as agent:proposed GitHub Issues")
    parser.add_argument("--json", action="store_true", help="Print output as JSON")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.worktree:
        with agent_backlog.temporary_agent_worktree(
            branch="agent/feature-proposer",
            base_branch=args.base_branch,
            repo_root=args.repo_root,
        ) as wt_path:
            prev_cwd = os.getcwd()
            try:
                os.chdir(wt_path)
                report = audit_and_propose_features(
                    repo=args.repo,
                    max_new_features=args.max_new_features,
                    max_open_features=args.max_open_features,
                    publish=args.publish,
                )
            finally:
                os.chdir(prev_cwd)
    else:
        report = audit_and_propose_features(
            repo=args.repo,
            max_new_features=args.max_new_features,
            max_open_features=args.max_open_features,
            publish=args.publish,
        )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"Open feature/roadmap issues: {report['open_feature_count']}/{report['max_open_features']} "
            f"(weekly proposal budget: {report['budget']})"
        )
        print(f"Selected {len(report['candidates'])} candidate feature enhancement(s):")
        for idx, c in enumerate(report["candidates"], 1):
            print(f"  {idx}. [{c['pillar']} | {c['priority']}] {c['title']}")
        if report["published"]:
            print("\nPublished GitHub Issues:")
            for item in report["published"]:
                issue = item["issue"]
                verb = "Matched existing" if item["deduplicated"] else "Created"
                print(f"  - {verb}: #{issue['number']} {issue['title']} ({issue['html_url']})")
                for shot in item.get("screenshots") or []:
                    print(f"    Screenshot [{shot['caption']}]: {shot['url']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
