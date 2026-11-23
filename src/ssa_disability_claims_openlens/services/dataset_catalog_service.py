"""
Dataset Catalog Service — SSA disability dataset metadata, grounded in official records.

Grounding rule
--------------
Facts that can be checked are never hand-typed here. A dataset's name, description,
landing page, download links, data dictionary, last-modified date, update frequency
and temporal coverage come only from:

  1. data/datagov_snapshot.json — SSA's own DCAT records on Data.gov, written by
     scripts/sync_catalog.py (run it after editing data/catalog_sources.json), or
  2. data/catalog_sources.json "manual" entries — for resources with no Data.gov
     record, each with who verified the URL, how, and when. A manual verification
     older than its max_age_days stops its URL from being shown.

This module adds only curated analyst notes (purpose, use cases, limitations,
a summary field list) keyed by dataset_id. Those notes must not contradict the
source record, and the field lists are flagged fields_verified=False unless they
were checked against the publisher's data dictionary.

Architecture:
  DatasetCatalogService loads from two adapters in priority order:
    1. StaticCatalogAdapter — snapshot + curated notes (works offline)
    2. DataGovAdapter       — live search of the Data.gov catalog API (optional)
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from abc import ABC, abstractmethod
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from ..config import get_settings
from ..models import (
    DatasetDetail,
    DatasetField,
    DatasetSummary,
    DataSource,
    UpdateFrequency,
)
from ..utils import get_logger

logger = get_logger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SOURCES_PATH = _DATA_DIR / "catalog_sources.json"
SNAPSHOT_PATH = _DATA_DIR / "datagov_snapshot.json"


# ── Helpers ────────────────────────────────────────────────────────────────────

_FREQUENCY_MAP: dict[str, UpdateFrequency] = {
    "daily": UpdateFrequency.DAILY,
    "weekly": UpdateFrequency.WEEKLY,
    "monthly": UpdateFrequency.MONTHLY,
    "quarterly": UpdateFrequency.QUARTERLY,
    "annual": UpdateFrequency.ANNUALLY,
    "annually": UpdateFrequency.ANNUALLY,
    "irregular": UpdateFrequency.IRREGULAR,
    "r/p1d": UpdateFrequency.DAILY,
    "r/p1w": UpdateFrequency.WEEKLY,
    "r/p1m": UpdateFrequency.MONTHLY,
    "r/p3m": UpdateFrequency.QUARTERLY,
    "r/p1y": UpdateFrequency.ANNUALLY,
}


def map_frequency(value: str | None) -> UpdateFrequency:
    """Map a DCAT accrualPeriodicity value to UpdateFrequency (UNKNOWN if absent)."""
    if not value:
        return UpdateFrequency.UNKNOWN
    return _FREQUENCY_MAP.get(value.strip().lower(), UpdateFrequency.UNKNOWN)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _primary_url(record: dict[str, Any], prefer_download: bool = False) -> str:
    """
    Landing page, else the first HTML distribution, else the first distribution.

    prefer_download skips the landing page — used for FOIA releases whose landing
    page is the generic https://www.ssa.gov/foia/ index rather than the dataset.
    """
    dists = record.get("distributions") or []
    if prefer_download and dists:
        return str(dists[0]["url"])
    if record.get("landing_page"):
        return str(record["landing_page"])
    for dist in dists:
        if str(dist.get("format", "")).upper() in ("HTML", "HTM"):
            return str(dist["url"])
    return str(dists[0]["url"]) if dists else ""


def _temporal_label(record: dict[str, Any]) -> str:
    start, end = record.get("temporal_start"), record.get("temporal_end")
    if start and end:
        return f"{start[:4]}–{end[:4]} (per Data.gov record)"
    if start:
        return f"{start[:4]} onward (per Data.gov record; end date not stated)"
    return "Not stated in the Data.gov record"


# Data.gov slugs are lowercase letters, digits, hyphens and underscores. Live results
# with any other slug are dropped, so every dataset_id the server hands out also
# passes the tools' DatasetId validation.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,119}$")

def _clean_untrusted(value: Any, limit: int) -> str:
    """
    Normalise third-party text from live Data.gov results before it reaches the model.

    The text is still untrusted. This replaces control and format characters
    (Unicode categories Cc and Cf, which include zero-width characters and
    bidirectional overrides that can hide text from a human reader), collapses
    whitespace and caps the length, so a record cannot hide instructions or flood
    the context. It does not make the content trustworthy.
    """
    if value is None:
        return ""
    raw = str(value)[: limit * 4]  # bound the work before scanning
    visible = "".join(" " if unicodedata.category(ch) in ("Cc", "Cf") else ch for ch in raw)
    text = " ".join(visible.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except FileNotFoundError:
        logger.error(f"Catalog file missing: {path}. Run scripts/sync_catalog.py.")
        return {}


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


# ── Curated analyst notes ──────────────────────────────────────────────────────
# Keyed by dataset_id from data/catalog_sources.json. Only judgement-based content
# lives here. Anything checkable (names, URLs, dates, frequency, coverage period)
# comes from the snapshot. Field lists summarise the source record's description;
# confirm against the data dictionary before setting "fields_verified": True.

# fmt: off
_CURATED_NOTES: dict[str, dict[str, Any]] = {
    "ssa-oasdi-beneficiaries-by-state": {
        "tags": ["OASDI", "beneficiaries", "geographic", "state", "county", "SSDI"],
        "purpose": (
            "Local-level statistics on people receiving Social Security benefits, by benefit "
            "type and beneficiary category. Supports geographic analysis of where disabled-worker "
            "beneficiaries live."
        ),
        "geographic_coverage": "State and county",
        "major_fields": [
            DatasetField(name="state", data_type="string", description="State", is_key_field=True),
            DatasetField(name="county", data_type="string", description="County within state", is_key_field=True),
            DatasetField(name="year", data_type="integer", description="Reference year of the annual publication", is_key_field=True),
            DatasetField(name="beneficiaries_by_benefit_type", data_type="integer", description="Beneficiaries by benefit type (retirement, survivors, disability)"),
            DatasetField(name="beneficiaries_by_category", data_type="integer", description="Beneficiaries by category, including disabled workers"),
        ],
        "use_cases": [
            "Identify states and counties with high concentrations of disabled-worker beneficiaries",
            "Track year-over-year changes in disability beneficiaries by geography",
            "Provide the population denominator for field office access analysis",
        ],
        "limitations": [
            "Covers people receiving benefits — applications, denials and pending claims are not part of this publication",
            "Annual publication — no monthly detail",
            "Race and ethnicity are not listed in the source record's description",
        ],
    },
    "ssa-ssi-recipients-by-state": {
        "tags": ["SSI", "recipients", "geographic", "state", "county", "payments"],
        "purpose": (
            "Annual statistics on SSI recipients, federal payments and federally administered "
            "state supplementation, by state and county."
        ),
        "geographic_coverage": "State and county",
        # The Data.gov record has no accrualPeriodicity; its description says
        # "An annual statistical report".
        "frequency_if_unstated": UpdateFrequency.ANNUALLY,
        "major_fields": [
            DatasetField(name="state", data_type="string", description="State", is_key_field=True),
            DatasetField(name="county", data_type="string", description="County within state", is_key_field=True),
            DatasetField(name="year", data_type="integer", description="Reference year of the annual report", is_key_field=True),
            DatasetField(name="recipients", data_type="integer", description="SSI recipients"),
            DatasetField(name="federal_payments", data_type="float", description="Federal SSI payments"),
            DatasetField(name="state_supplementation", data_type="float", description="Federally administered state supplementation"),
        ],
        "use_cases": [
            "Track SSI program size by state and county",
            "Identify counties with high concentrations of SSI recipients",
            "Support state-level fiscal and social-services coordination analysis",
        ],
        "limitations": [
            "Annual publication — no monthly detail",
            "Counts recipients — applicants and denials are not part of this publication",
            "No recipient income, asset or housing data",
        ],
    },
    "ssa-di-annual-statistical-report": {
        "tags": ["SSDI", "beneficiaries", "demographics", "disability statistics", "annual report"],
        "purpose": (
            "SSA's annual statistical report on people receiving Social Security disability "
            "benefits (disabled workers, disabled widow(er)s and disabled adult children), "
            "with program and demographic statistics."
        ),
        "geographic_coverage": "Not stated in the source record — check the report's table list",
        "major_fields": [
            DatasetField(name="year", data_type="integer", description="Report year", is_key_field=True),
            DatasetField(name="beneficiary_category", data_type="string", description="Disabled workers, disabled widow(er)s, disabled adult children", is_key_field=True),
            DatasetField(name="demographic_characteristics", data_type="string", description="Demographic statistics about beneficiaries (see the report tables for the specific breakdowns)"),
        ],
        "use_cases": [
            "Describe the demographic profile of SSDI beneficiaries",
            "Track long-run trends in the disabled beneficiary population",
        ],
        "limitations": [
            "Describes people receiving benefits — for applications and allowance rates use SSA Disability Claim Data or SSA State Agency Workload Data",
            "Published as report tables; the Data.gov record lists no machine-readable download",
            "Which breakdowns are included (e.g. age, sex, diagnosis) has not been checked against the report tables",
            "Race and ethnicity are not listed in the source record's description",
        ],
    },
    "ssa-disability-claim-data": {
        "tags": ["SSDI", "SSI", "applications", "allowance rate", "state", "initial claims", "DDS", "geographic"],
        "purpose": (
            "Fiscal-year data, by state, on initial disability claims referred to state agencies "
            "(Disability Determination Services) for a disability determination."
        ),
        "geographic_coverage": "State",
        "major_fields": [
            DatasetField(name="fiscal_year", data_type="integer", description="Federal fiscal year", is_key_field=True),
            DatasetField(name="state", data_type="string", description="State", is_key_field=True),
            DatasetField(name="receipts", data_type="integer", description="Initial claims received"),
            DatasetField(name="determinations", data_type="integer", description="Initial determinations made"),
            DatasetField(name="eligible_population", data_type="integer", description="Eligible population"),
            DatasetField(name="favorable_determination_rate", data_type="float", description="Share of determinations that were favorable (allowances)"),
        ],
        "use_cases": [
            "Compare initial-level allowance (favorable determination) rates across states",
            "Relate state claim volumes to eligible population",
            "Track state trends in initial disability claims over fiscal years",
        ],
        "limitations": [
            "Initial claims at the state agency level only — hearing and appeals outcomes are not part of this dataset",
            "State level only — no county or field office detail",
            "Race and ethnicity are not listed in the source record's description",
        ],
    },
    "ssa-state-agency-workload-data": {
        "tags": ["SSDI", "SSI", "allowance rate", "state", "workload", "pending", "reconsideration", "CDR", "DDS", "geographic"],
        "purpose": (
            "Monthly state-level workload for disability cases referred to state agencies: "
            "initial claims, reconsiderations and continuing disability reviews, broken out by "
            "claim title (SSDI, SSI)."
        ),
        "geographic_coverage": "State",
        "major_fields": [
            DatasetField(name="month", data_type="date", description="Reporting month", is_key_field=True),
            DatasetField(name="state", data_type="string", description="State", is_key_field=True),
            DatasetField(name="case_type", data_type="string", description="Initial claim, reconsideration, or continuing disability review", is_key_field=True),
            DatasetField(name="claim_title", data_type="string", description="SSDI or SSI"),
            DatasetField(name="receipts", data_type="integer", description="Cases received"),
            DatasetField(name="end_of_month_pending", data_type="integer", description="Cases pending at end of month"),
            DatasetField(name="decisions", data_type="integer", description="Decisions made"),
            DatasetField(name="allowances", data_type="integer", description="Decisions that were allowances"),
        ],
        "use_cases": [
            "Compute monthly state allowance rates at the initial and reconsideration levels",
            "Monitor state agency pending workloads over time",
            "Compare SSDI and SSI outcomes by state",
        ],
        "limitations": [
            "State agency levels only (initial, reconsideration, CDR) — hearing-level outcomes are not included",
            "State level only — no county or field office detail",
            "Race and ethnicity are not listed in the source record's description",
        ],
    },
    "ssa-hearing-office-workload": {
        "tags": ["OHO", "hearing", "appeals", "processing time", "backlog", "pending", "adjudication"],
        "purpose": (
            "Four workload indicators — pending, receipts, dispositions and average processing "
            "time — for each Office of Hearings Operations (OHO) hearing office."
        ),
        "geographic_coverage": "Each OHO hearing office",
        "major_fields": [
            DatasetField(name="hearing_office", data_type="string", description="OHO hearing office", is_key_field=True),
            DatasetField(name="pending", data_type="integer", description="Cases pending"),
            DatasetField(name="receipts", data_type="integer", description="Cases received"),
            DatasetField(name="dispositions", data_type="integer", description="Cases disposed"),
            DatasetField(name="average_processing_time", data_type="float", description="Average processing time"),
        ],
        "use_cases": [
            "Compare hearing backlogs across hearing offices",
            "Identify hearing offices with the longest average processing times",
        ],
        "limitations": [
            "This record is the current report; past months are published as separate Data.gov records",
            "Averages only — no distribution (median, percentiles)",
            "Claimant demographics are not listed in the source record's description",
        ],
    },
    "ssa-hearing-wait-time": {
        "tags": ["OHO", "hearing", "wait time", "processing time", "appeals"],
        "purpose": (
            "Average time, in months, from the hearing request date until a hearing is held, "
            "for claims closed in OHO hearing offices."
        ),
        "geographic_coverage": "OHO hearing offices (level of aggregation: see data dictionary)",
        "major_fields": [
            DatasetField(name="average_wait_months", data_type="float", description="Average months from hearing request to hearing held"),
        ],
        "use_cases": [
            "Track how long claimants wait for a hearing",
            "Compare hearing wait times across offices (if reported per office — check the data dictionary)",
        ],
        "limitations": [
            "Measures the hearing request-to-hearing interval only — not the time from initial application",
            "Averages only — no distribution (median, percentiles)",
            "This record is the current report; past months are published as separate Data.gov records",
        ],
    },
    "ssa-field-office-locator": {
        "tags": ["field office", "geographic", "access", "locations"],
        "purpose": (
            "Web service and downloadable file of SSA field office locations, telephone numbers "
            "and hours of operation."
        ),
        "geographic_coverage": "All SSA field offices",
        "major_fields": [
            DatasetField(name="office", data_type="string", description="Field office", is_key_field=True),
            DatasetField(name="address", data_type="string", description="Office location"),
            DatasetField(name="telephone", data_type="string", description="Office telephone number"),
            DatasetField(name="hours", data_type="string", description="Hours of operation"),
        ],
        "use_cases": [
            "Map SSA field office locations",
            "Relate office locations to county beneficiary counts for access analysis",
        ],
        "limitations": [
            "Directory only — no visit volumes, wait times or staffing per office",
            "Current snapshot — no history of office openings or closures",
            "No formal service-area boundaries",
        ],
    },
    "ssa-field-office-visitors": {
        "tags": ["field office", "visitors", "walk-in", "access", "demand"],
        "purpose": (
            "Average daily number of field office visitors: monthly visitor counts divided by "
            "the number of days in the month."
        ),
        "geographic_coverage": "Not stated in the source record (national vs. per office — check the data page)",
        "major_fields": [
            DatasetField(name="month", data_type="date", description="Reporting month", is_key_field=True),
            DatasetField(name="average_daily_visitors", data_type="float", description="Average daily field office visitors"),
        ],
        "use_cases": [
            "Track demand for in-person service over time",
        ],
        "limitations": [
            "Average daily visitors only — no appointment wait times or staffing",
            "Per-office breakdown is not described in the source record",
        ],
    },
    "ssa-initial-disability-processing-time": {
        "tags": ["processing time", "initial claims", "SSDI", "SSI", "wait time", "performance"],
        "purpose": (
            "Average elapsed days from filing to payment or denial notice for initial disability "
            "claims that need a medical determination (SSDI and SSI blind/disabled combined)."
        ),
        "geographic_coverage": "Not stated in the source record (check the data page for national vs. state)",
        "major_fields": [
            DatasetField(name="month", data_type="date", description="Reporting month (fiscal years 2016 on)", is_key_field=True),
            DatasetField(name="average_processing_days", data_type="float", description="Cumulative elapsed days, filing to payment or denial notice"),
        ],
        "use_cases": [
            "Track how long initial disability decisions take over time",
            "Compare initial-level waits with hearing-level waits",
        ],
        "limitations": [
            "Averages only — no distribution (median, percentiles)",
            "Combined SSDI/SSI figure; geographic breakdown not described in the record",
        ],
    },
    "ssa-reconsideration-processing-time": {
        "tags": ["processing time", "reconsideration", "appeals", "wait time", "performance"],
        "purpose": (
            "Average elapsed days from filing to payment or denial notice for reconsideration "
            "claims that need a medical determination (technical denials excluded)."
        ),
        "geographic_coverage": "Not stated in the source record",
        "major_fields": [
            DatasetField(name="fiscal_year", data_type="integer", description="Fiscal year (2014 on)", is_key_field=True),
            DatasetField(name="average_processing_days", data_type="float", description="Cumulative elapsed days, filing to payment or denial notice"),
        ],
        "use_cases": [
            "Track reconsideration-level processing times",
            "Build an approximate end-to-end timeline with initial and hearing-level data",
        ],
        "limitations": [
            "Annual averages only",
            "Excludes technical denials",
        ],
    },
    "ssa-alj-disposition-data": {
        "tags": ["ALJ", "hearing", "appeals", "allowance rate", "dispositions", "OHO", "adjudication"],
        "purpose": (
            "Hearing completions by individual administrative law judge (ALJ) in the Office of "
            "Hearings Operations, with hearing office, dispositions, decisions, allowances, denials "
            "and fully or partially favorable decisions."
        ),
        "geographic_coverage": "Each ALJ and hearing office",
        "major_fields": [
            DatasetField(name="alj_name", data_type="string", description="Administrative law judge", is_key_field=True),
            DatasetField(name="hearing_office", data_type="string", description="Hearing office", is_key_field=True),
            DatasetField(name="total_dispositions", data_type="integer", description="Total dispositions"),
            DatasetField(name="decisions", data_type="integer", description="Decisions"),
            DatasetField(name="allowances", data_type="integer", description="Allowances"),
            DatasetField(name="denials", data_type="integer", description="Denials"),
            DatasetField(name="fully_favorable", data_type="integer", description="Fully favorable decisions"),
            DatasetField(name="partially_favorable", data_type="integer", description="Partially favorable decisions"),
        ],
        "use_cases": [
            "Compute hearing-level allowance rates by hearing office or ALJ",
            "Compare hearing-level outcomes with state agency allowance rates",
        ],
        "limitations": [
            "Current report only; past months are separate Data.gov records",
            "No mapping of hearing offices to the states or counties they serve",
            "Claimant demographics are not listed in the source record's description",
        ],
    },
    "ssa-dds-accuracy": {
        "tags": ["accuracy", "DDS", "performance", "quality", "state agency"],
        "purpose": "Accuracy rates for disability medical determinations made by state Disability Determination Services.",
        "geographic_coverage": "Not stated in the source record (check the data page for national vs. state)",
        "major_fields": [
            DatasetField(name="fiscal_year", data_type="integer", description="Fiscal year (2007 on)", is_key_field=True),
            DatasetField(name="accuracy_rate", data_type="float", description="Accuracy rate of DDS medical determinations"),
        ],
        "use_cases": [
            "Track the quality of initial disability determinations over time",
        ],
        "limitations": [
            "Accuracy as measured by SSA's own quality review",
            "Record last modified 2023 — check the data page for recent years",
        ],
    },
    "ssa-ticket-to-work-fy11-17": {
        "tags": ["Ticket to Work", "work incentives", "employment", "return to work", "employment networks"],
        "purpose": "Total number of tickets assigned to Employment Networks, FY2011–FY2017 (FOIA release).",
        "geographic_coverage": "Not stated in the source record",
        "prefer_download": True,
        "major_fields": [
            DatasetField(name="fiscal_year", data_type="integer", description="Fiscal year (2011–2017)", is_key_field=True),
            DatasetField(name="tickets_assigned", data_type="integer", description="Tickets assigned to Employment Networks"),
        ],
        "use_cases": [
            "Describe Ticket to Work participation trends for FY2011–2017",
        ],
        "limitations": [
            "Ends in FY2017 — one-time FOIA release, not an ongoing series",
            "Ticket assignments only — no employment or earnings outcomes",
        ],
    },
    "ssa-national-beneficiary-survey": {
        "tags": ["survey", "beneficiaries", "employment", "work incentives", "health", "demographics"],
        "purpose": (
            "Descriptive statistics from the National Beneficiary Survey: beneficiary characteristics "
            "and health, program and service participation, employment interest and activity, job "
            "characteristics, and how benefits and employment interact."
        ),
        "geographic_coverage": "Not stated in the source record",
        "frequency_if_unstated": UpdateFrequency.IRREGULAR,
        "major_fields": [
            DatasetField(name="survey_year", data_type="integer", description="Survey year (2015, 2019)", is_key_field=True),
            DatasetField(name="statistic", data_type="string", description="Descriptive statistic on beneficiary characteristics, participation or employment"),
        ],
        "use_cases": [
            "Describe employment interest and activity among disability beneficiaries",
            "Context for work incentive participation questions",
        ],
        "limitations": [
            "Survey-based estimates for 2015 and 2019 only",
            "Published as report tables",
        ],
    },
    "ssa-field-office-employee-counts-2016": {
        "tags": ["field office", "staffing", "employees", "capacity"],
        "purpose": "Number of employees in each SSA field office for FY2016 (FOIA release).",
        "geographic_coverage": "Each field office (per dataset title)",
        "prefer_download": True,
        "major_fields": [
            DatasetField(name="field_office", data_type="string", description="Field office", is_key_field=True),
            DatasetField(name="employee_count", data_type="integer", description="Employees, FY2016"),
        ],
        "use_cases": [
            "Historical baseline for field office staffing levels",
        ],
        "limitations": [
            "FY2016 only — one-time FOIA release, not an ongoing series",
        ],
    },
    "ssa-field-office-visitor-counts-2016": {
        "tags": ["field office", "visitors", "walk-in", "demand"],
        "purpose": "Number of people who visited SSA field offices in FY2016 (FOIA release).",
        "geographic_coverage": "Field offices (per dataset title)",
        "prefer_download": True,
        "major_fields": [
            DatasetField(name="field_office", data_type="string", description="Field office", is_key_field=True),
            DatasetField(name="visitor_count", data_type="integer", description="Visitors, FY2016"),
        ],
        "use_cases": [
            "Historical baseline for in-person demand by office",
        ],
        "limitations": [
            "FY2016 only — one-time FOIA release, not an ongoing series",
        ],
    },
    "ssa-field-office-appointments-21-days": {
        "tags": ["field office", "appointments", "wait time", "access"],
        "purpose": (
            "Monthly percentage of field office claims appointments scheduled within 21 days, "
            "FY2005–2015. (SSA's public service indicator is 'within 28 days'.)"
        ),
        "geographic_coverage": "Not stated in the source record",
        "frequency_if_unstated": UpdateFrequency.MONTHLY,
        "major_fields": [
            DatasetField(name="month", data_type="date", description="Reporting month", is_key_field=True),
            DatasetField(name="pct_scheduled_within_21_days", data_type="float", description="Share of claims appointments scheduled within 21 days"),
        ],
        "use_cases": [
            "Historical view of how quickly claimants could get field office appointments",
        ],
        "limitations": [
            "Discontinued — ends September 2015",
            "A threshold share, not an average wait time",
        ],
    },
    "ssa-field-office-claims-pending": {
        "tags": ["field office", "pending", "backlog", "claims", "workload"],
        "purpose": (
            "Yearly national count of all claims pending (in process, not yet adjudicated) in "
            "SSA field offices, FY2006–2022. Covers retirement, survivor, disability and SSI claims."
        ),
        "geographic_coverage": "National only",
        "frequency_if_unstated": UpdateFrequency.ANNUALLY,
        "major_fields": [
            DatasetField(name="fiscal_year", data_type="integer", description="Federal fiscal year (2006–2022)", is_key_field=True),
            DatasetField(name="claims_pending", data_type="integer", description="All field office claims pending at year end"),
        ],
        "use_cases": [
            "Track the national trend in field office claim backlogs",
        ],
        "limitations": [
            "National total only — no per-office or per-state counts",
            "All claim types combined (RSI, DI, SSI) — disability claims are not broken out",
            "Pending counts only — no processing or wait times",
            "Ends in FY2022",
        ],
    },
    "ssa-field-office-telephone-service": {
        "tags": ["field office", "telephone", "access", "answer rate", "busy rate", "service"],
        "purpose": (
            "Monthly national answer rate and busy rate for calls to SSA field offices, "
            "fiscal years 2013 on."
        ),
        "geographic_coverage": "National only",
        "major_fields": [
            DatasetField(name="month", data_type="date", description="Reporting month", is_key_field=True),
            DatasetField(name="answer_rate", data_type="float", description="Share of calls to field offices that were answered"),
            DatasetField(name="busy_rate", data_type="float", description="Share of calls that received a busy signal"),
        ],
        "use_cases": [
            "Track phone access to field offices over time",
        ],
        "limitations": [
            "National only — no per-office figures",
            "Excludes abandoned calls and calls that waited past the 15-minute maximum",
            "Answer and busy rates, not call wait times",
        ],
    },
    "ssa-title2-claim-receipts-by-field-office-2016": {
        "tags": ["field office", "claims", "receipts", "SSDI", "workload", "demand"],
        "purpose": "Number of Title II disability claims received by each SSA field office in FY2016 (FOIA release).",
        "geographic_coverage": "Each field office (per dataset title)",
        "prefer_download": True,
        "major_fields": [
            DatasetField(name="field_office", data_type="string", description="Field office", is_key_field=True),
            DatasetField(name="title2_disability_receipts", data_type="integer", description="Title II disability claims received, FY2016 (includes 53rd week)"),
        ],
        "use_cases": [
            "Historical baseline for disability claim volume by field office",
            "Combine with FY2016 employee counts for a one-year claims-per-staff ratio",
        ],
        "limitations": [
            "FY2016 only — one-time FOIA release, not an ongoing series",
            "Title II (SSDI) only — SSI disability claims are not included",
            "Claim receipts only — no pending counts or decision times",
        ],
    },
    "ssa-di-ssi-participants-employment-2015": {
        "tags": ["employment", "return to work", "work activity", "SSDI", "SSI", "chartbook"],
        "purpose": (
            "Chartbook on the work activity of working-age adult SSDI beneficiaries and SSI "
            "recipients before and after disability award: work activity, employment expectations "
            "and characteristics, employment services, and factors affecting employment."
        ),
        "geographic_coverage": "Not stated in the source record",
        "major_fields": [
            DatasetField(name="work_activity", data_type="string", description="Work activity before and after award (chart series)"),
        ],
        "use_cases": [
            "Indirect evidence on how many beneficiaries work after award",
        ],
        "limitations": [
            "One edition (2015); published as charts, not a time series",
            "Work activity, not benefit suspensions or terminations due to work",
        ],
    },
    "ssa-nscf": {
        "tags": ["survey", "SSI", "children", "income", "socioeconomic", "household", "housing"],
        "purpose": (
            "National Survey of SSI Children and Families (2001–2002): health, functional "
            "limitations, services, SSI experience, household socioeconomic status and housing for "
            "over 8,000 children receiving, formerly receiving, or applying for SSI."
        ),
        "geographic_coverage": "Continental United States (excludes Alaska, Hawaii and territories)",
        "frequency_if_unstated": UpdateFrequency.IRREGULAR,
        "major_fields": [
            DatasetField(name="household_socioeconomic_status", data_type="string", description="Socioeconomic status of the child's household"),
            DatasetField(name="housing_characteristics", data_type="string", description="Housing characteristics"),
            DatasetField(name="ssi_status", data_type="string", description="Receiving, formerly receiving, or applying for SSI"),
        ],
        "use_cases": [
            "Historical evidence on the economic circumstances of SSI child applicants and recipients",
        ],
        "limitations": [
            "One-time survey, 2001–2002",
            "Children only — no adult applicants or recipients",
            "Not linked to current program data",
        ],
    },
    "ssa-red-book": {
        "tags": ["work incentives", "Ticket to Work", "SGA", "employment", "return to work"],
        "purpose": (
            "SSA's guide to work incentive rules for people with disabilities who receive "
            "SSDI or SSI. A policy reference, not a statistical dataset."
        ),
        "geographic_coverage": "National (policy applies uniformly)",
        "major_fields": [],
        "use_cases": [
            "Look up work incentive rules relevant to return-to-work questions",
        ],
        "limitations": [
            "Policy reference — not a statistical dataset",
            "No participation counts or outcomes for work incentive programs",
            "No Data.gov record; the link is checked manually",
        ],
    },
}
# fmt: on


def _manual_is_current(entry: dict[str, Any], today: date | None = None) -> bool:
    verified = _parse_date(entry.get("verified_on"))
    if verified is None:
        return False
    max_age = int(entry.get("max_age_days", 180))
    return ((today or date.today()) - verified).days <= max_age


# ── Static catalog (snapshot + curated notes; always available) ───────────────


class StaticCatalogAdapter(DatasetAdapter):
    """Serves the grounded catalog: Data.gov snapshot facts + curated notes."""

    def __init__(
        self,
        sources: dict[str, Any] | None = None,
        snapshot: dict[str, Any] | None = None,
        notes: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        sources = sources if sources is not None else _load_json(SOURCES_PATH)
        snapshot = snapshot if snapshot is not None else _load_json(SNAPSHOT_PATH)
        notes = notes if notes is not None else _CURATED_NOTES
        self.synced_at: str = str(snapshot.get("synced_at", ""))
        records: dict[str, Any] = snapshot.get("records", {})

        self._catalog: dict[str, dict[str, Any]] = {}
        self.datagov_slugs: set[str] = set()

        for dataset_id, slug in sources.get("datagov", {}).items():
            record = records.get(dataset_id)
            if record is None or record.get("slug") != slug:
                logger.error(
                    f"No Data.gov snapshot record for {dataset_id!r} (slug {slug!r}); "
                    "entry skipped. Run scripts/sync_catalog.py."
                )
                continue
            self.datagov_slugs.add(slug)
            self._catalog[dataset_id] = self._from_record(dataset_id, record, notes.get(dataset_id, {}))

        for dataset_id, manual in sources.get("manual", {}).items():
            self._catalog[dataset_id] = self._from_manual(dataset_id, manual, notes.get(dataset_id, {}))

    def _from_record(self, dataset_id: str, record: dict[str, Any], note: dict[str, Any]) -> dict[str, Any]:
        frequency = map_frequency(record.get("accrual_periodicity"))
        frequency_note = ""
        if frequency == UpdateFrequency.UNKNOWN and note.get("frequency_if_unstated"):
            frequency = note["frequency_if_unstated"]
            frequency_note = " Update frequency inferred from the record's description."
        synced = self.synced_at[:10]
        return {
            "dataset_id": dataset_id,
            "name": record["title"],
            "description": record["description"],
            "source": DataSource.SSA_OPEN_DATA,
            "update_frequency": frequency,
            "url": _primary_url(record, prefer_download=bool(note.get("prefer_download"))),
            "download_urls": [d["url"] for d in record.get("distributions", [])],
            "data_dictionary_url": record.get("data_dictionary") or "",
            "last_updated": _parse_date(record.get("modified")),
            "temporal_coverage": _temporal_label(record),
            "provenance": (
                f"Data.gov record {record['identifier']} "
                f"(metadata modified {record.get('modified') or 'n/a'}; synced {synced}).{frequency_note}"
            ),
            "source_record_url": record["datagov_url"],
            **self._note_fields(note, record["description"]),
        }

    def _from_manual(self, dataset_id: str, manual: dict[str, Any], note: dict[str, Any]) -> dict[str, Any]:
        current = _manual_is_current(manual)
        if current:
            provenance = (
                f"Manually verified {manual['verified_on']} by {manual['verified_by']} "
                f"({manual['method']}). No Data.gov record."
            )
        else:
            provenance = (
                f"Manual verification from {manual.get('verified_on', 'n/a')} has expired — "
                "link withheld until re-checked."
            )
            logger.warning(f"Manual verification expired for {dataset_id!r}; URL withheld.")
        return {
            "dataset_id": dataset_id,
            "name": manual["title"],
            "description": note.get("purpose", ""),
            "source": DataSource.SSA_OPEN_DATA,
            "update_frequency": UpdateFrequency.UNKNOWN,
            "url": manual["url"] if current else "",
            "download_urls": [],
            "data_dictionary_url": "",
            "last_updated": None,
            "temporal_coverage": "Not applicable (policy reference)",
            "provenance": provenance,
            "source_record_url": "",
            **self._note_fields(note, ""),
        }

    @staticmethod
    def _note_fields(note: dict[str, Any], fallback_purpose: str) -> dict[str, Any]:
        fields_verified = bool(note.get("fields_verified", False))
        limitations = list(note.get("limitations", []))
        if note.get("major_fields") and not fields_verified:
            limitations.append(
                "Field list summarises the official metadata description; it has not been "
                "checked column-by-column against the data dictionary"
            )
        return {
            "tags": list(note.get("tags", [])),
            "purpose": note.get("purpose", fallback_purpose),
            "major_fields": list(note.get("major_fields", [])),
            "fields_verified": fields_verified,
            "use_cases": list(note.get("use_cases", [])),
            "limitations": limitations,
            "geographic_coverage": note.get("geographic_coverage", "Not stated"),
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
                tags=d["tags"],
                last_updated=d["last_updated"],
                provenance=d["provenance"],
                source_record_url=d["source_record_url"],
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
            last_updated=d["last_updated"],
            geographic_coverage=d["geographic_coverage"],
            temporal_coverage=d["temporal_coverage"],
            provenance=d["provenance"],
            source_record_url=d["source_record_url"],
            download_urls=d["download_urls"],
            data_dictionary_url=d["data_dictionary_url"],
            fields_verified=d["fields_verified"],
        )

    def all_dataset_ids(self) -> list[str]:
        return list(self._catalog.keys())


# ── Live Data.gov adapter ──────────────────────────────────────────────────────


class DataGovAdapter(DatasetAdapter):
    """
    Searches the Data.gov catalog API (v1) for SSA disability datasets.

    Uses GET {base}/search?q=...&org_slug=ssa&has_download=true and
    GET {base}/dataset/{slug}. (The old CKAN /api/3/action endpoints were retired.)

    Results are cached for `cache_ttl` seconds, failures for `failure_ttl` seconds,
    so tool calls do not each wait on the network. The last failure is kept in
    `last_error` and surfaced to callers instead of being silently swallowed.

    Security: fetch_detail() only issues a network request for slugs that were
    previously returned by the search in the same process lifetime, so a caller
    cannot use an arbitrary dataset_id to probe the API.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        exclude_slugs: set[str] | None = None,
        cache_ttl: float = 3600.0,
        failure_ttl: float = 300.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"User-Agent": "ssa-openlens-mcp/1.0", "Accept": "application/json"}
        if api_key:
            self._headers["X-Api-Key"] = api_key
        self._exclude = exclude_slugs or set()
        self._cache_ttl = cache_ttl
        self._failure_ttl = failure_ttl
        self._query_cache: dict[str, tuple[float, list[DatasetSummary] | None]] = {}
        self.last_error: str = ""
        # Allowlist of Data.gov slugs discovered via fetch_summaries().
        # fetch_detail() refuses to query any slug not in this set.
        self._known_slugs: set[str] = set()

    def _search(self, query: str, rows: int = 20) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "q": query,
            "org_slug": "ssa",
            "has_download": "true",
            "per_page": rows,
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{self._base_url}/search", params=params, headers=self._headers)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        return results if isinstance(results, list) else []

    @staticmethod
    def _summary_from_result(result: dict[str, Any]) -> DatasetSummary | None:
        slug = result.get("slug")
        dcat = result.get("dcat") or {}
        if not isinstance(slug, str) or not _SLUG_RE.match(slug) or not dcat.get("title"):
            return None
        landing = dcat.get("landingPage")
        if isinstance(landing, dict):
            landing = landing.get("accessURL")
        url = landing if isinstance(landing, str) and landing.startswith("https://") else ""
        if not url:
            for dist in dcat.get("distribution") or []:
                candidate = dist.get("downloadURL") or dist.get("accessURL")
                if isinstance(candidate, str) and candidate.startswith("https://"):
                    url = candidate
                    break
        identifier = _clean_untrusted(dcat.get("identifier"), 64) or slug
        tags = [_clean_untrusted(k, 60) for k in (dcat.get("keyword") or []) if not str(k).isdigit()]
        return DatasetSummary(
            dataset_id=f"datagov-{slug}",
            name=_clean_untrusted(dcat["title"], 300),
            description=_clean_untrusted(dcat.get("description"), 2000) or "No description available.",
            source=DataSource.DATA_GOV,
            update_frequency=map_frequency(dcat.get("accrualPeriodicity")),
            url=url,
            tags=[t for t in tags if t][:10],
            last_updated=_parse_date(dcat.get("modified")),
            provenance=f"Data.gov record {identifier} (live search result)",
            source_record_url=f"https://catalog.data.gov/dataset/{slug}",
        )

    def search(self, query: str, rows: int = 20) -> list[DatasetSummary] | None:
        """
        Search SSA datasets with downloads; static-catalog datasets are excluded.

        Returns None when the API is unavailable (the error is kept in last_error).
        Results are cached per query.
        """
        now = time.monotonic()
        cached = self._query_cache.get(query)
        if cached is not None and now < cached[0]:
            return cached[1]
        try:
            results = self._search(query, rows=rows)
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Data.gov live search unavailable: {exc}"
            logger.warning(self.last_error)
            self._query_cache[query] = (now + self._failure_ttl, None)
            return None

        summaries: list[DatasetSummary] = []
        for result in results:
            try:
                summary = self._summary_from_result(result)
            except Exception:  # noqa: BLE001
                continue
            if summary is None:
                continue
            slug = summary.dataset_id.removeprefix("datagov-")
            if slug in self._exclude:
                continue  # already in the static catalog
            self._known_slugs.add(slug)
            summaries.append(summary)
        self.last_error = ""
        self._query_cache[query] = (now + self._cache_ttl, summaries)
        return summaries

    def fetch_summaries(self) -> list[DatasetSummary]:
        return self.search("disability") or []

    def fetch_detail(self, dataset_id: str) -> DatasetDetail | None:
        slug = dataset_id.removeprefix("datagov-")
        if slug not in self._known_slugs:
            logger.warning(
                f"DataGovAdapter.fetch_detail: '{slug}' is not in the known "
                "dataset allowlist — skipping network request."
            )
            return None
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{self._base_url}/dataset/{slug}", headers=self._headers)
                resp.raise_for_status()
                results = resp.json().get("results") or []
            summary = self._summary_from_result(results[0]) if results else None
            if summary is None:
                return None
            dcat = results[0].get("dcat") or {}
            downloads = [
                u for d in dcat.get("distribution") or []
                if isinstance(u := d.get("downloadURL") or d.get("accessURL"), str) and u.startswith("https://")
            ]
            described_by = dcat.get("describedBy")
            if isinstance(described_by, dict):
                described_by = described_by.get("accessURL")
            return DatasetDetail(
                dataset_id=dataset_id,
                name=summary.name,
                purpose=summary.description,
                major_fields=[],
                use_cases=[],
                limitations=["Field-level metadata not available from the Data.gov record"],
                source=DataSource.DATA_GOV,
                update_frequency=summary.update_frequency,
                url=summary.url,
                last_updated=summary.last_updated,
                provenance=summary.provenance.replace("live search result", "live lookup"),
                source_record_url=summary.source_record_url,
                download_urls=downloads,
                data_dictionary_url=described_by if isinstance(described_by, str) else "",
            )
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Data.gov detail lookup failed for {dataset_id}: {exc}"
            logger.warning(self.last_error)
            return None


# ── Uncatalogued-lead helpers ──────────────────────────────────────────────────

# Words too common in SSA titles to narrow a search (Data.gov matches exact terms).
_GENERIC_TERMS = {
    "ssa", "social", "security", "disability", "disabled", "data", "dataset", "public",
    "state", "national", "number", "rate", "people", "person", "program", "benefit",
    "receive", "receiving", "there", "any", "average", "between", "across", "compare",
    "change", "changed", "year", "differ", "different", "vary", "significantly", "highest",
    "lowest", "common", "most", "parts", "country", "relative", "office", "offices", "time",
    "times", "take", "entire", "process", "ultimately", "after", "all", "being", "get",
}


def _lead_terms(question: str, max_terms: int = 5) -> list[str]:
    from ..utils import extract_keywords  # local import keeps module import order simple

    terms: list[str] = []
    for word in extract_keywords(question):
        word = word.strip("'\"")
        if word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 4:
            word = word[:-1]
        if len(word) > 3 and word not in _GENERIC_TERMS and word.isalpha() and word not in terms:
            terms.append(word)
    return terms[:max_terms]


def _title_stem(title: str) -> str:
    """'Hearing Office Workload Data - August 2025' and '... (series)' share a stem."""
    stem = title.split(" - ")[0].split(" (")[0].split(",")[0]
    return " ".join(stem.lower().split())


# Words a user may search for, mapped to the words SSA's dataset titles and
# descriptions use for the same thing (e.g. SSA says "pending", not "backlog").
_QUERY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "backlog": ("pending",),
    "pending": ("backlog",),
    "wait": ("waiting", "processing time"),
    "waiting": ("wait", "processing time"),
    "delay": ("wait", "processing time"),
    "processing": ("wait",),
}


def _query_alternatives(word: str) -> tuple[str, ...]:
    """The word itself plus its synonyms; plural forms share the singular's synonyms."""
    base = word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word
    return (word, *_QUERY_SYNONYMS.get(base, ()))


def _query_words(query: str) -> list[str]:
    return [w.strip("?.!,;:\"'()[]") for w in query.lower().split() if w.strip("?.!,;:\"'()[]")]


def _live_search_terms(query: str, max_terms: int = 8) -> list[str]:
    """Single-word Data.gov search terms for a discovery query, synonyms included."""
    terms: list[str] = []
    for word in _query_words(query):
        if len(word) < 3 or word in _GENERIC_TERMS:
            continue
        for alt in _query_alternatives(word):
            if " " not in alt and alt not in terms:
                terms.append(alt)
    return terms[:max_terms]


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
        include_live: bool = True,
    ) -> list[DatasetSummary]:
        """
        Return all matching datasets.

        Applies optional keyword, source, and tag filters.
        Static catalog results appear first.

        With a query, Data.gov is searched for that query (plus synonyms) rather than
        a fixed term, so live results are not limited to whatever a generic search
        happened to return. Archived editions of catalogued datasets
        (e.g. "Hearing Office Workload Data - March 2019") are left out.
        """
        static = list(self._static.fetch_summaries())
        if query:
            static = [d for d in static if self._matches_query(d, query)]

        live: list[DatasetSummary] = []
        if include_live:
            existing_ids = {d.dataset_id for d in static}
            seen_stems = {_title_stem(d.name) for d in self._static.fetch_summaries()}
            for adapter in self._live:
                for ds in self._live_results(adapter, query):
                    stem = _title_stem(ds.name)
                    if ds.dataset_id in existing_ids or stem in seen_stems:
                        continue
                    live.append(ds)
                    existing_ids.add(ds.dataset_id)
                    seen_stems.add(stem)

        datasets = static + live

        if source_filter:
            datasets = [d for d in datasets if d.source.value == source_filter]

        if tags:
            tag_set = {t.lower() for t in tags}
            datasets = [
                d for d in datasets
                if any(t.lower() in tag_set for t in d.tags)
            ]

        return datasets

    @staticmethod
    def _matches_query(ds: DatasetSummary, query: str) -> bool:
        """True when any query word, or one of its synonyms, appears in the dataset text."""
        text = f"{ds.name} {ds.description} {' '.join(ds.tags)}".lower()
        return any(
            alt in text for word in _query_words(query) for alt in _query_alternatives(word)
        )

    def _live_results(self, adapter: DatasetAdapter, query: str | None) -> list[DatasetSummary]:
        """Live datasets for a query: searched at the source when the adapter can."""
        if query and isinstance(adapter, DataGovAdapter):
            terms = _live_search_terms(query)
            if terms:
                return adapter.search(" OR ".join(terms)) or []
        results = adapter.fetch_summaries()
        if query:
            results = [d for d in results if self._matches_query(d, query)]
        return results

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

    def find_uncatalogued_leads(self, question: str, limit: int = 3) -> tuple[list[dict[str, str]], str]:
        """
        Live-search Data.gov for SSA datasets relevant to `question` that the static
        catalog has not assessed. Returns (leads, note). Leads are not scored; they tell
        an analyst where the catalog may be missing evidence.
        """
        adapters = [a for a in self._live if isinstance(a, DataGovAdapter)]
        if not adapters:
            return [], "Live Data.gov search is disabled, so uncatalogued datasets were not checked."
        terms = _lead_terms(question)
        if not terms:
            return [], ""
        found = adapters[0].search(" OR ".join(terms), rows=25)
        if found is None:
            return [], "Live Data.gov search was unavailable, so uncatalogued datasets were not checked."

        covered_stems = {_title_stem(ds.name) for ds in self._static.fetch_summaries()}
        leads: list[dict[str, str]] = []
        seen_stems: set[str] = set()
        for ds in found:
            stem = _title_stem(ds.name)
            if stem in covered_stems or stem in seen_stems or not ds.url:
                continue  # an archived edition of a catalogued dataset, or a duplicate
            seen_stems.add(stem)
            identifier = ds.provenance.split(" ")[2] if ds.provenance.startswith("Data.gov record") else ""
            leads.append({"title": ds.name, "identifier": identifier, "url": ds.source_record_url})
            if len(leads) >= limit:
                break
        if not leads:
            return [], f"A live Data.gov search ({', '.join(terms)}) found no other SSA datasets with downloads."
        return leads, f"Live Data.gov search terms: {', '.join(terms)}."

    def source_notes(self) -> list[str]:
        """Human-readable status of each data source, including live-source failures."""
        notes = [f"Static catalog grounded in Data.gov records (snapshot synced {self._static.synced_at or 'never'})."]
        for adapter in self._live:
            error = getattr(adapter, "last_error", "")
            if error:
                notes.append(f"{error}. Results are limited to the static catalog.")
        return notes


@lru_cache(maxsize=1)
def get_catalog_service() -> DatasetCatalogService:
    """Return singleton DatasetCatalogService with settings-driven adapters."""
    settings = get_settings()
    static = StaticCatalogAdapter()
    live: list[DatasetAdapter] = []
    if settings.data_gov_api_base_url:
        live.append(
            DataGovAdapter(
                settings.data_gov_api_base_url,
                settings.data_gov_api_key,
                exclude_slugs=static.datagov_slugs,
                cache_ttl=float(settings.catalog_cache_ttl_seconds),
            )
        )
    return DatasetCatalogService(static_adapter=static, live_adapters=live)
