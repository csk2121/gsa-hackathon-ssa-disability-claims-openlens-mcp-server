"""
Resource: field_office_datasets

Every SSA field office dataset in the catalog, with what each one can and
cannot show. Read from the static catalog only, so reading it never makes a
network request.
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError

from ..services.dataset_catalog_service import get_catalog_service
from ..utils import get_logger

logger = get_logger(__name__)

# Every field office dataset ID in the catalog contains this marker, e.g.
# "ssa-field-office-locator" and "ssa-title2-claim-receipts-by-field-office-2016".
_FIELD_OFFICE_MARKER = "field-office"

_SUMMARY = (
    "Field offices take disability applications and check non-medical eligibility. "
    "They do not make the medical decision: state Disability Determination Services "
    "(DDS) decide initial and reconsideration claims, and hearing offices decide "
    "appeals. Current field office data is national or limited to locations; per-office "
    "counts of staff, visitors and claim receipts exist only for FY2016. No dataset "
    "reports decision times or pending claims for individual field offices."
)


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.resource(
        uri="openlens://datasets/field-offices",
        name="field_office_datasets",
        description=(
            "All SSA field office datasets in the catalog: locations, visitors, staffing, "
            "claim receipts, claims pending, appointments and phone service. Each entry "
            "gives its geographic level, time period, fields, limitations and source "
            "record. Use as a reference for questions about field office access, demand "
            "or workload."
        ),
        mime_type="application/json",
    )
    def field_office_datasets() -> str:
        """Return every field office dataset in the catalog as JSON."""
        try:
            catalog = get_catalog_service()
            ids = sorted(i for i in catalog.get_all_dataset_ids() if _FIELD_OFFICE_MARKER in i)
            details = [catalog.get_dataset_detail(i) for i in ids]
            datasets = [d.model_dump(mode="json") for d in details if d is not None]
            if not datasets:
                raise ResourceError("No field office datasets found in the catalog.")
            return json.dumps(
                {
                    "summary": _SUMMARY,
                    "dataset_count": len(datasets),
                    "datasets": datasets,
                },
                indent=2,
            )
        except ResourceError:
            raise
        except Exception:
            # Full details stay in the server log; the client gets a generic message.
            logger.exception("field_office_datasets resource failed")
            raise ResourceError("field_office_datasets could not be loaded.") from None
