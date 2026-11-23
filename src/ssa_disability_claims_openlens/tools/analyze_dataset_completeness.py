"""
Tool: analyze_dataset_completeness

Evaluates how completely a dataset covers geographic, temporal, and operational
dimensions of the disability domain. Produces a scored completeness analysis.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ..models import AnalyzeCompletenessInput
from ..services.dataset_analysis_service import DatasetAnalysisService
from ..services.dataset_catalog_service import get_catalog_service
from ..utils import get_logger
from ._common import (
    READ_ONLY_CLOSED,
    DatasetId,
    FocusDimensions,
    dataset_not_found,
    tool_errors,
)

logger = get_logger(__name__)

_analysis_service = DatasetAnalysisService()


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.tool(
        name="analyze_dataset_completeness",
        description=(
            "Evaluates how completely an SSA disability dataset covers geographic, temporal, "
            "and operational dimensions. Returns a scored completeness analysis identifying "
            "coverage gaps, missing dimensions, and an overall completeness rating. "
            "Use this tool when you need to understand a dataset's limitations before "
            "using it for analysis, or to identify what data is missing from the catalog. "
            "Optionally focus on specific dimensions: 'geographic', 'temporal', 'operational'."
        ),
        annotations=READ_ONLY_CLOSED,
    )
    def analyze_dataset_completeness(
        dataset_id: DatasetId,
        focus_dimensions: FocusDimensions = None,
    ) -> dict[str, Any]:
        """Evaluate dataset coverage across geographic, temporal, and operational axes."""
        with tool_errors("analyze_dataset_completeness"):
            inp = AnalyzeCompletenessInput(
                dataset_id=dataset_id,
                focus_dimensions=list(focus_dimensions or []),
            )
            catalog = get_catalog_service()
            detail = catalog.get_dataset_detail(inp.dataset_id)

            if detail is None:
                raise dataset_not_found(inp.dataset_id)

            analysis = _analysis_service.analyze_completeness(
                detail, inp.focus_dimensions or None
            )
            logger.info(
                f"analyze_dataset_completeness: {inp.dataset_id!r} → "
                f"score={analysis.completeness_score}, rating={analysis.completeness_rating}"
            )
            return analysis.model_dump(mode="json")
