"""Unit tests for `scripts/agent_backlog.py`."""

from __future__ import annotations

from datetime import datetime, timezone
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


def test_extract_issue_number_from_pr() -> None:
    assert agent_backlog.extract_issue_number_from_pr({"head": {"ref": "agent/issue-14"}, "body": ""}) == 14
    assert agent_backlog.extract_issue_number_from_pr({"head": {"ref": "agent/custom"}, "body": "Fixes #22"}) == 22
    assert agent_backlog.extract_issue_number_from_pr({"head": {"ref": "agent/custom"}, "body": "No link"}) is None


def test_analyze_pr_review_state_lifecycle() -> None:
    t1 = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)
    pr = {
        "number": 5,
        "head": {"ref": "agent/issue-4", "sha": "sha1"},
        "labels": [{"name": "agent:review"}],
    }
    # 1. Fresh PR awaiting review
    state1 = agent_backlog.analyze_pr_review_state(pr, [], [], [], latest_commit_at=t1)
    assert state1["needs_auto_review"] is True
    assert state1["needs_rework"] is False

    # 2. Auto-reviewer requests changes (via COMMENT fallback + label)
    rev1 = {
        "id": 1,
        "user": {"login": "bot"},
        "state": "COMMENTED",
        "commit_id": "sha1",
        "submitted_at": "2026-11-15T10:05:00Z",
        "body": "<!-- auto-review:sha=sha1 verdict=changes-requested round=1 -->\nPlease add edge case test.",
    }
    pr_changes = {**pr, "labels": [{"name": "agent:changes-requested"}, {"name": "review:changes-requested"}]}
    state2 = agent_backlog.analyze_pr_review_state(pr_changes, [rev1], [], [], latest_commit_at=t1)
    assert state2["needs_rework"] is True
    assert state2["needs_auto_review"] is False
    assert state2["auto_review_rounds"] == 1
    assert len(state2["feedback_items"]) == 1

    # 3. Executor pushes sha2, clears labels, posts completion marker -> awaits re-review
    t2 = datetime(2026, 11, 15, 10, 15, tzinfo=timezone.utc)
    pr_sha2 = {**pr, "head": {"ref": "agent/issue-4", "sha": "sha2"}, "labels": [{"name": "agent:review"}]}
    exec_comment = {
        "user": {"login": "bot"},
        "created_at": "2026-11-15T10:15:30Z",
        "body": "<!-- auto-executor:complete sha=sha2 -->\nAdded edge case test.",
    }
    state3 = agent_backlog.analyze_pr_review_state(pr_sha2, [rev1], [], [exec_comment], latest_commit_at=t2)
    assert state3["needs_rework"] is False
    assert state3["needs_auto_review"] is True

    # 4. Auto-reviewer approves sha2; later human leaves inline comment -> triggers rework
    rev2 = {
        "id": 2,
        "user": {"login": "bot"},
        "state": "COMMENTED",
        "commit_id": "sha2",
        "submitted_at": "2026-11-15T10:20:00Z",
        "body": "<!-- auto-review:sha=sha2 verdict=approved round=2 -->\nLooks good.",
    }
    pr_approved = {**pr_sha2, "labels": [{"name": "agent:review"}, {"name": "review:approved"}]}
    state4 = agent_backlog.analyze_pr_review_state(pr_approved, [rev1, rev2], [], [exec_comment], latest_commit_at=t2)
    assert state4["needs_rework"] is False
    assert state4["needs_auto_review"] is False

    human_inline = {
        "user": {"login": "Justin"},
        "path": "site_ui/helpers.js",
        "line": 42,
        "created_at": "2026-11-15T11:00:00Z",
        "body": "Handle negative values here too.",
    }
    state5 = agent_backlog.analyze_pr_review_state(
        pr_approved, [rev1, rev2], [human_inline], [exec_comment], latest_commit_at=t2
    )
    assert state5["needs_rework"] is True
    assert any(item.get("path") == "site_ui/helpers.js" for item in state5["feedback_items"])

    # 5. Native GitHub CHANGES_REQUESTED review vs later APPROVED review
    native_rc = {
        "id": 3,
        "user": {"login": "reviewer-bot"},
        "state": "CHANGES_REQUESTED",
        "commit_id": "sha2",
        "submitted_at": "2026-11-15T10:25:00Z",
        "body": "Fix naming.",
    }
    state6 = agent_backlog.analyze_pr_review_state(pr_sha2, [native_rc], [], [], latest_commit_at=t2)
    assert state6["needs_rework"] is True

    native_app = {
        "id": 4,
        "user": {"login": "reviewer-bot"},
        "state": "APPROVED",
        "commit_id": "sha2",
        "submitted_at": "2026-11-15T10:30:00Z",
        "body": "<!-- auto-review:sha=sha2 verdict=approved round=2 -->\nLGTM",
    }
    state7 = agent_backlog.analyze_pr_review_state(pr_sha2, [native_rc, native_app], [], [], latest_commit_at=t2)
    assert state7["needs_rework"] is False


def test_submit_pr_review_handles_422_fallback_and_max_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    pr_obj = {
        "number": 9,
        "head": {"ref": "agent/issue-8", "sha": "abc123"},
        "labels": [{"name": "agent:review"}],
    }
    issue_obj = {"number": 8, "labels": [{"name": "agent:review"}]}

    def fake_request(method: str, path: str, payload=None, repo=None, token=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/pulls/9":
            return pr_obj
        if method == "GET" and path == "/pulls/9/reviews":
            return []
        if method == "GET" and path == "/pulls/9/comments":
            return []
        if method == "GET" and path == "/issues/9/comments":
            return []
        if method == "GET" and path == "/commits/abc123":
            return {"commit": {"committer": {"date": "2026-11-15T10:00:00Z"}}}
        if method == "GET" and path == "/issues/8":
            return issue_obj
        if method == "POST" and path == "/pulls/9/reviews":
            if payload.get("event") == "APPROVE":
                raise RuntimeError("GitHub API POST failed with HTTP 422: Can not approve your own pull request")
            return {"html_url": "https://github.com/example/pr/9#pullrequestreview-1"}
        if method == "PATCH":
            return {"labels": [{"name": lbl} for lbl in payload.get("labels", [])]}
        return {}

    monkeypatch.setattr(agent_backlog, "github_request", fake_request)
    res = agent_backlog.submit_pr_review(
        pr_number=9,
        decision="approve",
        summary="All checks pass.",
        repo="example/repo",
        token="tok",
    )
    assert res["fallback_comment_review"] is True
    assert res["decision"] == "approve"
    assert res["round"] == 1
    patch_calls = [c for c in calls if c[0] == "PATCH"]
    assert any("review:approved" in c[2]["labels"] for c in patch_calls if c[1] == "/issues/9")

    # Exceeding max_rounds on request-changes should mark agent:blocked
    def fake_request_max_rounds(method: str, path: str, payload=None, repo=None, token=None):
        if method == "GET" and path == "/pulls/9/reviews":
            return [
                {"body": "<!-- auto-review:sha=s1 verdict=changes-requested round=1 -->"},
                {"body": "<!-- auto-review:sha=s2 verdict=changes-requested round=2 -->"},
                {"body": "<!-- auto-review:sha=s3 verdict=changes-requested round=3 -->"},
            ]
        return fake_request(method, path, payload=payload, repo=repo, token=token)

    monkeypatch.setattr(agent_backlog, "github_request", fake_request_max_rounds)
    blocked_res = agent_backlog.submit_pr_review(
        pr_number=9,
        decision="request-changes",
        summary="Still broken.",
        max_rounds=3,
        repo="example/repo",
        token="tok",
    )
    assert blocked_res["blocked"] is True
    assert blocked_res["decision"] == "blocked"


def test_pr_review_and_rework_worktree_rebase(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    # Push agent/issue-7 branch from v1
    _git(seed_dir, "checkout", "-b", "agent/issue-7")
    (seed_dir / "feature.txt").write_text("feature v1\n", encoding="utf-8")
    _git(seed_dir, "add", "feature.txt")
    _git(seed_dir, "commit", "-m", "feature v1")
    _git(seed_dir, "push", "-u", "origin", "agent/issue-7")
    b1 = _git(seed_dir, "rev-parse", "HEAD")

    # Advance main to v2 so agent/issue-7 is behind main
    _git(seed_dir, "checkout", "main")
    (seed_dir / "README.md").write_text("v2\n", encoding="utf-8")
    _git(seed_dir, "add", "README.md")
    _git(seed_dir, "commit", "-m", "v2 on main")
    _git(seed_dir, "push", "origin", "main")
    c2 = _git(seed_dir, "rev-parse", "HEAD")

    review_info = agent_backlog.prepare_pr_review_worktree("agent/issue-7", repo_root=str(local_dir))
    try:
        assert review_info["behind_main"] is True
        assert review_info["head_sha"] == b1
    finally:
        agent_backlog.cleanup_task_worktree(
            review_info["worktree_path"],
            delete_branch=review_info["branch"],
            repo_root=str(local_dir),
        )

    rework_info = agent_backlog.prepare_rework_worktree("agent/issue-7", repo_root=str(local_dir))
    try:
        assert rework_info["rebased"] is True
        assert rework_info["rebase_conflict"] is False
        wt = Path(rework_info["worktree_path"])
        assert (wt / "README.md").read_text(encoding="utf-8") == "v2\n"
        assert (wt / "feature.txt").read_text(encoding="utf-8") == "feature v1\n"
        # origin/main (c2) is now an ancestor of HEAD
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", c2, "HEAD"],
            cwd=str(wt),
            check=True,
        )
        monkeypatch.chdir(wt)
        pushed = agent_backlog.push_task_branch("agent/issue-7", force_with_lease=True)
        assert pushed == "agent/issue-7"
    finally:
        monkeypatch.chdir(tmp_path)
        agent_backlog.cleanup_task_worktree(
            rework_info["worktree_path"],
            delete_branch="agent/issue-7",
            repo_root=str(local_dir),
        )


def test_infer_and_backfill_manual_issue_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    manual_issue = {
        "number": 4,
        "title": "Fix schedule screen where score shows 0-0 while in-game",
        "body": 'Fix schedule screen where score shows 0-0 while in-game\n\n<img src="https://example.com/img.png" />',
        "labels": [{"name": "bug"}, {"name": "agent:ready"}],
    }
    inferred = agent_backlog.infer_task_spec(
        title=manual_issue["title"],
        body=manual_issue["body"],
        labels=["bug", "agent:ready"],
    )
    assert "site_ui/schedule/index.html" in inferred["owned_paths"]
    assert "site_ui/scoreboard/index.html" in inferred["owned_paths"]
    assert "site_ui/helpers.js" in inferred["owned_paths"]
    assert "firestore.rules" in inferred["forbidden_paths"]
    assert inferred["verification_commands"] == ["python -m pytest -v"]

    patched_payloads = []

    def fake_github_request(method, path, payload=None, repo=None, token=None):
        if method == "PATCH":
            patched_payloads.append(payload)
        return manual_issue

    monkeypatch.setattr(agent_backlog, "github_request", fake_github_request)
    spec, was_inferred, updated_body = agent_backlog.resolve_or_infer_issue_spec(
        manual_issue,
        persist=True,
        repo="owner/repo",
        token="tok",
    )
    assert was_inferred is True
    assert spec["owned_paths"] == inferred["owned_paths"]
    assert "```json agent-task-spec" in updated_body
    assert len(patched_payloads) == 1
    # Subsequent parse_task_spec on the backfilled body succeeds without inference
    parsed = agent_backlog.parse_task_spec(updated_body)
    assert parsed["owned_paths"] == inferred["owned_paths"]


def test_analyze_issue_comment_state_and_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    issue = {
        "number": 6,
        "title": "Add Quadrant 1-4 game list drilldown",
        "labels": [{"name": "agent:proposed"}, {"name": "source:feature"}],
        "comments": 2,
    }
    comments = [
        {
            "id": 101,
            "user": {"login": "Justin"},
            "created_at": "2026-11-16T12:00:00Z",
            "body": "Can we also show the game date for upcoming games in each quadrant?",
        }
    ]
    state1 = agent_backlog.analyze_issue_comment_state(issue, comments)
    assert state1["needs_reply"] is True
    assert state1["latest_comment_id"] == 101
    assert len(state1["unanswered_comments"]) == 1

    # Once the agent replies with the marker for comment_id=101, needs_reply becomes False
    comments_with_reply = [
        *comments,
        {
            "id": 102,
            "user": {"login": "bot"},
            "created_at": "2026-11-16T12:05:00Z",
            "body": "<!-- auto-issue-reply:comment_id=101 -->\nYes! Updated the spec to include `dateLabel`.",
        },
    ]
    state2 = agent_backlog.analyze_issue_comment_state(issue, comments_with_reply)
    assert state2["needs_reply"] is False
    assert state2["last_replied_comment_id"] == 101

    # Follow-up human comment triggers needs_reply again
    comments_followup = [
        *comments_with_reply,
        {
            "id": 103,
            "user": {"login": "Justin"},
            "created_at": "2026-11-16T12:10:00Z",
            "body": "Looks great, please mark ready!",
        },
    ]
    state3 = agent_backlog.analyze_issue_comment_state(issue, comments_followup)
    assert state3["needs_reply"] is True
    assert state3["latest_comment_id"] == 103
    assert [c["id"] for c in state3["unanswered_comments"]] == [103]

    posted_calls = []

    def fake_gh(method, path, payload=None, repo=None, token=None):
        posted_calls.append((method, path, payload))
        if method == "GET" and path == "/issues/6":
            return issue
        if method == "GET" and path == "/issues/6/comments":
            return comments_followup
        if method == "POST" and path == "/issues/6/comments":
            return {"html_url": "https://github.com/example/repo/issues/6#issuecomment-104"}
        return {}

    monkeypatch.setattr(agent_backlog, "github_request", fake_gh)
    res = agent_backlog.reply_to_issue_comment(
        issue_number=6,
        body="Marked `agent:ready` for execution!",
        new_status="ready",
        repo="example/repo",
        token="tok",
    )
    assert res["replied_to_comment_id"] == 103
    assert res["updated_issue"] is True
    post_call = [c for c in posted_calls if c[0] == "POST"][0]
    assert "<!-- auto-issue-reply:comment_id=103 -->" in post_call[2]["body"]


def test_list_task_issues_proposed_excludes_Dual_labeled_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_issues = [
        {"number": 1, "title": "Still proposed", "labels": [{"name": "agent:proposed"}, {"name": "priority:p2"}]},
        {
            "number": 7,
            "title": "Human added ready on GitHub",
            "labels": [{"name": "agent:proposed"}, {"name": "agent:ready"}, {"name": "priority:p2"}],
        },
    ]
    monkeypatch.setattr(agent_backlog, "_get_paginated_issues", lambda **kwargs: raw_issues)
    proposed = agent_backlog.list_task_issues(status="proposed", repo="example/repo", token="tok")
    assert [i["number"] for i in proposed] == [1]


