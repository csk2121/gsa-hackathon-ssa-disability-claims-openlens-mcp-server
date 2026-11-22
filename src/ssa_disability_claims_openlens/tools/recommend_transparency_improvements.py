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

logger = get_logger(__name__)

_recommendation_service = RecommendationService()


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.tool(
        name="recommend_transparency_improvements",
        description=(
            "Recommends specific, actionable improvements to SSA public data transparency "
            "based on a question, topic, or identified information gap. Each recommendation "
            "includes new data elements to publish, expected public impact, and implementation "
            "effort. Recommendations are ranked by priority (High / Medium / Low). "
            "\n\nUse this tool when an analyst wants to propose new datasets or data elements, "
            "improve answer coverage for a known gap, or build a data publication roadmap. "
            "Works best when given the output of evaluate_answer_coverage as context."
        ),
    )
    def recommend_transparency_improvements(
        context: str,
        focus_area: str | None = None,
        max_recommendations: int = 5,
    ) -> dict[str, Any]:
        """Generate prioritized transparency improvement recommendations."""
        try:
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
            return plan.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"recommend_transparency_improvements failed: {exc}")
            return {"error": str(exc)}
