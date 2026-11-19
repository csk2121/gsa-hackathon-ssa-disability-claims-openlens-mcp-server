"""
Tool: compare_datasets

Compares multiple SSA disability datasets side-by-side, identifying shared
dimensions, missing join relationships, and integration opportunities.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ..models import (
    CompareDatasetsInput,
    DatasetComparison,
    IntegrationOpportunity,
    MissingRelationship,
    SharedDimension,
)
from ..services.dataset_catalog_service import get_catalog_service
from ..utils import get_logger

logger = get_logger(__name__)

# ── Shared dimension knowledge base ───────────────────────────────────────────
# Maps dimension name → set of dataset IDs that contain it.

_SHARED_DIMS: dict[str, list[str]] = {
    "state": [
        "ssa-oasdi-beneficiaries-by-state",
        "ssa-odar-pending-cases",
        "ssa-disability-research-statistics",
        "ssa-ssi-recipients-by-state",
        "ssa-field-office-locator",
    ],
    "year / time period": [
        "ssa-oasdi-beneficiaries-by-state",
        "ssa-disability-applications-decisions",
        "ssa-disability-research-statistics",
        "ssa-ssi-recipients-by-state",
        "data-gov-ssa-performance",
        "ssa-red-book",
    ],
    "program type (SSDI/SSI)": [
        "ssa-disability-applications-decisions",
        "ssa-disability-research-statistics",
        "ssa-ssi-recipients-by-state",
        "ssa-oasdi-beneficiaries-by-state",
        "ssa-red-book",
    ],
    "beneficiary / recipient counts": [
        "ssa-oasdi-beneficiaries-by-state",
        "ssa-ssi-recipients-by-state",
        "ssa-disability-research-statistics",
    ],
    "average monthly benefit amount": [
        "ssa-oasdi-beneficiaries-by-state",
        "ssa-disability-research-statistics",
        "ssa-ssi-recipients-by-state",
    ],
    "age group": [
        "ssa-disability-applications-decisions",
        "ssa-disability-research-statistics",
    ],
}

# ── Missing relationship knowledge base ───────────────────────────────────────

_MISSING_RELS: list[dict[str, object]] = [
    {
        "datasets": {"ssa-odar-pending-cases", "ssa-disability-applications-decisions"},
        "description": "Cannot link initial claim volume to hearing backlog by state",
        "missing_field": "state (in applications/decisions dataset)",
        "impact": "Prevents analysis of whether high-application states also face hearing backlogs",
    },
    {
        "datasets": {"ssa-field-office-locator", "ssa-odar-pending-cases"},
        "description": "Cannot map field office proximity to hearing wait times",
        "missing_field": "claimant ZIP code or county (in ODAR dataset)",
        "impact": "Cannot determine if rural claimants face longer hearing waits than urban claimants",
    },
    {
        "datasets": {"ssa-disability-research-statistics", "ssa-disability-applications-decisions"},
        "description": "Cannot cross-tabulate beneficiary demographics with allowance rates",
        "missing_field": "race/ethnicity (in both datasets)",
        "impact": "Prevents equity analysis of adjudication outcomes by demographic group",
    },
    {
        "datasets": {"ssa-ssi-recipients-by-state", "ssa-oasdi-beneficiaries-by-state"},
        "description": "Cannot identify individuals receiving both SSI and SSDI (concurrent beneficiaries)",
        "missing_field": "individual claimant identifier (privacy-protected)",
        "impact": "Cannot measure program overlap or concurrent beneficiary burden",
    },
]

# ── Integration opportunity knowledge base ────────────────────────────────────

_INTEGRATION_OPPS: list[dict[str, object]] = [
    {
        "datasets": {"ssa-oasdi-beneficiaries-by-state", "ssa-ssi-recipients-by-state"},
        "title": "Combined State-Level Disability Program Dashboard",
        "description": (
            "Both datasets share state and time dimensions. Joining them yields a "
            "comprehensive state-level view of all SSA disability program participants."
        ),
        "expected_benefit": "Single source for total state disability program enrollment and payments",
    },
    {
        "datasets": {"ssa-field-office-locator", "ssa-oasdi-beneficiaries-by-state"},
        "title": "Geographic Access Analysis",
        "description": (
            "Field office locations can be spatially joined to beneficiary counts "
            "to calculate office-to-beneficiary ratios by county."
        ),
        "expected_benefit": "Identifies counties with high beneficiary density but low office coverage",
    },
    {
        "datasets": {"ssa-disability-applications-decisions", "data-gov-ssa-performance"},
        "title": "Application Volume vs. Performance Trend Analysis",
        "description": (
            "Joining application volumes with performance metrics reveals whether "
            "processing times correlate with application surges."
        ),
        "expected_benefit": "Evidence base for staffing and resource planning decisions",
    },
    {
        "datasets": {"ssa-odar-pending-cases", "data-gov-ssa-performance"},
        "title": "Hearing Backlog vs. Performance Target Comparison",
        "description": (
            "Monthly hearing office data can be compared to annual performance targets "
            "to assess whether targets reflect actual claimant experience."
        ),
        "expected_benefit": "Identifies gaps between reported performance and ground-level outcomes",
    },
]


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.tool(
        name="compare_datasets",
        description=(
            "Compares two or more SSA disability datasets side-by-side to identify "
            "shared dimensions, missing join relationships, and integration opportunities. "
            "Use this tool when you want to understand how datasets relate to each other, "
            "whether they can be combined for deeper analysis, or what analytic value is "
            "being left on the table due to missing linkages. "
            "Requires dataset_ids from discover_disability_datasets."
        ),
    )
    def compare_datasets(dataset_ids: list[str]) -> dict:  # type: ignore[return]
        """Compare multiple datasets for shared dimensions and integration opportunities."""
        if len(dataset_ids) < 2:
            return {
                "error": (
                    "compare_datasets requires at least two dataset IDs. "
                    f"Received {len(dataset_ids)}. "
                    "Use discover_disability_datasets to find valid dataset IDs."
                )
            }
        try:
            inp = CompareDatasetsInput(dataset_ids=dataset_ids)
            catalog = get_catalog_service()
            id_set = set(inp.dataset_ids)

            # Validate all IDs exist
            missing = [did for did in inp.dataset_ids if catalog.get_dataset_detail(did) is None]
            if missing:
                return {
                    "error": (
                        f"Dataset(s) not found: {', '.join(missing)}. "
                        "Use discover_disability_datasets to get valid IDs."
                    )
                }

            # Find shared dimensions
            shared: list[SharedDimension] = []
            for dim_name, dim_datasets in _SHARED_DIMS.items():
                present = [d for d in dim_datasets if d in id_set]
                if len(present) >= 2:
                    shared.append(SharedDimension(
                        dimension=dim_name,
                        present_in=present,
                        notes=f"All {len(present)} selected datasets share this dimension",
                    ))

            # Find missing relationships
            missing_rels: list[MissingRelationship] = []
            for rel in _MISSING_RELS:
                rel_datasets: set[str] = rel["datasets"]  # type: ignore[assignment]
                if rel_datasets.issubset(id_set):
                    missing_rels.append(MissingRelationship(
                        description=rel["description"],  # type: ignore[arg-type]
                        datasets_involved=list(rel_datasets),
                        missing_field=rel["missing_field"],  # type: ignore[arg-type]
                        impact=rel["impact"],  # type: ignore[arg-type]
                    ))

            # Find integration opportunities
            int_opps: list[IntegrationOpportunity] = []
            for opp in _INTEGRATION_OPPS:
                opp_datasets: set[str] = opp["datasets"]  # type: ignore[assignment]
                if opp_datasets.issubset(id_set):
                    int_opps.append(IntegrationOpportunity(
                        title=opp["title"],  # type: ignore[arg-type]
                        datasets=list(opp_datasets),
                        description=opp["description"],  # type: ignore[arg-type]
                        expected_benefit=opp["expected_benefit"],  # type: ignore[arg-type]
                    ))

            # Build summary
            names = [
                catalog.get_dataset_detail(did).name  # type: ignore[union-attr]
                for did in inp.dataset_ids
            ]
            summary = (
                f"Compared {len(inp.dataset_ids)} datasets: {', '.join(names)}. "
                f"Found {len(shared)} shared dimension(s), "
                f"{len(missing_rels)} missing relationship(s), and "
                f"{len(int_opps)} integration opportunity(ies)."
            )

            result = DatasetComparison(
                datasets_compared=inp.dataset_ids,
                shared_dimensions=shared,
                missing_relationships=missing_rels,
                integration_opportunities=int_opps,
                summary=summary,
            )
            logger.info(f"compare_datasets: compared {len(inp.dataset_ids)} datasets")
            return result.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"compare_datasets failed: {exc}")
            return {"error": str(exc)}
