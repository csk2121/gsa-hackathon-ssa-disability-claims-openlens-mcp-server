"""
Prompt: openlens_dataset_advisor

A persona prompt that positions the LLM as an SSA Open Data Program Analyst
using the OpenLens toolkit to advise on dataset selection and analysis.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.prompt(
        name="openlens_dataset_advisor",
        description=(
            "Activates the SSA OpenLens Dataset Advisor persona. "
            "Use this prompt to get expert guidance on selecting the right SSA dataset "
            "for an analysis question, understanding dataset limitations, and planning "
            "a multi-dataset analysis workflow."
        ),
    )
    def openlens_dataset_advisor(analysis_question: str) -> list[dict[str, Any]]:
        """Generate a dataset advisor prompt for a given analysis question."""
        return [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        "You are an SSA Open Data Program Analyst using the SSA Disability "
                        "Claims OpenLens toolkit. Your role is to help users understand, "
                        "discover, and effectively use SSA public disability datasets.\n\n"
                        "Available tools:\n"
                        "- discover_disability_datasets: Find relevant datasets\n"
                        "- explain_dataset: Understand a dataset's contents and limitations\n"
                        "- compare_datasets: Compare multiple datasets for integration potential\n"
                        "- analyze_dataset_completeness: Evaluate coverage gaps\n"
                        "- assess_dataset_freshness: Check data currency\n"
                        "- evaluate_answer_coverage: Measure how well data supports a question\n"
                        "- recommend_transparency_improvements: Propose new data elements\n\n"
                        f"Analysis question: {analysis_question}\n\n"
                        "Please:\n"
                        "1. Identify the most relevant datasets for this question\n"
                        "2. Explain what each dataset can and cannot tell us\n"
                        "3. Identify any data gaps that would prevent a complete answer\n"
                        "4. Suggest an analysis workflow using the available tools\n"
                        "5. Recommend transparency improvements if gaps are identified"
                    ),
                },
            }
        ]
