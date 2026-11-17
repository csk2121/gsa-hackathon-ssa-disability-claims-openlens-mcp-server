"""
Dataset Catalog Service — the authoritative source of SSA disability dataset metadata.

Architecture:
  DatasetCatalogService loads from two adapters in priority order:
    1. StaticCatalogAdapter  — curated, always-available catalog of known SSA datasets
    2. DataGovAdapter        — live query against the Data.gov CKAN API (optional)

  The static catalog is the foundation. The live adapter enriches it when the network
  is reachable. This design ensures the server is useful even in air-gapped environments.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import date
from functools import lru_cache
from typing import Any

import httpx

from ..config import get_settings
from ..models import (
    DataSource,
    DatasetDetail,
    DatasetField,
    DatasetSummary,
    UpdateFrequency,
)
from ..utils import get_logger, keyword_match_score

logger = get_logger(__name__)


# ── Abstract adapter interface ─────────────────────────────────────────────────


class DatasetAdapter(ABC):
    """Interface that all data source adapters must implement."""

    @abstractmethod
    def fetch_summaries(self) -> list[DatasetSummary]:
        """Return a list of DatasetSummary objects from this source."""
        ...

    @abstractmethod
    def fetch_detail(self, dataset_id: str) -> DatasetDetail | None:
        """Return full DatasetDetail for a specific dataset, or None if not found."""
        ...


# ── Static catalog (always available) ─────────────────────────────────────────


# fmt: off
_STATIC_CATALOG: list[dict[str, Any]] = [
    {
        "dataset_id": "ssa-oasdi-beneficiaries-by-state",
        "name": "OASDI Beneficiaries by State and County",
        "description": (
            "Annual counts and average monthly benefit amounts for OASDI "
            "(Old-Age, Survivors, and Disability Insurance) beneficiaries, "
            "disaggregated by state and county."
        ),
        "source": DataSource.SSA_OPEN_DATA,
        "update_frequency": UpdateFrequency.ANNUALLY,
        "url": "https://www.ssa.gov/policy/docs/statcomps/oasdi_sc/",
        "tags": ["OASDI", "beneficiaries", "geographic", "state", "county", "SSDI"],
        "last_updated": date(2024, 6, 1),
        "purpose": (
            "Enables geographic analysis of disability and retirement benefit distribution. "
            "Supports policy research on regional disparities in benefit receipt."
        ),
        "major_fields": [
            DatasetField(name="state", data_type="string", description="U.S. state name", is_key_field=True, example_values=["California", "Texas"]),
            DatasetField(name="county", data_type="string", description="County name within state", is_key_field=True, example_values=["Los Angeles", "Harris"]),
            DatasetField(name="total_beneficiaries", data_type="integer", description="Total number of beneficiaries", example_values=["1250000", "890000"]),
            DatasetField(name="disabled_workers", data_type="integer", description="Count of disabled worker beneficiaries", example_values=["445000", "312000"]),
            DatasetField(name="avg_monthly_benefit", data_type="float", description="Average monthly benefit amount in dollars", example_values=["1427.50", "1352.00"]),
            DatasetField(name="year", data_type="integer", description="Reference year", is_key_field=True, example_values=["2022", "2023"]),
        ],
        "use_cases": [
            "Identify states with high concentrations of disability beneficiaries",
            "Analyze regional disparities in average benefit amounts",
            "Track year-over-year changes in disability program enrollment by geography",
            "Support congressional district-level policy briefings",
        ],
        "limitations": [
            "Annual publication introduces 12-18 month lag from reference period",
            "County-level data may be suppressed for small populations (privacy)",
            "Does not include denied applicants or pending claims",
            "No demographic breakdown (age, gender) below state level",
        ],
        "geographic_coverage": "All 50 states, DC, and U.S. territories",
        "temporal_coverage": "1990–2023",
    },
    {
        "dataset_id": "ssa-odar-pending-cases",
        "name": "ODAR Pending Cases by Hearing Office",
        "description": (
            "Monthly counts of disability hearing cases pending at each SSA Office of "
            "Disability Adjudication and Review (ODAR) hearing office, with average "
            "processing times."
        ),
        "source": DataSource.SSA_OPEN_DATA,
        "update_frequency": UpdateFrequency.MONTHLY,
        "url": "https://www.ssa.gov/appeals/DataSets.html",
        "tags": ["ODAR", "appeals", "hearing", "processing time", "backlog", "adjudication"],
        "last_updated": date(2024, 10, 1),
        "purpose": (
            "Monitors disability appeals backlog and processing times across hearing offices. "
            "Critical for workload management and equity analysis."
        ),
        "major_fields": [
            DatasetField(name="hearing_office", data_type="string", description="Name of the ODAR hearing office", is_key_field=True, example_values=["Atlanta North", "Los Angeles"]),
            DatasetField(name="state", data_type="string", description="State where hearing office is located", is_key_field=True, example_values=["Georgia", "California"]),
            DatasetField(name="pending_cases", data_type="integer", description="Number of cases awaiting hearing", example_values=["3200", "5100"]),
            DatasetField(name="avg_processing_days", data_type="float", description="Average days from request to decision", example_values=["412", "398"]),
            DatasetField(name="report_month", data_type="date", description="Month the data was reported", is_key_field=True, example_values=["2024-09", "2024-10"]),
            DatasetField(name="dispositions", data_type="integer", description="Cases decided in the reporting month", example_values=["890", "1120"]),
        ],
        "use_cases": [
            "Monitor hearing backlog trends nationally and by office",
            "Identify hearing offices with longest processing times",
            "Measure the impact of SSA staffing or policy changes on wait times",
            "Support claimant advocacy with data on regional disparities",
        ],
        "limitations": [
            "No demographic breakdown of claimants",
            "Processing time is aggregate average — no distribution data (median, 90th percentile)",
            "Does not capture pre-hearing wait (initial claim to request for hearing)",
            "Hearing office boundaries do not align with congressional districts",
            "No information on case complexity or impairment type",
        ],
        "geographic_coverage": "All ODAR hearing offices nationally",
        "temporal_coverage": "2007–present",
    },
    {
        "dataset_id": "ssa-disability-applications-decisions",
        "name": "SSI/SSDI Applications and Decisions",
        "description": (
            "Annual counts of Supplemental Security Income (SSI) and Social Security "
            "Disability Insurance (SSDI) applications, awards, and denials, broken down "
            "by program, age group, and primary impairment category."
        ),
        "source": DataSource.SSA_OPEN_DATA,
        "update_frequency": UpdateFrequency.ANNUALLY,
        "url": "https://www.ssa.gov/policy/docs/statcomps/di_asr/",
        "tags": ["SSI", "SSDI", "applications", "awards", "denials", "impairment", "allowance rate"],
        "last_updated": date(2024, 3, 1),
        "purpose": (
            "Tracks the volume and outcomes of disability program applications. "
            "Essential for understanding program access and decision patterns."
        ),
        "major_fields": [
            DatasetField(name="program", data_type="string", description="SSDI or SSI", is_key_field=True, example_values=["SSDI", "SSI"]),
            DatasetField(name="year", data_type="integer", description="Calendar year", is_key_field=True, example_values=["2022", "2023"]),
            DatasetField(name="applications", data_type="integer", description="Total applications received", example_values=["2100000", "1890000"]),
            DatasetField(name="awards", data_type="integer", description="Applications resulting in award", example_values=["700000", "612000"]),
            DatasetField(name="denials", data_type="integer", description="Applications denied at initial level", example_values=["1300000", "1150000"]),
            DatasetField(name="allowance_rate", data_type="float", description="Percentage of applications awarded", example_values=["33.5", "32.4"]),
            DatasetField(name="age_group", data_type="string", description="Applicant age bracket", example_values=["18-29", "50-64"]),
            DatasetField(name="impairment_category", data_type="string", description="Primary disabling condition category", example_values=["Musculoskeletal", "Mental Disorders"]),
        ],
        "use_cases": [
            "Analyze national disability application trends over time",
            "Compare allowance rates across impairment categories",
            "Identify demographic groups with disproportionately high denial rates",
            "Evaluate impact of policy changes on application volumes",
        ],
        "limitations": [
            "Annual data — cannot capture within-year fluctuations",
            "No state/geographic disaggregation in published form",
            "Impairment categories are broad — cannot distinguish specific diagnoses",
            "Does not include reconsideration or hearing-level outcomes in same table",
            "Race and ethnicity data are not published",
        ],
        "geographic_coverage": "National only",
        "temporal_coverage": "1960–2023",
    },
    {
        "dataset_id": "ssa-field-office-locator",
        "name": "SSA Field Office Locations",
        "description": (
            "Directory of all SSA field offices with addresses, phone numbers, "
            "geographic coordinates, and service area information."
        ),
        "source": DataSource.SSA_OPEN_DATA,
        "update_frequency": UpdateFrequency.QUARTERLY,
        "url": "https://www.ssa.gov/locator/",
        "tags": ["field office", "geographic", "access", "locations", "service area"],
        "last_updated": date(2024, 7, 1),
        "purpose": (
            "Provides geographic access data for SSA in-person services. "
            "Supports equity analysis of service proximity."
        ),
        "major_fields": [
            DatasetField(name="office_name", data_type="string", description="Field office name", is_key_field=True, example_values=["Atlanta Downtown", "Chicago Loop"]),
            DatasetField(name="address", data_type="string", description="Street address", example_values=["401 W Peachtree St NW"]),
            DatasetField(name="city", data_type="string", description="City", example_values=["Atlanta", "Chicago"]),
            DatasetField(name="state", data_type="string", description="State abbreviation", is_key_field=True, example_values=["GA", "IL"]),
            DatasetField(name="zip_code", data_type="string", description="ZIP code", example_values=["30308", "60601"]),
            DatasetField(name="latitude", data_type="float", description="Geographic latitude", example_values=["33.7749", "41.8781"]),
            DatasetField(name="longitude", data_type="float", description="Geographic longitude", example_values=["-84.3880", "-87.6298"]),
            DatasetField(name="phone", data_type="string", description="Office phone number", example_values=["800-772-1213"]),
        ],
        "use_cases": [
            "Map SSA field office coverage and identify service deserts",
            "Analyze access equity for rural or low-income populations",
            "Determine proximity of disability applicants to nearest office",
            "Support policy analysis on office closures or openings",
        ],
        "limitations": [
            "No appointment wait time data",
            "No staffing or capacity information",
            "No data on walk-in vs. appointment traffic volumes",
            "Service area boundaries are not formally defined",
            "No accessibility information (ADA compliance, language services)",
        ],
        "geographic_coverage": "All 50 states, DC, and U.S. territories",
        "temporal_coverage": "Current snapshot only (no historical archive)",
    },
    {
        "dataset_id": "ssa-disability-research-statistics",
        "name": "SSA Disability Research Statistics",
        "description": (
            "Research statistics on SSDI beneficiary characteristics including age, "
            "gender, state of residence, and years of covered earnings."
        ),
        "source": DataSource.SSA_OPEN_DATA,
        "update_frequency": UpdateFrequency.ANNUALLY,
        "url": "https://www.ssa.gov/policy/docs/statcomps/disabled_workers/",
        "tags": ["SSDI", "demographics", "age", "gender", "earnings", "beneficiary characteristics"],
        "last_updated": date(2024, 2, 1),
        "purpose": (
            "Provides demographic profile of SSDI beneficiaries. "
            "Supports equity research and program design analysis."
        ),
        "major_fields": [
            DatasetField(name="year", data_type="integer", description="Reference year", is_key_field=True, example_values=["2022", "2023"]),
            DatasetField(name="age_group", data_type="string", description="Age bracket", is_key_field=True, example_values=["30-39", "55-59"]),
            DatasetField(name="sex", data_type="string", description="Reported sex (Male/Female)", example_values=["Male", "Female"]),
            DatasetField(name="state", data_type="string", description="State of residence", example_values=["California", "New York"]),
            DatasetField(name="beneficiary_count", data_type="integer", description="Number of beneficiaries in group", example_values=["285000", "412000"]),
            DatasetField(name="avg_monthly_benefit", data_type="float", description="Average monthly SSDI benefit", example_values=["1356.20", "1489.40"]),
            DatasetField(name="avg_years_covered_earnings", data_type="float", description="Average years of covered work history", example_values=["22.5", "28.1"]),
        ],
        "use_cases": [
            "Analyze gender and age disparities in SSDI benefit amounts",
            "Track demographic shifts in the disabled worker population",
            "Compare benefit levels by state of residence",
            "Research relationship between work history and benefit adequacy",
        ],
        "limitations": [
            "No race or ethnicity breakdown",
            "Sex is binary (Male/Female) — no non-binary category",
            "Annual publication creates significant lag",
            "Impairment type not cross-tabulated with demographics",
            "No income or asset data for means-testing analysis",
        ],
        "geographic_coverage": "State-level",
        "temporal_coverage": "1970–2023",
    },
    {
        "dataset_id": "ssa-ssi-recipients-by-state",
        "name": "SSI Recipients by State and County",
        "description": (
            "Monthly counts of Supplemental Security Income (SSI) recipients and "
            "total payment amounts, disaggregated by state and county."
        ),
        "source": DataSource.SSA_OPEN_DATA,
        "update_frequency": UpdateFrequency.MONTHLY,
        "url": "https://www.ssa.gov/policy/docs/statcomps/ssi_sc/",
        "tags": ["SSI", "recipients", "geographic", "state", "county", "payments"],
        "last_updated": date(2024, 10, 1),
        "purpose": (
            "Tracks geographic distribution of SSI recipients and payments. "
            "Essential for state-level fiscal analysis and equity assessments."
        ),
        "major_fields": [
            DatasetField(name="state", data_type="string", description="U.S. state", is_key_field=True, example_values=["California", "New York"]),
            DatasetField(name="county", data_type="string", description="County name", is_key_field=True, example_values=["Los Angeles", "Kings"]),
            DatasetField(name="total_recipients", data_type="integer", description="SSI recipients in month", example_values=["1200000", "890000"]),
            DatasetField(name="blind_disabled_recipients", data_type="integer", description="Recipients due to blindness or disability", example_values=["850000", "620000"]),
            DatasetField(name="aged_recipients", data_type="integer", description="Recipients due to age (65+)", example_values=["350000", "270000"]),
            DatasetField(name="total_payments", data_type="float", description="Total SSI payments in month (dollars)", example_values=["924000000", "687000000"]),
            DatasetField(name="report_month", data_type="date", description="Reference month", is_key_field=True, example_values=["2024-09", "2024-10"]),
        ],
        "use_cases": [
            "Track SSI program growth and contraction by geography",
            "Analyze payment adequacy relative to local cost of living",
            "Identify counties with high concentrations of disabled SSI recipients",
            "Support state Medicaid and social services coordination analysis",
        ],
        "limitations": [
            "No demographic breakdown below state level",
            "Payment amounts do not include state supplements (varies by state)",
            "No data on recipient income, assets, or housing status",
            "Counts reflect approved recipients — not applicants or denials",
        ],
        "geographic_coverage": "All 50 states, DC, and U.S. territories",
        "temporal_coverage": "2008–present",
    },
    {
        "dataset_id": "ssa-red-book",
        "name": "SSA Red Book — Work Incentives Summary",
        "description": (
            "Reference document describing SSA work incentive programs for people with "
            "disabilities, including Ticket to Work, Trial Work Period, and Substantial "
            "Gainful Activity thresholds."
        ),
        "source": DataSource.SSA_OPEN_DATA,
        "update_frequency": UpdateFrequency.ANNUALLY,
        "url": "https://www.ssa.gov/redbook/",
        "tags": ["work incentives", "Ticket to Work", "SGA", "employment", "return to work"],
        "last_updated": date(2024, 1, 1),
        "purpose": (
            "Reference for disability program rules related to employment. "
            "Not a statistical dataset but a structured policy reference."
        ),
        "major_fields": [
            DatasetField(name="program", data_type="string", description="SSDI or SSI", is_key_field=True, example_values=["SSDI", "SSI"]),
            DatasetField(name="sga_threshold", data_type="float", description="Substantial Gainful Activity monthly earnings threshold (dollars)", example_values=["1550.00", "2590.00"]),
            DatasetField(name="twp_threshold", data_type="float", description="Trial Work Period monthly service threshold", example_values=["1050.00"]),
            DatasetField(name="year", data_type="integer", description="Year the thresholds apply", is_key_field=True, example_values=["2024"]),
        ],
        "use_cases": [
            "Research employment incentives for disability beneficiaries",
            "Track changes in SGA thresholds over time",
            "Analyze whether SGA thresholds keep pace with wage growth",
        ],
        "limitations": [
            "Policy reference document — not a microdata or statistical file",
            "Cannot be joined to beneficiary data without individual-level records",
            "Does not include Ticket to Work participant counts or outcomes",
        ],
        "geographic_coverage": "National (policy applies uniformly)",
        "temporal_coverage": "1960–present",
    },
    {
        "dataset_id": "data-gov-ssa-performance",
        "name": "SSA Annual Performance Report (Data.gov)",
        "description": (
            "SSA agency performance metrics including disability claim processing times, "
            "initial decision accuracy rates, and customer satisfaction scores, as "
            "reported in the SSA Annual Performance Report."
        ),
        "source": DataSource.DATA_GOV,
        "update_frequency": UpdateFrequency.ANNUALLY,
        "url": "https://catalog.data.gov/dataset/ssa-annual-performance-report",
        "tags": ["performance", "processing time", "accuracy", "customer satisfaction", "agency metrics"],
        "last_updated": date(2024, 2, 1),
        "purpose": (
            "Tracks SSA operational performance against agency strategic goals. "
            "Key source for understanding disability processing time trends."
        ),
        "major_fields": [
            DatasetField(name="fiscal_year", data_type="integer", description="Federal fiscal year", is_key_field=True, example_values=["2022", "2023"]),
            DatasetField(name="metric_name", data_type="string", description="Performance metric name", is_key_field=True, example_values=["Average processing days — initial disability claim"]),
            DatasetField(name="target", data_type="float", description="Annual performance target", example_values=["120", "95"]),
            DatasetField(name="actual", data_type="float", description="Actual performance achieved", example_values=["131", "108"]),
            DatasetField(name="met_target", data_type="boolean", description="Whether the target was met", example_values=["false", "true"]),
            DatasetField(name="program", data_type="string", description="SSDI, SSI, or combined", example_values=["SSDI", "SSI"]),
        ],
        "use_cases": [
            "Track SSA processing time trends over multiple years",
            "Assess whether SSA meets its own performance targets",
            "Compare disability and retirement processing performance",
            "Support congressional oversight and budget justification analysis",
        ],
        "limitations": [
            "Annual aggregates only — no monthly or office-level breakdown",
            "Metrics are self-reported by SSA — no independent verification",
            "Coverage varies year-to-year as agency changes metric definitions",
            "No demographic breakdown of processing time outcomes",
        ],
        "geographic_coverage": "National only",
        "temporal_coverage": "2003–2023",
    },
]
# fmt: on


class StaticCatalogAdapter(DatasetAdapter):
    """Serves the curated static dataset catalog — always available."""

    def __init__(self) -> None:
        self._catalog: dict[str, dict[str, Any]] = {
            d["dataset_id"]: d for d in _STATIC_CATALOG
        }

    def fetch_summaries(self) -> list[DatasetSummary]:
        return [
            DatasetSummary(
                dataset_id=d["dataset_id"],
                name=d["name"],
                description=d["description"],
                source=d["source"],
                update_frequency=d["update_frequency"],
                url=d["url"],
                tags=d.get("tags", []),
                last_updated=d.get("last_updated"),
            )
            for d in self._catalog.values()
        ]

    def fetch_detail(self, dataset_id: str) -> DatasetDetail | None:
        d = self._catalog.get(dataset_id)
        if d is None:
            return None
        return DatasetDetail(
            dataset_id=d["dataset_id"],
            name=d["name"],
            purpose=d["purpose"],
            major_fields=d["major_fields"],
            use_cases=d["use_cases"],
            limitations=d["limitations"],
            source=d["source"],
            update_frequency=d["update_frequency"],
            url=d["url"],
            last_updated=d.get("last_updated"),
            geographic_coverage=d.get("geographic_coverage", "National"),
            temporal_coverage=d.get("temporal_coverage", "Unknown"),
        )

    def all_dataset_ids(self) -> list[str]:
        return list(self._catalog.keys())


class DataGovAdapter(DatasetAdapter):
    """
    Queries the Data.gov CKAN API for SSA disability datasets.

    Falls back gracefully when the network is unavailable.
    """

    def __init__(self, base_url: str, api_key: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-CKAN-API-Key": api_key} if api_key else {}

    def _search(self, query: str, rows: int = 20) -> list[dict[str, Any]]:
        try:
            url = f"{self._base_url}/package_search"
            params: dict[str, Any] = {
                "q": query,
                "fq": "organization:social-security-administration",
                "rows": rows,
            }
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, params=params, headers=self._headers)
                resp.raise_for_status()
                data = resp.json()
                return data.get("result", {}).get("results", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Data.gov adapter query failed: {exc}")
            return []

    def fetch_summaries(self) -> list[DatasetSummary]:
        results = self._search("disability SSA")
        summaries: list[DatasetSummary] = []
        for pkg in results:
            try:
                summaries.append(
                    DatasetSummary(
                        dataset_id=f"datagov-{pkg.get('name', 'unknown')}",
                        name=pkg.get("title", "Untitled"),
                        description=pkg.get("notes", "No description available."),
                        source=DataSource.DATA_GOV,
                        update_frequency=UpdateFrequency.UNKNOWN,
                        url=f"https://catalog.data.gov/dataset/{pkg.get('name', '')}",
                        tags=[t.get("name", "") for t in pkg.get("tags", [])],
                        last_updated=None,
                    )
                )
            except Exception:  # noqa: BLE001
                continue
        return summaries

    def fetch_detail(self, dataset_id: str) -> DatasetDetail | None:
        # Strip the "datagov-" prefix to get the CKAN package name
        ckan_name = dataset_id.removeprefix("datagov-")
        try:
            url = f"{self._base_url}/package_show"
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, params={"id": ckan_name}, headers=self._headers)
                resp.raise_for_status()
                pkg = resp.json().get("result", {})
                return DatasetDetail(
                    dataset_id=dataset_id,
                    name=pkg.get("title", "Untitled"),
                    purpose=pkg.get("notes", "No description available."),
                    major_fields=[],
                    use_cases=[],
                    limitations=["Field-level metadata not available from Data.gov API"],
                    source=DataSource.DATA_GOV,
                    update_frequency=UpdateFrequency.UNKNOWN,
                    url=f"https://catalog.data.gov/dataset/{ckan_name}",
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Data.gov detail fetch failed for {dataset_id}: {exc}")
            return None


# ── Catalog service (orchestrates adapters) ────────────────────────────────────


class DatasetCatalogService:
    """
    Unified interface for dataset discovery and detail retrieval.

    Combines the static catalog (always available) with optional
    live adapter results. Results from the static catalog take precedence
    when dataset_ids collide.
    """

    def __init__(
        self,
        static_adapter: StaticCatalogAdapter | None = None,
        live_adapters: list[DatasetAdapter] | None = None,
    ) -> None:
        self._static = static_adapter or StaticCatalogAdapter()
        self._live: list[DatasetAdapter] = live_adapters or []

    def list_datasets(
        self,
        query: str | None = None,
        source_filter: str | None = None,
        tags: list[str] | None = None,
    ) -> list[DatasetSummary]:
        """
        Return all matching datasets.

        Applies optional keyword, source, and tag filters.
        Static catalog results appear first.
        """
        datasets: list[DatasetSummary] = list(self._static.fetch_summaries())

        # Merge live adapter results (avoid duplicates by dataset_id)
        existing_ids = {d.dataset_id for d in datasets}
        for adapter in self._live:
            for ds in adapter.fetch_summaries():
                if ds.dataset_id not in existing_ids:
                    datasets.append(ds)
                    existing_ids.add(ds.dataset_id)

        # Apply source filter
        if source_filter:
            datasets = [d for d in datasets if d.source.value == source_filter]

        # Apply tag filter
        if tags:
            tag_set = {t.lower() for t in tags}
            datasets = [
                d for d in datasets
                if any(t.lower() in tag_set for t in d.tags)
            ]

        # Apply keyword search
        if query:
            keywords = query.lower().split()
            datasets = [
                d for d in datasets
                if keyword_match_score(
                    f"{d.name} {d.description} {' '.join(d.tags)}", keywords
                ) > 0
            ]

        return datasets

    def get_dataset_detail(self, dataset_id: str) -> DatasetDetail | None:
        """Return full DatasetDetail, checking static catalog first then live adapters."""
        detail = self._static.fetch_detail(dataset_id)
        if detail:
            return detail
        for adapter in self._live:
            detail = adapter.fetch_detail(dataset_id)
            if detail:
                return detail
        return None

    def get_all_dataset_ids(self) -> list[str]:
        """Return all known dataset IDs (static catalog only for reliability)."""
        return self._static.all_dataset_ids()


@lru_cache(maxsize=1)
def get_catalog_service() -> DatasetCatalogService:
    """Return singleton DatasetCatalogService with settings-driven adapters."""
    settings = get_settings()
    static = StaticCatalogAdapter()
    live: list[DatasetAdapter] = []
    if settings.data_gov_api_base_url:
        live.append(DataGovAdapter(settings.data_gov_api_base_url, settings.data_gov_api_key))
    return DatasetCatalogService(static_adapter=static, live_adapters=live)
