"""Unit tests for `scripts/agent_backlog.py`."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
import pytest
from scripts import agent_backlog


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


def _init_repo_with_origin(tmp_path: Path):
    """Create a bare `origin.git`, a `seed` clone, and a `local` clone on `main`."""
    origin_dir = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(origin_dir)], check=True, capture_output=True)

    seed_dir = tmp_path / "seed"
    subprocess.run(["git", "clone", str(origin_dir), str(seed_dir)], check=True, capture_output=True)
    _git(seed_dir, "config", "user.email", "test@example.com")
    _git(seed_dir, "config", "user.name", "Test User")
    (seed_dir / "README.md").write_text("v1\n", encoding="utf-8")
    _git(seed_dir, "add", "README.md")
    _git(seed_dir, "commit", "-m", "initial v1")
    _git(seed_dir, "push", "-u", "origin", "main")
    c1 = _git(seed_dir, "rev-parse", "HEAD")

    local_dir = tmp_path / "local"
    subprocess.run(["git", "clone", str(origin_dir), str(local_dir)], check=True, capture_output=True)
    _git(local_dir, "config", "user.email", "test@example.com")
    _git(local_dir, "config", "user.name", "Test User")

    # Advance origin/main to c2 via seed_dir so local_dir's main & origin/main are stale
    (seed_dir / "README.md").write_text("v2\n", encoding="utf-8")
    _git(seed_dir, "add", "README.md")
    _git(seed_dir, "commit", "-m", "advance main v2")
    _git(seed_dir, "push", "origin", "main")
    c2 = _git(seed_dir, "rev-parse", "HEAD")

    return origin_dir, seed_dir, local_dir, c1, c2


def test_validate_agent_branch_enforces_prefix() -> None:
    assert agent_backlog.validate_agent_branch("agent/issue-12") == "agent/issue-12"
    with pytest.raises(ValueError):
        agent_backlog.validate_agent_branch("main")
    with pytest.raises(ValueError):
        agent_backlog.validate_agent_branch("feature/custom")


def test_format_and_parse_task_spec_roundtrip() -> None:
    body = agent_backlog.format_task_body(
        objective="Add streak badge to group leaderboard",
        spec={
            "owned_paths": ["site_ui/helpers.js", "site_ui/group/index.html"],
            "forbidden_paths": ["firestore.rules"],
            "acceptance_criteria": ["Streak pill renders accurately"],
            "verification_commands": ["python -m pytest -v"],
        },
    )
    parsed = agent_backlog.parse_task_spec(body)
    assert parsed["owned_paths"] == ["site_ui/helpers.js", "site_ui/group/index.html"]
    assert parsed["forbidden_paths"] == ["firestore.rules"]
    assert parsed["acceptance_criteria"] == ["Streak pill renders accurately"]
    assert parsed["verification_commands"] == ["python -m pytest -v"]


def test_format_task_body_includes_context_examples_and_screenshots() -> None:
    body = agent_backlog.format_task_body(
        objective="Add streak badge",
        context="Users cannot see multi-game hot streaks on the leaderboard.",
        examples="Input: [20, 25] -> activeHotStreak: 2",
        screenshots=[{"caption": "Light Mode Preview", "url": "https://example.com/light.png"}],
        spec={
            "owned_paths": ["site_ui/helpers.js"],
            "forbidden_paths": ["firestore.rules"],
            "acceptance_criteria": ["Streak pill renders"],
            "verification_commands": ["python -m pytest -v"],
        },
    )
    assert "## Context & Motivation" in body
    assert "## Examples & Expected Behavior" in body
    assert "## UI / Screenshot Preview" in body
    assert "![Light Mode Preview](https://example.com/light.png)" in body
    parsed = agent_backlog.parse_task_spec(body)
    assert parsed["owned_paths"] == ["site_ui/helpers.js"]


def test_format_pr_body_includes_diff_examples_screenshots_and_verification() -> None:
    pr_body = agent_backlog.format_pr_body(
        issue_number=2,
        summary="Added eFG%, TS%, and AST/TO efficiency strip.",
        changed_files=[{"path": "site_ui/helpers.js", "additions": 74, "deletions": 0}],
        examples="calculateAdvancedEfficiency(...) -> efgDisplay: '64.7%'",
        screenshots=[{"caption": "After (Dark Mode)", "url": "https://example.com/dark.png"}],
        verification="python -m pytest -v -> 13 passed",
    )
    assert pr_body.startswith("Closes #2")
    assert "## Changes & Modified Files" in pr_body
    assert "| `site_ui/helpers.js` | `+74` | `-0` |" in pr_body
    assert "## Examples & Behavior Walkthrough" in pr_body
    assert "## Screenshots & Visual Preview" in pr_body
    assert "![After (Dark Mode)](https://example.com/dark.png)" in pr_body
    assert "## Verification & Test Results" in pr_body


def test_prepare_task_worktree_branches_from_latest_origin_main(tmp_path: Path) -> None:
    _, _, local_dir, c1, c2 = _init_repo_with_origin(tmp_path)
    # Put local_dir on a separate branch with uncommitted changes to ensure isolation
    _git(local_dir, "checkout", "-b", "feature/local-wip")
    (local_dir / "wip.txt").write_text("dirty\n", encoding="utf-8")
    assert _git(local_dir, "rev-parse", "main") == c1

    wt_path = agent_backlog.prepare_task_worktree("agent/issue-99", repo_root=str(local_dir))
    try:
        assert _git(Path(wt_path), "rev-parse", "--abbrev-ref", "HEAD") == "agent/issue-99"
        assert _git(Path(wt_path), "rev-parse", "HEAD") == c2
        assert (Path(wt_path) / "README.md").read_text(encoding="utf-8") == "v2\n"
    finally:
        agent_backlog.cleanup_task_worktree(wt_path, delete_branch="agent/issue-99", repo_root=str(local_dir))

    assert not os.path.exists(wt_path)


def test_prepare_task_worktree_fails_loudly_when_origin_fetch_fails(tmp_path: Path) -> None:
    repo_dir = tmp_path / "broken"
    subprocess.run(["git", "init", "--initial-branch=main", str(repo_dir)], check=True, capture_output=True)
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "Test User")
    (repo_dir / "README.md").write_text("local\n", encoding="utf-8")
    _git(repo_dir, "add", "README.md")
    _git(repo_dir, "commit", "-m", "local init")
    _git(repo_dir, "remote", "add", "origin", str(tmp_path / "does-not-exist.git"))

    with pytest.raises(RuntimeError, match="Failed to fetch latest 'origin/main'"):
        agent_backlog.prepare_task_worktree("agent/issue-100", repo_root=str(repo_dir))


def test_push_task_branch_rejects_outdated_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, local_dir, c1, _ = _init_repo_with_origin(tmp_path)
    _git(local_dir, "checkout", "-b", "agent/issue-101", c1)
    (local_dir / "work.txt").write_text("change\n", encoding="utf-8")
    _git(local_dir, "add", "work.txt")
    _git(local_dir, "commit", "-m", "stale base commit")

    monkeypatch.chdir(local_dir)
    with pytest.raises(RuntimeError, match="behind or not branched from the latest 'origin/main'"):
        agent_backlog.push_task_branch("agent/issue-101")


def test_temporary_agent_worktree_cleans_up_worktree_and_branch(tmp_path: Path) -> None:
    _, _, local_dir, _, c2 = _init_repo_with_origin(tmp_path)

    with agent_backlog.temporary_agent_worktree("agent/audit-main", repo_root=str(local_dir)) as wt_path:
        assert os.path.isdir(wt_path)
        assert _git(Path(wt_path), "rev-parse", "--abbrev-ref", "HEAD") == "agent/audit-main"
        assert _git(Path(wt_path), "rev-parse", "HEAD") == c2
        assert (Path(wt_path) / "README.md").read_text(encoding="utf-8") == "v2\n"

    assert not os.path.exists(wt_path)
    branches = _git(local_dir, "branch", "--list", "agent/audit-main")
    assert branches == ""
