"""Unit tests for `scripts/verify_task.py`."""

from __future__ import annotations

from pathlib import Path
import subprocess
from scripts import verify_task


def test_check_branch_safety() -> None:
    ok, _ = verify_task.check_branch_safety("agent/issue-7")
    assert ok is True

    ok_main, err_main = verify_task.check_branch_safety("main")
    assert ok_main is False
    assert "Protected" in err_main


def test_check_path_boundaries() -> None:
    ok, violations = verify_task.check_path_boundaries(
        modified_files=["site_ui/helpers.js", "tests/test_helpers_and_contracts.py"],
        owned_paths=["site_ui/", "tests/"],
        forbidden_paths=["firestore.rules"],
    )
    assert ok is True
    assert violations == []

    ok2, violations2 = verify_task.check_path_boundaries(
        modified_files=["firestore.rules", "README.md"],
        owned_paths=["site_ui/"],
        forbidden_paths=["firestore.rules"],
    )
    assert ok2 is False
    assert len(violations2) == 2


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


def test_check_base_branch_freshness_detects_stale_and_rebased_branches(tmp_path: Path) -> None:
    origin_dir = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(origin_dir)], check=True, capture_output=True)

    seed_dir = tmp_path / "seed"
    subprocess.run(["git", "clone", str(origin_dir), str(seed_dir)], check=True, capture_output=True)
    _git(seed_dir, "config", "user.email", "test@example.com")
    _git(seed_dir, "config", "user.name", "Test User")
    (seed_dir / "README.md").write_text("v1\n", encoding="utf-8")
    _git(seed_dir, "add", "README.md")
    _git(seed_dir, "commit", "-m", "v1")
    _git(seed_dir, "push", "-u", "origin", "main")

    local_dir = tmp_path / "local"
    subprocess.run(["git", "clone", str(origin_dir), str(local_dir)], check=True, capture_output=True)
    _git(local_dir, "config", "user.email", "test@example.com")
    _git(local_dir, "config", "user.name", "Test User")
    _git(local_dir, "checkout", "-b", "agent/issue-5")
    (local_dir / "feature.txt").write_text("agent change\n", encoding="utf-8")
    _git(local_dir, "add", "feature.txt")
    _git(local_dir, "commit", "-m", "agent work")

    # Advance origin/main after agent/issue-5 was created
    (seed_dir / "README.md").write_text("v2\n", encoding="utf-8")
    _git(seed_dir, "add", "README.md")
    _git(seed_dir, "commit", "-m", "v2 on main")
    _git(seed_dir, "push", "origin", "main")

    ok_stale, msg_stale, _ = verify_task.check_base_branch_freshness(cwd=str(local_dir))
    assert ok_stale is False
    assert "behind or not branched from latest 'origin/main'" in msg_stale

    _git(local_dir, "rebase", "origin/main")
    ok_fresh, _, diff_ref = verify_task.check_base_branch_freshness(cwd=str(local_dir))
    assert ok_fresh is True
    assert diff_ref == "origin/main...HEAD"
