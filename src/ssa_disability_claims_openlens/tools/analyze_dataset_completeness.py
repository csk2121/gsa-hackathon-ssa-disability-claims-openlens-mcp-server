"""
Tool: analyze_dataset_completeness

Evaluates how completely a dataset covers geographic, temporal, and operational
dimensions of the disability domain. Produces a scored completeness analysis.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ..models import AnalyzeCompletenessInput
from ..services.dataset_analysis_service import DatasetAnalysisService
from ..services.dataset_catalog_service import get_catalog_service
from ..utils import get_logger

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
    )
    def analyze_dataset_completeness(
        dataset_id: str,
        focus_dimensions: list[str] | None = None,
    ) -> dict:  # type: ignore[return]
        """Evaluate dataset coverage across geographic, temporal, and operational axes."""
        try:
            inp = AnalyzeCompletenessInput(
                dataset_id=dataset_id,
                focus_dimensions=focus_dimensions or [],
            )
            catalog = get_catalog_service()
            detail = catalog.get_dataset_detail(inp.dataset_id)

            if detail is None:
                return {
                    "error": (
                        f"Dataset '{inp.dataset_id}' not found. "
                        "Use discover_disability_datasets to get valid dataset IDs."
                    )
                }

            analysis = _analysis_service.analyze_completeness(
                detail, inp.focus_dimensions or None
            )
            logger.info(
                f"analyze_dataset_completeness: {inp.dataset_id!r} → "
                f"score={analysis.completeness_score}, rating={analysis.completeness_rating}"
            )
            return analysis.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"analyze_dataset_completeness failed: {exc}")
            return {"error": str(exc)}
