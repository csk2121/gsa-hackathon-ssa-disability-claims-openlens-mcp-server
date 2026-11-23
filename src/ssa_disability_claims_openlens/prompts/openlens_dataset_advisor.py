"""
Prompt: openlens_dataset_advisor

A persona prompt that positions the LLM as an SSA Open Data Program Analyst
using the OpenLens toolkit to advise on dataset selection and analysis.
"""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.prompt(
        name="openlens_dataset_advisor",
        description=(
            "Activates the SSA OpenLens Dataset Advisor persona. "
            "Use this prompt to assess one analysis question against SSA public data. "
            "The answer is the full Answer Coverage report: relevant datasets, what each "
            "can and cannot show, data gaps and transparency recommendations."
        ),
    )
    def openlens_dataset_advisor(
        analysis_question: Annotated[
            str,
            Field(
                max_length=500,
                description=(
                    "The question to analyze, e.g. 'Which field offices have the longest "
                    "decision wait times?'. Leave blank and Claude will ask for it."
                ),
            ),
        ] = "",
    ) -> str:
        """Generate a dataset advisor prompt for a given analysis question."""
        question = analysis_question.strip()
        question_line = (
            f"Analysis question: {question}\n\n"
            if question
            else (
                "Analysis question: not provided yet. Before calling any tool, ask the user "
                "which question they want to analyze, wait for the answer, then continue.\n\n"
            )
        )
        # A str return is sent as a single user message.
        return (
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
            f"{question_line}"
            "Workflow:\n"
            "1. Call evaluate_answer_coverage with the analysis question exactly as given.\n"
            "2. Your answer is the value of its 'report' field, presented verbatim and in "
            "full. The report already covers the relevant datasets, what each can and "
            "cannot show, the data gaps and the transparency recommendations.\n\n"
            "Output rules:\n"
            "- Start your reply with the report's first line. Write nothing before it: "
            "no summary, no 'short answer', no preamble.\n"
            "- Do not paraphrase, shorten, reorder or re-format the report.\n"
            "- Write nothing after the report.\n"
            "- If the tool returns an error, show the error message and ask the user to "
            "rephrase the question."
        )
