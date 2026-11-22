"""
Tool: discover_disability_datasets

Finds and returns SSA disability-related public datasets. Supports optional
keyword search and filtering by source or subject-matter tags.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ..models import (
    DataSource,
    DiscoverDatasetsInput,
    DiscoverDatasetsResult,
)
from ..services.dataset_catalog_service import get_catalog_service
from ..utils import get_logger

logger = get_logger(__name__)


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.tool(
        name="discover_disability_datasets",
        description=(
            "Discovers and lists SSA disability-related public datasets. "
            "Returns dataset names, descriptions, sources, update frequencies, and URLs. "
            "Use this tool first to understand what data is available before diving into "
            "a specific dataset, comparing datasets, or evaluating answer coverage. "
            "Supports optional keyword search (e.g., 'SSDI', 'field office', 'appeals') "
            "and filtering by source portal or subject tags."
        ),
    )
    def discover_disability_datasets(
        query: str | None = None,
        source_filter: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Find SSA disability-related public datasets."""
        try:
            inp = DiscoverDatasetsInput(
                query=query,
                source_filter=DataSource(source_filter) if source_filter else None,
                tags=tags or [],
            )
            catalog = get_catalog_service()
            datasets = catalog.list_datasets(
                query=inp.query,
                source_filter=inp.source_filter.value if inp.source_filter else None,
                tags=inp.tags if inp.tags else None,
            )
            result = DiscoverDatasetsResult(
                datasets=datasets,
                total_found=len(datasets),
                query_applied=inp.query,
                source_note=" ".join(
                    [
                        "Every dataset's name, URL, dates and update frequency come from its "
                        "official metadata record (see each dataset's 'provenance'). "
                        "Live Data.gov search results are included when the network is available."
                    ]
                    + catalog.source_notes()
                ),
            )
            logger.info(f"discover_disability_datasets: returned {len(datasets)} datasets")
            return result.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"discover_disability_datasets failed: {exc}")
            return {"error": str(exc), "datasets": [], "total_found": 0}
