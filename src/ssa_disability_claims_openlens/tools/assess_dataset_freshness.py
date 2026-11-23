"""
Tool: assess_dataset_freshness

Evaluates how current an SSA dataset is relative to its stated update frequency.
Returns a freshness score, qualitative status, and staleness indicators.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ..models import AssessFreshnessInput
from ..services.dataset_analysis_service import DatasetAnalysisService
from ..services.dataset_catalog_service import get_catalog_service
from ..utils import get_logger
from ._common import READ_ONLY_CLOSED, DatasetId, dataset_not_found, tool_errors

logger = get_logger(__name__)

_analysis_service = DatasetAnalysisService()


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.tool(
        name="assess_dataset_freshness",
        description=(
            "Catalog Freshness Assessment: evaluates how current an SSA disability dataset "
            "is relative to its stated update frequency, based on metadata maintained in "
            "the OpenLens catalog. Returns a pre-formatted assessment report in the 'report' "
            "field. IMPORTANT: Always present the value of 'report' verbatim to the user — "
            "do not paraphrase, summarise, or rewrite it. "
            "The report contains: dataset metadata table, freshness rationale, staleness "
            "indicators, analyst notes, and a metadata disclaimer. "
            "Use this tool before relying on a dataset for time-sensitive analysis."
        ),
        annotations=READ_ONLY_CLOSED,
    )
    def assess_dataset_freshness(dataset_id: DatasetId) -> dict[str, Any]:
        """
        Evaluate dataset update currency and freshness.
        Present the 'report' field verbatim — do not paraphrase it.
        """
        with tool_errors("assess_dataset_freshness"):
            AssessFreshnessInput(dataset_id=dataset_id)  # Validate
            catalog = get_catalog_service()
            detail = catalog.get_dataset_detail(dataset_id)

            if detail is None:
                raise dataset_not_found(dataset_id)

            assessment = _analysis_service.assess_freshness(detail)
            logger.info(
                f"assess_dataset_freshness: {dataset_id!r} → "
                f"score={assessment.freshness_score}, status={assessment.freshness_status}"
            )

            # Return only the report field.
            # Returning individual fields (freshness_score, staleness_indicators, etc.)
            # gives the LLM content to paraphrase instead of copy.
            # The report already contains all information the user needs.
            return {
                "report": assessment.format_report(),
            }
