"""
Tool: recommend_transparency_improvements

Generates prioritized, actionable recommendations for improving SSA public
data transparency, based on a question, topic, or identified coverage gaps.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ..models import RecommendTransparencyInput
from ..services.recommendation_service import RecommendationService
from ..utils import get_logger
from ._common import (
    READ_ONLY_CLOSED,
    FocusArea,
    MaxRecommendations,
    RecommendationContext,
    tool_errors,
)

logger = get_logger(__name__)

_recommendation_service = RecommendationService()


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.tool(
        name="recommend_transparency_improvements",
        description=(
            "Recommends specific, actionable improvements to SSA public data transparency "
            "based on a question, topic, or identified information gap. Returns a fully "
            "formatted report in the 'report' field. IMPORTANT: Always present the value "
            "of 'report' verbatim to the user — do not paraphrase, summarise, or rewrite it. "
            "When the context is a question (or a pasted evaluate_answer_coverage report), "
            "the question is assessed and recommendations are ranked by its real gaps: "
            "High closes information the question depends on most that is missing or only "
            "indirect; Medium and Low close smaller gaps or follow up on a gap already "
            "covered. Each one gives its priority_reason, and the first recommendations "
            "cover as many gaps as possible. "
            "\n\nUse this tool when an analyst wants to propose new datasets or data elements, "
            "improve answer coverage for a known gap, or build a data publication roadmap. "
            "Works best when given the output of evaluate_answer_coverage as context."
        ),
        annotations=READ_ONLY_CLOSED,
    )
    def recommend_transparency_improvements(
        context: RecommendationContext,
        focus_area: FocusArea = None,
        max_recommendations: MaxRecommendations = 5,
    ) -> dict[str, Any]:
        """Generate prioritized transparency improvement recommendations.

        Present the 'report' field verbatim — do not paraphrase it.
        """
        with tool_errors("recommend_transparency_improvements"):
            inp = RecommendTransparencyInput(
                context=context,
                focus_area=focus_area,
                max_recommendations=max_recommendations,
            )
            plan = _recommendation_service.generate_recommendations(
                context=inp.context,
                focus_area=inp.focus_area,
                max_recommendations=inp.max_recommendations,
            )
            logger.info(
                f"recommend_transparency_improvements: "
                f"generated {plan.total_recommendations} recommendations "
                f"({plan.high_priority_count} high priority)"
            )
            return {"report": plan.format_report()}
