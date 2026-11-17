"""
Application factory for SSA Disability Claims OpenLens MCP Server.

Creates and configures the FastMCP application by registering all tools,
prompts, and resources. This module is the single wiring point — all
imports of service and tool modules happen here.
"""

from __future__ import annotations

from fastmcp import FastMCP

from .config import get_settings

# ── Import all tool registration functions ─────────────────────────────────────
from .tools import (
    analyze_dataset_completeness,
    assess_dataset_freshness,
    compare_datasets,
    discover_disability_datasets,
    evaluate_answer_coverage,
    explain_dataset,
    recommend_transparency_improvements,
)

# ── Import all prompt registration functions ───────────────────────────────────
from .prompts import (
    answer_coverage_evaluator,
    openlens_dataset_advisor,
    transparency_reviewer,
)

# ── Import all resource registration functions ─────────────────────────────────
from .resources import (
    answer_coverage_framework,
    disability_datasets,
    field_office_datasets,
    transparency_recommendations,
)

from .utils import get_logger

logger = get_logger(__name__)


def create_app() -> FastMCP:
    """
    Build and return the configured FastMCP application.

    Registration order:
      1. Create the FastMCP instance with server metadata
      2. Register tools (7 tools representing meaningful user goals)
      3. Register prompts (3 agent workflow prompts)
      4. Register resources (4 reference data resources)
    """
    settings = get_settings()

    mcp = FastMCP(
        name=settings.server_name,
        version=settings.server_version,
        instructions=(
            "SSA Disability Claims OpenLens is an MCP Dataset Access Server that enables "
            "AI agents to discover, understand, compare, and evaluate SSA public datasets. "
            "\n\n"
            "SIGNATURE CAPABILITY: Answer Coverage\n"
            "Use evaluate_answer_coverage to measure how well SSA public datasets support "
            "answering a specific question. This tool identifies available data, missing "
            "information, information gaps, and transparency improvement opportunities.\n\n"
            "RECOMMENDED WORKFLOW:\n"
            "1. discover_disability_datasets — find relevant datasets\n"
            "2. explain_dataset — understand contents and limitations\n"
            "3. evaluate_answer_coverage — assess data support for your question\n"
            "4. recommend_transparency_improvements — propose improvements\n\n"
            "PRIMARY USER: SSA Open Data Program Analyst"
        ),
    )

    # Register tools
    discover_disability_datasets.register(mcp)
    explain_dataset.register(mcp)
    compare_datasets.register(mcp)
    analyze_dataset_completeness.register(mcp)
    assess_dataset_freshness.register(mcp)
    evaluate_answer_coverage.register(mcp)
    recommend_transparency_improvements.register(mcp)

    # Register prompts
    openlens_dataset_advisor.register(mcp)
    transparency_reviewer.register(mcp)
    answer_coverage_evaluator.register(mcp)

    # Register resources
    disability_datasets.register(mcp)
    field_office_datasets.register(mcp)
    answer_coverage_framework.register(mcp)
    transparency_recommendations.register(mcp)

    tool_count = 7
    prompt_count = 3
    resource_count = 4
    logger.info(
        f"OpenLens MCP server configured: "
        f"{tool_count} tools, {prompt_count} prompts, {resource_count} resources"
    )

    return mcp


def run() -> None:
    """Entry point for console_scripts."""
    app = create_app()
    app.run()
