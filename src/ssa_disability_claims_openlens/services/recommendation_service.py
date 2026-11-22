"""
Recommendation Service — the single source of truth for all transparency recommendations.

Both evaluate_answer_coverage and recommend_transparency_improvements call this service.
This guarantees:
  - Deterministic results: the same question always returns the same recommendations.
  - No divergence: there is only one KB and one lookup algorithm.
  - Consistent model: every recommendation is a Recommendation instance with
    title, closes_gap, category, justification, priority, affected_datasets,
    and expected_impact.

Architecture:
    RecommendationService
           ↓               ↓
  evaluate_answer_coverage   recommend_transparency_improvements

Lookup strategy:
  - for_gaps(elements):  gap-driven lookup used by evaluate_answer_coverage.
                         Takes a list of InformationElement objects, returns
                         Recommendation objects for each gap, capped at 8.
  - for_context(context): used by recommend_transparency_improvements. If the context
                          names coverage gaps verbatim, returns only the recommendations
                          that close them (via for_gaps). Otherwise scores the context
                          against topic keywords (word-start matches) and returns top N.
"""

from __future__ import annotations

import re
from typing import Any

from ..models import (
    InformationElement,
    Recommendation,
    RecommendationPriority,
    TransparencyImprovementPlan,
)
from ..utils import get_logger

logger = get_logger(__name__)


# ── Unified Recommendation Knowledge Base ─────────────────────────────────────
#
# Every entry is a Recommendation object.  Entries are grouped into topic
# buckets so keyword-driven lookup (for_context) can score by topic, while
# gap-driven lookup (for_gaps) uses the closes_gap field directly.
#
# When adding a new recommendation:
#   1. Set closes_gap to the exact InformationElement.element string from
#      the coverage KB in answer_coverage_service.py.
#   2. Set category to one of the standard labels.
#   3. Set priority (High = public-safety / equity impact; Medium = valuable
#      but not blocking; Low = nice-to-have).
#   4. Set affected_datasets to the catalog IDs the rec would extend.


_RECOMMENDATION_KB: list[dict[str, Any]] = [
    # ── Field office operational metrics ──────────────────────────────────────
    {
        "topic": "field_office_access",
        "keywords": ["field office", "access", "appointment", "wait", "in-person",
                     "location", "service", "demand", "busiest", "staffing", "staff"],
        "recommendations": [
            Recommendation(
                title="Publish monthly visit volumes and appointment counts for each field office",
                closes_gap="Field office operational metrics (staffing, volume, wait times)",
                category="Operational Metrics",
                justification=(
                    "SSA publishes national average daily visitors (US-GOV-SSA-434), but "
                    "per-office visitor counts exist only for FY2016 (US-GOV-SSA-1917), so "
                    "offices cannot be ranked by current demand."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-field-office-visitors", "ssa-field-office-visitor-counts-2016"],
                expected_impact=(
                    "Would enable geographic ranking of service demand and evidence-based "
                    "decisions about office resource allocation."
                ),
            ),
            Recommendation(
                title="Publish staffing FTE counts by field office every year",
                closes_gap="Field office operational metrics (staffing, volume, wait times)",
                category="Operational Metrics",
                justification=(
                    "Per-office employee counts were released once, for FY2016 "
                    "(US-GOV-SSA-1918). An annual series combined with visit volumes would "
                    "show where caseload-per-staff ratios indicate service strain."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-field-office-employee-counts-2016"],
                expected_impact=(
                    "Enables computation of caseload-per-FTE ratios and identification of "
                    "understaffed offices before service failures occur."
                ),
            ),
            Recommendation(
                title="Publish average appointment wait times by field office",
                closes_gap="Field office operational metrics (staffing, volume, wait times)",
                category="Access Data",
                justification=(
                    "Wait times are the most direct indicator of service accessibility "
                    "and demand pressure at the office level."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-field-office-appointments-21-days"],
                expected_impact=(
                    "Would show whether in-person access differs by geography. The only "
                    "published appointment measure is a national series discontinued in 2015 "
                    "(US-GOV-SSA-431)."
                ),
            ),
            Recommendation(
                title="Publish office service-capacity metrics (capacity utilisation, peak demand periods)",
                closes_gap="Field office operational metrics (staffing, volume, wait times)",
                category="Operational Metrics",
                justification=(
                    "Capacity metrics enable evidence-based decisions about resource "
                    "reallocation and new office openings."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=["ssa-field-office-visitors", "ssa-field-office-employee-counts-2016"],
                expected_impact=(
                    "Enables SSA to proactively identify offices approaching capacity limits "
                    "before wait times become critical."
                ),
            ),
            Recommendation(
                title="Publish monthly walk-in and appointment visit volumes by field office",
                closes_gap="Field office appointment and walk-in volume",
                category="Access Data",
                justification=(
                    "Visit volumes are the foundational metric for measuring service demand "
                    "and identifying access pressure points."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-field-office-visitors", "ssa-field-office-visitor-counts-2016"],
                expected_impact=(
                    "Provides the baseline demand data needed to evaluate whether office "
                    "capacity matches community need."
                ),
            ),
            Recommendation(
                title="Publish the percentage of visitors served within 30 and 60 minutes",
                closes_gap="Field office appointment and walk-in volume",
                category="Access Data",
                justification=(
                    "Time-to-service benchmarks translate volume data into a meaningful "
                    "access equity indicator."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=["ssa-field-office-visitors"],
                expected_impact=(
                    "Comparable service-time benchmarks across offices would expose "
                    "consistent access disparities and support equity-focused resource allocation."
                ),
            ),
            Recommendation(
                title="Archive historical field office locations with open/close dates",
                closes_gap="SSA field office locations and coverage",
                category="Geographic Detail",
                justification=(
                    "The current field office dataset is a snapshot with no history. "
                    "Archiving office openings and closures would enable longitudinal "
                    "analysis of SSA access trends."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=["ssa-field-office-locator"],
                expected_impact=(
                    "Would enable analysis of access loss in communities where offices "
                    "have closed, supporting policy decisions about remote service alternatives."
                ),
            ),
        ],
    },
    # ── Staffing and workload ──────────────────────────────────────────────────
    {
        "topic": "staffing_workload",
        "keywords": ["staffing", "staff", "headcount", "fte", "workload",
                     "caseload", "capacity", "adjudicator", "ratio"],
        "recommendations": [
            Recommendation(
                title="Publish annual FTE staffing levels by field office and hearing office",
                closes_gap="SSA office staffing levels",
                category="Operational Metrics",
                justification=(
                    "Staffing counts are needed to compute caseload ratios and explain "
                    "processing time disparities across offices. Only a one-time FY2016 "
                    "field office release exists (US-GOV-SSA-1918); no hearing office staffing "
                    "data is in the catalog."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-field-office-locator", "ssa-hearing-office-workload"],
                expected_impact=(
                    "Enables fair comparison of office performance by normalising pending "
                    "cases against available staff capacity."
                ),
            ),
            Recommendation(
                title="Report adjudicator-to-caseload ratios alongside pending case counts",
                closes_gap="SSA office staffing levels",
                category="Operational Metrics",
                justification=(
                    "Ratios contextualise raw pending case numbers — a large backlog at a "
                    "large office may be less severe than a smaller backlog at an understaffed one."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-hearing-office-workload", "ssa-hearing-wait-time"],
                expected_impact=(
                    "Transforms raw backlog counts into a meaningful equity metric, "
                    "enabling targeted intervention at genuinely strained offices."
                ),
            ),
            Recommendation(
                title="Publish monthly caseload-to-staff ratios for field offices and hearing offices",
                closes_gap="Office workload and capacity",
                category="Operational Metrics",
                justification=(
                    "Caseload ratios are the standard workload measure and would directly "
                    "answer questions about which offices are under the most pressure."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-hearing-office-workload", "ssa-field-office-locator"],
                expected_impact=(
                    "Provides the evidence base for SSA budget requests and congressional "
                    "oversight of staffing adequacy."
                ),
            ),
            Recommendation(
                title="Report hearing office disposition targets and actuals side-by-side",
                closes_gap="Office workload and capacity",
                category="Performance",
                justification=(
                    "Target-vs-actual comparison reveals whether offices are meeting workload "
                    "commitments, not just reporting raw counts."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=["ssa-hearing-office-workload"],
                expected_impact=(
                    "Closes the gap between self-reported performance targets and "
                    "claimant-experienced outcomes."
                ),
            ),
        ],
    },
    # ── Processing and wait times ──────────────────────────────────────────────
    {
        "topic": "processing_time",
        "keywords": ["wait", "processing", "time", "how long", "backlog",
                     "delay", "days", "hearing", "appeal", "odar"],
        "recommendations": [
            Recommendation(
                title="Publish state-level initial claim processing times",
                closes_gap="Disability claim processing times",
                category="Geographic Detail",
                justification=(
                    "SSA publishes average initial-claim processing time (US-GOV-SSA-1409), "
                    "but its record describes no state breakdown, and State Agency Workload "
                    "Data (US-GOV-SSA-307) has state counts without times. State-level times "
                    "would enable geographic equity analysis of initial claim timelines."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-initial-disability-processing-time", "ssa-state-agency-workload-data"],
                expected_impact=(
                    "Would reveal states where claimants face disproportionately long waits, "
                    "driving targeted resource allocation and policy attention."
                ),
            ),
            Recommendation(
                title="Publish wait-time distributions (median, 90th percentile) alongside averages",
                closes_gap="Hearing-level wait times",
                category="Temporal Granularity",
                justification=(
                    "Averages mask severe outliers; distributional data exposes the worst-case "
                    "experience for claimants waiting the longest."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-hearing-office-workload", "ssa-hearing-wait-time"],
                expected_impact=(
                    "Averages mask extreme outliers. Distribution data would expose cases "
                    "where claimants wait far longer than the published average."
                ),
            ),
            Recommendation(
                title="Track end-to-end processing time across all decision levels",
                closes_gap="Disability claim processing times",
                category="Temporal Granularity",
                justification=(
                    "Initial (US-GOV-SSA-1409), reconsideration (US-GOV-SSA-1768) and hearing "
                    "(US-GOV-SSA-304) times are published separately, as averages for different "
                    "claim groups, so they cannot be added up into one claimant's wait."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=[
                    "ssa-initial-disability-processing-time",
                    "ssa-reconsideration-processing-time",
                    "ssa-hearing-wait-time",
                ],
                expected_impact=(
                    "Would show the total time claimants who appeal wait for a final decision, "
                    "which no public dataset reports today."
                ),
            ),
            Recommendation(
                title="Publish average time to an initial decision for claims taken at each field office",
                closes_gap="Disability decision times by field office or DDS",
                category="Geographic Detail",
                justification=(
                    "Initial-claim processing time is published only as a national average "
                    "(US-GOV-SSA-1409), and per-office times exist only for hearing offices "
                    "(US-GOV-SSA-303). Times by the field office that took the claim would show "
                    "where claimants wait longest before their first decision."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-initial-disability-processing-time", "ssa-state-agency-workload-data"],
                expected_impact=(
                    "Would let the public rank field offices by how long initial decisions take, "
                    "which no public dataset allows today."
                ),
            ),
            Recommendation(
                title="Publish pending claims for each field office, not only the national total",
                closes_gap="Disability decision times by field office or DDS",
                category="Operational Metrics",
                justification=(
                    "Field Office Claims Pending (US-GOV-SSA-435) reports one national count per "
                    "fiscal year, FY2006–2022, for all claim types combined. Per-office disability "
                    "counts would show where backlogs build up."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=[],
                expected_impact=(
                    "Would give a current, per-office backlog measure to set alongside "
                    "decision times."
                ),
            ),
        ],
    },
    # ── Demographic equity ─────────────────────────────────────────────────────
    {
        "topic": "demographic_equity",
        "keywords": ["race", "racial", "ethnicity", "gender", "sex", "equity",
                     "disparit", "demographic", "minority", "hispanic", "black"],
        "recommendations": [
            Recommendation(
                title="Publish disability application, award, and denial rates disaggregated by race and ethnicity",
                closes_gap="Race and ethnicity data",
                category="Demographic Data",
                justification=(
                    "Race/ethnicity breakdowns are the minimum required to assess whether "
                    "the disability adjudication process produces equitable outcomes."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-disability-claim-data", "ssa-state-agency-workload-data"],
                expected_impact=(
                    "Would let the public test whether allowance rates differ by race and "
                    "ethnicity, at each decision level and in each state."
                ),
            ),
            Recommendation(
                title="Report race/ethnicity data at all levels of the appeals process",
                closes_gap="Race and ethnicity data",
                category="Demographic Data",
                justification=(
                    "Disparities may emerge or widen at specific decision levels; publishing "
                    "at each level pinpoints where intervention is needed."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-state-agency-workload-data", "ssa-alj-disposition-data"],
                expected_impact=(
                    "Enables identification of whether disparate treatment occurs at initial "
                    "adjudication, reconsideration, or hearing levels."
                ),
            ),
            Recommendation(
                title="Partner with the Census Bureau to link disability outcomes to demographic survey data",
                closes_gap="Race and ethnicity data",
                category="Demographic Data",
                justification=(
                    "Linked data would enable analysis of socioeconomic context alongside "
                    "program outcomes, supporting richer equity research."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=["ssa-disability-claim-data", "ssa-di-annual-statistical-report"],
                expected_impact=(
                    "Enables research on disability program access and outcomes across "
                    "demographic groups — a population with elevated unmet needs."
                ),
            ),
            Recommendation(
                title="Cross-tabulate processing times with race, age, and geography",
                closes_gap="Race and ethnicity data",
                category="Demographic Data",
                justification=(
                    "None of the published processing-time datasets has a demographic "
                    "dimension, so it is impossible to determine if protected groups face "
                    "systematically longer waits."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-initial-disability-processing-time", "ssa-hearing-wait-time"],
                expected_impact=(
                    "Critical for identifying and addressing adjudication bias."
                ),
            ),
        ],
    },
    # ── Income and economic status ─────────────────────────────────────────────
    {
        "topic": "ssi_adequacy",
        "keywords": ["ssi", "supplemental", "adequacy", "poverty", "income",
                     "payment", "low-income", "economic", "socioeconomic"],
        "recommendations": [
            Recommendation(
                title="Publish SSI application and outcome data cross-tabulated with income decile",
                closes_gap="Income and economic status of applicants and recipients",
                category="Program Outcomes",
                justification=(
                    "SSI is a means-tested program; without income data it is impossible "
                    "to evaluate whether the program reaches its intended population."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-ssi-recipients-by-state"],
                expected_impact=(
                    "Would let researchers measure how SSI payments compare with recipients' "
                    "other income and local poverty thresholds."
                ),
            ),
            Recommendation(
                title="Report geographic correlation of benefit amounts with local cost of living",
                closes_gap="Income and economic status of applicants and recipients",
                category="Finance",
                justification=(
                    "A fixed federal benefit has very different purchasing power across "
                    "regions; this analysis requires both benefit and cost-of-living data."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=["ssa-ssi-recipients-by-state", "ssa-oasdi-beneficiaries-by-state"],
                expected_impact=(
                    "Would support evidence-based advocacy for geographic benefit adjustments."
                ),
            ),
        ],
    },
    # ── Work incentives ────────────────────────────────────────────────────────
    {
        "topic": "work_incentives",
        "keywords": ["work", "employment", "ticket", "return", "incentive",
                     "earnings", "sga", "trial work"],
        "recommendations": [
            Recommendation(
                title="Resume annual Ticket to Work assignment counts and add return-to-work outcomes",
                closes_gap="Work incentive program participation",
                category="Program Outcomes",
                justification=(
                    "Ticket assignments were released only for FY2011–2017 (US-GOV-SSA-1915), "
                    "with no outcomes. Participation counts without outcomes cannot show "
                    "whether work incentive programs achieve their goal."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=["ssa-ticket-to-work-fy11-17", "ssa-national-beneficiary-survey"],
                expected_impact=(
                    "Would enable evaluation of whether work incentive programs achieve "
                    "their goal of helping beneficiaries return to self-sufficiency."
                ),
            ),
            Recommendation(
                title="Report earnings outcomes for beneficiaries using Trial Work Period provisions",
                closes_gap="Return-to-work outcomes",
                category="Program Outcomes",
                justification=(
                    "Earnings data would show whether the Trial Work Period is functioning "
                    "as a bridge to employment or is primarily used without sustained work."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=["ssa-red-book", "ssa-di-annual-statistical-report"],
                expected_impact=(
                    "Provides the evidence base for assessing and improving the Trial Work "
                    "Period as an employment transition mechanism."
                ),
            ),
        ],
    },
    # ── Program outcomes across decision levels ───────────────────────────────
    {
        "topic": "program_outcomes",
        "keywords": ["denial", "denied", "reason", "outcome", "final", "ultimately",
                     "approved", "appeal", "levels", "end-to-end"],
        "recommendations": [
            Recommendation(
                title="Publish outcomes that follow the same claims from application to final decision",
                closes_gap="Linked claim history across decision levels",
                category="Program Outcomes",
                justification=(
                    "Initial, reconsideration and hearing data are published separately for "
                    "different groups of claims (US-GOV-SSA-307, -299). Following one application "
                    "cohort through every level is the only way to measure final approval rates "
                    "and total waiting time."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-state-agency-workload-data", "ssa-alj-disposition-data"],
                expected_impact=(
                    "Would answer how many applicants are eventually approved and how long the "
                    "whole process takes — questions no public dataset answers today."
                ),
            ),
            Recommendation(
                title="Publish denial counts by reason (medical and technical) at each decision level",
                closes_gap="Reasons for claim denials",
                category="Program Outcomes",
                justification=(
                    "No SSA dataset on Data.gov reports why claims are denied (see gap evidence); "
                    "published processing times only mention technical denials as an exclusion."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=["ssa-state-agency-workload-data", "ssa-alj-disposition-data"],
                expected_impact=(
                    "Would show whether denials are driven by medical criteria or by technical "
                    "eligibility rules, and how that differs by state and level."
                ),
            ),
        ],
    },
    # ── Geographic equity ──────────────────────────────────────────────────────
    {
        "topic": "geographic_equity",
        "keywords": ["state", "county", "geographic", "region", "rural",
                     "urban", "local", "disparit", "area"],
        "recommendations": [
            Recommendation(
                title="Publish county-level initial claim receipts and allowance rates, and map hearing offices to the areas they serve",
                closes_gap="Geographic disaggregation of outcomes",
                category="Geographic Detail",
                justification=(
                    "State-level allowance data is published for the state agency levels "
                    "(US-GOV-SSA-307, -308), and hearing-level allowances by ALJ and hearing "
                    "office (US-GOV-SSA-299). None goes below state level, and hearing offices "
                    "are not mapped to the states or counties they serve, so sub-state and "
                    "end-to-end geographic comparisons are not possible."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-disability-claim-data", "ssa-state-agency-workload-data", "ssa-alj-disposition-data"],
                expected_impact=(
                    "Would show whether allowance outcomes differ within states and whether "
                    "state differences at the initial level persist on appeal."
                ),
            ),
        ],
    },
    # ── Geographic accessibility / rural-urban equity ─────────────────────────
    {
        "topic": "geographic_accessibility",
        "keywords": [
            "rural", "urban", "geographic", "access", "accessibility", "underserved",
            "service gap", "service desert", "county", "travel distance", "office coverage",
            "regional", "equity", "disparity",
        ],
        "recommendations": [
            Recommendation(
                title="Publish travel distance to nearest SSA field office by ZIP code or county",
                closes_gap="Travel distance to nearest SSA field office",
                category="Geographic Detail",
                justification=(
                    "Travel distance is the most direct proxy for access burden. Without it, "
                    "it is impossible to quantify whether rural communities face greater barriers "
                    "to in-person SSA services than urban communities."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-field-office-locator"],
                expected_impact=(
                    "Would enable researchers to map access deserts and demonstrate where "
                    "distance is a barrier to disability service participation."
                ),
            ),
            Recommendation(
                title="Publish SSA field office service area boundaries by county",
                closes_gap="Field office service area boundaries",
                category="Geographic Detail",
                justification=(
                    "Service area boundaries would allow cross-referencing of disability "
                    "population density against office coverage — the foundational step for "
                    "rural versus urban access analysis."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-field-office-locator"],
                expected_impact=(
                    "Enables county-level mapping of SSA coverage gaps and identifies "
                    "communities with no accessible field office within a reasonable distance."
                ),
            ),
            Recommendation(
                title="Publish county-level disability beneficiary counts alongside field office locations",
                closes_gap="Geographic distribution of disability service access",
                category="Geographic Detail",
                justification=(
                    "Combining beneficiary density with office locations would reveal where "
                    "SSA serves high-need populations well and where access lags population need."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-field-office-locator", "ssa-oasdi-beneficiaries-by-state", "ssa-ssi-recipients-by-state"],
                expected_impact=(
                    "Provides the evidence base needed to evaluate equitable distribution "
                    "of SSA field office resources relative to disability population density."
                ),
            ),
            Recommendation(
                title="Publish average appointment wait times disaggregated by rural vs. urban office classification",
                closes_gap="Field office operational metrics (staffing, volume, wait times)",
                category="Access Data",
                justification=(
                    "Rural-urban classification of wait times would directly answer whether "
                    "rural communities experience longer service delays than urban counterparts."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-field-office-appointments-21-days", "ssa-field-office-locator"],
                expected_impact=(
                    "The most direct dataset needed to confirm or refute rural access disparity "
                    "in SSA disability services."
                ),
            ),
            Recommendation(
                title="Publish ADA compliance status and accessibility accommodations for each field office",
                closes_gap="Accessibility accommodations at field offices",
                category="Access Data",
                justification=(
                    "Claimants with disabilities need to know whether offices are physically "
                    "accessible before making the trip. No SSA dataset on Data.gov describes "
                    "this (see gap evidence)."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=["ssa-field-office-locator"],
                expected_impact=(
                    "Would enable disability advocates to identify offices that may be "
                    "inaccessible to the very population they serve."
                ),
            ),
        ],
    },
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _gap_index() -> dict[str, list[Recommendation]]:
    """Build a closes_gap → [Recommendation] index from the unified KB."""
    idx: dict[str, list[Recommendation]] = {}
    for topic in _RECOMMENDATION_KB:
        for rec in topic["recommendations"]:
            idx.setdefault(rec.closes_gap, []).append(rec)
    return idx


_GAP_INDEX: dict[str, list[Recommendation]] = _gap_index()


def _keyword_in_text(keyword: str, text: str) -> bool:
    """
    True when `keyword` starts a word in `text`, allowing up to three trailing letters
    ("time" → "times", "wait" → "waiting", "disparit" → "disparities").

    Matching only at word starts stops short keywords firing inside unrelated words,
    e.g. "ssi" inside "processing" or "ratio" inside "operational".
    """
    return re.search(rf"\b{re.escape(keyword.lower())}[a-z]{{0,3}}\b", text) is not None


def _named_gaps(text: str) -> list[str]:
    """Gap element names that appear verbatim in `text`, in order of first appearance."""
    lowered = text.lower()
    found = [(lowered.find(g.lower()), g) for g in _GAP_INDEX if g.lower() in lowered]
    return [g for _, g in sorted(found)]


def _focus_matches_topic(focus_area: str, topic: str) -> bool:
    """'processing times', 'processing-time' and 'processing_time' all name one topic."""
    focus = re.sub(r"[\s\-]+", "_", focus_area.strip().lower())
    return topic in (focus, focus.removesuffix("s"))


# ── Service ────────────────────────────────────────────────────────────────────

class RecommendationService:
    """
    Single recommendation engine used by both MCP tools.

    Two entry points:
      for_gaps(elements)       — gap-driven; used by evaluate_answer_coverage
      for_context(context, …)  — keyword-driven; used by recommend_transparency_improvements
    """

    # ── Gap-driven lookup ──────────────────────────────────────────────────────

    _PRIORITY_RANK: dict[RecommendationPriority, int] = {
        RecommendationPriority.HIGH: 1,
        RecommendationPriority.MEDIUM: 2,
        RecommendationPriority.LOW: 3,
    }

    def for_gaps(
        self,
        elements: list[InformationElement],
        max_recommendations: int = 8,
    ) -> list[Recommendation]:
        """
        Return Recommendation objects that address the gaps in the given
        InformationElement list.

        Only elements with coverage_quality None, Partial, or Proxy generate
        recommendations.  Results are deduplicated by title, sorted High →
        Medium → Low, then capped at max_recommendations.
        """
        items: list[Recommendation] = []
        seen_titles: set[str] = set()

        for el in elements:
            if el.coverage_quality in ("None", "Partial", "Proxy"):
                for rec in _GAP_INDEX.get(el.element, []):
                    if rec.title not in seen_titles:
                        items.append(rec)
                        seen_titles.add(rec.title)

        # Fallback for gaps with no KB entry
        for el in elements:
            if el.coverage_quality == "None" and el.element not in _GAP_INDEX:
                fallback_title = f"Publish data covering: {el.element}"
                if fallback_title not in seen_titles:
                    items.append(Recommendation(
                        title=fallback_title,
                        closes_gap=el.element,
                        category="Program Outcomes",
                        justification=(
                            f"No dataset in the catalog provides this, and it is required to "
                            f"answer questions about {el.element.lower()}."
                        ),
                        priority=RecommendationPriority.HIGH,
                        affected_datasets=[],
                        expected_impact=(
                            f"Publishing {el.element.lower()} would directly close a "
                            "critical gap in public understanding."
                        ),
                    ))
                    seen_titles.add(fallback_title)

        # Sort High → Medium → Low before applying the cap so the most
        # important recommendations are never displaced by lower-priority ones.
        items.sort(key=lambda r: self._PRIORITY_RANK.get(r.priority, 99))
        return items[:max_recommendations]

    # ── Keyword-driven lookup ──────────────────────────────────────────────────

    def for_context(
        self,
        context: str,
        focus_area: str | None = None,
        max_recommendations: int = 5,
    ) -> TransparencyImprovementPlan:
        """
        Return a TransparencyImprovementPlan for a question or topic context.

        If the context names gaps from a coverage assessment (e.g. pasted from
        evaluate_answer_coverage), only recommendations that close those gaps are
        returned. Otherwise each topic bucket is scored against the context, results
        are deduplicated by title, and the top N are sorted by score then priority.
        """
        priority_order = {
            RecommendationPriority.HIGH: 0,
            RecommendationPriority.MEDIUM: 1,
            RecommendationPriority.LOW: 2,
        }
        full_text = f"{context} {focus_area or ''}"

        gaps = _named_gaps(full_text)
        if gaps:
            gap_recs = self.for_gaps(
                [
                    InformationElement(element=g, description="", available=True,
                                       coverage_quality="Partial")
                    for g in gaps
                ],
                max_recommendations=max_recommendations,
            )
            high_count = sum(1 for r in gap_recs if r.priority == RecommendationPriority.HIGH)
            return TransparencyImprovementPlan(
                context=context,
                recommendations=gap_recs,
                total_recommendations=len(gap_recs),
                high_priority_count=high_count,
                executive_summary=self._build_summary(context, gap_recs, high_count),
            )

        text = full_text.lower()
        scored: list[tuple[float, Recommendation]] = []

        for topic_entry in _RECOMMENDATION_KB:
            topic_keywords: list[str] = topic_entry["keywords"]
            recs: list[Recommendation] = topic_entry["recommendations"]

            match_count = sum(1 for tk in topic_keywords if _keyword_in_text(tk, text))
            topic_score = match_count / max(len(topic_keywords), 1)

            if topic_score > 0 or (
                focus_area and _focus_matches_topic(focus_area, str(topic_entry.get("topic", "")))
            ):
                for rec in recs:
                    priority_boost = 0.3 if rec.priority == RecommendationPriority.HIGH else 0.0
                    scored.append((topic_score + priority_boost, rec))

        # Deduplicate by title
        seen_titles: set[str] = set()
        unique: list[tuple[float, Recommendation]] = []
        for score, rec in scored:
            if rec.title not in seen_titles:
                seen_titles.add(rec.title)
                unique.append((score, rec))

        unique.sort(key=lambda x: (-x[0], priority_order.get(x[1].priority, 2)))
        top_recs = [rec for _, rec in unique[:max_recommendations]]

        if not top_recs:
            top_recs = self._generic_recommendations()[:max_recommendations]

        high_count = sum(1 for r in top_recs if r.priority == RecommendationPriority.HIGH)

        return TransparencyImprovementPlan(
            context=context,
            recommendations=top_recs,
            total_recommendations=len(top_recs),
            high_priority_count=high_count,
            executive_summary=self._build_summary(context, top_recs, high_count),
        )

    # Legacy compatibility method — recommend_transparency_improvements tool calls this
    def generate_recommendations(
        self,
        context: str,
        focus_area: str | None = None,
        max_recommendations: int = 5,
    ) -> TransparencyImprovementPlan:
        """Alias for for_context — preserves the existing tool call signature."""
        return self.for_context(context, focus_area, max_recommendations)

    @staticmethod
    def _build_summary(
        context: str, recs: list[Recommendation], high_count: int
    ) -> str:
        if not recs:
            return "No targeted recommendations were generated for this context."
        return (
            f"Generated {len(recs)} transparency recommendation(s) ({high_count} high priority) "
            f"based on: \"{context[:80]}{'...' if len(context) > 80 else ''}\". "
            f"Top recommendation: {recs[0].title}."
        )

    @staticmethod
    def _generic_recommendations() -> list[Recommendation]:
        return [
            Recommendation(
                title="Increase dataset publication frequency",
                closes_gap="Disability claim processing times",
                category="Temporal Granularity",
                justification=(
                    "Several SSA disability datasets are published annually, and some "
                    "Data.gov records (e.g. SSA Disability Claim Data, US-GOV-SSA-308) have "
                    "not been updated since 2022. More frequent updates would improve the "
                    "timeliness of public data."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-disability-claim-data", "ssa-di-annual-statistical-report"],
                expected_impact="Faster detection of program trends and emerging equity issues.",
            ),
            Recommendation(
                title="Add demographic disaggregation to core datasets",
                closes_gap="Race and ethnicity data",
                category="Demographic Data",
                justification=(
                    "No SSA disability dataset on Data.gov reports race, ethnicity or "
                    "applicant income (see gap evidence), preventing equity analysis."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-disability-claim-data", "ssa-state-agency-workload-data"],
                expected_impact="Enables identification and remediation of disparate program impacts.",
            ),
        ]
