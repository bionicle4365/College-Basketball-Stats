#!/usr/bin/env python3
"""GitHub Issues-backed autonomous task queue CLI for College-Basketball-Stats."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_REPO = "bionicle4365/College-Basketball-Stats"
GITHUB_API_BASE = "https://api.github.com"

SPEC_BLOCK_PATTERN = re.compile(
    r"```json\s+agent-task-spec\s*\r?\n(.*?)\r?\n```",
    re.DOTALL,
)

STATUS_LABELS: Dict[str, Tuple[str, str]] = {
    "agent:proposed": (
        "D4C5F9",
        "Proposed task awaiting human approval before execution",
    ),
    "agent:ready": (
        "0E8A16",
        "Ready for an autonomous agent to claim and execute",
    ),
    "agent:in-progress": (
        "FBCA04",
        "Currently claimed by an active autonomous agent",
    ),
    "agent:review": (
        "1D76DB",
        "Implementation complete; awaiting verifier or human PR review",
    ),
    "agent:blocked": (
        "D93F0B",
        "Blocked by external dependency, failing check, or ambiguity",
    ),
}

SOURCE_LABELS: Dict[str, Tuple[str, str]] = {
    "source:roadmap": (
        "5319E7",
        "Planned product roadmap milestone",
    ),
    "source:feature": (
        "7057FF",
        "New feature or UX enhancement proposal",
    ),
    "source:telemetry": (
        "006B75",
        "Auto-generated from live ESPN API or runtime health checks",
    ),
    "source:test-gap": (
        "C2E0C6",
        "Auto-generated from unit test or CI workflow audit",
    ),
    "source:data-drift": (
        "F9D0C4",
        "Auto-generated from contract, Firestore rules, or ESPN schema drift",
    ),
}

PRIORITY_LABELS: Dict[str, Tuple[str, str]] = {
    "priority:p1": ("B60205", "High priority task"),
    "priority:p2": ("FBCA04", "Medium priority task"),
    "priority:p3": ("0E8A16", "Low priority task"),
}

DOMAIN_LABELS: Dict[str, Tuple[str, str]] = {
    "domain:site-ui": ("C5DEF5", "Jekyll templates, Vanilla CSS/JS, responsive UI, modals"),
    "domain:espn-api": ("C5DEF5", "ESPN scoreboard, schedule, roster, standings, BPI APIs"),
    "domain:groups-firestore": ("C5DEF5", "Firebase Auth, Firestore rules, Pick'em & Groups"),
    "domain:analytics": ("C5DEF5", "VAL formula, Quadrant 1-4 cutoffs, BPI/SOR/SOS metrics"),
    "domain:pwa": ("C5DEF5", "Service worker, manifest, caching, accessibility & mobile UX"),
}

STANDARD_LABELS: Dict[str, Tuple[str, str]] = {
    **STATUS_LABELS,
    **SOURCE_LABELS,
    **PRIORITY_LABELS,
    **DOMAIN_LABELS,
}

PRIORITY_ORDER = {"priority:p1": 1, "priority:p2": 2, "priority:p3": 3}
PROTECTED_BRANCHES = {"main", "master"}


def validate_agent_branch(branch: str) -> str:
    """Ensure task executors only target isolated `agent/...` branches, never `main`/`master`."""
    cleaned = (branch or "").strip()
    if not cleaned or cleaned in PROTECTED_BRANCHES or not cleaned.startswith("agent/"):
        raise ValueError(
            f"Task executors must use an isolated 'agent/...' branch (got '{branch}'). "
            "Pushing or merging to 'main'/'master' is forbidden."
        )
    return cleaned


def get_current_git_branch() -> str:
    """Return the active local git branch name."""
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


def push_task_branch(branch: Optional[str] = None) -> str:
    """Safely push a validated `agent/...` branch to `origin`, refusing while on `main`/`master`."""
    current = get_current_git_branch()
    if current in PROTECTED_BRANCHES:
        raise ValueError(f"Refusing to push while checked out on protected branch '{current}'.")
    target = validate_agent_branch(branch or current)
    subprocess.run(["git", "push", "-u", "origin", f"{target}:{target}"], check=True)
    return target


def _resolve_base_ref(base_branch: str = "main") -> str:
    """Fetch `origin/<base_branch>` when available and return the cleanest base ref."""
    subprocess.run(
        ["git", "fetch", "origin", base_branch],
        text=True,
        capture_output=True,
        check=False,
    )
    remote_ref = f"origin/{base_branch}"
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", remote_ref],
        text=True,
        capture_output=True,
        check=False,
    )
    return remote_ref if probe.returncode == 0 else base_branch


def prepare_task_branch(branch: str, base_branch: str = "main") -> str:
    """Create/reset `branch` from fresh `origin/main` after verifying the working tree is clean."""
    target = validate_agent_branch(branch)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode == 0 and status.stdout.strip():
        raise RuntimeError(
            "Working tree has uncommitted changes. Commit/stash them or pass '--worktree' "
            "to isolate the task branch from local edits."
        )
    resolved_base = _resolve_base_ref(base_branch=base_branch)
    subprocess.run(["git", "checkout", "-B", target, resolved_base], check=True)
    return target


def prepare_task_worktree(
    branch: str,
    worktree_path: Optional[str] = None,
    base_branch: str = "main",
) -> str:
    """Create an isolated `scratch/worktrees/...` checkout on `branch` rooted at `origin/main`."""
    target = validate_agent_branch(branch)
    top_proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    repo_root = top_proc.stdout.strip() if top_proc.returncode == 0 and top_proc.stdout.strip() else os.getcwd()
    wt_path = worktree_path or os.path.join(repo_root, "scratch", "worktrees", target.replace("/", "-"))
    resolved_base = _resolve_base_ref(base_branch=base_branch)

    if os.path.exists(wt_path):
        subprocess.run(
            ["git", "worktree", "remove", "--force", wt_path],
            text=True,
            capture_output=True,
            check=False,
        )
    subprocess.run(["git", "worktree", "prune"], text=True, capture_output=True, check=False)
    os.makedirs(os.path.dirname(wt_path), exist_ok=True)
    subprocess.run(["git", "worktree", "add", "-B", target, wt_path, resolved_base], check=True)
    return wt_path.replace("\\", "/")


def detect_repo_slug(fallback: str = DEFAULT_REPO) -> str:
    """Detect the GitHub `owner/repo` slug from `git remote get-url origin`."""
    try:
        proc = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            url = proc.stdout.strip()
            match = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", url)
            if match:
                return match.group(1)
    except OSError:
        pass
    return fallback


def get_github_token() -> str:
    """Retrieve a GitHub personal access token from env vars or git credential fill."""
    for env_var in ("GITHUB_TOKEN", "GH_TOKEN"):
        token = os.environ.get(env_var, "").strip()
        if token:
            return token

    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if line.startswith("password="):
                    token = line.split("=", 1)[1].strip()
                    if token:
                        return token
    except OSError as exc:
        raise RuntimeError(f"Unable to invoke git credential fill: {exc}") from exc

    raise RuntimeError(
        "No GitHub token found in GITHUB_TOKEN, GH_TOKEN, or git credential helper."
    )


def github_request(
    method: str,
    path: str,
    payload: Optional[Any] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Any:
    """Execute an authenticated GitHub REST API request scoped to `repo`."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()
    if not path or path == "/":
        normalized_path = ""
    else:
        normalized_path = path if path.startswith("/") else f"/{path}"
    url = f"{GITHUB_API_BASE}/repos/{target_repo}{normalized_path}"

    data_bytes: Optional[bytes] = None
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "College-Basketball-Stats-Agent",
    }
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API {method.upper()} {url} failed with HTTP {err.code}: {err_body}"
        ) from err


def validate_task_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize an agent task specification dictionary."""
    if not isinstance(spec, dict):
        raise ValueError("Task spec must be a JSON object.")

    owned = [str(p).strip().replace("\\", "/") for p in spec.get("owned_paths") or [] if str(p).strip()]
    if not owned:
        raise ValueError("Task spec must include at least one path in 'owned_paths'.")

    forbidden_raw = spec.get("forbidden_paths")
    if forbidden_raw is None:
        default_forbidden = []
        if not any(p == "firestore.rules" for p in owned):
            default_forbidden.append("firestore.rules")
        if not any(p.startswith(".github/") for p in owned):
            default_forbidden.append(".github/workflows/")
        forbidden = default_forbidden
    else:
        forbidden = [str(p).strip().replace("\\", "/") for p in forbidden_raw if str(p).strip()]

    acceptance = [str(a).strip() for a in spec.get("acceptance_criteria") or [] if str(a).strip()]
    if not acceptance:
        raise ValueError("Task spec must include at least one item in 'acceptance_criteria'.")

    verify_cmds = [str(c).strip() for c in spec.get("verification_commands") or [] if str(c).strip()]
    if not verify_cmds:
        raise ValueError("Task spec must include at least one command in 'verification_commands'.")

    normalized = {
        "owned_paths": owned,
        "forbidden_paths": forbidden,
        "acceptance_criteria": acceptance,
        "verification_commands": verify_cmds,
    }
    if spec.get("objective"):
        normalized["objective"] = str(spec["objective"]).strip()
    return normalized


def format_task_body(
    objective: str,
    spec: Dict[str, Any],
    context: Optional[str] = None,
    examples: Optional[str] = None,
    screenshots: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Format a GitHub Issue body with rich context, examples, screenshots, and an agent-task-spec block."""
    validated = validate_task_spec({**spec, "objective": objective})
    spec_json = json.dumps(
        {
            "owned_paths": validated["owned_paths"],
            "forbidden_paths": validated["forbidden_paths"],
            "acceptance_criteria": validated["acceptance_criteria"],
            "verification_commands": validated["verification_commands"],
        },
        indent=2,
    )

    context_text = (context if context is not None else spec.get("context") or "").strip()
    examples_text = (examples if examples is not None else spec.get("examples") or "").strip()
    shot_items = screenshots if screenshots is not None else (spec.get("screenshots") or [])

    lines: List[str] = []
    if context_text:
        lines.extend(["## Context & Motivation", context_text, ""])

    lines.extend(["## Objective", objective.strip(), ""])

    if examples_text:
        lines.extend(["## Examples & Expected Behavior", examples_text, ""])

    if shot_items:
        lines.append("## UI / Screenshot Preview")
        for idx, item in enumerate(shot_items, 1):
            if isinstance(item, dict):
                caption = str(item.get("caption") or f"Preview {idx}").strip()
                url = str(item.get("url") or "").strip()
            else:
                caption = f"Preview {idx}"
                url = str(item).strip()
            if url:
                lines.append(f"**{caption}**")
                lines.append(f"![{caption}]({url})")
                lines.append("")

    lines.extend([
        "## Owned Paths",
        *[f"- `{p}`" for p in validated["owned_paths"]],
        "",
        "## Forbidden Paths",
        *([f"- `{p}`" for p in validated["forbidden_paths"]] or ["- *(None)*"]),
        "",
        "## Acceptance Criteria",
        *[f"- [ ] {item}" for item in validated["acceptance_criteria"]],
        "",
        "## Verification Commands",
        *[f"- `{cmd}`" for cmd in validated["verification_commands"]],
        "",
        "```json agent-task-spec",
        spec_json,
        "```",
    ])
    return "\n".join(lines)


def _extract_markdown_section_items(body: str, heading: str) -> List[str]:
    """Extract bulleted or line items under a Markdown H2/H3 heading from Issue Forms or prose."""
    pattern = re.compile(
        rf"^#{{2,3}}\s+{re.escape(heading)}\s*\r?\n(.*?)(?=^#{{2,3}}\s+|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(body or "")
    if not match:
        return []
    items: List[str] = []
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.lower() in ("_no response_", "*(none)*", "none"):
            continue
        line = re.sub(r"^[-*]\s+(?:\[[ xX]\]\s+)?", "", line).strip()
        if line.startswith("`") and line.endswith("`") and len(line) > 2:
            line = line[1:-1]
        if line:
            items.append(line)
    return items


def parse_task_spec(issue_body: str) -> Dict[str, Any]:
    """Parse and validate an agent task spec from either embedded JSON or Markdown headings."""
    body = issue_body or ""
    match = SPEC_BLOCK_PATTERN.search(body)
    if match:
        raw_spec = json.loads(match.group(1))
        return validate_task_spec(raw_spec)

    spec = {
        "owned_paths": _extract_markdown_section_items(body, "Owned Paths"),
        "forbidden_paths": _extract_markdown_section_items(body, "Forbidden Paths"),
        "acceptance_criteria": _extract_markdown_section_items(body, "Acceptance Criteria"),
        "verification_commands": _extract_markdown_section_items(body, "Verification Commands"),
    }
    return validate_task_spec(spec)


def _get_paginated_issues(
    state: str = "open",
    labels: Optional[List[str]] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> List[dict]:
    """Fetch repository issues (excluding pull requests) across pages."""
    issues: List[dict] = []
    page = 1
    while True:
        params: Dict[str, Any] = {"state": state, "per_page": 100, "page": page}
        if labels:
            params["labels"] = ",".join(labels)
        query = urllib.parse.urlencode(params)
        batch = github_request("GET", f"/issues?{query}", repo=repo, token=token) or []
        if not batch:
            break
        for item in batch:
            if "pull_request" not in item:
                issues.append(item)
        if len(batch) < 100:
            break
        page += 1
    return issues


def _issue_priority_rank(issue: dict) -> Tuple[int, int]:
    """Sort key placing P1 before P2 before P3, then ascending issue number."""
    labels = {lbl.get("name", "") for lbl in issue.get("labels", [])}
    rank = min((PRIORITY_ORDER[l] for l in labels if l in PRIORITY_ORDER), default=99)
    return (rank, int(issue.get("number", 0)))


def init_repo(repo: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
    """Enable GitHub Issues on the repository and create/update all standard agentic labels."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    repo_resp = github_request(
        "PATCH",
        "",
        payload={"has_issues": True},
        repo=target_repo,
        token=auth_token,
    )

    existing_labels: Dict[str, dict] = {}
    page = 1
    while True:
        batch = github_request(
            "GET",
            f"/labels?per_page=100&page={page}",
            repo=target_repo,
            token=auth_token,
        ) or []
        for lbl in batch:
            existing_labels[lbl["name"].casefold()] = lbl
        if len(batch) < 100:
            break
        page += 1

    created = 0
    updated = 0
    for name, (color, description) in STANDARD_LABELS.items():
        payload = {"name": name, "color": color, "description": description}
        existing = existing_labels.get(name.casefold())
        if existing is None:
            github_request("POST", "/labels", payload=payload, repo=target_repo, token=auth_token)
            created += 1
        elif existing.get("color", "").upper() != color.upper() or existing.get("description") != description:
            encoded_name = urllib.parse.quote(existing["name"], safe="")
            github_request(
                "PATCH",
                f"/labels/{encoded_name}",
                payload=payload,
                repo=target_repo,
                token=auth_token,
            )
            updated += 1

    return {
        "repo": target_repo,
        "has_issues": bool(repo_resp.get("has_issues", True)) if isinstance(repo_resp, dict) else True,
        "labels_created": created,
        "labels_updated": updated,
        "total_standard_labels": len(STANDARD_LABELS),
    }


def create_task_issue(
    title: str,
    objective: str,
    owned_paths: List[str],
    acceptance_criteria: List[str],
    verification_commands: List[str],
    forbidden_paths: Optional[List[str]] = None,
    priority: str = "p2",
    source: str = "roadmap",
    domains: Optional[List[str]] = None,
    initial_status: str = "proposed",
    context: Optional[str] = None,
    examples: Optional[str] = None,
    screenshots: Optional[List[Dict[str, str]]] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an agentic GitHub Issue if no open issue with the same title already exists."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    status_label = initial_status if initial_status.startswith("agent:") else f"agent:{initial_status}"
    if status_label not in STATUS_LABELS:
        raise ValueError(f"Invalid initial_status '{initial_status}'.")

    open_issues = _get_paginated_issues(state="open", repo=target_repo, token=auth_token)
    normalized_title = title.strip().casefold()
    for existing in open_issues:
        if (existing.get("title") or "").strip().casefold() == normalized_title:
            return {"deduplicated": True, "issue": existing}

    body = format_task_body(
        objective=objective,
        spec={
            "owned_paths": owned_paths,
            "forbidden_paths": forbidden_paths,
            "acceptance_criteria": acceptance_criteria,
            "verification_commands": verification_commands,
        },
        context=context,
        examples=examples,
        screenshots=screenshots,
    )

    labels = [status_label]
    prio_label = priority if priority.startswith("priority:") else f"priority:{priority}"
    if prio_label in PRIORITY_LABELS:
        labels.append(prio_label)

    src_label = source if source.startswith("source:") else f"source:{source}"
    if src_label in SOURCE_LABELS:
        labels.append(src_label)

    for dom in domains or []:
        dom_label = dom if dom.startswith("domain:") else f"domain:{dom}"
        if dom_label in DOMAIN_LABELS and dom_label not in labels:
            labels.append(dom_label)

    created = github_request(
        "POST",
        "/issues",
        payload={"title": title.strip(), "body": body, "labels": labels},
        repo=target_repo,
        token=auth_token,
    )
    return {"deduplicated": False, "issue": created}


def list_task_issues(
    status: str = "ready",
    domain: Optional[str] = None,
    source: Optional[str] = None,
    state: str = "open",
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> List[dict]:
    """List agentic issues filtered by status/domain/source and sorted by priority."""
    labels: List[str] = []
    if status and status != "all":
        labels.append(status if status.startswith("agent:") else f"agent:{status}")
    if domain:
        labels.append(domain if domain.startswith("domain:") else f"domain:{domain}")
    if source:
        labels.append(source if source.startswith("source:") else f"source:{source}")

    issues = _get_paginated_issues(state=state, labels=labels or None, repo=repo, token=token)
    return sorted(issues, key=_issue_priority_rank)


def get_task_issue(
    issue_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch a single issue and parse its embedded task specification."""
    issue = github_request("GET", f"/issues/{issue_number}", repo=repo, token=token)
    spec: Optional[Dict[str, Any]] = None
    spec_error: Optional[str] = None
    try:
        spec = parse_task_spec(issue.get("body", ""))
    except Exception as exc:
        spec_error = str(exc)

    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "html_url": issue.get("html_url"),
        "labels": [lbl.get("name") for lbl in issue.get("labels", [])],
        "spec": spec,
        "spec_error": spec_error,
        "body": issue.get("body", ""),
    }


def _replace_status_label(current_labels: List[str], target_status_label: str) -> List[str]:
    """Return updated label list replacing any `agent:*` status label with `target_status_label`."""
    preserved = [lbl for lbl in current_labels if lbl not in STATUS_LABELS]
    if target_status_label not in preserved:
        preserved.append(target_status_label)
    return preserved


def approve_task_issue(
    issue_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Approve a proposed issue by transitioning its status label to `agent:ready`."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    current_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    new_labels = _replace_status_label(current_labels, "agent:ready")

    updated = github_request(
        "PATCH",
        f"/issues/{issue_number}",
        payload={"labels": new_labels},
        repo=target_repo,
        token=auth_token,
    )
    github_request(
        "POST",
        f"/issues/{issue_number}/comments",
        payload={"body": "Approved for autonomous execution (`agent:ready`)."},
        repo=target_repo,
        token=auth_token,
    )
    return updated


def claim_task_issue(
    issue_number: int,
    agent_name: str,
    branch: Optional[str] = None,
    force: bool = False,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Transition an approved `agent:ready` issue to `agent:in-progress` and post a claim comment."""
    if branch is not None:
        branch = validate_agent_branch(branch)
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    current_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    if not force and "agent:ready" not in current_labels:
        raise ValueError(
            f"Issue #{issue_number} is not approved for execution (missing 'agent:ready' label; "
            f"current labels: {current_labels}). Approve it first with "
            f"'python scripts/agent_backlog.py approve {issue_number}' or by setting the 'agent:ready' label on GitHub."
        )
    new_labels = _replace_status_label(current_labels, "agent:in-progress")

    updated = github_request(
        "PATCH",
        f"/issues/{issue_number}",
        payload={"labels": new_labels},
        repo=target_repo,
        token=auth_token,
    )

    branch_note = f" on branch `{branch}`" if branch else ""
    comment = f"Claimed by autonomous agent `{agent_name}`{branch_note}."
    github_request(
        "POST",
        f"/issues/{issue_number}/comments",
        payload={"body": comment},
        repo=target_repo,
        token=auth_token,
    )
    return updated


def get_next_ready_issue(
    domain: Optional[str] = None,
    reclaim_stale_hours: Optional[float] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch the highest-priority `agent:ready` issue, parse its spec, and suggest a feature branch."""
    if reclaim_stale_hours is not None and reclaim_stale_hours > 0:
        reclaim_stale_in_progress_issues(
            max_age_hours=reclaim_stale_hours,
            repo=repo,
            token=token,
        )
    issues = list_task_issues(status="ready", domain=domain, state="open", repo=repo, token=token)
    if not issues:
        return None
    top_number = int(issues[0]["number"])
    task = get_task_issue(top_number, repo=repo, token=token)
    task["branch"] = f"agent/issue-{top_number}"
    return task


def _parse_github_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 UTC timestamp string returned by the GitHub REST API."""
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = f"{cleaned[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def reclaim_stale_in_progress_issues(
    max_age_hours: float = 6.0,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> List[dict]:
    """Reclaim open `agent:in-progress` issues older than `max_age_hours` back to `agent:ready` (or `agent:review` if a PR exists)."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()
    owner = target_repo.split("/")[0]
    now = datetime.now(timezone.utc)

    in_progress = list_task_issues(
        status="in-progress",
        state="open",
        repo=target_repo,
        token=auth_token,
    )
    reclaimed: List[dict] = []
    for item in in_progress:
        issue_number = int(item.get("number", 0))
        if not issue_number:
            continue
        updated_at = _parse_github_iso_timestamp(item.get("updated_at") or item.get("created_at"))
        if updated_at is None:
            continue
        age_hours = (now - updated_at).total_seconds() / 3600.0
        if age_hours < max_age_hours:
            continue

        head_branch = f"agent/issue-{issue_number}"
        pr_query = urllib.parse.urlencode(
            {"state": "open", "head": f"{owner}:{head_branch}", "base": "main"}
        )
        open_prs = github_request("GET", f"/pulls?{pr_query}", repo=target_repo, token=auth_token) or []
        current_labels = [lbl.get("name", "") for lbl in item.get("labels", [])]

        if open_prs:
            new_labels = _replace_status_label(current_labels, "agent:review")
            pr_url = open_prs[0].get("html_url", "")
            comment = (
                f"Detected open Pull Request ({pr_url}) on stale `agent:in-progress` issue "
                f"({age_hours:.1f}h old); transitioning to `agent:review`."
            )
        else:
            new_labels = _replace_status_label(current_labels, "agent:ready")
            comment = (
                f"Reclaimed stale `agent:in-progress` lease after {age_hours:.1f}h without an open PR; "
                "resetting status to `agent:ready` for retry."
            )

        updated = github_request(
            "PATCH",
            f"/issues/{issue_number}",
            payload={"labels": new_labels},
            repo=target_repo,
            token=auth_token,
        )
        github_request(
            "POST",
            f"/issues/{issue_number}/comments",
            payload={"body": comment},
            repo=target_repo,
            token=auth_token,
        )
        reclaimed.append(updated)

    return reclaimed


def update_task_issue(
    issue_number: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
    labels: Optional[List[str]] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Update title, body, or labels of an existing GitHub Issue."""
    payload: Dict[str, Any] = {}
    if title is not None:
        payload["title"] = title.strip()
    if body is not None:
        payload["body"] = body
    if labels is not None:
        payload["labels"] = labels
    if not payload:
        raise ValueError("At least one field (title, body, or labels) must be provided.")
    return github_request(
        "PATCH",
        f"/issues/{issue_number}",
        payload=payload,
        repo=repo,
        token=token,
    )


def _collect_git_diff_files(base_branch: str = "main", head_ref: str = "HEAD") -> List[Dict[str, Any]]:
    """Return changed files with added/deleted line counts against `origin/<base_branch>` when in a git checkout."""
    base_ref = _resolve_base_ref(base_branch=base_branch)
    proc = subprocess.run(
        ["git", "diff", "--numstat", f"{base_ref}...{head_ref}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    files: List[Dict[str, Any]] = []
    for raw_line in proc.stdout.splitlines():
        parts = raw_line.split("\t", 2)
        if len(parts) != 3:
            continue
        add_s, del_s, path = parts
        additions = int(add_s) if add_s.isdigit() else 0
        deletions = int(del_s) if del_s.isdigit() else 0
        files.append({"path": path.strip(), "additions": additions, "deletions": deletions})
    return files


def format_pr_body(
    issue_number: int,
    summary: str = "",
    changed_files: Optional[List[Dict[str, Any]]] = None,
    changes_summary: Optional[str] = None,
    examples: Optional[str] = None,
    screenshots: Optional[List[Dict[str, str]]] = None,
    verification: Optional[str] = None,
) -> str:
    """Format a rich GitHub Pull Request body with diff summary, examples, screenshots, and verification output."""
    summary_text = (summary or "").strip() or "Autonomous implementation verified via `scripts/verify_task.py`."
    lines: List[str] = [f"Closes #{issue_number}", "", "## Summary", summary_text, ""]

    if changes_summary and changes_summary.strip():
        lines.extend(["## Changes & Modified Files", changes_summary.strip(), ""])
    elif changed_files:
        lines.extend([
            "## Changes & Modified Files",
            "| File | Added | Removed |",
            "| --- | ---: | ---: |",
        ])
        for entry in changed_files:
            lines.append(f"| `{entry['path']}` | `+{entry.get('additions', 0)}` | `-{entry.get('deletions', 0)}` |")
        lines.append("")

    if examples and examples.strip():
        lines.extend(["## Examples & Behavior Walkthrough", examples.strip(), ""])

    if screenshots:
        lines.append("## Screenshots & Visual Preview")
        for idx, item in enumerate(screenshots, 1):
            if isinstance(item, dict):
                caption = str(item.get("caption") or f"Screenshot {idx}").strip()
                url = str(item.get("url") or "").strip()
            else:
                caption = f"Screenshot {idx}"
                url = str(item).strip()
            if url:
                lines.append(f"### {caption}")
                lines.append(f"![{caption}]({url})")
                lines.append("")

    if verification and verification.strip():
        lines.extend(["## Verification & Test Results", verification.strip(), ""])

    return "\n".join(lines).rstrip()


def update_pull_request(
    pr_number: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Update title or body of an existing GitHub Pull Request."""
    payload: Dict[str, Any] = {}
    if title is not None:
        payload["title"] = title.strip()
    if body is not None:
        payload["body"] = body
    if not payload:
        raise ValueError("At least one field (title or body) must be provided.")
    return github_request(
        "PATCH",
        f"/pulls/{pr_number}",
        payload=payload,
        repo=repo,
        token=token,
    )


def create_or_get_pull_request(
    issue_number: int,
    head_branch: str,
    base_branch: str = "main",
    title: Optional[str] = None,
    summary: str = "",
    examples: str = "",
    verification: str = "",
    screenshots: Optional[List[Dict[str, str]]] = None,
    changes_summary: Optional[str] = None,
    update_existing: bool = False,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a GitHub Pull Request for `head_branch` -> `base_branch` or return/update an existing open PR."""
    head_branch = validate_agent_branch(head_branch)
    if (base_branch or "").strip() != "main":
        raise ValueError(f"Task executor Pull Requests must target 'main' (got '{base_branch}').")
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()
    owner = target_repo.split("/")[0]

    changed_files = _collect_git_diff_files(base_branch=base_branch, head_ref=head_branch)
    pr_body = format_pr_body(
        issue_number=issue_number,
        summary=summary,
        changed_files=changed_files,
        changes_summary=changes_summary,
        examples=examples,
        screenshots=screenshots,
        verification=verification,
    )

    query = urllib.parse.urlencode(
        {"state": "open", "head": f"{owner}:{head_branch}", "base": base_branch}
    )
    existing = github_request("GET", f"/pulls?{query}", repo=target_repo, token=auth_token) or []
    if existing:
        existing_pr = existing[0]
        if update_existing:
            existing_pr = update_pull_request(
                int(existing_pr["number"]),
                title=title,
                body=pr_body,
                repo=target_repo,
                token=auth_token,
            )
        return {"deduplicated": True, "pull_request": existing_pr}

    pr_title = title
    if not pr_title:
        issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
        pr_title = f"{issue.get('title', f'Task #{issue_number}')} (#{issue_number})"

    created = github_request(
        "POST",
        "/pulls",
        payload={
            "title": pr_title,
            "head": head_branch,
            "base": base_branch,
            "body": pr_body,
        },
        repo=target_repo,
        token=auth_token,
    )
    return {"deduplicated": False, "pull_request": created}


def complete_task_issue(
    issue_number: int,
    summary: str = "",
    pr: Optional[str] = None,
    push: bool = False,
    open_pr: bool = False,
    base_branch: str = "main",
    close: bool = False,
    examples: str = "",
    verification: str = "",
    screenshots: Optional[List[Dict[str, str]]] = None,
    changes_summary: Optional[str] = None,
    update_pr: bool = False,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Transition an issue to `agent:review` (optionally pushing, opening/updating a PR, or closing) and post a comment."""
    head_branch: Optional[str] = None
    if push or open_pr or pr is not None:
        head_branch = validate_agent_branch(pr or f"agent/issue-{issue_number}")

    if push:
        push_task_branch(head_branch)

    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    current_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    new_labels = _replace_status_label(current_labels, "agent:review")

    patch_payload: Dict[str, Any] = {"labels": new_labels}
    if close:
        patch_payload["state"] = "closed"

    updated = github_request(
        "PATCH",
        f"/issues/{issue_number}",
        payload=patch_payload,
        repo=target_repo,
        token=auth_token,
    )

    pr_info: Optional[dict] = None
    if open_pr:
        assert head_branch is not None
        pr_res = create_or_get_pull_request(
            issue_number=issue_number,
            head_branch=head_branch,
            base_branch=base_branch,
            summary=summary,
            examples=examples,
            verification=verification,
            screenshots=screenshots,
            changes_summary=changes_summary,
            update_existing=update_pr,
            repo=target_repo,
            token=auth_token,
        )
        pr_info = pr_res["pull_request"]
        updated["pull_request"] = pr_info

    comment_parts = ["Verification passed and task implementation is ready for review."]
    if pr:
        comment_parts.append(f"Branch / PR: `{pr}`")
    if pr_info and pr_info.get("html_url"):
        comment_parts.append(f"Pull Request: {pr_info['html_url']}")
    if summary:
        comment_parts.append(f"\nSummary:\n{summary}")

    github_request(
        "POST",
        f"/issues/{issue_number}/comments",
        payload={"body": "\n".join(comment_parts)},
        repo=target_repo,
        token=auth_token,
    )
    return updated


def block_task_issue(
    issue_number: int,
    reason: str = "",
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Transition an issue to `agent:blocked` and post the failure/blocker reason."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    current_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    new_labels = _replace_status_label(current_labels, "agent:blocked")

    updated = github_request(
        "PATCH",
        f"/issues/{issue_number}",
        payload={"labels": new_labels},
        repo=target_repo,
        token=auth_token,
    )
    reason_text = reason.strip() or "Autonomous execution failed or requires human intervention."
    github_request(
        "POST",
        f"/issues/{issue_number}/comments",
        payload={"body": f"Blocked during autonomous execution (`agent:blocked`).\n\nReason:\n{reason_text}"},
        repo=target_repo,
        token=auth_token,
    )
    return updated


def _parse_screenshot_args(raw_items: Optional[List[str]]) -> List[Dict[str, str]]:
    """Parse repeatable `Caption=URL` or bare `URL` CLI arguments into screenshot dicts."""
    parsed: List[Dict[str, str]] = []
    for idx, raw in enumerate(raw_items or [], 1):
        val = (raw or "").strip()
        if not val:
            continue
        if "=" in val and not val.startswith(("http://", "https://")):
            caption, url = val.split("=", 1)
            parsed.append({"caption": caption.strip() or f"Preview {idx}", "url": url.strip()})
        else:
            parsed.append({"caption": f"Preview {idx}", "url": val})
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GitHub Issues-backed autonomous task backlog CLI")
    parser.add_argument("--repo", default=None, help="GitHub repo slug owner/name (defaults to git origin)")
    parser.add_argument("--cwd", default=None, help="Optional working directory (e.g. isolated git worktree path)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Enable GitHub Issues and sync standard agentic labels")

    create_p = subparsers.add_parser("create", help="Create a deduplicated agentic GitHub Issue")
    create_p.add_argument("--title", required=True)
    create_p.add_argument("--objective", required=True)
    create_p.add_argument("--context", default=None, help="Background motivation and user impact")
    create_p.add_argument("--examples", default=None, help="Concrete input/output or UI behavior examples")
    create_p.add_argument("--screenshot", action="append", default=[], help="Optional Caption=URL screenshot preview")
    create_p.add_argument("--owned-paths", nargs="+", required=True)
    create_p.add_argument("--forbidden-paths", nargs="*", default=None)
    create_p.add_argument("--acceptance", nargs="+", required=True)
    create_p.add_argument("--verify", nargs="+", required=True)
    create_p.add_argument("--priority", choices=["p1", "p2", "p3"], default="p2")
    create_p.add_argument(
        "--source",
        choices=["roadmap", "feature", "telemetry", "test-gap", "data-drift"],
        default="roadmap",
    )
    create_p.add_argument("--domain", nargs="*", default=[])
    create_p.add_argument("--status", choices=["proposed", "ready"], default="proposed")
    create_p.add_argument("--json", action="store_true")

    list_p = subparsers.add_parser("list", help="List backlog issues sorted by priority")
    list_p.add_argument(
        "--status",
        choices=["proposed", "ready", "in-progress", "review", "blocked", "all"],
        default="ready",
    )
    list_p.add_argument("--domain", default=None)
    list_p.add_argument("--source", default=None)
    list_p.add_argument("--state", choices=["open", "closed", "all"], default="open")
    list_p.add_argument("--json", action="store_true")

    get_p = subparsers.add_parser("get", help="Fetch an issue and parse its task spec")
    get_p.add_argument("issue_number", type=int)
    get_p.add_argument("--json", action="store_true")

    next_p = subparsers.add_parser("next", help="Fetch the highest-priority approved (agent:ready) task")
    next_p.add_argument("--domain", default=None)
    next_p.add_argument("--claim", action="store_true")
    next_p.add_argument("--agent", default="autonomous-executor")
    next_p.add_argument("--checkout", action="store_true")
    next_p.add_argument("--worktree", action="store_true", help="Create an isolated git worktree from origin/main")
    next_p.add_argument(
        "--reclaim-stale-hours",
        type=float,
        default=None,
        help="Reclaim stale agent:in-progress issues older than N hours before selecting the next task",
    )
    next_p.add_argument("--json", action="store_true")

    approve_p = subparsers.add_parser("approve", help="Approve a proposed issue (transition agent:proposed -> agent:ready)")
    approve_p.add_argument("issue_number", type=int)

    claim_p = subparsers.add_parser("claim", help="Claim an issue as agent:in-progress")
    claim_p.add_argument("issue_number", type=int)
    claim_p.add_argument("--agent", required=True)
    claim_p.add_argument("--branch", default=None)

    block_p = subparsers.add_parser("block", help="Mark an issue agent:blocked with a diagnostic reason")
    block_p.add_argument("issue_number", type=int)
    block_p.add_argument("--reason", required=True)
    block_p.add_argument("--cwd", dest="sub_cwd", default=None, help="Optional working directory")

    complete_p = subparsers.add_parser("complete", help="Mark an issue agent:review or close it")
    complete_p.add_argument("issue_number", type=int)
    complete_p.add_argument("--summary", default="")
    complete_p.add_argument("--examples", default="", help="Concrete input/output or behavior examples for the PR body")
    complete_p.add_argument("--verification", default="", help="Formatted verification & test output for the PR body")
    complete_p.add_argument("--screenshot", action="append", default=[], help="Optional Caption=URL screenshot for the PR body")
    complete_p.add_argument("--pr", default=None)
    complete_p.add_argument("--push", action="store_true", help="Safely push the validated agent/... branch to origin before completing")
    complete_p.add_argument("--open-pr", action="store_true", help="Open or reuse a GitHub Pull Request for the task branch")
    complete_p.add_argument("--update-pr", action="store_true", help="Update an existing open PR body with the latest summary/screenshots")
    complete_p.add_argument("--base", default="main", help="Base branch for the pull request")
    complete_p.add_argument("--close", action="store_true")
    complete_p.add_argument("--cwd", dest="sub_cwd", default=None, help="Optional working directory (e.g. git worktree)")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    target_cwd = getattr(args, "sub_cwd", None) or getattr(args, "cwd", None)
    if target_cwd:
        os.chdir(target_cwd)

    if args.command == "init":
        result = init_repo(repo=args.repo)
        print(
            f"Initialized {result['repo']} (has_issues={result['has_issues']}): "
            f"{result['labels_created']} labels created, {result['labels_updated']} updated "
            f"({result['total_standard_labels']} standard labels)."
        )
        return 0

    if args.command == "create":
        res = create_task_issue(
            title=args.title,
            objective=args.objective,
            owned_paths=args.owned_paths,
            forbidden_paths=args.forbidden_paths,
            acceptance_criteria=args.acceptance,
            verification_commands=args.verify,
            priority=args.priority,
            source=args.source,
            domains=args.domain,
            initial_status=args.status,
            context=args.context,
            examples=args.examples,
            screenshots=_parse_screenshot_args(args.screenshot) or None,
            repo=args.repo,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            issue = res["issue"]
            action = "Existing open issue matched" if res["deduplicated"] else "Created issue"
            print(f"{action}: #{issue['number']} {issue['title']} ({issue['html_url']})")
        return 0

    if args.command == "list":
        issues = list_task_issues(
            status=args.status,
            domain=args.domain,
            source=args.source,
            state=args.state,
            repo=args.repo,
        )
        if args.json:
            print(json.dumps(issues, indent=2))
        else:
            print(f"Found {len(issues)} issue(s):")
            for issue in issues:
                lbls = ", ".join(l.get("name", "") for l in issue.get("labels", []))
                print(f"  #{issue['number']} [{lbls}] {issue['title']}")
        return 0

    if args.command == "get":
        data = get_task_issue(args.issue_number, repo=args.repo)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"#{data['number']} {data['title']} ({data['state']}) - {data['html_url']}")
            print(f"Labels: {', '.join(data['labels'])}")
            if data["spec_error"]:
                print(f"Spec Error: {data['spec_error']}")
            else:
                print(json.dumps(data["spec"], indent=2))
        return 0

    if args.command == "next":
        task = get_next_ready_issue(
            domain=args.domain,
            reclaim_stale_hours=args.reclaim_stale_hours,
            repo=args.repo,
        )
        if task is None:
            if args.json:
                print("null")
            else:
                print("No approved (agent:ready) issues queued.")
            return 0
        if args.worktree:
            task["worktree_path"] = prepare_task_worktree(task["branch"])
        elif args.checkout:
            prepare_task_branch(task["branch"])
        if args.claim:
            claim_task_issue(
                int(task["number"]),
                agent_name=args.agent,
                branch=task["branch"],
                repo=args.repo,
            )
            task["labels"] = _replace_status_label(task["labels"], "agent:in-progress")
        if args.json:
            print(json.dumps(task, indent=2))
        else:
            print(f"Next ready task: #{task['number']} {task['title']} (branch: {task['branch']})")
            if task.get("worktree_path"):
                print(f"Isolated worktree prepared at: {task['worktree_path']}")
        return 0

    if args.command == "approve":
        updated = approve_task_issue(args.issue_number, repo=args.repo)
        print(f"Approved #{updated['number']} -> agent:ready ({updated['html_url']})")
        return 0

    if args.command == "claim":
        updated = claim_task_issue(
            args.issue_number,
            agent_name=args.agent,
            branch=args.branch,
            repo=args.repo,
        )
        print(f"Claimed #{updated['number']} -> agent:in-progress ({updated['html_url']})")
        return 0

    if args.command == "block":
        updated = block_task_issue(
            args.issue_number,
            reason=args.reason,
            repo=args.repo,
        )
        print(f"Blocked #{updated['number']} -> agent:blocked ({updated['html_url']})")
        return 0

    if args.command == "complete":
        updated = complete_task_issue(
            args.issue_number,
            summary=args.summary,
            pr=args.pr,
            push=args.push,
            open_pr=args.open_pr,
            base_branch=args.base,
            close=args.close,
            examples=args.examples,
            verification=args.verification,
            screenshots=_parse_screenshot_args(args.screenshot) or None,
            update_pr=args.update_pr,
            repo=args.repo,
        )
        state_str = "closed" if args.close else "agent:review"
        pr_url = (updated.get("pull_request") or {}).get("html_url")
        pr_suffix = f" | PR: {pr_url}" if pr_url else ""
        print(f"Completed #{updated['number']} -> {state_str} ({updated['html_url']}){pr_suffix}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
