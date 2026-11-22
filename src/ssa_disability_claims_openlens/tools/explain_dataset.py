"""
Tool: explain_dataset

Explains a specific SSA dataset in plain English — purpose, major fields,
use cases, and known limitations.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ..models import ExplainDatasetInput, ExplainDatasetResult
from ..services.dataset_catalog_service import get_catalog_service
from ..utils import get_logger

logger = get_logger(__name__)


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.tool(
        name="explain_dataset",
        description=(
            "Explains the contents, purpose, key fields, use cases, and limitations of a "
            "specific SSA disability dataset in plain English. Use this tool when you need "
            "to understand what a dataset contains before using it for analysis, or to "
            "explain a dataset to a non-technical stakeholder. "
            "Requires a dataset_id from discover_disability_datasets."
        ),
    )
    def explain_dataset(dataset_id: str) -> dict[str, Any]:
        """Explain a dataset's contents, fields, use cases, and limitations."""
        try:
            ExplainDatasetInput(dataset_id=dataset_id)  # Validate input
            catalog = get_catalog_service()
            detail = catalog.get_dataset_detail(dataset_id)

            if detail is None:
                return {
                    "error": (
                        f"Dataset '{dataset_id}' not found. "
                        "Use discover_disability_datasets to get valid dataset IDs."
                    )
                }

            # Build a plain-English analyst summary
            field_names = [f.name for f in detail.major_fields[:5]]
            field_summary = ", ".join(field_names) if field_names else "see major_fields"
            limitation_count = len(detail.limitations)

            analyst_summary = (
                f"{detail.name} is published by {detail.source.value} and updated "
                f"{detail.update_frequency.value.lower()}. "
                f"It covers {detail.geographic_coverage} from {detail.temporal_coverage}. "
                f"Key fields include: {field_summary}. "
                f"The dataset has {limitation_count} known limitation(s) — "
                f"notably: {detail.limitations[0] if detail.limitations else 'none documented'}. "
                f"Source: {detail.provenance or 'unverified'}"
                + ("" if detail.fields_verified or not detail.major_fields
                   else " Field list not yet checked against the data dictionary.")
            )

            result = ExplainDatasetResult(dataset=detail, analyst_summary=analyst_summary)
            logger.info(f"explain_dataset: explained {dataset_id!r}")
            return result.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"explain_dataset failed: {exc}")
            return {"error": str(exc)}
