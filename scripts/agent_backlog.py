#!/usr/bin/env python3
"""GitHub Issues-backed autonomous task queue CLI for College-Basketball-Stats."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterator, List, Optional, Tuple

DEFAULT_REPO = "bionicle4365/College-Basketball-Stats"
GITHUB_API_BASE = "https://api.github.com"

SPEC_BLOCK_PATTERN = re.compile(
    r"```json\s+agent-task-spec\s*\r?\n(.*?)\r?\n```",
    re.DOTALL,
)
AUTO_REVIEW_MARKER_RE = re.compile(
    r"<!--\s*auto-review:sha=([^\s>]+)(?:\s+verdict=([a-z-]+))?(?:\s+round=(\d+))?\s*-->"
)
AUTO_EXECUTOR_MARKER_RE = re.compile(r"<!--\s*auto-executor:[^\s>]+.*?-->")
MAX_AUTO_REVIEW_ROUNDS = 3

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
    "agent:changes-requested": (
        "E99695",
        "PR review requested changes; ready for autonomous rework",
    ),
    "agent:blocked": (
        "D93F0B",
        "Blocked by external dependency, failing check, or ambiguity",
    ),
}

REVIEW_LABELS: Dict[str, Tuple[str, str]] = {
    "review:approved": (
        "0E8A16",
        "Automated code review approved the latest PR commit",
    ),
    "review:changes-requested": (
        "D93F0B",
        "Automated or human code review requested changes",
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
    **REVIEW_LABELS,
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


def get_current_git_branch(cwd: Optional[str] = None) -> str:
    """Return the active local git branch name."""
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


def _get_canonical_repo_root(cwd: Optional[str] = None) -> str:
    """Return the primary repository root even when invoked from inside a git worktree."""
    common_proc = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if common_proc.returncode == 0 and common_proc.stdout.strip():
        common_dir = os.path.normpath(common_proc.stdout.strip())
        if os.path.basename(common_dir) == ".git":
            return os.path.dirname(common_dir)

    top_proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if top_proc.returncode == 0 and top_proc.stdout.strip():
        return os.path.normpath(top_proc.stdout.strip())
    return os.path.abspath(cwd or os.getcwd())


def _has_git_remote(remote_name: str = "origin", cwd: Optional[str] = None) -> bool:
    """Return True if the specified git remote is configured in the repository."""
    proc = subprocess.run(
        ["git", "remote", "get-url", remote_name],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0 and bool(proc.stdout.strip())


def _ref_exists(ref: str, cwd: Optional[str] = None) -> bool:
    """Return True if `ref` resolves to a valid git commit object."""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def _fetch_remote_branch(
    base_branch: str = "main",
    remote_name: str = "origin",
    cwd: Optional[str] = None,
) -> str:
    """Fetch `refs/heads/<base_branch>` from `remote_name` into `refs/remotes/<remote_name>/<base_branch>`."""
    remote_ref = f"{remote_name}/{base_branch}"
    refspec = f"+refs/heads/{base_branch}:refs/remotes/{remote_name}/{base_branch}"
    proc = subprocess.run(
        ["git", "fetch", remote_name, refspec],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or f"exit code {proc.returncode}"
        raise RuntimeError(f"Failed to fetch latest '{remote_ref}' from remote '{remote_name}': {detail}")
    if not _ref_exists(remote_ref, cwd=cwd):
        raise RuntimeError(f"Fetched '{remote_name}', but '{remote_ref}' could not be resolved.")
    return remote_ref


def _resolve_base_ref(
    base_branch: str = "main",
    require_fetch: bool = True,
    cwd: Optional[str] = None,
) -> str:
    """Fetch `origin/<base_branch>` when `origin` exists and return the latest base ref."""
    remote_ref = f"origin/{base_branch}"
    if _has_git_remote("origin", cwd=cwd):
        if require_fetch:
            return _fetch_remote_branch(base_branch=base_branch, remote_name="origin", cwd=cwd)
        try:
            return _fetch_remote_branch(base_branch=base_branch, remote_name="origin", cwd=cwd)
        except RuntimeError:
            if _ref_exists(remote_ref, cwd=cwd):
                return remote_ref

    for candidate in (remote_ref, base_branch):
        if _ref_exists(candidate, cwd=cwd):
            return candidate

    raise RuntimeError(
        f"Could not resolve base branch '{remote_ref}' or '{base_branch}'."
    )


def ensure_branch_based_on_latest(
    target_ref: str = "HEAD",
    base_branch: str = "main",
    fetch: bool = True,
    cwd: Optional[str] = None,
) -> str:
    """Verify `target_ref` includes every commit from the latest `origin/<base_branch>`."""
    resolved_base = _resolve_base_ref(base_branch=base_branch, require_fetch=fetch, cwd=cwd)
    probe = subprocess.run(
        ["git", "merge-base", "--is-ancestor", resolved_base, target_ref],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        active_label = target_ref
        if target_ref == "HEAD":
            try:
                active_label = get_current_git_branch(cwd=cwd)
            except subprocess.CalledProcessError:
                pass
        raise RuntimeError(
            f"Branch '{active_label}' is behind or not branched from the latest '{resolved_base}'. "
            f"Rebase onto '{resolved_base}' (e.g. 'git fetch origin {base_branch} && git rebase {resolved_base}') "
            "or recreate the worktree from latest main before continuing."
        )
    return resolved_base


def _verify_checked_out_base(wt_path: str, expected_branch: str, expected_base_ref: str) -> None:
    """Verify `wt_path` has `expected_branch` checked out at the exact commit of `expected_base_ref`."""
    active = get_current_git_branch(cwd=wt_path)
    if active != expected_branch:
        raise RuntimeError(
            f"Expected branch '{expected_branch}' in '{wt_path}', found '{active}'."
        )
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=wt_path,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    base_sha = subprocess.run(
        ["git", "rev-parse", f"{expected_base_ref}^{{commit}}"],
        cwd=wt_path,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    if head_sha != base_sha:
        raise RuntimeError(
            f"Branch '{expected_branch}' in '{wt_path}' ({head_sha}) does not match "
            f"'{expected_base_ref}' ({base_sha})."
        )


def push_task_branch(
    branch: Optional[str] = None,
    base_branch: str = "main",
    force_with_lease: bool = False,
) -> str:
    """Safely push a validated `agent/...` branch based on latest `main`, refusing while on `main`/`master`."""
    current = get_current_git_branch()
    if current in PROTECTED_BRANCHES:
        raise ValueError(f"Refusing to push while checked out on protected branch '{current}'.")
    target = validate_agent_branch(branch or current)
    if branch is not None and current != target:
        raise ValueError(
            f"Checked out branch '{current}' does not match requested push branch '{target}'."
        )
    ensure_branch_based_on_latest(target_ref=target, base_branch=base_branch, fetch=True)
    cmd = ["git", "push"]
    if force_with_lease:
        cmd.append("--force-with-lease")
    cmd.extend(["-u", "origin", f"{target}:{target}"])
    subprocess.run(cmd, check=True)
    return target


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
    resolved_base = _resolve_base_ref(base_branch=base_branch, require_fetch=True)
    subprocess.run(["git", "checkout", "-B", target, resolved_base], check=True)
    _verify_checked_out_base(".", target, resolved_base)
    return target


def _reset_and_add_worktree(
    root: str,
    wt_path: str,
    local_branch: str,
    start_ref: str,
) -> str:
    """Remove any stale worktree at `wt_path` and create a fresh worktree on `local_branch` at `start_ref`."""
    if os.path.exists(wt_path):
        subprocess.run(
            ["git", "worktree", "remove", "--force", wt_path],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    subprocess.run(["git", "worktree", "prune"], cwd=root, text=True, capture_output=True, check=False)
    os.makedirs(os.path.dirname(wt_path), exist_ok=True)
    subprocess.run(["git", "worktree", "add", "-B", local_branch, wt_path, start_ref], cwd=root, check=True)
    _verify_checked_out_base(wt_path, local_branch, start_ref)
    return wt_path.replace("\\", "/")


def prepare_task_worktree(
    branch: str,
    worktree_path: Optional[str] = None,
    base_branch: str = "main",
    repo_root: Optional[str] = None,
) -> str:
    """Create an isolated `scratch/worktrees/...` checkout on `branch` rooted at latest `origin/main`."""
    target = validate_agent_branch(branch)
    root = os.path.abspath(repo_root) if repo_root else _get_canonical_repo_root()
    wt_path = os.path.abspath(
        worktree_path or os.path.join(root, "scratch", "worktrees", target.replace("/", "-"))
    )
    resolved_base = _resolve_base_ref(base_branch=base_branch, require_fetch=True, cwd=root)
    return _reset_and_add_worktree(root, wt_path, target, resolved_base)


def prepare_pr_review_worktree(
    head_branch: str,
    worktree_path: Optional[str] = None,
    base_branch: str = "main",
    repo_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an isolated worktree checking out remote PR branch `origin/<head_branch>` and check freshness vs `origin/main`."""
    target = validate_agent_branch(head_branch)
    root = os.path.abspath(repo_root) if repo_root else _get_canonical_repo_root()
    resolved_base = _resolve_base_ref(base_branch=base_branch, require_fetch=True, cwd=root)
    remote_head = _fetch_remote_branch(base_branch=target, remote_name="origin", cwd=root)

    review_branch = f"agent/review-{target.replace('/', '-')}"
    wt_path = os.path.abspath(
        worktree_path or os.path.join(root, "scratch", "worktrees", review_branch.replace("/", "-"))
    )
    wt_posix = _reset_and_add_worktree(root, wt_path, review_branch, remote_head)

    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=wt_posix,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    ancestor_probe = subprocess.run(
        ["git", "merge-base", "--is-ancestor", resolved_base, "HEAD"],
        cwd=wt_posix,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "worktree_path": wt_posix,
        "branch": review_branch,
        "head_branch": target,
        "head_sha": head_sha,
        "base_ref": resolved_base,
        "behind_main": ancestor_probe.returncode != 0,
    }


def prepare_rework_worktree(
    head_branch: str,
    worktree_path: Optional[str] = None,
    base_branch: str = "main",
    repo_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an isolated worktree on `head_branch` from `origin/<head_branch>` and rebase onto latest `origin/main`."""
    target = validate_agent_branch(head_branch)
    root = os.path.abspath(repo_root) if repo_root else _get_canonical_repo_root()
    resolved_base = _resolve_base_ref(base_branch=base_branch, require_fetch=True, cwd=root)
    start_ref = (
        _fetch_remote_branch(base_branch=target, remote_name="origin", cwd=root)
        if _has_git_remote("origin", cwd=root)
        else target
    )
    wt_path = os.path.abspath(
        worktree_path or os.path.join(root, "scratch", "worktrees", target.replace("/", "-"))
    )
    wt_posix = _reset_and_add_worktree(root, wt_path, target, start_ref)

    rebased = False
    rebase_conflict = False
    ancestor_probe = subprocess.run(
        ["git", "merge-base", "--is-ancestor", resolved_base, "HEAD"],
        cwd=wt_posix,
        text=True,
        capture_output=True,
        check=False,
    )
    if ancestor_probe.returncode != 0:
        rebase_proc = subprocess.run(
            ["git", "rebase", resolved_base],
            cwd=wt_posix,
            text=True,
            capture_output=True,
            check=False,
        )
        if rebase_proc.returncode == 0:
            rebased = True
        else:
            subprocess.run(
                ["git", "rebase", "--abort"],
                cwd=wt_posix,
                text=True,
                capture_output=True,
                check=False,
            )
            rebase_conflict = True

    return {
        "worktree_path": wt_posix,
        "branch": target,
        "base_ref": resolved_base,
        "rebased": rebased,
        "rebase_conflict": rebase_conflict,
    }


def cleanup_task_worktree(
    worktree_path: str,
    delete_branch: Optional[str] = None,
    repo_root: Optional[str] = None,
) -> None:
    """Remove an isolated git worktree and optionally delete its temporary `agent/...` branch."""
    root = os.path.abspath(repo_root) if repo_root else _get_canonical_repo_root()
    wt_abs = os.path.abspath(worktree_path)
    if os.path.exists(wt_abs):
        subprocess.run(
            ["git", "worktree", "remove", "--force", wt_abs],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    subprocess.run(["git", "worktree", "prune"], cwd=root, text=True, capture_output=True, check=False)
    if delete_branch:
        target = validate_agent_branch(delete_branch)
        subprocess.run(
            ["git", "branch", "-D", target],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )


@contextmanager
def temporary_agent_worktree(
    branch: str,
    base_branch: str = "main",
    repo_root: Optional[str] = None,
) -> Iterator[str]:
    """Context manager yielding an isolated worktree on `branch` from latest `origin/main` and cleaning it up."""
    root = os.path.abspath(repo_root) if repo_root else _get_canonical_repo_root()
    wt_path = prepare_task_worktree(branch=branch, base_branch=base_branch, repo_root=root)
    try:
        yield wt_path
    finally:
        cleanup_task_worktree(wt_path, delete_branch=branch, repo_root=root)


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


def get_github_reviewer_token() -> str:
    """Retrieve `REVIEWER_GITHUB_TOKEN` when configured, falling back to `get_github_token()`."""
    token = os.environ.get("REVIEWER_GITHUB_TOKEN", "").strip()
    return token or get_github_token()


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


_EXPLICIT_REPO_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])((?:site_ui|scripts|tests|docs)/[A-Za-z0-9_./-]+|firestore\.rules)(?![A-Za-z0-9_./-])"
)

_SCREEN_KEYWORD_PATHS: List[Tuple[Tuple[str, ...], List[str]]] = [
    (("schedule",), ["site_ui/schedule/index.html"]),
    (("scoreboard", "box score", "boxscore", "in-game", "live score"), ["site_ui/scoreboard/index.html"]),
    (("roster",), ["site_ui/roster/index.html"]),
    (("standings", "bpi", "quad", "quadrant", "bracket", "resume", "sos"), ["site_ui/standings/index.html"]),
    (("group", "groups", "pick'em", "pickem", "leaderboard"), ["site_ui/group/index.html"]),
    (("setting", "settings", "dark mode", "theme"), ["site_ui/settings/index.html"]),
    (("login", "sign in", "signin", "auth"), ["site_ui/login/index.html"]),
    (("pwa", "service worker", "manifest", "offline", "sw.js"), ["site_ui/sw.js", "site_ui/manifest.json"]),
]

_SHARED_UI_AND_TEST_PATHS: List[str] = [
    "site_ui/helpers.js",
    "site_ui/styles.css",
    "docs/contracts/schemas_and_routes.json",
    "tests/test_helpers_and_contracts.py",
]


def infer_task_spec(
    title: str = "",
    body: str = "",
    labels: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Infer a complete, validated task specification for manually created GitHub Issues
    that omit an `agent-task-spec` block or Markdown `Owned Paths` section.
    """
    raw_body = body or ""
    raw_title = (title or "").strip()
    label_set = {str(lbl).strip().lower() for lbl in (labels or []) if str(lbl).strip()}

    owned_paths = _extract_markdown_section_items(raw_body, "Owned Paths")
    forbidden_paths = _extract_markdown_section_items(raw_body, "Forbidden Paths")
    acceptance_criteria = _extract_markdown_section_items(raw_body, "Acceptance Criteria")
    verification_commands = _extract_markdown_section_items(raw_body, "Verification Commands")

    combined_text = f"{raw_title}\n{raw_body}"
    combined_lower = combined_text.lower()

    if not owned_paths:
        inferred_owned: List[str] = []

        def _add_owned(path_str: str) -> None:
            cleaned = path_str.strip().rstrip(".,;:)`'\"").replace("\\", "/")
            if cleaned and cleaned not in inferred_owned:
                inferred_owned.append(cleaned)

        for match in _EXPLICIT_REPO_PATH_RE.finditer(combined_text):
            _add_owned(match.group(1))

        matched_ui = any(p.startswith("site_ui/") for p in inferred_owned)
        for keywords, target_paths in _SCREEN_KEYWORD_PATHS:
            if any(kw in combined_lower for kw in keywords):
                for tp in target_paths:
                    _add_owned(tp)
                matched_ui = True

        if "domain:pwa" in label_set:
            _add_owned("site_ui/sw.js")
            _add_owned("site_ui/manifest.json")
            matched_ui = True

        if "domain:groups-firestore" in label_set:
            _add_owned("site_ui/group/index.html")
            matched_ui = True

        if matched_ui or any(
            lbl in label_set for lbl in ("domain:site-ui", "domain:espn-api", "domain:analytics", "bug")
        ):
            for shared_path in _SHARED_UI_AND_TEST_PATHS:
                _add_owned(shared_path)

        if not inferred_owned:
            for default_path in ("site_ui/", "docs/contracts/schemas_and_routes.json", "tests/"):
                _add_owned(default_path)

        owned_paths = inferred_owned

    if not acceptance_criteria:
        checklist_items: List[str] = []
        for raw_line in raw_body.splitlines():
            m = re.match(r"^\s*[-*]\s+\[[ xX]\]\s+(.+)$", raw_line)
            if m and m.group(1).strip():
                checklist_items.append(m.group(1).strip())
        if checklist_items:
            acceptance_criteria = checklist_items
        else:
            summary_goal = raw_title or "Resolve the issue described in the ticket"
            acceptance_criteria = [
                f"Resolve issue: {summary_goal}",
                "Ensure all unit and contract tests pass (`python -m pytest -v`)",
            ]

    if not verification_commands:
        verification_commands = ["python -m pytest -v"]

    return validate_task_spec(
        {
            "owned_paths": owned_paths,
            "forbidden_paths": forbidden_paths or None,
            "acceptance_criteria": acceptance_criteria,
            "verification_commands": verification_commands,
            "objective": raw_title or None,
        }
    )


def append_task_spec_to_body(body: str, spec: Dict[str, Any]) -> str:
    """Append Markdown spec sections and an `agent-task-spec` JSON block to a manual issue body."""
    validated = validate_task_spec(spec)
    existing = (body or "").rstrip()
    if SPEC_BLOCK_PATTERN.search(existing):
        return existing

    spec_json = json.dumps(
        {
            "owned_paths": validated["owned_paths"],
            "forbidden_paths": validated["forbidden_paths"],
            "acceptance_criteria": validated["acceptance_criteria"],
            "verification_commands": validated["verification_commands"],
        },
        indent=2,
    )

    spec_block_lines = [
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
    ]
    suffix = "\n".join(spec_block_lines)
    return f"{existing}\n\n{suffix}" if existing else suffix


def resolve_or_infer_issue_spec(
    issue: dict,
    persist: bool = False,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool, str]:
    """
    Parse an issue's task spec or automatically infer one when missing.
    When `persist=True` and the issue lacks an embedded `agent-task-spec` block,
    PATCH the GitHub Issue body so the inferred spec is persisted on GitHub.
    """
    body = issue.get("body") or ""
    title = issue.get("title") or ""
    raw_labels = issue.get("labels") or []
    label_names = [
        (lbl.get("name", "") if isinstance(lbl, dict) else str(lbl))
        for lbl in raw_labels
    ]

    try:
        spec = parse_task_spec(body)
        return (spec, False, body)
    except Exception:
        spec = infer_task_spec(title=title, body=body, labels=label_names)

    updated_body = body
    if persist and not SPEC_BLOCK_PATTERN.search(body):
        issue_number = issue.get("number")
        updated_body = append_task_spec_to_body(body, spec)
        if issue_number is not None:
            try:
                github_request(
                    "PATCH",
                    f"/issues/{int(issue_number)}",
                    payload={"body": updated_body},
                    repo=repo,
                    token=token,
                )
            except Exception:
                pass
    return (spec, True, updated_body)


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
    persist_inferred_spec: bool = False,
) -> Dict[str, Any]:
    """Fetch a single issue and parse or infer its task specification."""
    issue = github_request("GET", f"/issues/{issue_number}", repo=repo, token=token)
    spec: Optional[Dict[str, Any]] = None
    spec_error: Optional[str] = None
    spec_inferred = False
    resolved_body = issue.get("body", "") or ""
    try:
        spec, spec_inferred, resolved_body = resolve_or_infer_issue_spec(
            issue,
            persist=persist_inferred_spec,
            repo=repo,
            token=token,
        )
    except Exception as exc:
        spec_error = str(exc)

    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "html_url": issue.get("html_url"),
        "labels": [lbl.get("name") for lbl in issue.get("labels", [])],
        "spec": spec,
        "spec_inferred": spec_inferred,
        "spec_error": spec_error,
        "body": resolved_body,
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
    """Approve a proposed issue by transitioning its status label to `agent:ready` and ensuring a task spec."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    current_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    new_labels = _replace_status_label(current_labels, "agent:ready")

    _, spec_inferred, updated_body = resolve_or_infer_issue_spec(
        issue,
        persist=False,
        repo=target_repo,
        token=auth_token,
    )
    patch_payload: Dict[str, Any] = {"labels": new_labels}
    if spec_inferred and updated_body != (issue.get("body") or ""):
        patch_payload["body"] = append_task_spec_to_body(issue.get("body") or "", infer_task_spec(
            title=issue.get("title") or "",
            body=issue.get("body") or "",
            labels=new_labels,
        ))

    updated = github_request(
        "PATCH",
        f"/issues/{issue_number}",
        payload=patch_payload,
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
    """Transition an approved `agent:ready` issue to `agent:in-progress`, persisting an inferred spec if missing."""
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

    spec, spec_inferred, _ = resolve_or_infer_issue_spec(
        issue,
        persist=False,
        repo=target_repo,
        token=auth_token,
    )
    patch_payload: Dict[str, Any] = {"labels": new_labels}
    raw_body = issue.get("body") or ""
    if spec_inferred and not SPEC_BLOCK_PATTERN.search(raw_body):
        patch_payload["body"] = append_task_spec_to_body(raw_body, spec)

    updated = github_request(
        "PATCH",
        f"/issues/{issue_number}",
        payload=patch_payload,
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
    include_rework: bool = False,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch the next task: PR rework first (if `include_rework`), otherwise highest-priority `agent:ready` issue."""
    if reclaim_stale_hours is not None and reclaim_stale_hours > 0:
        reclaim_stale_in_progress_issues(
            max_age_hours=reclaim_stale_hours,
            repo=repo,
            token=token,
        )
    if include_rework:
        rework_task = get_next_rework_pr(domain=domain, repo=repo, token=token)
        if rework_task is not None:
            return rework_task
    issues = list_task_issues(status="ready", domain=domain, state="open", repo=repo, token=token)
    if not issues:
        return None
    top_number = int(issues[0]["number"])
    task = get_task_issue(top_number, repo=repo, token=token, persist_inferred_spec=True)
    task["branch"] = f"agent/issue-{top_number}"
    task["mode"] = "new"
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
            pr_obj = open_prs[0]
            pr_labels = {lbl.get("name", "") for lbl in pr_obj.get("labels", [])}
            needs_changes = bool(
                {"agent:changes-requested", "review:changes-requested"} & pr_labels
            )
            target_status = "agent:changes-requested" if needs_changes else "agent:review"
            new_labels = _replace_status_label(current_labels, target_status)
            pr_url = pr_obj.get("html_url", "")
            comment = (
                f"Detected open Pull Request ({pr_url}) on stale `agent:in-progress` issue "
                f"({age_hours:.1f}h old); transitioning to `{target_status}`."
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
    try:
        base_ref = _resolve_base_ref(base_branch=base_branch, require_fetch=False)
    except RuntimeError:
        return []
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


def extract_issue_number_from_pr(pr: dict) -> Optional[int]:
    """Extract the linked GitHub Issue number from an `agent/issue-<N>` branch or PR body."""
    head_ref = str((pr.get("head") or {}).get("ref") or "").strip()
    branch_match = re.match(r"^agent/issue-(\d+)$", head_ref)
    if branch_match:
        return int(branch_match.group(1))
    body = str(pr.get("body") or "")
    body_match = re.search(r"(?:closes|fixes|resolves)\s+#(\d+)", body, re.IGNORECASE)
    if body_match:
        return int(body_match.group(1))
    return None


def _get_paginated_pulls(
    state: str = "open",
    base: str = "main",
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> List[dict]:
    """Fetch repository pull requests targeting `base` across pages."""
    pulls: List[dict] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {"state": state, "base": base, "per_page": 100, "page": page}
        )
        batch = github_request("GET", f"/pulls?{query}", repo=repo, token=token) or []
        if not batch:
            break
        pulls.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return pulls


def _format_auto_review_marker(head_sha: str, verdict: str, round_num: int) -> str:
    """Return an HTML comment marker tracking reviewed commit SHAs and review round counts."""
    return f"<!-- auto-review:sha={head_sha} verdict={verdict} round={round_num} -->"


def _is_automation_comment(body: str) -> bool:
    """Return True if a PR/issue comment was generated by the automated reviewer or executor."""
    text = (body or "").strip()
    if not text:
        return True
    if AUTO_REVIEW_MARKER_RE.search(text) or AUTO_EXECUTOR_MARKER_RE.search(text):
        return True
    if text.startswith((
        "Claimed by autonomous agent",
        "Verification passed and task implementation",
        "Approved for autonomous execution",
        "Blocked during autonomous execution",
        "Detected open Pull Request",
        "Reclaimed stale `agent:in-progress`",
    )):
        return True
    return False


def _sync_labels_removing_review_state(current_labels: List[str], target_status: Optional[str] = None) -> List[str]:
    """Strip `review:*` and `agent:changes-requested` labels and optionally set `target_status`."""
    cleaned = [
        lbl for lbl in current_labels
        if lbl not in REVIEW_LABELS and lbl != "agent:changes-requested"
    ]
    if target_status:
        return _replace_status_label(cleaned, target_status)
    return cleaned


def analyze_pr_review_state(
    pr: dict,
    reviews: List[dict],
    review_comments: List[dict],
    issue_comments: List[dict],
    latest_commit_at: Optional[datetime] = None,
    linked_issue: Optional[dict] = None,
) -> Dict[str, Any]:
    """Evaluate whether a PR needs automated review or rework based on reviews, labels, and comments."""
    head = pr.get("head") or {}
    head_sha = str(head.get("sha") or "").strip()
    pr_labels = [lbl.get("name", "") for lbl in pr.get("labels", [])]
    issue_labels = [lbl.get("name", "") for lbl in (linked_issue or {}).get("labels", [])]
    combined_labels = set(pr_labels) | set(issue_labels)
    is_blocked = "agent:blocked" in combined_labels

    reviewed_shas: List[str] = []
    max_round = 0
    auto_review_count = 0
    latest_executor_dt: Optional[datetime] = None

    for entry in [*reviews, *issue_comments]:
        body = str(entry.get("body") or "")
        for match in AUTO_REVIEW_MARKER_RE.finditer(body):
            sha_val = match.group(1)
            if sha_val and sha_val not in reviewed_shas:
                reviewed_shas.append(sha_val)
            auto_review_count += 1
            if match.group(3):
                max_round = max(max_round, int(match.group(3)))
        if AUTO_EXECUTOR_MARKER_RE.search(body):
            exec_dt = _parse_github_iso_timestamp(entry.get("created_at") or entry.get("submitted_at"))
            if exec_dt and (latest_executor_dt is None or exec_dt > latest_executor_dt):
                latest_executor_dt = exec_dt

    auto_review_rounds = max(max_round, auto_review_count)
    effective_commit_dt = latest_commit_at
    if latest_executor_dt and (effective_commit_dt is None or latest_executor_dt > effective_commit_dt):
        effective_commit_dt = latest_executor_dt

    rework_reasons: List[str] = []
    feedback_items: List[Dict[str, Any]] = []

    if not is_blocked:
        if "agent:changes-requested" in combined_labels or "review:changes-requested" in combined_labels:
            rework_reasons.append("PR or linked issue carries changes-requested label")

        # Track latest formal review state per reviewer login
        latest_formal_by_user: Dict[str, dict] = {}
        for rev in sorted(
            reviews,
            key=lambda r: str(r.get("submitted_at") or r.get("created_at") or ""),
        ):
            state = str(rev.get("state") or "").upper()
            if state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
                user_login = str((rev.get("user") or {}).get("login") or f"id:{rev.get('id')}")
                latest_formal_by_user[user_login] = rev

        for rev in latest_formal_by_user.values():
            if str(rev.get("state") or "").upper() == "CHANGES_REQUESTED":
                sub_dt = _parse_github_iso_timestamp(rev.get("submitted_at") or rev.get("created_at"))
                rev_sha = str(rev.get("commit_id") or "").strip()
                is_active = (
                    (sub_dt is not None and effective_commit_dt is not None and sub_dt >= effective_commit_dt)
                    or (head_sha and rev_sha == head_sha)
                )
                if is_active:
                    rework_reasons.append(
                        f"CHANGES_REQUESTED review by {(rev.get('user') or {}).get('login', 'reviewer')}"
                    )

        # Check human PR conversation or inline review comments posted after latest commit
        for c in review_comments:
            body = str(c.get("body") or "").strip()
            if not body or _is_automation_comment(body):
                continue
            created_dt = _parse_github_iso_timestamp(c.get("created_at"))
            if effective_commit_dt is not None and created_dt is not None and created_dt > effective_commit_dt:
                rework_reasons.append(
                    f"New inline review comment on {c.get('path', 'PR')} by {(c.get('user') or {}).get('login', 'reviewer')}"
                )

        for c in issue_comments:
            body = str(c.get("body") or "").strip()
            if not body or _is_automation_comment(body):
                continue
            created_dt = _parse_github_iso_timestamp(c.get("created_at"))
            if effective_commit_dt is not None and created_dt is not None and created_dt > effective_commit_dt:
                rework_reasons.append(
                    f"New PR comment by {(c.get('user') or {}).get('login', 'reviewer')}"
                )

        # Collect relevant feedback items whenever rework is needed
        if rework_reasons:
            for rev in reviews:
                body = str(rev.get("body") or "").strip()
                state = str(rev.get("state") or "").upper()
                if state == "CHANGES_REQUESTED" or "verdict=changes-requested" in body:
                    feedback_items.append({
                        "source": "review",
                        "author": (rev.get("user") or {}).get("login"),
                        "state": state,
                        "commit_id": rev.get("commit_id"),
                        "created_at": rev.get("submitted_at") or rev.get("created_at"),
                        "body": body,
                    })
            for c in review_comments:
                body = str(c.get("body") or "").strip()
                if not body:
                    continue
                feedback_items.append({
                    "source": "inline_comment",
                    "author": (c.get("user") or {}).get("login"),
                    "path": c.get("path"),
                    "line": c.get("line") or c.get("original_line"),
                    "created_at": c.get("created_at"),
                    "body": body,
                })
            for c in issue_comments:
                body = str(c.get("body") or "").strip()
                if not body or AUTO_EXECUTOR_MARKER_RE.search(body):
                    continue
                if AUTO_REVIEW_MARKER_RE.search(body) and "verdict=changes-requested" not in body:
                    continue
                feedback_items.append({
                    "source": "pr_comment",
                    "author": (c.get("user") or {}).get("login"),
                    "created_at": c.get("created_at"),
                    "body": body,
                })

    needs_rework = bool(rework_reasons) and not is_blocked
    needs_auto_review = (
        not is_blocked
        and not needs_rework
        and bool(head_sha)
        and head_sha not in reviewed_shas
    )

    return {
        "head_sha": head_sha,
        "reviewed_shas": reviewed_shas,
        "auto_review_rounds": auto_review_rounds,
        "is_blocked": is_blocked,
        "needs_rework": needs_rework,
        "needs_auto_review": needs_auto_review,
        "rework_reasons": rework_reasons,
        "feedback_items": feedback_items,
    }


def _fetch_pr_review_bundle(
    pr: dict,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch PR reviews, inline comments, PR comments, head commit timestamp, and linked issue."""
    pr_number = int(pr["number"])
    head = pr.get("head") or {}
    head_sha = str(head.get("sha") or "").strip()
    reviews = github_request("GET", f"/pulls/{pr_number}/reviews", repo=repo, token=token) or []
    review_comments = github_request("GET", f"/pulls/{pr_number}/comments", repo=repo, token=token) or []
    issue_comments = github_request("GET", f"/issues/{pr_number}/comments", repo=repo, token=token) or []

    latest_commit_at: Optional[datetime] = None
    if head_sha:
        try:
            commit_obj = github_request("GET", f"/commits/{head_sha}", repo=repo, token=token) or {}
            commit_inner = commit_obj.get("commit") or {}
            raw_date = (
                (commit_inner.get("committer") or {}).get("date")
                or (commit_inner.get("author") or {}).get("date")
            )
            latest_commit_at = _parse_github_iso_timestamp(raw_date)
        except Exception:
            latest_commit_at = None

    issue_number = extract_issue_number_from_pr(pr)
    linked_issue: Optional[dict] = None
    if issue_number is not None:
        try:
            linked_issue = github_request("GET", f"/issues/{issue_number}", repo=repo, token=token)
        except Exception:
            linked_issue = None

    analysis = analyze_pr_review_state(
        pr=pr,
        reviews=reviews,
        review_comments=review_comments,
        issue_comments=issue_comments,
        latest_commit_at=latest_commit_at,
        linked_issue=linked_issue,
    )
    return {
        "pr": pr,
        "pr_number": pr_number,
        "issue_number": issue_number,
        "linked_issue": linked_issue,
        "analysis": analysis,
    }


def list_prs_to_review(
    repo: Optional[str] = None,
    max_rounds: int = MAX_AUTO_REVIEW_ROUNDS,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return open `agent/...` Pull Requests targeting `main` whose latest commit awaits review."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_reviewer_token()
    pulls = _get_paginated_pulls(state="open", base="main", repo=target_repo, token=auth_token)
    queue: List[Dict[str, Any]] = []

    for pr in pulls:
        head_ref = str((pr.get("head") or {}).get("ref") or "").strip()
        if not head_ref.startswith("agent/"):
            continue
        bundle = _fetch_pr_review_bundle(pr, repo=target_repo, token=auth_token)
        analysis = bundle["analysis"]
        if not analysis["needs_auto_review"]:
            continue

        issue_number = bundle["issue_number"]
        spec: Optional[Dict[str, Any]] = None
        spec_error: Optional[str] = None
        if bundle["linked_issue"]:
            try:
                spec, _, _ = resolve_or_infer_issue_spec(bundle["linked_issue"], persist=False, repo=target_repo, token=auth_token)
            except Exception as exc:
                spec_error = str(exc)

        queue.append({
            "pr_number": bundle["pr_number"],
            "title": pr.get("title"),
            "html_url": pr.get("html_url"),
            "head_branch": head_ref,
            "head_sha": analysis["head_sha"],
            "base_branch": str((pr.get("base") or {}).get("ref") or "main"),
            "issue_number": issue_number,
            "spec": spec,
            "spec_error": spec_error,
            "auto_review_rounds": analysis["auto_review_rounds"],
            "max_rounds_reached": analysis["auto_review_rounds"] >= max_rounds,
        })

    return queue


def _update_issue_or_pr_labels(
    number: int,
    new_labels: List[str],
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Update labels on a GitHub Issue or Pull Request."""
    return github_request(
        "PATCH",
        f"/issues/{number}",
        payload={"labels": new_labels},
        repo=repo,
        token=token,
    )


def submit_pr_review(
    pr_number: int,
    decision: str,
    summary: str,
    comments: Optional[List[Dict[str, Any]]] = None,
    max_rounds: int = MAX_AUTO_REVIEW_ROUNDS,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Submit a PR review (`approve`, `request-changes`, or `comment`) and sync PR/Issue labels."""
    normalized_decision = decision.strip().lower()
    if normalized_decision not in ("approve", "request-changes", "comment"):
        raise ValueError(f"Unsupported review decision '{decision}'. Use 'approve', 'request-changes', or 'comment'.")

    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_reviewer_token()
    pr = github_request("GET", f"/pulls/{pr_number}", repo=target_repo, token=auth_token)
    bundle = _fetch_pr_review_bundle(pr, repo=target_repo, token=auth_token)
    analysis = bundle["analysis"]
    head_sha = analysis["head_sha"]
    issue_number = bundle["issue_number"]
    next_round = analysis["auto_review_rounds"] + 1

    if normalized_decision == "request-changes" and next_round > max_rounds:
        reason = (
            f"PR #{pr_number} reached {analysis['auto_review_rounds']} automated review rounds "
            f"(limit={max_rounds}) and still requires changes:\n\n{summary.strip()}"
        )
        if issue_number is not None:
            block_task_issue(issue_number, reason=reason, repo=target_repo, token=auth_token)
        pr_labels = [lbl.get("name", "") for lbl in pr.get("labels", [])]
        updated_pr_labels = _sync_labels_removing_review_state(pr_labels, target_status="agent:blocked")
        _update_issue_or_pr_labels(pr_number, updated_pr_labels, repo=target_repo, token=auth_token)
        github_request(
            "POST",
            f"/issues/{pr_number}/comments",
            payload={
                "body": (
                    f"{_format_auto_review_marker(head_sha, 'blocked', next_round)}\n"
                    f"## Automated Review Halted (`agent:blocked`)\n\n{reason}"
                )
            },
            repo=target_repo,
            token=auth_token,
        )
        return {
            "pr_number": pr_number,
            "issue_number": issue_number,
            "decision": "blocked",
            "round": next_round,
            "blocked": True,
        }

    marker = _format_auto_review_marker(head_sha, normalized_decision, next_round)
    heading_map = {
        "approve": "## Automated Code Review: Approved",
        "request-changes": "## Automated Code Review: Changes Requested",
        "comment": "## Automated Code Review: Comment",
    }
    review_body = f"{marker}\n{heading_map[normalized_decision]}\n\n{summary.strip()}"
    event_map = {
        "approve": "APPROVE",
        "request-changes": "REQUEST_CHANGES",
        "comment": "COMMENT",
    }

    inline_comments: List[Dict[str, Any]] = []
    for item in comments or []:
        path = str(item.get("path") or "").strip()
        body_txt = str(item.get("body") or "").strip()
        line_val = item.get("line")
        if path and body_txt and line_val is not None:
            inline_comments.append({
                "path": path,
                "line": int(line_val),
                "side": "RIGHT",
                "body": body_txt,
            })

    def _post_review(event_name: str, body_text: str, c_list: List[Dict[str, Any]]) -> dict:
        payload: Dict[str, Any] = {
            "commit_id": head_sha,
            "body": body_text,
            "event": event_name,
        }
        if c_list:
            payload["comments"] = c_list
        return github_request(
            "POST",
            f"/pulls/{pr_number}/reviews",
            payload=payload,
            repo=target_repo,
            token=auth_token,
        )

    fallback_used = False
    try:
        review_resp = _post_review(event_map[normalized_decision], review_body, inline_comments)
    except RuntimeError as exc:
        if "HTTP 422" not in str(exc):
            raise
        fallback_used = True
        try:
            review_resp = _post_review("COMMENT", review_body, inline_comments)
        except RuntimeError as exc2:
            if "HTTP 422" not in str(exc2) or not inline_comments:
                raise
            notes = "\n".join(
                f"- `{c['path']}` (line {c['line']}): {c['body']}"
                for c in inline_comments
            )
            review_resp = _post_review("COMMENT", f"{review_body}\n\n### File Comments\n{notes}", [])

    pr_labels = [lbl.get("name", "") for lbl in pr.get("labels", [])]
    if normalized_decision == "approve":
        new_pr_labels = _sync_labels_removing_review_state(pr_labels, target_status="agent:review")
        new_pr_labels.append("review:approved")
    elif normalized_decision == "request-changes":
        new_pr_labels = _sync_labels_removing_review_state(pr_labels, target_status="agent:changes-requested")
        new_pr_labels.append("review:changes-requested")
    else:
        new_pr_labels = pr_labels

    if normalized_decision in ("approve", "request-changes"):
        _update_issue_or_pr_labels(pr_number, new_pr_labels, repo=target_repo, token=auth_token)
        if issue_number is not None and bundle["linked_issue"] is not None:
            issue_labels = [lbl.get("name", "") for lbl in bundle["linked_issue"].get("labels", [])]
            if "agent:blocked" not in issue_labels:
                target_issue_status = (
                    "agent:changes-requested" if normalized_decision == "request-changes" else "agent:review"
                )
                updated_issue_labels = _sync_labels_removing_review_state(
                    issue_labels, target_status=target_issue_status
                )
                _update_issue_or_pr_labels(
                    issue_number, updated_issue_labels, repo=target_repo, token=auth_token
                )

    return {
        "pr_number": pr_number,
        "issue_number": issue_number,
        "head_sha": head_sha,
        "decision": normalized_decision,
        "round": next_round,
        "fallback_comment_review": fallback_used,
        "review_url": (review_resp or {}).get("html_url"),
        "blocked": False,
    }


def get_next_rework_pr(
    domain: Optional[str] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return the highest-priority open `agent/...` PR needing rework from human or automated review."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()
    pulls = _get_paginated_pulls(state="open", base="main", repo=target_repo, token=auth_token)
    domain_label = (
        domain if (not domain or domain.startswith("domain:")) else f"domain:{domain}"
    )

    candidates: List[Tuple[Tuple[int, int], Dict[str, Any]]] = []
    for pr in pulls:
        head_ref = str((pr.get("head") or {}).get("ref") or "").strip()
        if not head_ref.startswith("agent/"):
            continue
        bundle = _fetch_pr_review_bundle(pr, repo=target_repo, token=auth_token)
        if not bundle["analysis"]["needs_rework"]:
            continue

        linked_issue = bundle["linked_issue"]
        if domain_label and linked_issue:
            issue_lbls = {l.get("name", "") for l in linked_issue.get("labels", [])}
            if domain_label not in issue_lbls:
                continue

        issue_number = bundle["issue_number"]
        if issue_number is not None:
            task = get_task_issue(issue_number, repo=target_repo, token=auth_token)
        else:
            task = {
                "number": bundle["pr_number"],
                "title": pr.get("title"),
                "state": pr.get("state"),
                "html_url": pr.get("html_url"),
                "labels": [l.get("name", "") for l in pr.get("labels", [])],
                "spec": None,
                "spec_error": "No linked issue found for PR.",
                "body": pr.get("body", ""),
            }

        rank = _issue_priority_rank(linked_issue) if linked_issue else (99, bundle["pr_number"])
        task["mode"] = "rework"
        task["branch"] = head_ref
        task["pr_number"] = bundle["pr_number"]
        task["pr_url"] = pr.get("html_url")
        task["head_sha"] = bundle["analysis"]["head_sha"]
        task["auto_review_rounds"] = bundle["analysis"]["auto_review_rounds"]
        task["rework_reasons"] = bundle["analysis"]["rework_reasons"]
        task["review_feedback"] = bundle["analysis"]["feedback_items"]
        candidates.append((rank, task))

    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


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
    force_with_lease: bool = False,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Transition an issue to `agent:review` (optionally pushing, opening/updating a PR, or closing) and post a comment."""
    head_branch: Optional[str] = None
    if push or open_pr or pr is not None:
        head_branch = validate_agent_branch(pr or f"agent/issue-{issue_number}")

    if push:
        push_task_branch(
            head_branch,
            base_branch=base_branch,
            force_with_lease=force_with_lease,
        )

    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    current_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    new_labels = _sync_labels_removing_review_state(current_labels, target_status="agent:review")

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
        pr_num = int(pr_info["number"])
        pr_labels = [lbl.get("name", "") for lbl in pr_info.get("labels", [])]
        cleaned_pr_labels = _sync_labels_removing_review_state(pr_labels, target_status="agent:review")
        if set(cleaned_pr_labels) != set(pr_labels):
            _update_issue_or_pr_labels(pr_num, cleaned_pr_labels, repo=target_repo, token=auth_token)
        if pr_res.get("deduplicated"):
            pr_head_sha = str((pr_info.get("head") or {}).get("sha") or "").strip()
            note = summary.strip() or "Pushed updated changes and verification results."
            github_request(
                "POST",
                f"/issues/{pr_num}/comments",
                payload={
                    "body": (
                        f"<!-- auto-executor:complete sha={pr_head_sha} -->\n"
                        f"Pushed updated changes and verification results.\n\n{note}"
                    )
                },
                repo=target_repo,
                token=auth_token,
            )

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
        choices=["proposed", "ready", "in-progress", "review", "changes-requested", "blocked", "all"],
        default="ready",
    )
    list_p.add_argument("--domain", default=None)
    list_p.add_argument("--source", default=None)
    list_p.add_argument("--state", choices=["open", "closed", "all"], default="open")
    list_p.add_argument("--json", action="store_true")

    get_p = subparsers.add_parser("get", help="Fetch an issue and parse or infer its task spec")
    get_p.add_argument("issue_number", type=int)
    get_p.add_argument("--persist-spec", action="store_true", help="Persist inferred task spec onto the GitHub issue body if missing")
    get_p.add_argument("--json", action="store_true")

    next_p = subparsers.add_parser("next", help="Fetch the highest-priority rework PR or approved (agent:ready) task")
    next_p.add_argument("--domain", default=None)
    next_p.add_argument("--claim", action="store_true")
    next_p.add_argument("--agent", default="autonomous-executor")
    next_p.add_argument("--checkout", action="store_true")
    next_p.add_argument("--worktree", action="store_true", help="Create an isolated git worktree from origin/main (or rework PR branch)")
    next_p.add_argument(
        "--include-rework",
        action="store_true",
        help="Prioritize open PRs with requested changes (human or automated) before new agent:ready issues",
    )
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
    complete_p.add_argument("--force-with-lease", action="store_true", help="Use --force-with-lease when pushing a rebased agent/... rework branch")
    complete_p.add_argument("--base", default="main", help="Base branch for the pull request")
    complete_p.add_argument("--close", action="store_true")
    complete_p.add_argument("--cwd", dest="sub_cwd", default=None, help="Optional working directory (e.g. git worktree)")

    rq_p = subparsers.add_parser("review-queue", help="List open agent/... PRs whose latest commit awaits automated review")
    rq_p.add_argument("--max-rounds", type=int, default=MAX_AUTO_REVIEW_ROUNDS)
    rq_p.add_argument("--json", action="store_true")

    pr_wt_p = subparsers.add_parser("pr-worktree", help="Create an isolated git worktree for reviewing a Pull Request branch")
    pr_wt_p.add_argument("pr_number", type=int)
    pr_wt_p.add_argument("--base", default="main", help="Base branch to compare against (default: main)")
    pr_wt_p.add_argument("--path", default=None, help="Optional worktree directory path")
    pr_wt_p.add_argument("--json", action="store_true")

    sr_p = subparsers.add_parser("submit-review", help="Submit an automated code review on a GitHub Pull Request")
    sr_p.add_argument("pr_number", type=int)
    sr_p.add_argument("--decision", choices=["approve", "request-changes", "comment"], required=True)
    sr_p.add_argument("--summary", required=True)
    sr_p.add_argument("--comment", action="append", default=[], help="Inline review comment formatted as path:line:message")
    sr_p.add_argument("--comments-json", default=None, help="Optional path to JSON list of {path, line, body} comments")
    sr_p.add_argument("--max-rounds", type=int, default=MAX_AUTO_REVIEW_ROUNDS)
    sr_p.add_argument("--json", action="store_true")

    wt_p = subparsers.add_parser("worktree", help="Create an isolated git worktree on an agent/... branch from latest origin/main")
    wt_p.add_argument("--branch", required=True, help="Target agent/... branch name")
    wt_p.add_argument("--base", default="main", help="Base branch to fetch and branch from (default: main)")
    wt_p.add_argument("--path", default=None, help="Optional worktree directory path")
    wt_p.add_argument("--json", action="store_true")

    clean_wt_p = subparsers.add_parser("cleanup-worktree", help="Remove an isolated git worktree and optionally delete its temporary branch")
    clean_wt_p.add_argument("--path", required=True, help="Path to the worktree directory to remove")
    clean_wt_p.add_argument("--delete-branch", default=None, help="Optional agent/... branch name to delete after removal")

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
        data = get_task_issue(args.issue_number, repo=args.repo, persist_inferred_spec=args.persist_spec)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"#{data['number']} {data['title']} ({data['state']}) - {data['html_url']}")
            print(f"Labels: {', '.join(data['labels'])}")
            if data.get("spec_inferred"):
                print("Spec Source: Inferred from issue title/body/labels")
            if data["spec_error"]:
                print(f"Spec Error: {data['spec_error']}")
            else:
                print(json.dumps(data["spec"], indent=2))
        return 0

    if args.command == "next":
        task = get_next_ready_issue(
            domain=args.domain,
            reclaim_stale_hours=args.reclaim_stale_hours,
            include_rework=args.include_rework,
            repo=args.repo,
        )
        if task is None:
            if args.json:
                print("null")
            else:
                print("No approved (agent:ready) or rework tasks queued.")
            return 0
        is_rework = task.get("mode") == "rework"
        if args.worktree:
            if is_rework:
                wt_info = prepare_rework_worktree(task["branch"])
                task["worktree_path"] = wt_info["worktree_path"]
                task["rebased"] = wt_info["rebased"]
                task["rebase_conflict"] = wt_info["rebase_conflict"]
            else:
                task["worktree_path"] = prepare_task_worktree(task["branch"])
        elif args.checkout and not is_rework:
            prepare_task_branch(task["branch"])
        if args.claim and task.get("spec_error") != "No linked issue found for PR.":
            claim_task_issue(
                int(task["number"]),
                agent_name=args.agent,
                branch=task["branch"],
                force=is_rework,
                repo=args.repo,
            )
            task["labels"] = _replace_status_label(task["labels"], "agent:in-progress")
        if args.json:
            print(json.dumps(task, indent=2))
        else:
            label = "Next rework PR" if is_rework else "Next ready task"
            print(f"{label}: #{task['number']} {task['title']} (branch: {task['branch']})")
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
            force_with_lease=args.force_with_lease,
            repo=args.repo,
        )
        state_str = "closed" if args.close else "agent:review"
        pr_url = (updated.get("pull_request") or {}).get("html_url")
        pr_suffix = f" | PR: {pr_url}" if pr_url else ""
        print(f"Completed #{updated['number']} -> {state_str} ({updated['html_url']}){pr_suffix}")
        return 0

    if args.command == "review-queue":
        queue = list_prs_to_review(repo=args.repo, max_rounds=args.max_rounds)
        if args.json:
            print(json.dumps(queue, indent=2))
        else:
            print(f"Found {len(queue)} PR(s) awaiting code review:")
            for item in queue:
                print(f"  PR #{item['pr_number']} [{item['head_branch']}] {item['title']} ({item['html_url']})")
        return 0

    if args.command == "pr-worktree":
        pr_obj = github_request("GET", f"/pulls/{args.pr_number}", repo=args.repo, token=get_github_reviewer_token())
        head_branch = str((pr_obj.get("head") or {}).get("ref") or "").strip()
        wt_info = prepare_pr_review_worktree(
            head_branch=head_branch,
            worktree_path=args.path,
            base_branch=args.base,
        )
        wt_info["pr_number"] = args.pr_number
        wt_info["issue_number"] = extract_issue_number_from_pr(pr_obj)
        if args.json:
            print(json.dumps(wt_info, indent=2))
        else:
            print(
                f"Prepared review worktree for PR #{args.pr_number} ({head_branch}) at {wt_info['worktree_path']} "
                f"(behind_main={wt_info['behind_main']})"
            )
        return 0

    if args.command == "submit-review":
        parsed_comments: List[Dict[str, Any]] = []
        if args.comments_json:
            with open(args.comments_json, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    parsed_comments.extend(loaded)
        for raw in args.comment:
            parts = raw.split(":", 2)
            if len(parts) != 3 or not parts[1].strip().isdigit():
                raise ValueError(f"Expected --comment as 'path:line:message', got '{raw}'.")
            parsed_comments.append({
                "path": parts[0].strip(),
                "line": int(parts[1].strip()),
                "body": parts[2].strip(),
            })
        res = submit_pr_review(
            pr_number=args.pr_number,
            decision=args.decision,
            summary=args.summary,
            comments=parsed_comments or None,
            max_rounds=args.max_rounds,
            repo=args.repo,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(
                f"Submitted {res['decision']} review on PR #{res['pr_number']} "
                f"(round {res['round']}, blocked={res['blocked']})"
            )
        return 0

    if args.command == "worktree":
        wt_path = prepare_task_worktree(
            branch=args.branch,
            worktree_path=args.path,
            base_branch=args.base,
        )
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=wt_path,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        payload = {
            "branch": validate_agent_branch(args.branch),
            "base_branch": args.base,
            "head_sha": head_sha,
            "worktree_path": wt_path,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Prepared isolated worktree on '{payload['branch']}' at {wt_path} (HEAD={head_sha[:7]})")
        return 0

    if args.command == "cleanup-worktree":
        cleanup_task_worktree(worktree_path=args.path, delete_branch=args.delete_branch)
        print(f"Removed worktree: {args.path}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
