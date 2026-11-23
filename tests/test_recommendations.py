"""
Unit tests for recommend_transparency_improvements tool.

Tests:
- Returns prioritized recommendations for a known topic
- High-priority recommendations appear first
- Each recommendation has required fields
- Executive summary is generated
- Generic recommendations returned for unknown topic
- max_recommendations limit is respected
"""

from __future__ import annotations

import pytest

from src.ssa_disability_claims_openlens.models import InformationElement, RecommendationPriority
from src.ssa_disability_claims_openlens.services import answer_coverage_service as acs
from src.ssa_disability_claims_openlens.services import recommendation_service as rs
from src.ssa_disability_claims_openlens.services.recommendation_service import (
    RecommendationService,
)


class TestRecommendTransparencyImprovements:
    def test_processing_time_topic_returns_recommendations(
        self, recommendation_service: RecommendationService
    ) -> None:
        plan = recommendation_service.generate_recommendations(
            context="How long are people waiting for disability decisions?"
        )
        assert plan.total_recommendations > 0
        assert any(
            "processing" in r.title.lower() or "wait" in r.title.lower()
            for r in plan.recommendations
        )

    def test_race_equity_topic_returns_recommendations(
        self, recommendation_service: RecommendationService
    ) -> None:
        plan = recommendation_service.generate_recommendations(
            context="Are there racial disparities in disability allowance rates?"
        )
        assert plan.total_recommendations > 0
        assert any(
            "race" in r.title.lower() or "ethnicity" in r.title.lower() or "demographic" in r.title.lower()
            for r in plan.recommendations
        )

    def test_max_recommendations_respected(
        self, recommendation_service: RecommendationService
    ) -> None:
        plan = recommendation_service.generate_recommendations(
            context="processing time wait backlog delay",
            max_recommendations=2,
        )
        assert plan.total_recommendations <= 2
        assert len(plan.recommendations) <= 2

    def test_high_priority_count_accurate(
        self, recommendation_service: RecommendationService
    ) -> None:
        plan = recommendation_service.generate_recommendations(
            context="processing time wait backlog delay race equity demographic"
        )
        expected_high = sum(
            1 for r in plan.recommendations
            if r.priority == RecommendationPriority.HIGH
        )
        assert plan.high_priority_count == expected_high

    def test_each_recommendation_has_required_fields(
        self, recommendation_service: RecommendationService
    ) -> None:
        plan = recommendation_service.generate_recommendations(
            context="field office access appointment wait times"
        )
        for rec in plan.recommendations:
            assert rec.title, "Recommendation must have a title"
            assert rec.closes_gap, "Recommendation must have closes_gap"
            assert rec.justification, "Recommendation must have a justification"
            assert rec.expected_impact, "Recommendation must have expected_impact"
            assert rec.priority in RecommendationPriority.__members__.values()

    def test_executive_summary_generated(
        self, recommendation_service: RecommendationService
    ) -> None:
        plan = recommendation_service.generate_recommendations(
            context="geographic equity state disparities allowance rate"
        )
        assert len(plan.executive_summary) > 20

    def test_focus_area_narrows_recommendations(
        self, recommendation_service: RecommendationService
    ) -> None:
        broad_plan = recommendation_service.generate_recommendations(
            context="SSA data improvement", max_recommendations=10
        )
        focused_plan = recommendation_service.generate_recommendations(
            context="SSA data improvement",
            focus_area="processing_time",
            max_recommendations=10,
        )
        # Focused plan should contain more processing-time-related recommendations
        broad_processing = sum(
            1 for r in broad_plan.recommendations
            if "processing" in r.title.lower() or "wait" in r.title.lower()
        )
        focused_processing = sum(
            1 for r in focused_plan.recommendations
            if "processing" in r.title.lower() or "wait" in r.title.lower()
        )
        # Focused should be at least as many processing recs as broad
        assert focused_processing >= broad_processing

    def test_no_duplicate_recommendations(
        self, recommendation_service: RecommendationService
    ) -> None:
        plan = recommendation_service.generate_recommendations(
            context="processing time wait racial equity demographic geographic state",
            max_recommendations=20,
        )
        titles = [r.title for r in plan.recommendations]
        assert len(titles) == len(set(titles)), "Duplicate recommendation titles found"

    def test_model_validates_total_and_high_count(
        self, recommendation_service: RecommendationService
    ) -> None:
        plan = recommendation_service.generate_recommendations(
            context="all topics processing time racial equity geographic",
            max_recommendations=10,
        )
        assert plan.total_recommendations == len(plan.recommendations)
        assert plan.high_priority_count >= 0


# ── Gap-driven context and keyword matching ───────────────────────────────────


class TestGapNamedContext:
    def test_only_recommendations_for_named_gaps_are_returned(
        self, recommendation_service: RecommendationService
    ) -> None:
        gaps = {
            "Disability claim processing times",
            "Field office operational metrics (staffing, volume, wait times)",
        }
        plan = recommendation_service.generate_recommendations(
            context="Gaps found: " + "; ".join(sorted(gaps)) + ". Hearing offices are not mapped.",
            focus_area="processing times",
            max_recommendations=10,
        )
        assert plan.recommendations
        assert {r.closes_gap for r in plan.recommendations} <= gaps

    def test_office_decision_time_gap_has_recommendations(
        self, recommendation_service: RecommendationService
    ) -> None:
        plan = recommendation_service.generate_recommendations(
            context="Gap: Disability decision times by field office or DDS"
        )
        assert plan.recommendations
        assert all(
            r.closes_gap == "Disability decision times by field office or DDS"
            for r in plan.recommendations
        )


class TestKeywordMatching:
    def test_short_keywords_do_not_match_inside_words(self) -> None:
        assert not rs._keyword_in_text("ssi", "processing")
        assert not rs._keyword_in_text("ratio", "operational metrics")

    def test_keywords_match_plurals_and_stems(self) -> None:
        assert rs._keyword_in_text("time", "processing times")
        assert rs._keyword_in_text("wait", "people waiting")
        assert rs._keyword_in_text("disparit", "racial disparities")

    def test_focus_area_names_a_topic_with_spaces_or_plurals(self) -> None:
        for focus in ("processing_time", "processing time", "Processing Times", "processing-time"):
            assert rs._focus_matches_topic(focus, "processing_time"), focus
        assert not rs._focus_matches_topic("processing times", "staffing_workload")


def test_field_office_recommendations_cite_the_datasets_they_extend() -> None:
    """The locator is a contact list; recs about visits, staff or waits extend other datasets."""
    topic = next(t for t in rs._RECOMMENDATION_KB if t["topic"] == "field_office_access")
    for rec in topic["recommendations"]:
        if rec.closes_gap == "SSA field office locations and coverage":
            continue
        assert rec.affected_datasets != ["ssa-field-office-locator"], rec.title


# ── Priorities derived from the gaps a question really has ────────────────────

ACCESS_Q = (
    "If SSA wanted to maximize public understanding of disability service accessibility, "
    "what additional datasets or metrics should be published first?"
)
FIELD_OFFICE_Q = "Which field offices have the longest decision wait times?"
OPS = "Field office operational metrics (staffing, volume, wait times)"
DECISION = "Disability decision times by field office or DDS"
PROCESSING = "Disability claim processing times"
TRAVEL = "Travel distance to nearest SSA field office"


def _el(name: str, quality: str) -> InformationElement:
    return InformationElement(
        element=name, description="", available=quality != "None", coverage_quality=quality
    )


class TestDerivedPriority:
    def test_gap_severity_matches_the_coverage_points(self) -> None:
        for quality, severity in rs._GAP_SEVERITY.items():
            assert severity == pytest.approx(1 - acs._QUALITY_SCORE[quality]), quality

    @pytest.mark.parametrize(
        ("quality", "weight", "expected"),
        [
            ("None", 2, "High"), ("Proxy", 2, "High"), ("None", 1, "High"),
            ("Partial", 2, "Medium"), ("Proxy", 1, "Medium"), ("Partial", 1, "Low"),
        ],
    )
    def test_priority_table(self, quality: str, weight: int, expected: str) -> None:
        priority, reason = rs._gap_priority(quality, weight, 0, RecommendationPriority.HIGH)
        assert priority.value == expected
        assert ("critical" if weight == 2 else "supporting") in reason

    def test_follow_ups_drop_one_level_and_never_exceed_the_kb_priority(self) -> None:
        high, medium, low = (RecommendationPriority.HIGH, RecommendationPriority.MEDIUM,
                             RecommendationPriority.LOW)
        assert rs._gap_priority("Proxy", 2, 1, high)[0] == medium
        assert rs._gap_priority("Partial", 1, 1, high)[0] == low
        assert rs._gap_priority("None", 2, 0, medium)[0] == medium
        assert rs._gap_priority("Proxy", 2, 1, high)[1].startswith("Follow-up: ")

    def test_first_recommendations_cover_each_gap_before_follow_ups(
        self, recommendation_service: RecommendationService
    ) -> None:
        recs = recommendation_service.for_gaps(
            [_el(DECISION, "Proxy"), _el(OPS, "Proxy"), _el(PROCESSING, "Partial")],
            weights=[2, 2, 1],
        )
        assert [r.closes_gap for r in recs[:2]] == [DECISION, OPS]
        assert all(r.priority == RecommendationPriority.HIGH for r in recs[:2])
        assert all(r.priority != RecommendationPriority.HIGH for r in recs[2:])
        assert all(r.priority_reason for r in recs)
        assert recs[-1].closes_gap == PROCESSING
        assert recs[-1].priority == RecommendationPriority.LOW

    def test_kb_recommendations_are_not_modified(
        self, recommendation_service: RecommendationService
    ) -> None:
        before = [r.priority for r in rs._GAP_INDEX[OPS]]
        recommendation_service.for_gaps([_el(OPS, "Partial")], weights=[1])
        assert [r.priority for r in rs._GAP_INDEX[OPS]] == before
        assert all(not r.priority_reason for r in rs._GAP_INDEX[OPS])

    def test_without_weights_kb_priorities_are_kept(
        self, recommendation_service: RecommendationService
    ) -> None:
        recs = recommendation_service.for_gaps([_el(OPS, "Partial")])
        kb = {r.title: r.priority for r in rs._GAP_INDEX[OPS]}
        assert all(r.priority == kb[r.title] and not r.priority_reason for r in recs)

    def test_what_to_publish_first_is_not_all_high(
        self, recommendation_service: RecommendationService
    ) -> None:
        plan = recommendation_service.generate_recommendations(ACCESS_Q, max_recommendations=6)
        priorities = [r.priority for r in plan.recommendations]
        assert RecommendationPriority.HIGH in priorities
        assert len(set(priorities)) > 1, priorities
        assert plan.high_priority_count < plan.total_recommendations
        assert plan.recommendations[0].closes_gap == TRAVEL  # unpublished critical info first
        high_gaps = [
            r.closes_gap for r in plan.recommendations if r.priority == RecommendationPriority.HIGH
        ]
        assert len(high_gaps) == len(set(high_gaps)), "each High recommendation closes a different gap"

    def test_pasted_report_is_ranked_by_its_question(
        self, recommendation_service: RecommendationService
    ) -> None:
        report = acs.get_answer_coverage_engine().evaluate(FIELD_OFFICE_Q).format_report()
        assert rs._question_from_context(report) == FIELD_OFFICE_Q
        plan = recommendation_service.generate_recommendations(report, max_recommendations=6)
        assert [r.closes_gap for r in plan.recommendations[:2]] == [DECISION, OPS]
        assert plan.recommendations[0].priority == RecommendationPriority.HIGH
        assert all(r.priority_reason for r in plan.recommendations)

    def test_one_publication_is_one_recommendation_under_each_gap_it_closes(
        self, recommendation_service: RecommendationService
    ) -> None:
        """Found by the agent evaluation: visit volumes and staffing each appeared twice."""
        plan = recommendation_service.generate_recommendations(ACCESS_Q, max_recommendations=20)
        titles = [r.title for r in plan.recommendations]
        assert sum("visit volumes" in t for t in titles) == 1, titles
        assert sum("FTE" in t for t in titles) == 1, titles
        first_by_gap: dict[str, str] = {}
        for r in plan.recommendations:
            first_by_gap.setdefault(r.closes_gap, r.title)
        assert "visit volumes" in first_by_gap["Field office appointment and walk-in volume"]
        assert "FTE" in first_by_gap["SSA office staffing levels"]

    def test_a_shared_recommendation_is_presented_under_the_gap_the_question_has(
        self, recommendation_service: RecommendationService
    ) -> None:
        recs = recommendation_service.for_gaps([_el(OPS, "Proxy")], weights=[2])
        shared = next(r for r in recs if "FTE" in r.title)
        assert shared.closes_gap == OPS
        assert "SSA office staffing levels" in shared.also_closes

    def test_long_context_without_a_report_uses_the_keyword_lookup(self) -> None:
        assert rs._question_from_context("processing times " * 40) is None
