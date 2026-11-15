"""Unit tests for `scripts/agent_backlog.py`."""

from __future__ import annotations

import pytest
from scripts import agent_backlog


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
