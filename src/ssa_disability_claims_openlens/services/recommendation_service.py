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
  - for_context(context): keyword-driven lookup used by recommend_transparency_improvements.
                          Scores the context against topic keywords, returns top N.
"""

from __future__ import annotations

from ..models import (
    InformationElement,
    Recommendation,
    RecommendationPriority,
    TransparencyImprovementPlan,
)
from ..utils import extract_keywords, get_logger

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


_RECOMMENDATION_KB: list[dict] = [
    # ── Field office operational metrics ──────────────────────────────────────
    {
        "topic": "field_office_access",
        "keywords": ["field office", "access", "appointment", "wait", "in-person",
                     "location", "service", "demand", "busiest", "staffing", "staff"],
        "recommendations": [
            Recommendation(
                title="Publish monthly field office visit volumes and appointment counts",
                closes_gap="Field office operational metrics (staffing, volume, wait times)",
                category="Operational Metrics",
                justification=(
                    "Without visit volume data, it is impossible to rank offices by demand "
                    "or identify where resources are insufficient."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-field-office-locator"],
                expected_impact=(
                    "Would enable geographic ranking of service demand and evidence-based "
                    "decisions about office resource allocation."
                ),
            ),
            Recommendation(
                title="Publish staffing FTE counts by field office",
                closes_gap="Field office operational metrics (staffing, volume, wait times)",
                category="Operational Metrics",
                justification=(
                    "Staffing data combined with visit volumes would reveal offices where "
                    "caseload-per-staff ratios indicate service strain."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-field-office-locator"],
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
                affected_datasets=["ssa-field-office-locator"],
                expected_impact=(
                    "Would reveal geographic disparities in in-person access. Rural and "
                    "underserved communities may face multi-week waits; public data would "
                    "support targeted improvements."
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
                affected_datasets=["ssa-field-office-locator"],
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
                affected_datasets=["ssa-field-office-locator"],
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
                affected_datasets=["ssa-field-office-locator"],
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
                    "processing time disparities across offices."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-field-office-locator", "ssa-odar-pending-cases"],
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
                affected_datasets=["ssa-odar-pending-cases"],
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
                affected_datasets=["ssa-odar-pending-cases", "ssa-field-office-locator"],
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
                affected_datasets=["ssa-odar-pending-cases", "data-gov-ssa-performance"],
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
                title="Publish state-level initial claim processing times disaggregated from national averages",
                closes_gap="Disability claim processing times",
                category="Geographic Detail",
                justification=(
                    "National averages conceal large state-level variation; state-level data "
                    "would enable geographic equity analysis of initial claim timelines."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-odar-pending-cases", "data-gov-ssa-performance"],
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
                affected_datasets=["ssa-odar-pending-cases"],
                expected_impact=(
                    "Averages mask extreme outliers. Distribution data would expose cases "
                    "where claimants wait years, not months, for disability decisions."
                ),
            ),
            Recommendation(
                title="Track end-to-end processing time across all decision levels",
                closes_gap="Disability claim processing times",
                category="Temporal Granularity",
                justification=(
                    "Current datasets track hearing-level times independently from initial "
                    "claims. An integrated end-to-end timeline would show total claimant burden."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-odar-pending-cases", "ssa-disability-applications-decisions"],
                expected_impact=(
                    "Claimants who appeal can wait 2–4 years for final decisions. "
                    "Transparent end-to-end data would increase accountability for the "
                    "total claimant experience."
                ),
            ),
        ],
    },
    # ── Demographic equity ─────────────────────────────────────────────────────
    {
        "topic": "demographic_equity",
        "keywords": ["race", "ethnicity", "gender", "sex", "equity",
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
                affected_datasets=["ssa-disability-applications-decisions"],
                expected_impact=(
                    "Would enable equity analysis of SSA disability adjudication. Research "
                    "suggests racial disparities exist in allowance rates; public data would "
                    "confirm or refute and drive corrective action."
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
                affected_datasets=["ssa-disability-applications-decisions", "ssa-odar-pending-cases"],
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
                affected_datasets=["ssa-disability-applications-decisions", "ssa-disability-research-statistics"],
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
                    "Current processing time data has no demographic dimension — it is "
                    "impossible to determine if protected groups face systematically longer waits."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-odar-pending-cases"],
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
                closes_gap="Applicant income and economic status",
                category="Program Outcomes",
                justification=(
                    "SSI is a means-tested program; without income data it is impossible "
                    "to evaluate whether the program reaches its intended population."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-ssi-recipients-by-state"],
                expected_impact=(
                    "SSI benefits are well below the poverty line in most states. "
                    "Published adequacy data would support evidence-based policy reform."
                ),
            ),
            Recommendation(
                title="Report geographic correlation of benefit amounts with local cost of living",
                closes_gap="Applicant income and economic status",
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
                title="Publish annual Ticket to Work assignment and return-to-work outcome statistics",
                closes_gap="Work incentive program participation and outcomes",
                category="Program Outcomes",
                justification=(
                    "Participation counts without outcomes cannot demonstrate whether work "
                    "incentive programs achieve their goal of reducing benefit dependency."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=["ssa-red-book"],
                expected_impact=(
                    "Would enable evaluation of whether work incentive programs achieve "
                    "their goal of helping beneficiaries return to self-sufficiency."
                ),
            ),
            Recommendation(
                title="Report earnings outcomes for beneficiaries using Trial Work Period provisions",
                closes_gap="Work incentive program participation and outcomes",
                category="Program Outcomes",
                justification=(
                    "Earnings data would show whether the Trial Work Period is functioning "
                    "as a bridge to employment or is primarily used without sustained work."
                ),
                priority=RecommendationPriority.MEDIUM,
                affected_datasets=["ssa-red-book", "ssa-disability-applications-decisions"],
                expected_impact=(
                    "Provides the evidence base for assessing and improving the Trial Work "
                    "Period as an employment transition mechanism."
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
                title="Publish state-level disability allowance rates",
                closes_gap="Geographic disaggregation of outcomes",
                category="Geographic Detail",
                justification=(
                    "Application and decision data is currently published at national level "
                    "only. State-level allowance rates would reveal whether disability "
                    "adjudication quality and equity varies by geography."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-disability-applications-decisions"],
                expected_impact=(
                    "Research shows significant state-level variation in allowance rates. "
                    "Public data would confirm patterns and support policy harmonization."
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
                            f"This information element is entirely absent from public data "
                            f"and is required to answer questions about {el.element.lower()}."
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

        Scores each topic bucket against context keywords, deduplicates by title,
        and returns the top N recommendations sorted by score then priority.
        """
        keywords = extract_keywords(context)
        if focus_area:
            keywords.extend(extract_keywords(focus_area))

        priority_order = {
            RecommendationPriority.HIGH: 0,
            RecommendationPriority.MEDIUM: 1,
            RecommendationPriority.LOW: 2,
        }
        scored: list[tuple[float, Recommendation]] = []

        for topic_entry in _RECOMMENDATION_KB:
            topic_keywords: list[str] = topic_entry["keywords"]
            recs: list[Recommendation] = topic_entry["recommendations"]

            match_count = sum(
                1 for tk in topic_keywords
                if any(tk.lower() in kw.lower() or kw.lower() in tk.lower() for kw in keywords)
            )
            topic_score = match_count / max(len(topic_keywords), 1)

            if topic_score > 0 or (
                focus_area and focus_area.lower() in str(topic_entry.get("topic", ""))
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
                    "Several SSA disability datasets are published annually, introducing "
                    "12–18 month lags. Increasing to quarterly or monthly would significantly "
                    "improve timeliness of public data."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-disability-applications-decisions", "ssa-disability-research-statistics"],
                expected_impact="Faster detection of program trends and emerging equity issues.",
            ),
            Recommendation(
                title="Add demographic disaggregation to core datasets",
                closes_gap="Race and ethnicity data",
                category="Demographic Data",
                justification=(
                    "Core SSA disability statistics lack race, ethnicity, and income "
                    "disaggregation, preventing equity analysis."
                ),
                priority=RecommendationPriority.HIGH,
                affected_datasets=["ssa-disability-applications-decisions"],
                expected_impact="Enables identification and remediation of disparate program impacts.",
            ),
        ]
