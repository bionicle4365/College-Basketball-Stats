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
    from scripts import agent_backlog
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import agent_backlog  # type: ignore[no-redef]


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
    parser.add_argument("--repo", default=None, help="GitHub repo slug owner/name")
    parser.add_argument("--max-new-features", type=int, default=2, help="Max new feature issues per run")
    parser.add_argument("--max-open-features", type=int, default=4, help="Max open feature/roadmap issues allowed")
    parser.add_argument("--publish", action="store_true", help="Publish candidate feature specs as agent:proposed GitHub Issues")
    parser.add_argument("--json", action="store_true", help="Print output as JSON")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
