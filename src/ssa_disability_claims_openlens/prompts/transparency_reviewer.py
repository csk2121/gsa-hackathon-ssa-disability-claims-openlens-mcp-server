"""
Prompt: transparency_reviewer

A persona prompt for reviewing SSA public data transparency and generating
a structured improvement plan.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.prompt(
        name="transparency_reviewer",
        description=(
            "Activates the SSA Transparency Reviewer persona. "
            "Use this prompt to conduct a structured review of SSA public data transparency "
            "for a specific program area or policy topic, and generate a prioritized "
            "improvement plan."
        ),
    )
    def transparency_reviewer(program_area: str) -> list[dict[str, Any]]:
        """Generate a transparency review prompt for a specific SSA program area."""
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        "You are an SSA Transparency Reviewer conducting a structured "
                        "assessment of public data availability for the following program area.\n\n"
                        f"Program area: {program_area}\n\n"
                        "Conduct a transparency review using this workflow:\n\n"
                        "STEP 1 — Catalog review\n"
                        "Use discover_disability_datasets to find all datasets relevant to "
                        f"'{program_area}'.\n\n"
                        "STEP 2 — Completeness assessment\n"
                        "For each relevant dataset, use analyze_dataset_completeness to "
                        "evaluate coverage gaps.\n\n"
                        "STEP 3 — Freshness assessment\n"
                        "Use assess_dataset_freshness to identify any stale datasets.\n\n"
                        "STEP 4 — Answer Coverage test\n"
                        "Identify 2-3 questions that stakeholders commonly ask about "
                        f"'{program_area}'. Use evaluate_answer_coverage for each.\n\n"
                        "STEP 5 — Recommendations\n"
                        "Use recommend_transparency_improvements to generate a prioritized "
                        "improvement plan.\n\n"
                        "Produce a structured Transparency Review Report with:\n"
                        "- Executive summary\n"
                        "- Dataset inventory\n"
                        "- Coverage gaps\n"
                        "- Freshness issues\n"
                        "- Answer Coverage results for key questions\n"
                        "- Prioritized recommendations"
                    ),
                },
            }
        ]
