"""Unit tests for `scripts/verify_task.py`."""

from __future__ import annotations

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
