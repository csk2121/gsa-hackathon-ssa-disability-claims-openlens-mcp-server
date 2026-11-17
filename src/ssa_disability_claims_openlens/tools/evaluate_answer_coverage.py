"""
Tool: evaluate_answer_coverage  ← SIGNATURE TOOL

Evaluates how well SSA public datasets support answering a natural language question.
Produces an AnswerCoverageAssessment with a numeric score, coverage rating,
available data, missing information, gap analysis, and transparency recommendations.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ..models import EvaluateAnswerCoverageInput
from ..services.answer_coverage_service import get_answer_coverage_engine
from ..utils import get_logger

logger = get_logger(__name__)


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.tool(
        name="evaluate_answer_coverage",
        description=(
            "SIGNATURE TOOL: Evaluates how well SSA public datasets support answering a "
            "specific natural language question. Identifies which information elements are "
            "available vs. missing, calculates an Answer Coverage Score (0–100), assigns a "
            "qualitative rating (Complete / High / Partial / Limited / Unsupported), "
            "performs a gap analysis, and recommends transparency improvements. "
            "\n\nUse this tool when an analyst or the public wants to know: "
            "'Can SSA public data answer this question?' Examples: "
            "'How long are people waiting for disability decisions by state?', "
            "'Are there racial disparities in disability allowance rates?', "
            "'Which field offices have the longest backlogs?'"
        ),
    )
    def evaluate_answer_coverage(
        question: str,
        include_recommendations: bool = True,
    ) -> dict:  # type: ignore[return]
        """
        Assess Answer Coverage: how well SSA public datasets support answering a question.
        """
        try:
            inp = EvaluateAnswerCoverageInput(
                question=question,
                include_recommendations=include_recommendations,
            )
            engine = get_answer_coverage_engine()
            assessment = engine.evaluate(inp.question)

            # Optionally strip recommendations from output
            result_dict = assessment.model_dump(mode="json")
            if not inp.include_recommendations:
                result_dict.pop("transparency_recommendations", None)

            # Add the formatted report as a convenience field
            result_dict["formatted_report"] = assessment.format_report()

            logger.info(
                f"evaluate_answer_coverage: score={assessment.answer_coverage_score}, "
                f"rating={assessment.coverage_rating.value}"
            )
            return result_dict
        except Exception as exc:  # noqa: BLE001
            logger.error(f"evaluate_answer_coverage failed: {exc}")
            return {"error": str(exc)}
