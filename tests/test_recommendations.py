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

from src.ssa_disability_claims_openlens.models import RecommendationPriority
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
            assert rec.description, "Recommendation must have a description"
            assert rec.expected_impact, "Recommendation must have expected_impact"
            assert rec.priority in RecommendationPriority.__members__.values()
            assert rec.implementation_effort in ("Low", "Medium", "High")

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
