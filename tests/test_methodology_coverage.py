from __future__ import annotations

import pytest

from cases.methodology import (
    PQA_METHODOLOGY_CRITERIA,
    evidence_file,
    load_methodology_criteria,
    load_methodology_source,
)


pytestmark = pytest.mark.methodology


def test_methodology_registry_covers_every_source_criterion():
    criteria = load_methodology_criteria()

    assert {criterion.criterion_id for criterion in criteria} == PQA_METHODOLOGY_CRITERIA
    assert len(criteria) == len(PQA_METHODOLOGY_CRITERIA)
    assert all(set(criterion.source_slides) <= {2, 3, 4} for criterion in criteria)


def test_methodology_covered_and_partial_items_point_to_real_evidence():
    criteria = load_methodology_criteria()
    missing = []

    for criterion in criteria:
        if criterion.status in {"covered", "partial"} and not criterion.evidence:
            missing.append(f"{criterion.criterion_id}: no evidence")
        for evidence in criterion.evidence:
            if not evidence_file(evidence).exists():
                missing.append(f"{criterion.criterion_id}: {evidence}")
        if criterion.status == "partial" and not criterion.next_actions:
            missing.append(f"{criterion.criterion_id}: partial without next action")

    assert not missing, "Methodology evidence is incomplete:\n" + "\n".join(missing)


def test_methodology_gaps_are_explicit_and_risky_work_has_a_safety_gate():
    criteria = load_methodology_criteria()
    failures = []

    for criterion in criteria:
        if criterion.status == "gap":
            if criterion.evidence:
                failures.append(f"{criterion.criterion_id}: gap must not claim evidence")
            if not criterion.next_actions:
                failures.append(f"{criterion.criterion_id}: gap has no next action")
        if criterion.risk in {"destructive", "long_running", "concurrent"} and not criterion.safety_gate:
            failures.append(f"{criterion.criterion_id}: risky work has no safety gate")

    assert not failures, "Methodology gap tracking is incomplete:\n" + "\n".join(failures)


def test_methodology_source_is_traceable_to_the_reviewed_presentation():
    source = load_methodology_source()

    assert source["label"] == "PQA Test methdology-250725_AI.pptx"
    assert source["sha256"] == "C8E6BFDF405DDDB3288E6079C187335313B5A50AAE64B331F5BF0D8E8396275E"
    assert source["slides_used"] == [2, 3, 4]
