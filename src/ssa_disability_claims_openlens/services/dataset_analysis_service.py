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
    UpdateFrequency,
)
from ..utils import compute_freshness_score, days_since, get_logger

logger = get_logger(__name__)


# ── Completeness scoring knowledge base ───────────────────────────────────────
# Maps dataset_id → pre-computed coverage axis assessments.
# This avoids expensive runtime inference for known datasets.

_COMPLETENESS_KB: dict[str, dict[str, object]] = {
    "ssa-oasdi-beneficiaries-by-state": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=85.0,
            details="Covers all 50 states, DC, and territories; county-level data available",
            gaps=["Sub-county (ZIP/census tract) data not published",
                  "Small-population county cells are suppressed"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=70.0,
            details="Annual data from 1990 to 2023; 12–18 month lag from reference year",
            gaps=["No monthly or quarterly snapshots",
                  "Within-year trend analysis not possible"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=60.0,
            details="Covers OASDI beneficiary counts and average benefits",
            gaps=["No pending claims or decision data",
                  "No demographic cross-tabulation at county level",
                  "Denied applicants excluded"],
        ),
        "missing_dimensions": [
            "Race and ethnicity breakdown",
            "Claimant income levels",
            "Impairment type at sub-national level",
        ],
        "analyst_notes": (
            "Strong geographic foundation for beneficiary analysis. The main limitation is "
            "annual frequency and lack of demographic granularity below state level."
        ),
    },
    "ssa-odar-pending-cases": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=75.0,
            details="Covers all ODAR hearing offices; state-level rollup available",
            gaps=["Hearing office catchment areas do not align with political boundaries",
                  "No ZIP code or county mapping for claimants"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=90.0,
            details="Monthly data from 2007 to present; 1-month publication lag",
            gaps=["Historical data format changed in 2015 — comparability limited"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=50.0,
            details="Covers pending case counts and average processing days",
            gaps=["No processing time distribution (median, percentiles)",
                  "No demographic breakdown of claimants",
                  "No impairment type or case complexity data",
                  "Pre-hearing wait time (initial claim to hearing request) not included"],
        ),
        "missing_dimensions": [
            "Processing time distribution (not just averages)",
            "Claimant demographics",
            "Case complexity indicators",
        ],
        "analyst_notes": (
            "Best available source for hearing backlog monitoring. Operational coverage "
            "is limited — averages hide the distribution of wait times across claimants."
        ),
    },
    "ssa-disability-applications-decisions": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=20.0,
            details="National totals only — no state or local breakdown",
            gaps=["No state-level application or outcome data",
                  "Cannot identify geographic disparities in allowance rates"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=65.0,
            details="Annual data from 1960 to 2023",
            gaps=["Annual only — cannot track within-year surges",
                  "12-month publication lag"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=75.0,
            details="Covers applications, awards, denials, and allowance rates by program and impairment",
            gaps=["Reconsideration and hearing outcomes in separate publications",
                  "Race/ethnicity not published",
                  "No claim complexity data"],
        ),
        "missing_dimensions": [
            "Geographic disaggregation",
            "Race and ethnicity",
            "Multi-level outcomes in single table",
        ],
        "analyst_notes": (
            "Comprehensive national view of disability program access. The absence of "
            "geographic and demographic disaggregation is a significant limitation for "
            "equity analysis."
        ),
    },
    "ssa-field-office-locator": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=95.0,
            details="Complete directory of all SSA field offices with geocoordinates",
            gaps=["Formal service area boundaries not defined"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=40.0,
            details="Current snapshot only — no historical archive of office openings/closures",
            gaps=["Cannot track office closures over time",
                  "No longitudinal access analysis possible"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=30.0,
            details="Basic directory data: address, phone, coordinates",
            gaps=["No appointment wait time data",
                  "No staffing or capacity information",
                  "No visit volume or service type data",
                  "No ADA or language service information"],
        ),
        "missing_dimensions": [
            "Appointment wait times",
            "Staffing levels",
            "Visit volumes by service type",
            "ADA accessibility status",
            "Languages served",
        ],
        "analyst_notes": (
            "Useful for proximity analysis but lacks the operational data needed to assess "
            "access quality. The absence of wait time and capacity data is the critical gap."
        ),
    },
    "ssa-disability-research-statistics": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=65.0,
            details="State-level data available for key metrics",
            gaps=["No county or sub-state breakdown",
                  "Geographic detail limited for demographic cross-tabs"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=70.0,
            details="Annual data from 1970 to 2023",
            gaps=["Annual publication — no within-year analysis",
                  "12-18 month publication lag"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=65.0,
            details="Covers age, sex, benefit amounts, and covered earnings for SSDI beneficiaries",
            gaps=["No race or ethnicity data",
                  "Sex is binary — no non-binary category",
                  "No impairment type cross-tabulation",
                  "No income or asset data"],
        ),
        "missing_dimensions": [
            "Race and ethnicity",
            "Non-binary gender categories",
            "Impairment type cross-tabulation",
        ],
        "analyst_notes": (
            "Good demographic foundation for SSDI research. The absence of race/ethnicity "
            "data is the most significant gap for equity-focused analysis."
        ),
    },
    "ssa-ssi-recipients-by-state": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=88.0,
            details="State and county-level data for all U.S. jurisdictions",
            gaps=["No sub-county detail",
                  "Small-population cell suppression"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=92.0,
            details="Monthly data from 2008 to present; 2-3 month publication lag",
            gaps=["Historical data before 2008 in separate publication"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=50.0,
            details="Covers recipient counts and total payment amounts by eligibility category",
            gaps=["No demographic breakdown below state level",
                  "Payment amounts exclude state supplements",
                  "No income, housing, or asset data"],
        ),
        "missing_dimensions": [
            "Recipient demographics at county level",
            "State supplement amounts",
            "Income and asset information",
        ],
        "analyst_notes": (
            "Excellent temporal frequency for SSI program monitoring. Limited operational "
            "depth — cannot assess benefit adequacy or recipient characteristics at scale."
        ),
    },
    "data-gov-ssa-performance": {
        "geographic": CoverageAxis(
            axis="Geographic",
            score=10.0,
            details="National performance metrics only",
            gaps=["No regional or office-level performance breakdown"],
        ),
        "temporal": CoverageAxis(
            axis="Temporal",
            score=75.0,
            details="Annual fiscal year data from 2003 to present",
            gaps=["Annual only — cannot identify within-year performance shifts",
                  "Metric definitions change between fiscal years"],
        ),
        "operational": CoverageAxis(
            axis="Operational",
            score=60.0,
            details="Covers SSA-defined performance metrics including processing times and accuracy",
            gaps=["Metrics are self-defined and self-reported",
                  "No demographic breakdown of performance outcomes",
                  "Coverage of metrics varies year-to-year"],
        ),
        "missing_dimensions": [
            "Regional or office-level performance breakdown",
            "Demographic disaggregation of performance outcomes",
            "Independent verification of reported metrics",
        ],
        "analyst_notes": (
            "Useful for tracking SSA's own performance commitments. Limited for "
            "independent evaluation due to national aggregation and self-reporting."
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
            staleness_indicators=staleness,
            analyst_notes=self._freshness_note(score, dataset.update_frequency, elapsed),
        )

    @staticmethod
    def _freshness_note(
        score: float, freq: UpdateFrequency, elapsed: int | None
    ) -> str:
        if elapsed is None:
            return "Last update date unknown — cannot assess currency."
        if score >= 90:
            return f"Dataset is current. Update frequency ({freq.value}) is being met."
        if score >= 60:
            return (
                f"Dataset is aging ({elapsed} days since last update). "
                f"Expected frequency: {freq.value}."
            )
        return (
            f"Dataset is stale ({elapsed} days since last update). "
            f"Expected frequency: {freq.value}. "
            "Consider filing a data refresh request with the SSA Open Data Program."
        )
