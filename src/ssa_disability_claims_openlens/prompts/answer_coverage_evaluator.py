"""
Prompt: answer_coverage_evaluator

A prompt template for systematically evaluating Answer Coverage across
a set of benchmark questions.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP


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
    def answer_coverage_evaluator(questions: str) -> list[dict[str, Any]]:
        """
        Generate a prompt for systematic Answer Coverage evaluation.

        Args:
            questions: Newline-separated list of questions to evaluate.
        """
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        "You are an SSA Open Data Analyst evaluating how well SSA public "
                        "datasets support answering important public questions.\n\n"
                        "Questions to evaluate:\n"
                        f"{questions}\n\n"
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
                    ),
                },
            }
        ]
