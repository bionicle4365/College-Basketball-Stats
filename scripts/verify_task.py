#!/usr/bin/env python3
"""Deterministic verification runner for autonomous tasks and Verifier agents."""

from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
from typing import List, Optional, Sequence, Tuple

try:
    from scripts import agent_backlog
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import agent_backlog  # type: ignore[no-redef]


def _normalize_path(path: str) -> str:
    """Normalize path separators and strip leading './'."""
    norm = path.strip().strip('"').replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    return norm


def _matches_pattern(file_path: str, pattern: str) -> bool:
    """Return True if `file_path` matches a file path, directory prefix, or glob `pattern`."""
    norm_file = _normalize_path(file_path)
    norm_pat = _normalize_path(pattern)
    if not norm_pat:
        return False
    if norm_pat.endswith("/"):
        return norm_file.startswith(norm_pat)
    if norm_file == norm_pat or norm_file.startswith(f"{norm_pat}/"):
        return True
    return fnmatch.fnmatch(norm_file, norm_pat)


def get_current_branch() -> str:
    """Return the active local git branch name."""
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.stdout.strip()


def check_branch_safety(branch: str) -> Tuple[bool, str]:
    """Ensure verification runs on an isolated `agent/...` branch rather than `main`/`master`."""
    cleaned = (branch or "").strip()
    if cleaned in ("main", "master") or not cleaned.startswith("agent/"):
        return (
            False,
            f"Protected or non-agent branch '{cleaned}' is active. Task executors must work on an "
            "'agent/...' branch and never modify 'main' directly.",
        )
    return (True, "")


def check_base_branch_freshness(
    base_branch: str = "main",
    explicit_base: Optional[str] = None,
    fetch: bool = True,
    cwd: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """Verify `HEAD` includes every commit from the latest `origin/<base_branch>` (or `explicit_base`)."""
    if explicit_base:
        base_commit_ref = explicit_base.split("...", 1)[0].split("..", 1)[0].strip()
        diff_ref = explicit_base if ("..." in explicit_base or ".." in explicit_base) else f"{base_commit_ref}...HEAD"
        if base_commit_ref and agent_backlog._ref_exists(base_commit_ref, cwd=cwd):
            probe = subprocess.run(
                ["git", "merge-base", "--is-ancestor", base_commit_ref, "HEAD"],
                cwd=cwd,
                text=True,
                capture_output=True,
                check=False,
            )
            if probe.returncode != 0:
                return (
                    False,
                    f"Active branch is behind or not branched from '{base_commit_ref}'. "
                    f"Rebase onto '{base_commit_ref}' before completing verification.",
                    None,
                )
        return (True, f"HEAD includes '{base_commit_ref}'", diff_ref)

    has_origin = agent_backlog._has_git_remote("origin", cwd=cwd)
    try:
        resolved_base = agent_backlog._resolve_base_ref(
            base_branch=base_branch,
            require_fetch=fetch and has_origin,
            cwd=cwd,
        )
    except RuntimeError as exc:
        if has_origin:
            return (False, str(exc), None)
        return (True, "No 'origin' remote or 'main' branch in local-only repo", None)

    probe = subprocess.run(
        ["git", "merge-base", "--is-ancestor", resolved_base, "HEAD"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        return (
            False,
            f"Active branch is behind or not branched from latest '{resolved_base}'. "
            f"Run 'git fetch origin {base_branch} && git rebase {resolved_base}' or recreate the worktree from latest '{base_branch}'.",
            None,
        )
    return (True, f"HEAD includes latest '{resolved_base}'", f"{resolved_base}...HEAD")


def resolve_default_base_ref() -> Optional[str]:
    """Return `origin/main...HEAD` (or `main...HEAD`) when available for committed-branch diffs."""
    for candidate in ("origin/main", "main"):
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", candidate],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            return f"{candidate}...HEAD"
    return None


def get_modified_files(base_ref: Optional[str] = None) -> List[str]:
    """Return modified and untracked repository files, ignoring .git/ and scratch/."""
    files: List[str] = []
    seen = set()

    def _add(raw_path: str) -> None:
        norm = _normalize_path(raw_path)
        if not norm or norm.startswith(".git/") or norm == ".git" or norm.startswith("scratch/"):
            return
        if norm not in seen:
            seen.add(norm)
            files.append(norm)

    status_proc = subprocess.run(
        ["git", "status", "--porcelain"],
        text=True,
        capture_output=True,
        check=False,
    )
    if status_proc.returncode == 0:
        for line in status_proc.stdout.splitlines():
            if len(line) < 4:
                continue
            path_part = line[3:]
            if " -> " in path_part:
                path_part = path_part.split(" -> ", 1)[1]
            _add(path_part)

    if base_ref:
        diff_proc = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            text=True,
            capture_output=True,
            check=False,
        )
        if diff_proc.returncode == 0:
            for line in diff_proc.stdout.splitlines():
                _add(line)

    return files


def check_path_boundaries(
    modified_files: Sequence[str],
    owned_paths: Sequence[str],
    forbidden_paths: Sequence[str],
) -> Tuple[bool, List[str]]:
    """
    Validate that all `modified_files` stay within `owned_paths` (if specified)
    and do not touch any path in `forbidden_paths`.
    """
    violations: List[str] = []
    owned_clean = [p for p in owned_paths if _normalize_path(p)]
    forbidden_clean = [p for p in forbidden_paths if _normalize_path(p)]

    for raw_file in modified_files:
        norm_file = _normalize_path(raw_file)
        if not norm_file or norm_file.startswith(".git/") or norm_file.startswith("scratch/"):
            continue

        if any(_matches_pattern(norm_file, pat) for pat in forbidden_clean):
            violations.append(f"Forbidden path modified: {norm_file}")
            continue

        if owned_clean and not any(_matches_pattern(norm_file, pat) for pat in owned_clean):
            violations.append(f"Out-of-scope file modified (not in owned_paths): {norm_file}")

    return len(violations) == 0, violations


def infer_domain_checks(modified_files: Sequence[str]) -> List[str]:
    """Infer deterministic verification commands from the modified file paths."""
    norm_files = [_normalize_path(f) for f in modified_files]
    if not norm_files:
        return []
    return ["python -m pytest"]


def run_verification_commands(commands: Sequence[str]) -> List[Tuple[str, int]]:
    """Run verification commands sequentially and return `(command, exit_code)` results."""
    results: List[Tuple[str, int]] = []
    seen = set()
    for raw_cmd in commands:
        cmd = raw_cmd.strip()
        if not cmd or cmd in seen:
            continue
        seen.add(cmd)
        print(f"\n>>> Running verification: {cmd}")
        proc = subprocess.run(cmd, shell=True, check=False)
        results.append((cmd, proc.returncode))
        if proc.returncode != 0:
            print(f"!!! FAILED (exit {proc.returncode}): {cmd}")
        else:
            print(f"+++ PASSED: {cmd}")
    return results


def verify_task(
    issue_number: Optional[int] = None,
    base_ref: Optional[str] = None,
    owned_paths: Optional[Sequence[str]] = None,
    forbidden_paths: Optional[Sequence[str]] = None,
    verify_cmds: Optional[Sequence[str]] = None,
    skip_git_check: bool = False,
    repo: Optional[str] = None,
    cwd: Optional[str] = None,
) -> int:
    """Execute full boundary + test verification for a task and return exit code (0=pass, 1=fail)."""
    prev_cwd: Optional[str] = None
    if cwd:
        prev_cwd = os.getcwd()
        os.chdir(cwd)
    try:
        return _verify_task_impl(
            issue_number=issue_number,
            base_ref=base_ref,
            owned_paths=owned_paths,
            forbidden_paths=forbidden_paths,
            verify_cmds=verify_cmds,
            skip_git_check=skip_git_check,
            repo=repo,
        )
    finally:
        if prev_cwd is not None:
            os.chdir(prev_cwd)


def _verify_task_impl(
    issue_number: Optional[int] = None,
    base_ref: Optional[str] = None,
    owned_paths: Optional[Sequence[str]] = None,
    forbidden_paths: Optional[Sequence[str]] = None,
    verify_cmds: Optional[Sequence[str]] = None,
    skip_git_check: bool = False,
    repo: Optional[str] = None,
) -> int:
    resolved_owned: List[str] = list(owned_paths or [])
    resolved_forbidden: List[str] = list(forbidden_paths or [])
    resolved_cmds: List[str] = list(verify_cmds or [])

    if issue_number is not None:
        issue_data = agent_backlog.get_task_issue(issue_number, repo=repo)
        if issue_data.get("spec_error") or not issue_data.get("spec"):
            print(f"ERROR: Could not parse task spec from issue #{issue_number}: {issue_data.get('spec_error')}")
            return 1
        spec = issue_data["spec"]
        if not resolved_owned:
            resolved_owned = list(spec.get("owned_paths", []))
        if not resolved_forbidden:
            resolved_forbidden = list(spec.get("forbidden_paths", []))
        for cmd in spec.get("verification_commands", []):
            if cmd not in resolved_cmds:
                resolved_cmds.append(cmd)
        print(f"Loaded task spec from GitHub Issue #{issue_number}: {issue_data.get('title')}")

    modified_files: List[str] = []
    if not skip_git_check:
        branch = get_current_branch()
        branch_ok, branch_err = check_branch_safety(branch)
        if not branch_ok:
            print(f"ERROR: {branch_err}")
            return 1
        print(f"Branch safety check: PASSED ({branch})")
        fresh_ok, fresh_msg, resolved_base = check_base_branch_freshness(explicit_base=base_ref)
        if not fresh_ok:
            print(f"ERROR: {fresh_msg}")
            return 1
        print(f"Base branch freshness check: PASSED ({fresh_msg})")
        if resolved_base:
            print(f"Diff base: {resolved_base}")
        modified_files = get_modified_files(base_ref=resolved_base)
        print(f"Modified files ({len(modified_files)}): {modified_files}")
        ok, violations = check_path_boundaries(modified_files, resolved_owned, resolved_forbidden)
        if not ok:
            print("\n=== PATH BOUNDARY VIOLATIONS ===")
            for v in violations:
                print(f"  - {v}")
            return 1
        print("Path boundary check: PASSED")

    inferred = infer_domain_checks(modified_files) if modified_files else []
    all_commands = [*inferred, *resolved_cmds]
    if not all_commands:
        print("No verification commands specified or inferred. Exiting cleanly.")
        return 0

    results = run_verification_commands(all_commands)
    failed = [cmd for cmd, code in results if code != 0]

    print("\n=== VERIFICATION SUMMARY ===")
    for cmd, code in results:
        status = "PASS" if code == 0 else f"FAIL ({code})"
        print(f"  [{status}] {cmd}")

    return 1 if failed else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic task verification runner")
    parser.add_argument("--issue", type=int, default=None, help="GitHub Issue number to load spec from")
    parser.add_argument("--repo", default=None, help="GitHub repo slug owner/name")
    parser.add_argument("--cwd", default=None, help="Optional working directory (e.g. isolated git worktree path)")
    parser.add_argument("--base", default=None, help="Optional git base ref for diff file detection")
    parser.add_argument("--owned-paths", nargs="*", default=[], help="Allowed file/directory paths")
    parser.add_argument("--forbidden-paths", nargs="*", default=[], help="Disallowed file/directory paths")
    parser.add_argument("--verify-cmd", action="append", default=[], help="Verification command to execute")
    parser.add_argument("--skip-git-check", action="store_true", help="Skip git status boundary check")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return verify_task(
        issue_number=args.issue,
        base_ref=args.base,
        owned_paths=args.owned_paths,
        forbidden_paths=args.forbidden_paths,
        verify_cmds=args.verify_cmd,
        skip_git_check=args.skip_git_check,
        repo=args.repo,
        cwd=args.cwd,
    )


if __name__ == "__main__":
    sys.exit(main())
