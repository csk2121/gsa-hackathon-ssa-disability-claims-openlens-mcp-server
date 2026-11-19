"""
Regression tests: Accessibility and Geographic Equity intent recognition.

Prevents future changes from classifying accessibility/equity questions as
Unsupported. Covers the specific question that exposed the original bug:

  "Can a researcher use currently available SSA public datasets to determine
   whether rural communities have less access to disability services than
   urban communities?"

And a broader set of accessibility/equity phrasings.
"""

from __future__ import annotations

import pytest

from src.ssa_disability_claims_openlens.models import CoverageRating
from src.ssa_disability_claims_openlens.services.answer_coverage_service import (
    AnswerCoverageEngine,
)

RURAL_URBAN_QUESTION = (
    "Can a researcher use currently available SSA public datasets to determine "
    "whether rural communities have less access to disability services than "
    "urban communities?"
)

ACCESSIBILITY_QUESTIONS = [
    RURAL_URBAN_QUESTION,
    "Do rural areas have less access to SSA disability services than urban areas?",
    "Is there a service desert for disability claimants in rural counties?",
    "Which counties are underserved by SSA field offices?",
    "How far do rural disability applicants have to travel to reach an SSA office?",
]

GEOGRAPHIC_EQUITY_QUESTIONS = [
    "Is there geographic equity in the distribution of SSA disability services?",
    "Are there regional disparities in disability service access?",
    "Which counties have poor office coverage for disability claimants?",
]


class TestAccessibilityIntentRecognition:
    """The rural/urban access question must never return Unsupported."""

    def test_rural_urban_question_not_unsupported(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(RURAL_URBAN_QUESTION)
        assert assessment.coverage_rating != CoverageRating.UNSUPPORTED, (
            f"Rural/urban access question must not be Unsupported — "
            f"got {assessment.coverage_rating}"
        )

    def test_rural_urban_question_is_limited_or_partial(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(RURAL_URBAN_QUESTION)
        assert assessment.coverage_rating in (
            CoverageRating.LIMITED,
            CoverageRating.PARTIAL,
            CoverageRating.HIGH,
        ), (
            f"Rural/urban access question should be Limited, Partial, or High — "
            f"got {assessment.coverage_rating}"
        )

    def test_rural_urban_question_has_accessibility_intent(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(RURAL_URBAN_QUESTION)
        assert assessment.intent is not None, (
            "Rural/urban access question must produce a recognized intent"
        )
        assert "access" in assessment.intent.intent_category.lower() or \
               "accessibility" in assessment.intent.intent_category.lower() or \
               "equity" in assessment.intent.intent_category.lower(), (
            f"Intent category should be Accessibility or Geographic Equity — "
            f"got '{assessment.intent.intent_category}'"
        )

    def test_rural_urban_question_has_available_data(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(RURAL_URBAN_QUESTION)
        assert len(assessment.available_data) > 0, (
            "Rural/urban access question must identify at least one available dataset"
        )

    def test_rural_urban_question_missing_info_includes_distance_or_wait(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(RURAL_URBAN_QUESTION)
        missing_text = " ".join(assessment.missing_information).lower()
        assert "travel distance" in missing_text or \
               "wait time" in missing_text or \
               "service area" in missing_text or \
               "operational metric" in missing_text, (
            f"Missing information should include travel distance, wait times, or service areas — "
            f"got: {assessment.missing_information}"
        )

    def test_rural_urban_question_has_recommendations(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(RURAL_URBAN_QUESTION)
        assert len(assessment.transparency_recommendations) > 0, (
            "Rural/urban access question must generate at least one transparency recommendation"
        )

    def test_rural_urban_question_score_above_zero(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(RURAL_URBAN_QUESTION)
        assert assessment.answer_coverage_score > 0.0, (
            f"Rural/urban access question should score > 0 — got {assessment.answer_coverage_score}"
        )


class TestAccessibilityPhrasings:
    """All accessibility-phrased questions must produce a non-Unsupported rating."""

    @pytest.mark.parametrize("question", ACCESSIBILITY_QUESTIONS)
    def test_accessibility_question_not_unsupported(
        self, coverage_engine: AnswerCoverageEngine, question: str
    ) -> None:
        assessment = coverage_engine.evaluate(question)
        assert assessment.coverage_rating != CoverageRating.UNSUPPORTED, (
            f"Accessibility question classified as Unsupported: {question!r}"
        )

    @pytest.mark.parametrize("question", ACCESSIBILITY_QUESTIONS)
    def test_accessibility_question_has_available_data(
        self, coverage_engine: AnswerCoverageEngine, question: str
    ) -> None:
        assessment = coverage_engine.evaluate(question)
        assert len(assessment.available_data) > 0, (
            f"No available data returned for: {question!r}"
        )


class TestGeographicEquityPhrasings:
    """Geographic equity questions must produce a non-Unsupported rating."""

    @pytest.mark.parametrize("question", GEOGRAPHIC_EQUITY_QUESTIONS)
    def test_geographic_equity_question_not_unsupported(
        self, coverage_engine: AnswerCoverageEngine, question: str
    ) -> None:
        assessment = coverage_engine.evaluate(question)
        assert assessment.coverage_rating != CoverageRating.UNSUPPORTED, (
            f"Geographic equity question classified as Unsupported: {question!r}"
        )
