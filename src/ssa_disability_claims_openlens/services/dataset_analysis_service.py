"""
Dataset Analysis Service — completeness and freshness evaluation.

This service evaluates individual datasets on two orthogonal dimensions:
  1. Completeness: how well does the dataset cover geographic, temporal,
     and operational dimensions of the disability domain?
  2. Freshness: how current is the dataset relative to its stated update frequency?
"""

from __future__ import annotations

from datetime import date

from ..models import (
    CompletenessAnalysis,
    CoverageAxis,
    DatasetDetail,
    FreshnessAssessment,
    FreshnessStatus,
    UpdateFrequency,
)
from ..utils import compute_freshness_score, days_since, frequency_to_expected_days, get_logger

logger = get_logger(__name__)


# ── Completeness scoring knowledge base ───────────────────────────────────────
# Maps dataset_id → coverage axis assessments. Scores are analyst judgements;
# the facts in "details" and "gaps" must be supported by the dataset's Data.gov
# record (see data/datagov_snapshot.json). Datasets not listed here fall back
# to _default_completeness().

_COMPLETENESS_KB: dict[str, dict[str, object]] = {
    "ssa-oasdi-beneficiaries-by-state": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=85.0,
            details="State and county tables",
            gaps=["Sub-county (ZIP/census tract) data not published"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=70.0,
            details="Annual publication; Data.gov record covers 1999–2024",
            gaps=["No monthly or quarterly snapshots",
                  "Within-year trend analysis not possible"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=55.0,
            details="Beneficiaries by benefit type and beneficiary category",
            gaps=["No application, decision or pending-claim data",
                  "Denied applicants excluded"],
        ),
        "missing_dimensions": [
            "Race and ethnicity breakdown",
            "Claimant income levels",
            "Impairment type at sub-national level",
        ],
        "analyst_notes": (
            "Strong geographic foundation for beneficiary analysis. It describes who receives "
            "benefits, not who applies or how claims are decided."
        ),
    },
    "ssa-ssi-recipients-by-state": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=88.0,
            details="State and county tables",
            gaps=["No sub-county detail"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=70.0,
            details="Annual report; Data.gov record covers December 1998–2024",
            gaps=["No monthly or quarterly snapshots"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=55.0,
            details="Recipients, federal payments and federally administered state supplementation",
            gaps=["No applicant or denial data",
                  "No income, housing, or asset data"],
        ),
        "missing_dimensions": [
            "Recipient demographics at county level",
            "Income and asset information",
        ],
        "analyst_notes": (
            "Good geographic depth for SSI program size and payments. Limited for assessing "
            "benefit adequacy or recipient circumstances."
        ),
    },
    "ssa-di-annual-statistical-report": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=40.0,
            details="Geographic detail is not described in the Data.gov record",
            gaps=["Check the report's table list for state-level tables"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=75.0,
            details="Annual report; Data.gov record covers 1960–2025",
            gaps=["Annual only — cannot track within-year changes"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=55.0,
            details="Program and demographic statistics on disability beneficiaries",
            gaps=["Beneficiaries only — applications and decisions are in other datasets",
                  "No machine-readable download listed in the Data.gov record"],
        ),
        "missing_dimensions": [
            "Race and ethnicity",
            "Application and decision outcomes",
        ],
        "analyst_notes": (
            "The main source for the demographic profile of SSDI beneficiaries. Pair it with "
            "SSA Disability Claim Data for application and allowance analysis."
        ),
    },
    "ssa-disability-claim-data": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=70.0,
            details="State level",
            gaps=["No county or field office detail"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=55.0,
            details="Fiscal-year data from October 2000; Data.gov metadata last modified 2022-07-07",
            gaps=["Annual only",
                  "Recent fiscal years may be missing — the record has not been updated since 2022"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=65.0,
            details="Receipts, determinations, eligible population and favorable determination rates for initial claims",
            gaps=["Initial (state agency) level only — no hearing outcomes"],
        ),
        "missing_dimensions": [
            "Race and ethnicity",
            "Sub-state geography",
            "Hearing-level outcomes",
        ],
        "analyst_notes": (
            "Publishes state-level initial allowance (favorable determination) rates — the "
            "key source for comparing states at the initial level."
        ),
    },
    "ssa-state-agency-workload-data": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=70.0,
            details="State level",
            gaps=["No county or field office detail"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=80.0,
            details="Monthly data from October 2000",
            gaps=["Data.gov metadata last modified 2023-08-08 — check the data page for recent months"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=75.0,
            details="Receipts, end-of-month pending, decisions and allowances for initial, reconsideration and CDR cases, by SSDI/SSI",
            gaps=["State agency levels only — no hearing outcomes",
                  "No processing times"],
        ),
        "missing_dimensions": [
            "Race and ethnicity",
            "Processing times",
            "Hearing-level outcomes",
        ],
        "analyst_notes": (
            "The most detailed public view of state agency disability workloads and allowances, "
            "by month and case type."
        ),
    },
    "ssa-hearing-office-workload": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=70.0,
            details="Each OHO hearing office",
            gaps=["No mapping of hearing offices to claimant ZIP code or county"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=70.0,
            details="Monthly current report; past months are separate Data.gov records",
            gaps=["History must be assembled from monthly archive records"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=50.0,
            details="Pending, receipts, dispositions and average processing time",
            gaps=["No processing time distribution (median, percentiles)",
                  "No claimant demographics",
                  "No case complexity data"],
        ),
        "missing_dimensions": [
            "Processing time distribution (not just averages)",
            "Claimant demographics",
            "Case complexity indicators",
        ],
        "analyst_notes": (
            "Best available source for hearing backlog monitoring by office. Averages hide the "
            "distribution of wait times across claimants."
        ),
    },
    "ssa-field-office-locator": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=90.0,
            details="Directory of SSA field offices with locations",
            gaps=["Formal service area boundaries not defined"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=40.0,
            details="Current snapshot, updated quarterly",
            gaps=["Cannot track office closures over time"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=30.0,
            details="Locations, telephone numbers and hours of operation",
            gaps=["No appointment wait time data",
                  "No staffing or capacity information",
                  "No visit volume per office"],
        ),
        "missing_dimensions": [
            "Appointment wait times",
            "Staffing levels",
            "Visit volumes per office",
            "ADA accessibility status",
        ],
        "analyst_notes": (
            "Useful for proximity analysis but lacks the operational data needed to assess "
            "access quality."
        ),
    },
}


def _default_completeness(dataset: DatasetDetail) -> CompletenessAnalysis:
    """Compute a default completeness analysis for datasets not in the KB."""
    # For datasets not explicitly profiled, generate a reasonable default
    has_geo = any(
        kw in (dataset.geographic_coverage or "").lower()
        for kw in ["state", "county", "national", "all 50"]
    )
    geo_score = 50.0 if has_geo else 20.0

    freq_temporal = {
        UpdateFrequency.MONTHLY: 85.0,
        UpdateFrequency.QUARTERLY: 75.0,
        UpdateFrequency.ANNUALLY: 60.0,
        UpdateFrequency.WEEKLY: 90.0,
        UpdateFrequency.IRREGULAR: 40.0,
    }
    temporal_score = freq_temporal.get(dataset.update_frequency, 40.0)

    operational_score = min(50.0 + len(dataset.major_fields) * 5.0, 70.0)

    scores = [geo_score, temporal_score, operational_score]
    overall = sum(scores) / len(scores)

    rating = (
        "Strong" if overall >= 75 else
        "Moderate" if overall >= 50 else
        "Limited"
    )

    return CompletenessAnalysis(
        dataset_id=dataset.dataset_id,
        dataset_name=dataset.name,
        geographic_coverage=CoverageAxis(
            axis="Geographic", score=geo_score,
            details=dataset.geographic_coverage or "Geographic coverage details not available",
            gaps=[],
        ),
        temporal_coverage=CoverageAxis(
            axis="Temporal", score=temporal_score,
            details=dataset.temporal_coverage or "Temporal coverage details not available",
            gaps=[],
        ),
        operational_coverage=CoverageAxis(
            axis="Operational", score=operational_score,
            details=f"Dataset includes {len(dataset.major_fields)} documented fields",
            gaps=[lim for lim in dataset.limitations[:3]],
        ),
        missing_dimensions=[],
        completeness_score=round(overall, 1),
        completeness_rating=rating,
        analyst_notes="Automated assessment — not explicitly profiled in the knowledge base.",
    )


class DatasetAnalysisService:
    """Evaluates dataset completeness and freshness."""

    def analyze_completeness(
        self,
        dataset: DatasetDetail,
        focus_dimensions: list[str] | None = None,
    ) -> CompletenessAnalysis:
        """
        Evaluate dataset coverage along geographic, temporal, and operational axes.

        Uses the pre-profiled knowledge base when available; falls back to
        automated heuristics otherwise.
        """
        kb_entry = _COMPLETENESS_KB.get(dataset.dataset_id)
        if kb_entry is None:
            logger.info(
                f"Dataset {dataset.dataset_id!r} not in completeness KB — using heuristics"
            )
            return _default_completeness(dataset)

        geo: CoverageAxis = kb_entry["geographic"]  # type: ignore[assignment]
        temporal: CoverageAxis = kb_entry["temporal"]  # type: ignore[assignment]
        operational: CoverageAxis = kb_entry["operational"]  # type: ignore[assignment]

        # Apply focus dimension weighting
        if focus_dimensions:
            axes_map = {
                "geographic": geo.score,
                "temporal": temporal.score,
                "operational": operational.score,
            }
            focused_scores = [
                axes_map[dim.lower()]
                for dim in focus_dimensions
                if dim.lower() in axes_map
            ]
            if focused_scores:
                overall = round(sum(focused_scores) / len(focused_scores), 1)
            else:
                overall = round((geo.score + temporal.score + operational.score) / 3, 1)
        else:
            overall = round((geo.score + temporal.score + operational.score) / 3, 1)

        rating = (
            "Strong" if overall >= 75 else
            "Moderate" if overall >= 50 else
            "Limited"
        )

        return CompletenessAnalysis(
            dataset_id=dataset.dataset_id,
            dataset_name=dataset.name,
            geographic_coverage=geo,
            temporal_coverage=temporal,
            operational_coverage=operational,
            missing_dimensions=kb_entry.get("missing_dimensions", []),  # type: ignore[arg-type]
            completeness_score=overall,
            completeness_rating=rating,
            analyst_notes=kb_entry.get("analyst_notes", ""),  # type: ignore[arg-type]
        )

    def assess_freshness(self, dataset: DatasetDetail) -> FreshnessAssessment:
        """
        Evaluate how current the dataset is relative to its stated update frequency.
        """
        score, status, staleness = compute_freshness_score(
            dataset.last_updated, dataset.update_frequency
        )
        elapsed = days_since(dataset.last_updated)

        return FreshnessAssessment(
            dataset_id=dataset.dataset_id,
            dataset_name=dataset.name,
            last_updated=dataset.last_updated,
            update_frequency=dataset.update_frequency,
            days_since_update=elapsed,
            freshness_score=score,
            freshness_status=status,
            freshness_rationale=self._freshness_rationale(
                score, status, dataset.update_frequency, dataset.last_updated, elapsed
            ),
            staleness_indicators=staleness,
            analyst_notes=self._freshness_note(score, dataset.update_frequency, elapsed),
        )

    @staticmethod
    def _freshness_rationale(
        score: float,
        status: FreshnessStatus,
        freq: UpdateFrequency,
        last_updated: date | None,
        elapsed: int | None,
    ) -> str:
        if status == FreshnessStatus.UNKNOWN or elapsed is None or last_updated is None:
            return (
                "OpenLens could not determine dataset freshness because required update "
                "metadata is unavailable. The dataset is classified as Unknown until "
                "sufficient metadata is available."
            )

        expected = frequency_to_expected_days(freq) or 180
        overdue = elapsed - expected

        line1 = f"- This dataset is expected to be updated {freq.value.lower()}."
        line2 = f"- The most recent catalog metadata indicates an update date of {last_updated}."

        if status == FreshnessStatus.CURRENT:
            line3 = f"- The dataset is {elapsed} days old, which is within the expected {freq.value.lower()} refresh interval."
            line4 = f"- As a result, the dataset is classified as Current and receives a freshness score of {round(score)}/100."
        elif status == FreshnessStatus.AGING:
            line3 = f"- The dataset is {elapsed} days old, which exceeds the expected {freq.value.lower()} refresh interval by {overdue} days."
            line4 = f"- As a result, the dataset is classified as Aging and receives a freshness score of {round(score)}/100."
        else:  # STALE
            line3 = f"- The dataset is {elapsed} days old, which exceeds the expected {freq.value.lower()} refresh interval by {overdue} days."
            line4 = f"- As a result, the dataset is classified as Stale and receives a freshness score of {round(score)}/100."

        return f"{line1}\n{line2}\n{line3}\n{line4}"

    @staticmethod
    def _freshness_note(
        score: float, freq: UpdateFrequency, elapsed: int | None
    ) -> str:
        if elapsed is None:
            return (
                "- Freshness could not be assessed due to missing update metadata.\n"
                "- Confirm the dataset is still actively maintained before use."
            )
        if score >= 90:
            return (
                "- Dataset is current and suitable for use in analysis.\n"
                "- Continue monitoring for updates per the expected refresh schedule."
            )
        if score >= 60:
            return (
                "- This dataset may not reflect the most recent program conditions.\n"
                "- Consider validating findings against more recent SSA publications or reports.\n"
                "- Monitor for an updated release before relying on time-sensitive analysis."
            )
        return (
            "- This dataset may not accurately reflect current program conditions.\n"
            "- Consider validating findings against more recent SSA publications or reports.\n"
            "- Consider requesting updated metadata from the SSA Open Data Program if this "
            "dataset is required for policy or operational analysis."
        )
