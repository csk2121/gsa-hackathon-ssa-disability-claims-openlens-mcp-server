"""
Resource: disability_datasets

Exposes the full SSA disability dataset catalog as a readable MCP resource.
"""

from __future__ import annotations

import json

from fastmcp import FastMCP

from ..services.dataset_catalog_service import get_catalog_service
from ..utils import get_logger

logger = get_logger(__name__)


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.resource(
        uri="openlens://datasets/disability",
        name="disability_datasets",
        description=(
            "Full catalog of SSA disability-related public datasets. "
            "Contains dataset names, descriptions, sources, update frequencies, URLs, "
            "and subject-matter tags. Use as a quick reference before calling tools."
        ),
        mime_type="application/json",
    )
    def disability_datasets() -> str:
        """Return the full disability dataset catalog as JSON."""
        try:
            catalog = get_catalog_service()
            datasets = catalog.list_datasets()
            return json.dumps(
                [ds.model_dump(mode="json") for ds in datasets],
                indent=2,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"disability_datasets resource failed: {exc}")
            return json.dumps({"error": str(exc)})
