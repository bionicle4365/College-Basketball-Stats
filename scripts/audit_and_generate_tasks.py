#!/usr/bin/env python3
"""Autonomous audit and GitHub Issue task generator for College-Basketball-Stats.

Focuses strictly on contract synchronization, Firestore security rules alignment,
frontend security/CSP/placeholder integrity, unit test coverage/failures, live ESPN
API telemetry, and GitHub Actions CI health. Product feature ideation is handled
separately by `scripts/propose_feature_tasks.py`.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from scripts import agent_backlog
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import agent_backlog  # type: ignore[no-redef]


REQUIRED_TEST_FILES = [
    "test_helpers_and_contracts.py",
    "test_agent_backlog.py",
    "test_verify_task.py",
    "test_audit_and_generate_tasks.py",
]


def _make_task(
    *,
    title: str,
    objective: str,
    owned_paths: List[str],
    forbidden_paths: List[str],
    acceptance_criteria: List[str],
    verification_commands: List[str],
    priority: str,
    source: str,
    domains: List[str],
    context: Optional[str] = None,
    examples: Optional[str] = None,
) -> Dict[str, Any]:
    """Build and validate a structured task specification dictionary."""
    validated = agent_backlog.validate_task_spec(
        {
            "owned_paths": owned_paths,
            "forbidden_paths": forbidden_paths,
            "acceptance_criteria": acceptance_criteria,
            "verification_commands": verification_commands,
        }
    )
    task: Dict[str, Any] = {
        "title": title,
        "objective": objective,
        "owned_paths": validated["owned_paths"],
        "forbidden_paths": validated["forbidden_paths"],
        "acceptance_criteria": validated["acceptance_criteria"],
        "verification_commands": validated["verification_commands"],
        "priority": priority,
        "source": source,
        "domains": domains,
    }
    if context:
        task["context"] = context.strip()
    if examples:
        task["examples"] = examples.strip()
    return task


def _extract_js_function_names(js_text: str) -> List[str]:
    """Extract top-level `function <name>(` declarations from `site_ui/helpers.js`."""
    names: List[str] = []
    for match in re.finditer(r"^(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(", js_text, re.MULTILINE):
        fn = match.group(1)
        if fn not in names:
            names.append(fn)
    return names


def audit_contract_and_firestore_drift(repo_root: str = ".") -> List[Dict[str, Any]]:
    """Verify `docs/contracts/schemas_and_routes.json` matches `firestore.rules`, `helpers.js`, and `sw.js`."""
    contract_path = os.path.join(repo_root, "docs", "contracts", "schemas_and_routes.json")
    rules_path = os.path.join(repo_root, "firestore.rules")
    helpers_path = os.path.join(repo_root, "site_ui", "helpers.js")
    sw_path = os.path.join(repo_root, "site_ui", "sw.js")

    if not (os.path.exists(contract_path) and os.path.exists(rules_path) and os.path.exists(helpers_path)):
        return []

    with open(contract_path, "r", encoding="utf-8") as f:
        contract = json.load(f)
    with open(rules_path, "r", encoding="utf-8") as f:
        rules_text = f.read()
    with open(helpers_path, "r", encoding="utf-8") as f:
        helpers_text = f.read()

    drift_items: List[str] = []

    # 1. Check helper_functions in contract vs site_ui/helpers.js
    actual_helpers = _extract_js_function_names(helpers_text)
    contract_helpers = [str(fn) for fn in contract.get("helper_functions", [])]
    missing_in_contract = [fn for fn in actual_helpers if fn not in contract_helpers]
    missing_in_helpers = [fn for fn in contract_helpers if fn not in actual_helpers]
    if missing_in_contract or missing_in_helpers:
        drift_items.append(
            f"helper_functions mismatch (missing_in_contract={missing_in_contract}, "
            f"missing_in_helpers={missing_in_helpers})"
        )

    # 2. Check Firestore collection regex & user_settings fields
    fs_contract = contract.get("firestore_collections", {})
    pick_regex = fs_contract.get("team_game_picks", {}).get("collection_regex", "")
    if pick_regex and pick_regex not in rules_text:
        drift_items.append(f"Firestore pick collection regex '{pick_regex}' missing from firestore.rules")

    for field in fs_contract.get("user_settings", {}).get("allowed_write_fields", []):
        if f"'{field}'" not in rules_text and f'"{field}"' not in rules_text:
            drift_items.append(f"user_settings field '{field}' in contract not found in firestore.rules")

    for field in fs_contract.get("groups", {}).get("required_create_fields", []):
        if f"'{field}'" not in rules_text and f'"{field}"' not in rules_text:
            drift_items.append(f"groups required_create_field '{field}' in contract not found in firestore.rules")

    # 3. Check Service Worker precached assets
    if os.path.exists(sw_path):
        with open(sw_path, "r", encoding="utf-8") as f:
            sw_text = f.read()
        for asset in contract.get("service_worker", {}).get("required_precached_assets", []):
            suffix = asset.replace("/College-Basketball-Stats", "")
            if suffix and suffix not in sw_text:
                drift_items.append(f"Service worker asset '{asset}' missing from site_ui/sw.js ASSETS")

    # 4. Check declared pages exist
    for page in contract.get("pages", []):
        rel_src = str(page.get("source", "")).strip()
        if rel_src and not os.path.exists(os.path.join(repo_root, rel_src)):
            drift_items.append(f"Declared page source '{rel_src}' does not exist")

    if not drift_items:
        return []

    return [
        _make_task(
            title="Synchronize docs/contracts/schemas_and_routes.json with helpers.js, sw.js, and firestore.rules",
            context=(
                "Autonomous tasks and CI rely on `docs/contracts/schemas_and_routes.json` as the single source of truth "
                "for registered helpers, precached PWA assets, and Firestore rules."
            ),
            objective=(
                "Contract drift detected between `docs/contracts/schemas_and_routes.json` and "
                "repository source files:\n- " + "\n- ".join(drift_items)
            ),
            examples=(
                "### Observed Drift Items\n"
                + "\n".join(f"- {item}" for item in drift_items)
                + "\n\nEnsure `helper_functions`, `service_worker.required_precached_assets`, and "
                "`firestore_collections` in `docs/contracts/schemas_and_routes.json` match the source files."
            ),
            owned_paths=["docs/contracts/schemas_and_routes.json", "tests/test_helpers_and_contracts.py"],
            forbidden_paths=["firestore.rules", ".github/workflows/"],
            acceptance_criteria=[
                "docs/contracts/schemas_and_routes.json matches all top-level functions in site_ui/helpers.js, precached assets in site_ui/sw.js, and rules in firestore.rules",
                "python -m pytest tests/test_helpers_and_contracts.py -v exits 0",
            ],
            verification_commands=["python -m pytest tests/test_helpers_and_contracts.py -v"],
            priority="p1",
            source="data-drift",
            domains=["site-ui", "groups-firestore"],
        )
    ]


def audit_frontend_security_and_routes(repo_root: str = ".") -> List[Dict[str, Any]]:
    """Audit `site_ui/` for Firebase placeholder safety, CSP headers, and undeclared ESPN API endpoints."""
    tasks: List[Dict[str, Any]] = []
    common_js_path = os.path.join(repo_root, "site_ui", "common.js")
    layout_path = os.path.join(repo_root, "site_ui", "_layouts", "default.html")
    contract_path = os.path.join(repo_root, "docs", "contracts", "schemas_and_routes.json")

    if os.path.exists(common_js_path):
        with open(common_js_path, "r", encoding="utf-8") as f:
            common_text = f.read()
        required_placeholders = [
            "FIREBASE_API_KEY_PLACEHOLDER",
            "FIREBASE_AUTH_DOMAIN_PLACEHOLDER",
            "FIREBASE_PROJECT_ID_PLACEHOLDER",
            "FIREBASE_APP_ID_PLACEHOLDER",
        ]
        missing_ph = [ph for ph in required_placeholders if ph not in common_text]
        if missing_ph:
            tasks.append(
                _make_task(
                    title="Restore Firebase CI placeholders in site_ui/common.js",
                    objective=(
                        "Detected missing Firebase secret placeholder(s) in `site_ui/common.js`: "
                        f"{missing_ph}. `site_ui/common.js` must keep placeholders so CI injects secrets "
                        "at deploy time without committing credentials."
                    ),
                    owned_paths=["site_ui/common.js", "tests/test_helpers_and_contracts.py"],
                    forbidden_paths=["firestore.rules", ".github/workflows/"],
                    acceptance_criteria=[
                        "All FIREBASE_*_PLACEHOLDER tokens are present in site_ui/common.js",
                        "python -m pytest tests/test_helpers_and_contracts.py -v exits 0",
                    ],
                    verification_commands=["python -m pytest tests/test_helpers_and_contracts.py -v"],
                    priority="p1",
                    source="data-drift",
                    domains=["site-ui", "groups-firestore"],
                )
            )

    if os.path.exists(layout_path):
        with open(layout_path, "r", encoding="utf-8") as f:
            layout_text = f.read()
        if "Content-Security-Policy" not in layout_text or "site.api.espn.com" not in layout_text:
            tasks.append(
                _make_task(
                    title="Restore Content-Security-Policy meta header in site_ui/_layouts/default.html",
                    objective=(
                        "`site_ui/_layouts/default.html` is missing the Content-Security-Policy meta tag "
                        "or required `connect-src` allowances for ESPN and Firebase."
                    ),
                    owned_paths=["site_ui/_layouts/default.html", "tests/test_helpers_and_contracts.py"],
                    forbidden_paths=["firestore.rules", ".github/workflows/"],
                    acceptance_criteria=[
                        "Content-Security-Policy meta header is present in site_ui/_layouts/default.html allowing ESPN and Firebase origins",
                        "python -m pytest tests/test_helpers_and_contracts.py -v exits 0",
                    ],
                    verification_commands=["python -m pytest tests/test_helpers_and_contracts.py -v"],
                    priority="p1",
                    source="data-drift",
                    domains=["site-ui", "pwa"],
                )
            )

    # Check if any helper functions in site_ui/helpers.js lack unit test references
    helpers_path = os.path.join(repo_root, "site_ui", "helpers.js")
    test_helpers_path = os.path.join(repo_root, "tests", "test_helpers_and_contracts.py")
    if os.path.exists(helpers_path) and os.path.exists(test_helpers_path):
        with open(helpers_path, "r", encoding="utf-8") as f:
            helpers_text = f.read()
        with open(test_helpers_path, "r", encoding="utf-8") as f:
            test_text = f.read()

        pure_Sync_fns = [
            "escapeHtml",
            "sanitizeUrl",
            "calculateVal",
            "getValTooltip",
            "getValDetails",
            "parseLegacyBreakdownText",
            "renderValBreakdownHtml",
            "getSportPath",
            "getCollectionName",
            "getTeamLogoHtml",
            "getValTierClass",
            "formatRankToken",
            "calculateScheduleSosSummary",
            "getGameQuadrant",
            "calculateScheduleQuadSummary",
        ]
        actual_fns = set(_extract_js_function_names(helpers_text))
        untested = [fn for fn in pure_Sync_fns if fn in actual_fns and fn not in test_text]
        if untested:
            tasks.append(
                _make_task(
                    title=f"Add unit test coverage for untested helper `{untested[0]}` in site_ui/helpers.js",
                    objective=(
                        "Pure helper function(s) in `site_ui/helpers.js` have no direct test assertions "
                        f"in `tests/test_helpers_and_contracts.py`: {', '.join(untested)}."
                    ),
                    owned_paths=["tests/test_helpers_and_contracts.py"],
                    forbidden_paths=["firestore.rules", "site_ui/"],
                    acceptance_criteria=[
                        f"Add deterministic unit tests covering {', '.join(untested)} in tests/test_helpers_and_contracts.py",
                        "python -m pytest tests/test_helpers_and_contracts.py -v exits 0",
                    ],
                    verification_commands=["python -m pytest tests/test_helpers_and_contracts.py -v"],
                    priority="p2",
                    source="test-gap",
                    domains=["analytics", "site-ui"],
                )
            )

    return tasks


def audit_test_suites(repo_root: str = ".", run_tests: bool = False) -> List[Dict[str, Any]]:
    """Audit required test files in `tests/` and optionally run `python -m pytest`."""
    tasks: List[Dict[str, Any]] = []
    tests_dir = os.path.join(repo_root, "tests")

    for tf in REQUIRED_TEST_FILES:
        if not os.path.exists(os.path.join(tests_dir, tf)):
            tasks.append(
                _make_task(
                    title=f"Add missing unit test module tests/{tf}",
                    objective=f"Required unit test module `tests/{tf}` is missing from the repository.",
                    owned_paths=[f"tests/{tf}"],
                    forbidden_paths=["firestore.rules", ".github/workflows/"],
                    acceptance_criteria=[
                        f"Create deterministic unit tests in `tests/{tf}`",
                        f"python -m pytest tests/{tf} -v exits 0",
                    ],
                    verification_commands=[f"python -m pytest tests/{tf} -v"],
                    priority="p2",
                    source="test-gap",
                    domains=["site-ui", "analytics"],
                )
            )

    if not run_tests:
        return tasks

    py_proc = subprocess.run(
        "python -m pytest -q",
        shell=True,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if py_proc.returncode != 0:
        combined = f"{py_proc.stdout}\n{py_proc.stderr}"
        failed_files = sorted(set(re.findall(r"(tests/test_[A-Za-z0-9_]+\.py)", combined)))
        owned = failed_files if failed_files else ["tests/", "site_ui/helpers.js"]
        tasks.append(
            _make_task(
                title="Fix failing pytest unit test suite in College-Basketball-Stats",
                objective=(
                    f"Live `python -m pytest -q` failed with exit code {py_proc.returncode}.\n\n"
                    f"Excerpt:\n{combined[-1200:]}"
                ),
                owned_paths=owned,
                forbidden_paths=["firestore.rules", ".github/workflows/"],
                acceptance_criteria=[
                    "Resolve all failing unit test assertions without weakening test coverage",
                    "python -m pytest -v exits 0",
                ],
                verification_commands=["python -m pytest -v"],
                priority="p1",
                source="test-gap",
                domains=["analytics", "site-ui"],
            )
        )

    return tasks


def audit_espn_api_health(team_id: str = "152") -> List[Dict[str, Any]]:
    """Probe live ESPN College Basketball API endpoints for HTTP failures or schema drift."""
    probes = [
        (
            "Men's Scoreboard",
            "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&limit=5",
            "events",
        ),
        (
            "Women's Scoreboard",
            "https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/scoreboard?groups=50&limit=5",
            "events",
        ),
        (
            "Men's Standings",
            "https://site.api.espn.com/apis/v2/sports/basketball/mens-college-basketball/standings",
            "children",
        ),
        (
            f"Team {team_id} Schedule",
            f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{team_id}/schedule",
            "events",
        ),
        (
            f"Team {team_id} Roster",
            f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{team_id}/roster",
            "athletes",
        ),
    ]

    failures: List[str] = []
    for label, url, expected_key in probes:
        req = urllib.request.Request(url, headers={"User-Agent": "College-Basketball-Stats-Audit/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status != 200:
                    failures.append(f"{label} returned HTTP {resp.status} ({url})")
                    continue
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
                if not isinstance(payload, dict) or (
                    expected_key not in payload
                    and "team" not in payload
                    and "standings" not in payload
                ):
                    failures.append(
                        f"{label} response missing expected key '{expected_key}' (keys={list(payload.keys())[:6]})"
                    )
        except Exception as exc:
            failures.append(f"{label} request failed ({url}): {exc}")

    if not failures:
        return []

    return [
        _make_task(
            title="Handle upstream ESPN API response drift or fallback in site_ui/helpers.js",
            objective=(
                "Live ESPN API telemetry probe detected endpoint error(s) or schema drift:\n- "
                + "\n- ".join(failures)
            ),
            owned_paths=["site_ui/helpers.js", "tests/test_helpers_and_contracts.py"],
            forbidden_paths=["firestore.rules", ".github/workflows/"],
            acceptance_criteria=[
                "Ensure fetch helpers in site_ui/helpers.js gracefully handle the observed ESPN response shape or fallback endpoint",
                "Add unit test coverage for the fallback behavior in tests/test_helpers_and_contracts.py",
            ],
            verification_commands=["python -m pytest tests/test_helpers_and_contracts.py -v"],
            priority="p1",
            source="telemetry",
            domains=["espn-api", "site-ui"],
        )
    ]


def audit_github_actions_failures(
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Check the latest completed GitHub Actions workflow runs on `main` for CI/Pages failures."""
    try:
        data = agent_backlog.github_request(
            "GET",
            "/actions/runs?branch=main&per_page=10",
            repo=repo,
            token=token,
        )
    except Exception:
        return []

    runs = data.get("workflow_runs") or [] if isinstance(data, dict) else []
    latest_by_workflow: Dict[Any, dict] = {}
    for run in sorted(runs, key=lambda r: str(r.get("created_at", "")), reverse=True):
        if run.get("status") != "completed":
            continue
        wf_id = run.get("workflow_id") or run.get("name")
        if wf_id not in latest_by_workflow:
            latest_by_workflow[wf_id] = run

    failed_workflows: List[str] = []
    for run in latest_by_workflow.values():
        if run.get("conclusion") == "failure":
            failed_workflows.append(
                f"{run.get('name', 'Workflow')}: {run.get('html_url', '')}".strip()
            )

    if not failed_workflows:
        return []

    return [
        _make_task(
            title="Fix failing GitHub Actions workflow on main",
            objective=(
                "Latest completed workflow run(s) on `main` failed:\n- "
                + "\n- ".join(failed_workflows)
            ),
            owned_paths=[".github/workflows/", "site_ui/", "tests/"],
            forbidden_paths=["firestore.rules"],
            acceptance_criteria=[
                "Identify and fix the root cause of the failing GitHub Actions workflow on main",
                "Local unit test suite (`python -m pytest`) passes cleanly",
            ],
            verification_commands=["python -m pytest -v"],
            priority="p1",
            source="test-gap",
            domains=["site-ui"],
        )
    ]


def collect_all_tasks(
    repo_root: str = ".",
    run_tests: bool = False,
    check_espn: bool = False,
    check_ci: bool = False,
    repo: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run enabled audits and return all discovered structured task specs."""
    tasks: List[Dict[str, Any]] = []
    tasks.extend(audit_contract_and_firestore_drift(repo_root=repo_root))
    tasks.extend(audit_frontend_security_and_routes(repo_root=repo_root))
    tasks.extend(audit_test_suites(repo_root=repo_root, run_tests=run_tests))
    if check_espn:
        try:
            tasks.extend(audit_espn_api_health())
        except Exception as exc:
            print(f"WARNING: ESPN API telemetry audit skipped: {exc}", file=sys.stderr)
    if check_ci:
        tasks.extend(audit_github_actions_failures(repo=repo))
    return tasks


def publish_discovered_tasks(
    tasks: List[Dict[str, Any]],
    repo: Optional[str] = None,
    max_new_issues: Optional[int] = 3,
    max_open_proposed: Optional[int] = 5,
    daily_window_hours: Optional[float] = 24.0,
) -> List[Dict[str, Any]]:
    """Publish discovered tasks as deduplicated GitHub Issues via `agent_backlog.create_task_issue`."""
    prio_rank = {"p1": 1, "p2": 2, "p3": 3}
    ordered_tasks = sorted(
        tasks,
        key=lambda t: prio_rank.get(str(t.get("priority", "p2")).lower(), 9),
    )

    budget: Optional[int] = max_new_issues
    if max_open_proposed is not None or (daily_window_hours is not None and daily_window_hours > 0):
        try:
            open_issues = agent_backlog.list_task_issues(status="all", state="open", repo=repo)
            now = datetime.now(timezone.utc)
            open_proposed_count = 0
            recent_24h_count = 0
            for item in open_issues:
                lbls = {l.get("name", "") for l in item.get("labels", [])}
                if "source:feature" in lbls or "source:roadmap" in lbls:
                    continue
                if "agent:proposed" in lbls:
                    open_proposed_count += 1
                if any(lbl in agent_backlog.STATUS_LABELS for lbl in lbls):
                    created_dt = agent_backlog._parse_github_iso_timestamp(item.get("created_at"))
                    if (
                        created_dt is not None
                        and daily_window_hours is not None
                        and (now - created_dt).total_seconds() <= daily_window_hours * 3600.0
                    ):
                        recent_24h_count += 1

            if max_open_proposed is not None:
                rem_proposed = max(0, max_open_proposed - open_proposed_count)
                budget = rem_proposed if budget is None else min(budget, rem_proposed)
            if max_new_issues is not None and daily_window_hours is not None and daily_window_hours > 0:
                rem_daily = max(0, max_new_issues - recent_24h_count)
                budget = rem_daily if budget is None else min(budget, rem_daily)
        except Exception:
            pass

    results: List[Dict[str, Any]] = []
    created_count = 0
    for task in ordered_tasks:
        if budget is not None and created_count >= budget:
            break
        res = agent_backlog.create_task_issue(
            title=task["title"],
            objective=task["objective"],
            owned_paths=task["owned_paths"],
            forbidden_paths=task["forbidden_paths"],
            acceptance_criteria=task["acceptance_criteria"],
            verification_commands=task["verification_commands"],
            priority=task.get("priority", "p2"),
            source=task.get("source", "telemetry"),
            domains=task.get("domains", []),
            context=task.get("context"),
            examples=task.get("examples"),
            repo=repo,
        )
        results.append(res)
        if not res.get("deduplicated"):
            created_count += 1
    return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit system health/gaps and generate GitHub Issue tasks")
    parser.add_argument("--repo-root", default=".", help="Path to repository root")
    parser.add_argument("--repo", default=None, help="GitHub repo slug owner/name")
    parser.add_argument("--worktree", action="store_true", help="Audit an isolated agent/... worktree branched from latest origin/main")
    parser.add_argument("--base-branch", default="main", help="Base branch to fetch when --worktree is enabled (default: main)")
    parser.add_argument("--max-new-issues", type=int, default=3, help="Maximum net-new issues created per 24h window")
    parser.add_argument("--max-open-proposed", type=int, default=5, help="Maximum open agent:proposed audit issues allowed before pausing")
    parser.add_argument("--run-tests", action="store_true", help="Run live pytest suite")
    parser.add_argument("--espn", action="store_true", help="Probe live ESPN College Basketball API endpoints")
    parser.add_argument("--ci", action="store_true", help="Check GitHub Actions CI runs on main for failures")
    parser.add_argument("--publish", action="store_true", help="Create deduplicated GitHub Issues for discovered tasks")
    parser.add_argument("--json", action="store_true", help="Print output as JSON")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.worktree:
        with agent_backlog.temporary_agent_worktree(
            branch="agent/audit-main",
            base_branch=args.base_branch,
            repo_root=args.repo_root,
        ) as wt_path:
            tasks = collect_all_tasks(
                repo_root=wt_path,
                run_tests=args.run_tests,
                check_espn=args.espn,
                check_ci=args.ci,
                repo=args.repo,
            )
    else:
        tasks = collect_all_tasks(
            repo_root=args.repo_root,
            run_tests=args.run_tests,
            check_espn=args.espn,
            check_ci=args.ci,
            repo=args.repo,
        )

    published: List[Dict[str, Any]] = []
    if args.publish and tasks:
        published = publish_discovered_tasks(
            tasks,
            repo=args.repo,
            max_new_issues=args.max_new_issues,
            max_open_proposed=args.max_open_proposed,
        )

    if args.json:
        print(json.dumps({"tasks": tasks, "published": published}, indent=2))
    else:
        print(f"Discovered {len(tasks)} audit task(s):")
        for idx, t in enumerate(tasks, 1):
            print(f"  {idx}. [{t['priority']} | {t['source']}] {t['title']}")
        if published:
            print("\nGitHub Issue sync results:")
            for item in published:
                issue = item["issue"]
                verb = "Matched existing" if item["deduplicated"] else "Created"
                print(f"  - {verb}: #{issue['number']} {issue['title']} ({issue['html_url']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
