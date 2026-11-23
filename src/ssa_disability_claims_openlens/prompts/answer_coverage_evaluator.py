"""
Prompt: answer_coverage_evaluator

A prompt template for systematically evaluating Answer Coverage across
a set of benchmark questions.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.prompt(
        name="answer_coverage_evaluator",
        description=(
            "Activates the Answer Coverage Evaluator workflow. "
            "Use this prompt to systematically evaluate how well SSA public datasets "
            "support answering a set of questions, producing a comparative coverage "
            "analysis across multiple questions."
        ),
    )
    def answer_coverage_evaluator(
        questions: Annotated[
            str,
            Field(
                max_length=3000,
                description=(
                    "The questions to compare, one per line or numbered on one line, e.g. "
                    "'1) Wait times by state? 2) Allowance rates by race?'. "
                    "Leave blank and Claude will ask for them."
                ),
            ),
        ] = "",
    ) -> str:
        """
        Generate a prompt for systematic Answer Coverage evaluation.

        Args:
            questions: The questions to evaluate, one per line or numbered.
        """
        listed = questions.strip()
        questions_block = (
            f"Questions to evaluate:\n{listed}\n\n"
            if listed
            else (
                "Questions to evaluate: not provided yet. Before calling any tool, ask the "
                "user for the questions to compare (two to five works best), wait for the "
                "answer, then continue.\n\n"
            )
        )
        # A str return is sent as a single user message.
        return (
            "You are an SSA Open Data Analyst evaluating how well SSA public "
            "datasets support answering important public questions.\n\n"
            f"{questions_block}"
            "For each question:\n"
            "1. Use evaluate_answer_coverage to get the coverage assessment\n"
            "2. Record the Answer Coverage Score and Rating\n"
            "3. Note the top 2-3 missing information elements\n"
            "4. Note the top recommendation\n\n"
            "After evaluating all questions, produce a Coverage Summary Table:\n\n"
            "| Question | Score | Rating | Key Gap | Top Recommendation |\n"
            "|----------|-------|--------|---------|--------------------|\n"
            "| ...      | ...   | ...    | ...     | ...                |\n\n"
            "Then identify:\n"
            "- The question with the LOWEST coverage (most critical gap)\n"
            "- Common gaps across multiple questions\n"
            "- The single highest-impact transparency improvement\n\n"
            "Conclude with a prioritized Data Publication Roadmap."
        )
