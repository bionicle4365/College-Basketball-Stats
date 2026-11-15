"""Unit tests for `scripts/audit_and_generate_tasks.py` and `scripts/propose_feature_tasks.py`."""

from __future__ import annotations

import os
from scripts import audit_and_generate_tasks, propose_feature_tasks

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_clean_repo_has_zero_static_audit_tasks() -> None:
    tasks = audit_and_generate_tasks.collect_all_tasks(
        repo_root=REPO_ROOT,
        run_tests=False,
        check_espn=False,
        check_ci=False,
    )
    assert tasks == [], f"Expected zero static drift/security/test-gap tasks on clean repo, got: {tasks}"


def test_propose_feature_tasks_selects_diverse_pillars() -> None:
    candidates = propose_feature_tasks.select_candidate_features(existing_titles=set(), limit=2)
    assert len(candidates) == 2
    assert candidates[0]["pillar"] != candidates[1]["pillar"]

    # Deduplication by title
    existing = {candidates[0]["title"]}
    next_candidates = propose_feature_tasks.select_candidate_features(existing_titles=existing, limit=2)
    assert all(c["title"] != candidates[0]["title"] for c in next_candidates)


def test_feature_catalog_entries_include_context_and_examples() -> None:
    for spec in propose_feature_tasks.FEATURE_CATALOG:
        assert spec.get("context"), f"Feature '{spec['title']}' missing context"
        assert spec.get("examples"), f"Feature '{spec['title']}' missing examples"
