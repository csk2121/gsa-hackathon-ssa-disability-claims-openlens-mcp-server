"""
Recommendation Service — generates prioritized transparency improvement recommendations.

Recommendations are generated from two sources:
  1. The Answer Coverage Engine (gap-driven): based on what information is missing.
  2. The Recommendation Knowledge Base: curated, topic-scoped recommendations for
     known transparency gaps in SSA public data.

Each recommendation includes expected impact and implementation effort so the
SSA Open Data Program Analyst can prioritize effectively.
"""

from __future__ import annotations

from ..models import (
    RecommendationPriority,
    TransparencyImprovementPlan,
    TransparencyRecommendation,
)
from ..utils import extract_keywords, get_logger

logger = get_logger(__name__)


# ── Recommendation knowledge base ─────────────────────────────────────────────
# Organized by topic area. Each entry maps a topic keyword to a list of
# specific, actionable transparency recommendations.

_RECOMMENDATION_KB: list[dict[str, object]] = [
    {
        "topic": "processing_time",
        "keywords": ["wait", "processing", "time", "how long", "backlog", "delay", "days"],
        "recommendations": [
            TransparencyRecommendation(
                title="Publish Monthly Initial Decision Processing Time by State",
                description=(
                    "SSA currently publishes national average processing times annually. "
                    "Publishing monthly state-level breakdowns would reveal geographic "
                    "disparities and enable early detection of backlog formation."
                ),
                affected_datasets=["ssa-odar-pending-cases", "data-gov-ssa-performance"],
                new_data_elements=["state_avg_processing_days", "state_pending_initial_claims", "month"],
                expected_impact=(
                    "Would enable researchers and advocates to identify states where "
                    "claimants face disproportionately long waits, driving targeted "
                    "resource allocation and policy attention."
                ),
                priority=RecommendationPriority.HIGH,
                implementation_effort="Medium",
            ),
            TransparencyRecommendation(
                title="Publish Processing Time Distribution (Not Just Averages)",
                description=(
                    "Current data reports average processing days. Publishing the full "
                    "distribution (median, 75th, 90th, 95th percentile) would reveal the "
                    "experience of the longest-waiting claimants — the most vulnerable group."
                ),
                affected_datasets=["ssa-odar-pending-cases"],
                new_data_elements=["median_processing_days", "p75_processing_days", "p90_processing_days", "p95_processing_days"],
                expected_impact=(
                    "Averages mask extreme outliers. Distribution data would expose cases "
                    "where claimants wait years, not months, for disability decisions."
                ),
                priority=RecommendationPriority.HIGH,
                implementation_effort="Low",
            ),
            TransparencyRecommendation(
                title="Track End-to-End Processing Time Across All Levels",
                description=(
                    "Current datasets track hearing-level times independently from initial "
                    "claims. Publishing an integrated end-to-end timeline (application → "
                    "initial decision → reconsideration → hearing → ALJ decision) would "
                    "show total claimant burden."
                ),
                affected_datasets=["ssa-odar-pending-cases", "ssa-disability-applications-decisions"],
                new_data_elements=["total_days_application_to_final_decision", "decision_level"],
                expected_impact=(
                    "Claimants who appeal can wait 2–4 years for final decisions. "
                    "Transparent end-to-end data would increase accountability for the "
                    "total claimant experience."
                ),
                priority=RecommendationPriority.HIGH,
                implementation_effort="High",
            ),
        ],
    },
    {
        "topic": "demographic_equity",
        "keywords": ["race", "ethnicity", "gender", "sex", "equity", "disparit", "demographic", "minority"],
        "recommendations": [
            TransparencyRecommendation(
                title="Publish Disability Application and Award Rates by Race and Ethnicity",
                description=(
                    "SSA does not currently publish disability application, award, or denial "
                    "rates disaggregated by race or ethnicity. This is a critical gap for "
                    "evaluating equity in program access and decision-making."
                ),
                affected_datasets=["ssa-disability-applications-decisions"],
                new_data_elements=["race_ethnicity", "applications_by_race", "awards_by_race", "allowance_rate_by_race"],
                expected_impact=(
                    "Would enable equity analysis of SSA disability adjudication. Research "
                    "suggests racial disparities exist in allowance rates; public data would "
                    "confirm or refute and drive corrective action."
                ),
                priority=RecommendationPriority.HIGH,
                implementation_effort="Medium",
            ),
            TransparencyRecommendation(
                title="Expand Gender Categories Beyond Binary Male/Female",
                description=(
                    "Current SSA statistics use binary sex categories. Expanding to include "
                    "non-binary and gender non-conforming categories in published data would "
                    "improve inclusivity and support research on disability equity for LGBTQ+ individuals."
                ),
                affected_datasets=["ssa-disability-research-statistics"],
                new_data_elements=["gender_category"],
                expected_impact=(
                    "Enables research on disability program access and outcomes for "
                    "non-binary individuals — a population with elevated disability rates."
                ),
                priority=RecommendationPriority.MEDIUM,
                implementation_effort="Medium",
            ),
            TransparencyRecommendation(
                title="Cross-Tabulate Processing Times with Race, Age, and Geography",
                description=(
                    "Current processing time data has no demographic dimension. "
                    "Publishing processing times by race, age group, and state would "
                    "reveal whether certain populations face systematically longer waits."
                ),
                affected_datasets=["ssa-odar-pending-cases"],
                new_data_elements=["avg_processing_days_by_race", "avg_processing_days_by_age", "avg_processing_days_by_state"],
                expected_impact=(
                    "Critical for identifying and addressing adjudication bias. "
                    "Currently impossible to determine if protected groups face "
                    "disparate treatment in disability processing."
                ),
                priority=RecommendationPriority.HIGH,
                implementation_effort="High",
            ),
        ],
    },
    {
        "topic": "field_office_access",
        "keywords": ["field office", "access", "appointment", "wait", "in-person", "location", "service"],
        "recommendations": [
            TransparencyRecommendation(
                title="Publish Monthly Field Office Appointment Wait Times",
                description=(
                    "SSA field offices are the primary in-person access point for disability "
                    "claimants. Publishing monthly average appointment wait times by office "
                    "would enable access equity analysis."
                ),
                affected_datasets=["ssa-field-office-locator"],
                new_data_elements=["avg_appointment_wait_days", "walk_in_avg_wait_minutes", "monthly_visits"],
                expected_impact=(
                    "Would reveal geographic disparities in in-person access. "
                    "Rural and underserved communities may face multi-week waits; "
                    "public data would support targeted improvements."
                ),
                priority=RecommendationPriority.HIGH,
                implementation_effort="Medium",
            ),
            TransparencyRecommendation(
                title="Publish Field Office Staffing and Capacity Metrics",
                description=(
                    "Current field office data includes only location information. "
                    "Publishing staffing FTEs, capacity, and workload metrics would enable "
                    "analysis of access equity relative to local disability population."
                ),
                affected_datasets=["ssa-field-office-locator"],
                new_data_elements=["fte_count", "caseload_per_fte", "pending_appointments"],
                expected_impact=(
                    "Enables evidence-based decisions about office resource allocation "
                    "and justification for new office openings in underserved areas."
                ),
                priority=RecommendationPriority.MEDIUM,
                implementation_effort="Medium",
            ),
            TransparencyRecommendation(
                title="Archive Historical Field Office Locations",
                description=(
                    "The current field office dataset is a snapshot with no history. "
                    "Archiving office openings, closures, and service area changes would "
                    "enable longitudinal analysis of SSA access trends."
                ),
                affected_datasets=["ssa-field-office-locator"],
                new_data_elements=["open_date", "close_date", "service_change_history"],
                expected_impact=(
                    "Would enable analysis of access loss in communities where offices "
                    "have closed, supporting policy decisions about remote service alternatives."
                ),
                priority=RecommendationPriority.MEDIUM,
                implementation_effort="Low",
            ),
        ],
    },
    {
        "topic": "geographic_equity",
        "keywords": ["state", "county", "geographic", "region", "rural", "urban", "local", "disparit"],
        "recommendations": [
            TransparencyRecommendation(
                title="Publish State-Level Disability Allowance Rates",
                description=(
                    "Application and decision data is currently published at national level only. "
                    "State-level allowance rates would reveal whether disability adjudication "
                    "quality and equity varies by geography."
                ),
                affected_datasets=["ssa-disability-applications-decisions"],
                new_data_elements=["state", "state_applications", "state_awards", "state_allowance_rate"],
                expected_impact=(
                    "Research shows significant state-level variation in allowance rates. "
                    "Public data would confirm patterns and support policy harmonization."
                ),
                priority=RecommendationPriority.HIGH,
                implementation_effort="Medium",
            ),
            TransparencyRecommendation(
                title="Map Disability Beneficiary Rates to Local Cost of Living",
                description=(
                    "Geographic benefit data is published but cannot be linked to cost-of-living "
                    "data without a crosswalk. Publishing benefit adequacy ratios (benefit / "
                    "local living wage) would reveal geographic adequacy disparities."
                ),
                affected_datasets=["ssa-oasdi-beneficiaries-by-state", "ssa-ssi-recipients-by-state"],
                new_data_elements=["benefit_to_living_wage_ratio", "metro_area"],
                expected_impact=(
                    "SSI and SSDI benefit amounts are fixed nationally while living costs vary "
                    "dramatically. This data would support evidence-based advocacy for "
                    "geographic benefit adjustments."
                ),
                priority=RecommendationPriority.MEDIUM,
                implementation_effort="Low",
            ),
        ],
    },
    {
        "topic": "work_incentives",
        "keywords": ["work", "employment", "ticket", "return", "incentive", "earnings", "sga"],
        "recommendations": [
            TransparencyRecommendation(
                title="Publish Annual Ticket to Work Assignment and Outcome Statistics",
                description=(
                    "SSA's Ticket to Work program is a major work incentive initiative, but "
                    "participant counts, employment outcomes, and benefit cessation rates "
                    "are not published as a standalone dataset."
                ),
                affected_datasets=["ssa-red-book"],
                new_data_elements=["ttw_assignments", "ttw_employment_outcomes", "ttw_benefit_cessations", "state"],
                expected_impact=(
                    "Would enable evaluation of whether work incentive programs achieve "
                    "their goal of helping beneficiaries return to self-sufficiency."
                ),
                priority=RecommendationPriority.MEDIUM,
                implementation_effort="Medium",
            ),
        ],
    },
    {
        "topic": "ssi_adequacy",
        "keywords": ["ssi", "supplemental", "adequacy", "poverty", "income", "payment"],
        "recommendations": [
            TransparencyRecommendation(
                title="Publish SSI Recipient Income and Resource Data",
                description=(
                    "SSI is a means-tested program, yet published datasets contain no "
                    "information on recipient income levels, assets, or housing status. "
                    "This prevents analysis of benefit adequacy and program effectiveness."
                ),
                affected_datasets=["ssa-ssi-recipients-by-state"],
                new_data_elements=["avg_recipient_income", "pct_recipients_in_poverty", "housing_status"],
                expected_impact=(
                    "SSI benefits are well below the poverty line in most states. "
                    "Published adequacy data would support evidence-based policy reform."
                ),
                priority=RecommendationPriority.HIGH,
                implementation_effort="High",
            ),
        ],
    },
]


class RecommendationService:
    """Generates prioritized transparency recommendations."""

    def generate_recommendations(
        self,
        context: str,
        focus_area: str | None = None,
        max_recommendations: int = 5,
    ) -> TransparencyImprovementPlan:
        """
        Generate actionable transparency recommendations based on a question or topic.

        Matches the context against the recommendation knowledge base using
        keyword scoring, then returns the top N prioritized recommendations.
        """
        keywords = extract_keywords(context)
        if focus_area:
            keywords.extend(extract_keywords(focus_area))

        scored: list[tuple[float, TransparencyRecommendation]] = []

        for topic_entry in _RECOMMENDATION_KB:
            topic_keywords: list[str] = topic_entry["keywords"]  # type: ignore[assignment]
            recs: list[TransparencyRecommendation] = topic_entry["recommendations"]  # type: ignore[assignment]

            # Score topic relevance
            match_count = sum(
                1 for tk in topic_keywords
                if any(tk.lower() in kw.lower() or kw.lower() in tk.lower() for kw in keywords)
            )
            topic_score = match_count / max(len(topic_keywords), 1)

            if topic_score > 0 or (focus_area and focus_area.lower() in str(topic_entry.get("topic", ""))):
                for rec in recs:
                    # Boost score for High priority items
                    priority_boost = 0.3 if rec.priority == RecommendationPriority.HIGH else 0.0
                    scored.append((topic_score + priority_boost, rec))

        # Deduplicate by title
        seen_titles: set[str] = set()
        unique: list[tuple[float, TransparencyRecommendation]] = []
        for score, rec in scored:
            if rec.title not in seen_titles:
                seen_titles.add(rec.title)
                unique.append((score, rec))

        # Sort by score descending, then by priority
        priority_order = {
            RecommendationPriority.HIGH: 0,
            RecommendationPriority.MEDIUM: 1,
            RecommendationPriority.LOW: 2,
        }
        unique.sort(key=lambda x: (-x[0], priority_order.get(x[1].priority, 2)))

        top_recs = [rec for _, rec in unique[:max_recommendations]]

        # If nothing matched, return a generic set
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

    @staticmethod
    def _build_summary(
        context: str, recs: list[TransparencyRecommendation], high_count: int
    ) -> str:
        if not recs:
            return "No targeted recommendations were generated for this context."
        return (
            f"Generated {len(recs)} transparency recommendations ({high_count} high priority) "
            f"based on the context: \"{context[:80]}{'...' if len(context) > 80 else ''}\". "
            f"Top recommendation: {recs[0].title}."
        )

    @staticmethod
    def _generic_recommendations() -> list[TransparencyRecommendation]:
        return [
            TransparencyRecommendation(
                title="Increase Dataset Publication Frequency",
                description=(
                    "Several SSA disability datasets are published annually, introducing "
                    "12–18 month lags. Increasing publication frequency to quarterly or "
                    "monthly would significantly improve timeliness of public data."
                ),
                affected_datasets=["ssa-disability-applications-decisions", "ssa-disability-research-statistics"],
                new_data_elements=["reporting_period"],
                expected_impact="Faster detection of program trends and emerging equity issues.",
                priority=RecommendationPriority.HIGH,
                implementation_effort="Medium",
            ),
            TransparencyRecommendation(
                title="Add Demographic Disaggregation to Core Datasets",
                description=(
                    "Core SSA disability statistics lack race, ethnicity, and income "
                    "disaggregation. Adding these dimensions would enable equity analysis."
                ),
                affected_datasets=["ssa-disability-applications-decisions"],
                new_data_elements=["race_ethnicity", "income_decile"],
                expected_impact="Enables identification and remediation of disparate program impacts.",
                priority=RecommendationPriority.HIGH,
                implementation_effort="High",
            ),
        ]
