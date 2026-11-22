"""
Unit tests for evaluate_answer_coverage tool — the SIGNATURE TOOL.

Tests:
- Returns AnswerCoverageAssessment for well-known questions
- Score is in 0–100 range
- Coverage rating matches score thresholds
- Available data is populated for matched elements
- Missing information is populated for unmatched elements
- Gap analysis identifies critical vs. partial gaps
- Transparency recommendations are actionable strings
- Unsupported question returns UNSUPPORTED rating
- format_report() produces structured output
"""

from __future__ import annotations

from src.ssa_disability_claims_openlens.models import CoverageRating
from src.ssa_disability_claims_openlens.services.answer_coverage_service import (
    AnswerCoverageEngine,
)


class TestEvaluateAnswerCoverage:
    # Questions expected to have PARTIAL or higher coverage
    PARTIALLY_SUPPORTED_QUESTIONS = [
        "How many people are receiving SSDI benefits by state?",
        "What is the average processing time for disability appeals?",
        "How many SSI recipients are there in California?",
        "What is the disability claim allowance rate?",
        "Where are SSA field offices located?",
    ]

    # Questions expected to have LIMITED or UNSUPPORTED coverage
    LOW_COVERAGE_QUESTIONS = [
        "Are there racial disparities in disability allowance rates?",
        "How long are appointment wait times at field offices?",
        "How many staff work at each hearing office?",
    ]

    def test_score_in_valid_range(self, coverage_engine: AnswerCoverageEngine) -> None:
        for q in self.PARTIALLY_SUPPORTED_QUESTIONS + self.LOW_COVERAGE_QUESTIONS:
            assessment = coverage_engine.evaluate(q)
            assert 0.0 <= assessment.answer_coverage_score <= 100.0, (
                f"Score {assessment.answer_coverage_score} out of range for: {q}"
            )

    def test_coverage_rating_matches_score(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        for q in self.PARTIALLY_SUPPORTED_QUESTIONS + self.LOW_COVERAGE_QUESTIONS:
            assessment = coverage_engine.evaluate(q)
            score = assessment.answer_coverage_score
            rating = assessment.coverage_rating
            if score >= 90:
                assert rating == CoverageRating.COMPLETE
            elif score >= 75:
                assert rating == CoverageRating.HIGH
            elif score >= 40:
                assert rating == CoverageRating.PARTIAL
            elif score >= 15:
                assert rating == CoverageRating.LIMITED
            else:
                assert rating == CoverageRating.UNSUPPORTED

    def test_beneficiary_question_returns_partial_or_higher(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(
            "How many people are receiving SSDI benefits by state?"
        )
        assert assessment.coverage_rating in (
            CoverageRating.COMPLETE,
            CoverageRating.HIGH,
            CoverageRating.PARTIAL,
        )
        assert assessment.answer_coverage_score >= 40.0

    def test_race_question_returns_limited_or_lower(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(
            "Are there racial disparities in disability allowance rates?"
        )
        # Race/ethnicity data is not published — should be low coverage
        assert assessment.answer_coverage_score < 50.0
        assert len(assessment.missing_information) > 0

    def test_field_office_wait_time_question_has_gaps(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(
            "How long are appointment wait times at SSA field offices?"
        )
        # Only a discontinued national series exists (US-GOV-SSA-431), so the
        # element is a partial gap rather than wholly missing.
        gaps = assessment.gap_analysis.critical_gaps + assessment.gap_analysis.partial_gaps
        assert "Field office appointment wait times" in gaps, (
            "Field office appointment wait times should be identified as a gap"
        )

    def test_gap_analysis_populated(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(
            "What are disability claim processing times by state?"
        )
        gap = assessment.gap_analysis
        assert gap.impact_on_answer, "Gap analysis must have an impact statement"
        assert isinstance(gap.critical_gaps, list)
        assert isinstance(gap.partial_gaps, list)

    def test_transparency_recommendations_are_strings(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(
            "Are there racial disparities in disability allowance rates?"
        )
        for rec in assessment.transparency_recommendations:
            assert isinstance(rec, str)
            assert len(rec) > 10

    def test_unsupported_question_returns_unsupported(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(
            "What is the weather like in Washington DC today?"
        )
        assert assessment.coverage_rating == CoverageRating.UNSUPPORTED
        assert assessment.answer_coverage_score < 15.0

    def test_format_report_contains_required_sections(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(
            "How many people are waiting for disability hearings by state?"
        )
        report = assessment.format_report()
        assert "Answer Coverage" in report
        assert "Available Data" in report
        assert "Missing Information" in report
        assert "Gap Analysis" in report
        assert "Transparency Recommendations" in report
        assert "Potential Impact" in report

    def test_processing_time_question_has_available_data(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(
            "What is the average processing time for disability appeals?"
        )
        assert len(assessment.available_data) > 0

    def test_datasets_consulted_are_valid_ids(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        from src.ssa_disability_claims_openlens.services.dataset_catalog_service import (
            StaticCatalogAdapter,
        )
        adapter = StaticCatalogAdapter()
        valid_ids = set(adapter.all_dataset_ids())

        assessment = coverage_engine.evaluate(
            "How many SSDI beneficiaries are there in Texas?"
        )
        for did in assessment.datasets_consulted:
            assert did in valid_ids, f"Referenced unknown dataset: {did}"

    def test_question_is_preserved_in_output(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        question = "How long do people wait for disability decisions by state?"
        assessment = coverage_engine.evaluate(question)
        assert assessment.question == question

    def test_potential_impact_is_non_empty(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        assessment = coverage_engine.evaluate(
            "What are disability claim processing times by state?"
        )
        assert len(assessment.potential_impact) > 20


class TestDistinctIntentRouting:
    """
    Regression tests: questions with different user intent must produce
    distinct reports. These tests encode the specific bug where "what should
    SSA publish?" and "assess current coverage" collapsed to identical output.
    """

    Q_PUBLISH = (
        "If SSA wanted to maximize public understanding of disability service "
        "accessibility, what additional datasets or metrics should be published first?"
    )
    Q_ASSESS = (
        "Assess the ability of current SSA public datasets to support public "
        "understanding of disability service accessibility."
    )

    def test_publish_question_routes_to_policy_intent(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        a = coverage_engine.evaluate(self.Q_PUBLISH)
        assert a.intent is not None
        assert a.intent.intent_category == "Policy", (
            f"Expected 'Policy' intent, got '{a.intent.intent_category}'"
        )

    def test_assess_question_routes_to_access_intent(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        a = coverage_engine.evaluate(self.Q_ASSESS)
        assert a.intent is not None
        assert a.intent.intent_category == "Access", (
            f"Expected 'Access' intent, got '{a.intent.intent_category}'"
        )

    def test_primary_intents_are_different(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        a1 = coverage_engine.evaluate(self.Q_PUBLISH)
        a2 = coverage_engine.evaluate(self.Q_ASSESS)
        assert a1.intent is not None and a2.intent is not None
        assert a1.intent.primary_intent != a2.intent.primary_intent, (
            "Both questions mapped to the same primary intent — intent routing is broken"
        )

    def test_reports_are_not_identical(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        r1 = coverage_engine.evaluate(self.Q_PUBLISH).format_report()
        r2 = coverage_engine.evaluate(self.Q_ASSESS).format_report()
        assert r1 != r2, (
            "Both questions produced identical reports — "
            "the intent split is not propagating to report content"
        )

    def test_potential_impacts_are_different(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        a1 = coverage_engine.evaluate(self.Q_PUBLISH)
        a2 = coverage_engine.evaluate(self.Q_ASSESS)
        assert a1.potential_impact != a2.potential_impact, (
            "Both questions produced the same Potential Impact — "
            "intent-specific potential_impact branch is not firing"
        )

    def test_publish_question_potential_impact_mentions_prioritisation(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        """The roadmap question must reference prioritisation/publication order."""
        a = coverage_engine.evaluate(self.Q_PUBLISH)
        impact_lower = a.potential_impact.lower()
        assert any(w in impact_lower for w in ["priority", "highest-priority", "first", "published"]), (
            "Policy intent potential_impact should mention publication priority"
        )

    def test_assess_question_potential_impact_mentions_evaluation(
        self, coverage_engine: AnswerCoverageEngine
    ) -> None:
        """The assessment question must reference evaluating existing coverage."""
        a = coverage_engine.evaluate(self.Q_ASSESS)
        impact_lower = a.potential_impact.lower()
        assert any(w in impact_lower for w in ["rural", "urban", "geographic", "evaluate"]), (
            "Access intent potential_impact should mention geographic/evaluation framing"
        )
