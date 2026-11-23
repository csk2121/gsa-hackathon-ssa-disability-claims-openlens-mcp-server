"""
Tool: evaluate_answer_coverage  ← SIGNATURE TOOL

Evaluates how well SSA public datasets support answering a natural language question.
Returns a pre-formatted assessment report as the primary output field.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ..models import EvaluateAnswerCoverageInput
from ..services.answer_coverage_service import get_answer_coverage_engine
from ..utils import get_logger
from ._common import READ_ONLY_CLOSED, Question, tool_errors

logger = get_logger(__name__)


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.tool(
        name="evaluate_answer_coverage",
        description=(
            "SIGNATURE TOOL: Evaluates how well SSA public datasets support answering a "
            "specific natural language question. Returns a fully formatted assessment report "
            "in the 'report' field. IMPORTANT: Always present the value of 'report' verbatim "
            "to the user — do not paraphrase, summarise, or rewrite it. "
            "The report contains: intent analysis, answer coverage rating, available datasets, "
            "missing information, gap analysis, and transparency recommendations. "
            "\n\nUse this tool when an analyst or the public wants to know: "
            "'Can SSA public data answer this question?' Examples: "
            "'How long are people waiting for disability decisions by state?', "
            "'Are there racial disparities in disability allowance rates?', "
            "'Which field offices have the longest backlogs?', "
            "'What data should SSA publish to improve transparency?'"
        ),
        annotations=READ_ONLY_CLOSED,
    )
    def evaluate_answer_coverage(
        question: Question,
    ) -> dict[str, Any]:
        """
        Assess how well SSA public datasets support answering a question.
        Present the 'report' field verbatim — do not paraphrase it.
        """
        with tool_errors("evaluate_answer_coverage"):
            inp = EvaluateAnswerCoverageInput(
                question=question,
                include_recommendations=True,
            )
            engine = get_answer_coverage_engine()
            # The rating uses only the grounded catalog (deterministic, offline).
            assessment = engine.evaluate(inp.question)

            logger.info(
                f"evaluate_answer_coverage: score={assessment.answer_coverage_score}, "
                f"rating={assessment.coverage_rating.value}"
            )

            # Return only the report field.
            # Returning additional fields (coverage_rating, datasets_consulted)
            # gives the LLM content to paraphrase instead of copy.
            # The report already contains all information the user needs.
            return {
                "report": assessment.format_report(),
            }
