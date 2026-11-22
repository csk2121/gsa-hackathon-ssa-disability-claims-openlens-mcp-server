"""
Tool: compare_datasets

Compares multiple SSA disability datasets side-by-side, identifying shared
dimensions, missing join relationships, and integration opportunities.
"""

from __future__ import annotations

from typing import Any

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
# Maps dimension name → dataset IDs that contain it. Each membership must be
# supported by the dataset's Data.gov record (title or description).

_SHARED_DIMS: dict[str, list[str]] = {
    "state": [
        "ssa-oasdi-beneficiaries-by-state",
        "ssa-ssi-recipients-by-state",
        "ssa-disability-claim-data",
        "ssa-state-agency-workload-data",
    ],
    "county": [
        "ssa-oasdi-beneficiaries-by-state",
        "ssa-ssi-recipients-by-state",
    ],
    "year / time period": [
        "ssa-oasdi-beneficiaries-by-state",
        "ssa-ssi-recipients-by-state",
        "ssa-di-annual-statistical-report",
        "ssa-disability-claim-data",
        "ssa-state-agency-workload-data",
        "ssa-field-office-visitors",
    ],
    "program type (SSDI/SSI)": [
        "ssa-state-agency-workload-data",
        "ssa-ssi-recipients-by-state",
        "ssa-oasdi-beneficiaries-by-state",
        "ssa-di-annual-statistical-report",
    ],
    "beneficiary / recipient counts": [
        "ssa-oasdi-beneficiaries-by-state",
        "ssa-ssi-recipients-by-state",
        "ssa-di-annual-statistical-report",
    ],
    "claim receipts and decisions": [
        "ssa-disability-claim-data",
        "ssa-state-agency-workload-data",
        "ssa-hearing-office-workload",
    ],
    "allowance / favorable determination counts": [
        "ssa-disability-claim-data",
        "ssa-state-agency-workload-data",
        "ssa-alj-disposition-data",
    ],
    "hearing office": [
        "ssa-hearing-office-workload",
        "ssa-hearing-wait-time",
        "ssa-alj-disposition-data",
    ],
    "average processing time": [
        "ssa-initial-disability-processing-time",
        "ssa-reconsideration-processing-time",
        "ssa-hearing-office-workload",
        "ssa-hearing-wait-time",
    ],
    "field office": [
        "ssa-field-office-locator",
        "ssa-field-office-visitor-counts-2016",
        "ssa-field-office-employee-counts-2016",
    ],
}

# ── Missing relationship knowledge base ───────────────────────────────────────

_MISSING_RELS: list[dict[str, object]] = [
    {
        "datasets": {"ssa-hearing-office-workload", "ssa-state-agency-workload-data"},
        "description": "Cannot follow claims from state agency decisions to hearing offices",
        "missing_field": "mapping of hearing offices to the states they serve",
        "impact": "Prevents analysis of whether states with low initial allowance rates also face hearing backlogs",
    },
    {
        "datasets": {"ssa-field-office-locator", "ssa-hearing-office-workload"},
        "description": "Cannot map field office proximity to hearing wait times",
        "missing_field": "claimant ZIP code or county (in hearing office data)",
        "impact": "Cannot determine if rural claimants face longer hearing waits than urban claimants",
    },
    {
        "datasets": {"ssa-disability-claim-data", "ssa-di-annual-statistical-report"},
        "description": "Cannot cross-tabulate demographics with allowance rates",
        "missing_field": "race/ethnicity (not listed in either source record)",
        "impact": "Prevents equity analysis of adjudication outcomes by demographic group",
    },
    {
        "datasets": {"ssa-ssi-recipients-by-state", "ssa-oasdi-beneficiaries-by-state"},
        "description": "Cannot identify individuals receiving both SSI and SSDI (concurrent beneficiaries)",
        "missing_field": "individual claimant identifier (privacy-protected)",
        "impact": "Cannot measure program overlap or concurrent beneficiary burden",
    },
    {
        "datasets": {"ssa-field-office-locator", "ssa-field-office-visitors"},
        "description": "Cannot attribute visitor volume to individual field offices",
        "missing_field": "field office identifier (visitor data is not described per office)",
        "impact": "Cannot rank offices by in-person demand",
    },
]

# ── Integration opportunity knowledge base ────────────────────────────────────

_INTEGRATION_OPPS: list[dict[str, object]] = [
    {
        "datasets": {"ssa-oasdi-beneficiaries-by-state", "ssa-ssi-recipients-by-state"},
        "title": "Combined State-Level Disability Program Dashboard",
        "description": (
            "Both datasets share state, county and year dimensions. Joining them yields a "
            "state- and county-level view of SSDI beneficiaries and SSI recipients."
        ),
        "expected_benefit": "Single source for total state disability program enrollment and payments",
    },
    {
        "datasets": {"ssa-field-office-locator", "ssa-oasdi-beneficiaries-by-state"},
        "title": "Geographic Access Analysis",
        "description": (
            "Field office locations can be geocoded and joined to county beneficiary counts "
            "to calculate office-to-beneficiary ratios by county."
        ),
        "expected_benefit": "Identifies counties with high beneficiary density but low office coverage",
    },
    {
        "datasets": {"ssa-disability-claim-data", "ssa-state-agency-workload-data"},
        "title": "Annual and Monthly State Allowance Trends",
        "description": (
            "Both publish state-level receipts, decisions and allowances for cases referred "
            "to state agencies — one by fiscal year, one by month and case type."
        ),
        "expected_benefit": "State allowance-rate trends with both long-run and within-year detail",
    },
    {
        "datasets": {"ssa-disability-claim-data", "ssa-oasdi-beneficiaries-by-state"},
        "title": "Allowance Rates vs. Beneficiary Prevalence by State",
        "description": (
            "Joining state favorable-determination rates with state beneficiary counts shows "
            "whether high-prevalence states also have high initial allowance rates."
        ),
        "expected_benefit": "Context for interpreting state differences in disability program size",
    },
    {
        "datasets": {"ssa-state-agency-workload-data", "ssa-alj-disposition-data"},
        "title": "Allowance Rates Across Decision Levels",
        "description": (
            "State agency allowances (initial, reconsideration) and ALJ allowances by hearing "
            "office can be set side by side to compare outcomes at each level."
        ),
        "expected_benefit": "Shows how allowance rates change from the initial level to hearings",
    },
    {
        "datasets": {"ssa-field-office-visitor-counts-2016", "ssa-field-office-employee-counts-2016"},
        "title": "FY2016 Visitors per Field Office Employee",
        "description": (
            "Both FY2016 releases are per field office, so visitors can be divided by "
            "employees to give a one-year demand-to-staff ratio."
        ),
        "expected_benefit": "A historical baseline for field office workload pressure",
    },
    {
        "datasets": {"ssa-hearing-office-workload", "ssa-hearing-wait-time"},
        "title": "Hearing Backlog vs. Wait Time",
        "description": (
            "Pending, receipts and dispositions per hearing office can be read alongside the "
            "average time from hearing request to hearing held."
        ),
        "expected_benefit": "Shows whether offices with growing backlogs also have longer waits",
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
    def compare_datasets(dataset_ids: list[str]) -> dict[str, Any]:
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
