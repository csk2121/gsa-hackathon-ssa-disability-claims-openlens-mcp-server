"""
Tool: assess_dataset_freshness

Evaluates how current an SSA dataset is relative to its stated update frequency.
Returns a freshness score, qualitative status, and staleness indicators.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ..models import AssessFreshnessInput
from ..services.dataset_analysis_service import DatasetAnalysisService
from ..services.dataset_catalog_service import get_catalog_service
from ..utils import get_logger

logger = get_logger(__name__)

_analysis_service = DatasetAnalysisService()


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.tool(
        name="assess_dataset_freshness",
        description=(
            "Evaluates how current an SSA disability dataset is relative to its stated "
            "update frequency. Returns a freshness score (0–100), qualitative status "
            "(Current / Aging / Stale / Unknown), days since last update, and staleness "
            "indicators. Use this tool before relying on a dataset for time-sensitive "
            "analysis to understand whether the data reflects recent conditions."
        ),
    )
    def assess_dataset_freshness(dataset_id: str) -> dict:  # type: ignore[return]
        """Evaluate dataset update currency and freshness."""
        try:
            AssessFreshnessInput(dataset_id=dataset_id)  # Validate
            catalog = get_catalog_service()
            detail = catalog.get_dataset_detail(dataset_id)

            if detail is None:
                return {
                    "error": (
                        f"Dataset '{dataset_id}' not found. "
                        "Use discover_disability_datasets to get valid dataset IDs."
                    )
                }

            assessment = _analysis_service.assess_freshness(detail)
            logger.info(
                f"assess_dataset_freshness: {dataset_id!r} → "
                f"score={assessment.freshness_score}, status={assessment.freshness_status}"
            )
            return assessment.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"assess_dataset_freshness failed: {exc}")
            return {"error": str(exc)}
