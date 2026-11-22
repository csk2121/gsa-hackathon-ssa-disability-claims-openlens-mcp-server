"""
Benchmark regression tests — the engine must reproduce every reviewed expectation in
eval/benchmark_questions.yaml.

Expectations are reviewed against the grounded catalog (see the comments in the YAML).
When the catalog or rubric changes, re-review the affected expectations rather than
tuning patterns until the numbers match.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.ssa_disability_claims_openlens.services.answer_coverage_service import (
    AnswerCoverageEngine,
)

BENCHMARK = yaml.safe_load(
    (Path(__file__).parent.parent / "eval" / "benchmark_questions.yaml").read_text(encoding="utf-8")
)["benchmark_questions"]
ENGINE = AnswerCoverageEngine()


@pytest.mark.parametrize("case", BENCHMARK, ids=[c["id"] for c in BENCHMARK])
def test_rating_matches_reviewed_expectation(case: dict) -> None:
    assessment = ENGINE.evaluate(case["question"])
    assert assessment.coverage_rating.value == case["expected_coverage"], (
        f"{case['id']}: expected {case['expected_coverage']}, got "
        f"{assessment.coverage_rating.value} ({assessment.answer_coverage_score})"
    )


@pytest.mark.parametrize("case", BENCHMARK, ids=[c["id"] for c in BENCHMARK])
def test_key_datasets_are_cited(case: dict) -> None:
    assessment = ENGINE.evaluate(case["question"])
    cited = {d for el in assessment.required_information_elements for d in el.dataset_ids}
    missing = set(case.get("key_datasets") or []) - cited
    assert not missing, f"{case['id']}: key datasets not cited: {sorted(missing)}"
