"""
routes.py — Alternative route registration approach for frameworks that need it.

In FastMCP, tools/prompts/resources are registered directly on the FastMCP instance
via decorators. This module provides a register_all() helper for use in testing
and alternate embedding scenarios.
"""

from __future__ import annotations

from fastmcp import FastMCP

from .tools import (
    analyze_dataset_completeness,
    assess_dataset_freshness,
    compare_datasets,
    discover_disability_datasets,
    evaluate_answer_coverage,
    explain_dataset,
    recommend_transparency_improvements,
)
from .prompts import (
    answer_coverage_evaluator,
    openlens_dataset_advisor,
    transparency_reviewer,
)
from .resources import (
    answer_coverage_framework,
    disability_datasets,
    field_office_datasets,
    transparency_recommendations,
)


def register_all(mcp: FastMCP) -> FastMCP:
    """Register all tools, prompts, and resources onto an existing FastMCP instance."""
    # Tools
    discover_disability_datasets.register(mcp)
    explain_dataset.register(mcp)
    compare_datasets.register(mcp)
    analyze_dataset_completeness.register(mcp)
    assess_dataset_freshness.register(mcp)
    evaluate_answer_coverage.register(mcp)
    recommend_transparency_improvements.register(mcp)

    # Prompts
    openlens_dataset_advisor.register(mcp)
    transparency_reviewer.register(mcp)
    answer_coverage_evaluator.register(mcp)

    # Resources
    disability_datasets.register(mcp)
    field_office_datasets.register(mcp)
    answer_coverage_framework.register(mcp)
    transparency_recommendations.register(mcp)

    return mcp
