"""
Resource: field_office_datasets

Exposes SSA field office dataset information as a readable MCP resource.
"""

from __future__ import annotations

import json

from fastmcp import FastMCP

from ..services.dataset_catalog_service import get_catalog_service
from ..utils import get_logger

logger = get_logger(__name__)


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.resource(
        uri="openlens://datasets/field-offices",
        name="field_office_datasets",
        description=(
            "SSA field office location dataset details including geographic coverage, "
            "data fields, limitations, and known gaps. "
            "Use as reference when analyzing SSA geographic access or proximity."
        ),
        mime_type="application/json",
    )
    def field_office_datasets() -> str:
        """Return field office dataset details as JSON."""
        try:
            catalog = get_catalog_service()
            detail = catalog.get_dataset_detail("ssa-field-office-locator")
            if detail is None:
                return json.dumps({"error": "Field office dataset not found"})
            return json.dumps(detail.model_dump(mode="json"), indent=2)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"field_office_datasets resource failed: {exc}")
            return json.dumps({"error": str(exc)})
