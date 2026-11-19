"""
Answer Coverage Engine — the signature capability of SSA Disability Claims OpenLens.

The engine answers one question:
  "How well do available SSA public datasets support answering a user's question?"

Algorithm:
  1. Accept a natural language question.
  2. Extract primary intent — what is the user fundamentally trying to understand?
  3. Use intent to seed required information elements before keyword matching.
  4. Match question keywords against the coverage knowledge base.
  5. Merge intent-seeded and keyword-matched elements (deduplicated).
  6. Score each element's coverage quality (Full / Partial / Proxy / None).
  7. Compute an aggregate Answer Coverage Score (0–100).
  8. Classify the score into a CoverageRating.
  9. Identify critical and partial gaps.
  10. Generate structured recommendations that directly address each gap,
      with category labels and justifications.
  11. Return an AnswerCoverageAssessment.

Design decisions:
  - No LLM dependency: the engine uses deterministic pattern matching so it works
    offline and produces reproducible results. This is intentional for a tool that
    must be auditable and explainable.
  - Intent extraction runs before keyword matching so meta-questions (e.g. "what
    should SSA publish?") still map to the correct information needs.
  - Each recommendation is linked to the specific gap it closes, categorised, and
    accompanied by a justification — not a generic suggestion list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..models import (
    AnswerCoverageAssessment,
    CoverageRating,
    GapAnalysis,
    InformationElement,
    IntentAnalysis,
    Recommendation,
)
from ..services.recommendation_service import RecommendationService
from ..utils import extract_keywords, get_logger, score_to_coverage_rating

_recommendation_service = RecommendationService()

logger = get_logger(__name__)


# ── Coverage knowledge base ────────────────────────────────────────────────────
# Maps semantic topic patterns → information element specifications.
# Each entry describes:
#   - patterns: regex fragments matched against the question
#   - element: human-readable information element name
#   - description: why it's needed
#   - dataset_ids: which datasets partially or fully supply it
#   - coverage_quality: Full | Partial | Proxy | None
#   - weight: 1 (supporting) or 2 (critical)

@dataclass
class _CoverageEntry:
    patterns: list[str]           # Regex patterns to detect relevance
    element: str                  # Information element name
    description: str              # Why it's needed
    dataset_ids: list[str]        # Datasets that supply it
    coverage_quality: str         # Full | Partial | Proxy | None
    weight: int = 1               # 1=supporting, 2=critical


_COVERAGE_KB: list[_CoverageEntry] = [
    # ── Processing / wait times ────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"wait\s*(time|period)", r"processing\s*time", r"how\s*long",
                  r"days?\s*(to|for)\s*(decide|decision|process)", r"backlog"],
        element="Disability claim processing times",
        description="Average or distribution of days from application to initial decision",
        dataset_ids=["ssa-odar-pending-cases", "data-gov-ssa-performance"],
        coverage_quality="Partial",
        weight=2,
    ),
    _CoverageEntry(
        patterns=[r"hearing\s*(wait|time|backlog|delay)", r"appeal.*wait", r"odar"],
        element="Hearing-level wait times",
        description="Time from request for hearing to hearing office decision",
        dataset_ids=["ssa-odar-pending-cases"],
        coverage_quality="Partial",
        weight=2,
    ),
    _CoverageEntry(
        patterns=[r"appointment", r"walk.?in", r"office\s*visit", r"in.?person",
                  r"walk.?in\s*traffic", r"appointment\s*volume"],
        element="Field office appointment and walk-in volume",
        description="Volume of in-person visits and appointments at SSA field offices",
        dataset_ids=[],
        coverage_quality="None",
        weight=2,
    ),
    # ── Geographic analysis ────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"state", r"geographic", r"region", r"county", r"local", r"area"],
        element="Geographic disaggregation of outcomes",
        description="Disability outcomes broken down by state or sub-state geography",
        dataset_ids=["ssa-oasdi-beneficiaries-by-state", "ssa-ssi-recipients-by-state", "ssa-odar-pending-cases"],
        coverage_quality="Partial",
        weight=1,
    ),
    _CoverageEntry(
        patterns=[r"field\s*office", r"office\s*location", r"access\s*to\s*ssa", r"service\s*desert"],
        element="SSA field office locations and coverage",
        description="Geographic distribution of SSA field offices",
        dataset_ids=["ssa-field-office-locator"],
        coverage_quality="Full",
        weight=1,
    ),
    _CoverageEntry(
        patterns=[r"field\s*office.*demand", r"field\s*office.*service",
                  r"demand.*field\s*office", r"service.*field\s*office",
                  r"field\s*office.*volume", r"field\s*office.*traffic",
                  r"which.*office", r"highest.*office", r"busiest.*office"],
        element="Field office operational metrics (staffing, volume, wait times)",
        description=(
            "Per-field-office operational data: staffing levels, appointment volumes, "
            "walk-in traffic, and wait times needed to rank offices by service demand"
        ),
        dataset_ids=[],
        coverage_quality="None",
        weight=2,
    ),
    # ── Staffing / workload ────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"staffing", r"staff\s*level", r"headcount", r"employees?", r"workers?\s*at",
                  r"how\s*many.*staff", r"staff.*work\s*at", r"work\s*at.*office",
                  r"staff.*capacity", r"office.*staff"],
        element="SSA office staffing levels",
        description="Number of adjudicators or staff at field or hearing offices",
        dataset_ids=[],
        coverage_quality="None",
        weight=2,
    ),
    _CoverageEntry(
        patterns=[r"workload", r"case\s*load", r"capacity", r"productivity",
                  r"demand", r"service\s*volume", r"busiest", r"highest.*demand",
                  r"demand.*office", r"office.*demand"],
        element="Office workload and capacity",
        description="Case volume relative to office processing capacity",
        dataset_ids=["ssa-odar-pending-cases"],
        coverage_quality="Proxy",
        weight=2,
    ),
    # ── Demographics ───────────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"age\s*group", r"age\s*of\s*applicants?", r"older\s*workers?", r"young\s*(disabled|applicants?)"],
        element="Applicant age distribution",
        description="Age breakdown of disability applicants and recipients",
        dataset_ids=["ssa-disability-applications-decisions", "ssa-disability-research-statistics"],
        coverage_quality="Partial",
        weight=1,
    ),
    _CoverageEntry(
        patterns=[r"\bsex\b", r"\bgender\b", r"men\b", r"women\b", r"male", r"female"],
        element="Gender disaggregation",
        description="Disability outcomes broken down by gender",
        dataset_ids=["ssa-disability-research-statistics"],
        coverage_quality="Partial",
        weight=1,
    ),
    _CoverageEntry(
        patterns=[r"race", r"ethnic", r"racial\s*dispar", r"minority", r"hispanic", r"black", r"white"],
        element="Race and ethnicity data",
        description="Disability application, award, and denial rates by race/ethnicity",
        dataset_ids=[],
        coverage_quality="None",
        weight=2,
    ),
    _CoverageEntry(
        patterns=[r"income", r"poverty", r"low.income", r"economic", r"socioeconomic"],
        element="Applicant income and economic status",
        description="Relationship between income level and disability program access/outcomes",
        dataset_ids=[],
        coverage_quality="None",
        weight=2,
    ),
    # ── Impairments ────────────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"impairment", r"diagnosis", r"condition", r"disease", r"mental\s*(health|disorder)",
                  r"musculoskeletal", r"disability\s*type"],
        element="Impairment/diagnosis categories",
        description="Distribution of disabilities by medical category",
        dataset_ids=["ssa-disability-applications-decisions"],
        coverage_quality="Partial",
        weight=1,
    ),
    # ── Program outcomes ───────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"allowance\s*rate", r"approval\s*rate", r"denial\s*rate", r"award\s*rate"],
        element="Disability program allowance rates",
        description="Percentage of applications approved at each decision level",
        dataset_ids=["ssa-disability-applications-decisions"],
        coverage_quality="Partial",
        weight=2,
    ),
    _CoverageEntry(
        patterns=[r"application\s*(volume|count|number|trend)", r"applicants?", r"filed"],
        element="Application volumes",
        description="Number of disability applications submitted over time",
        dataset_ids=["ssa-disability-applications-decisions"],
        coverage_quality="Full",
        weight=1,
    ),
    _CoverageEntry(
        patterns=[r"benefit\s*(amount|level|adequacy)", r"monthly\s*payment", r"average\s*benefit"],
        element="Benefit amounts by geography and demographics",
        description="Average disability benefit payments",
        dataset_ids=["ssa-oasdi-beneficiaries-by-state", "ssa-disability-research-statistics"],
        coverage_quality="Partial",
        weight=1,
    ),
    _CoverageEntry(
        patterns=[r"beneficiar(y|ies)", r"recipients?", r"enrolled", r"on\s*(SSDI|SSI)"],
        element="Beneficiary/recipient counts",
        description="Number of people currently receiving disability benefits",
        dataset_ids=["ssa-oasdi-beneficiaries-by-state", "ssa-ssi-recipients-by-state"],
        coverage_quality="Full",
        weight=1,
    ),
    # ── Appeals ────────────────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"appeal", r"reconsider", r"hearing", r"alj\b", r"administrative\s*law"],
        element="Appeals and hearing outcomes",
        description="Results and processing metrics for disability appeal hearings",
        dataset_ids=["ssa-odar-pending-cases"],
        coverage_quality="Partial",
        weight=1,
    ),
    # ── Employment / return to work ────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"return\s*to\s*work", r"employment", r"ticket\s*to\s*work", r"work\s*incentive", r"sga\b"],
        element="Work incentive program participation and outcomes",
        description="Participation in and outcomes from SSA work incentive programs",
        dataset_ids=["ssa-red-book"],
        coverage_quality="Proxy",
        weight=1,
    ),
    # ── Performance metrics ────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"performance", r"target", r"goal", r"accuracy", r"customer\s*satisfaction"],
        element="Agency performance metrics",
        description="SSA operational performance against official targets",
        dataset_ids=["data-gov-ssa-performance"],
        coverage_quality="Partial",
        weight=1,
    ),
    # ── SSI-specific ───────────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"\bssi\b", r"supplemental\s*security\s*income"],
        element="SSI program data",
        description="Supplemental Security Income recipient and payment data",
        dataset_ids=["ssa-ssi-recipients-by-state"],
        coverage_quality="Partial",
        weight=1,
    ),
    # ── SSDI-specific ──────────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"\bssdi\b", r"disability\s*insurance", r"title\s*ii"],
        element="SSDI program data",
        description="Social Security Disability Insurance beneficiary data",
        dataset_ids=["ssa-oasdi-beneficiaries-by-state", "ssa-disability-research-statistics"],
        coverage_quality="Partial",
        weight=1,
    ),
    # ── Accessibility / geographic equity ─────────────────────────────────────
    _CoverageEntry(
        patterns=[
            r"rural", r"urban", r"geographic\s*equit", r"regional\s*dispar",
            r"underserved", r"service\s*gap", r"service\s*desert", r"county\s*coverage",
            r"office\s*coverage", r"less\s*access", r"access.*rural", r"rural.*access",
        ],
        element="Geographic distribution of disability service access",
        description=(
            "County- or region-level data showing where disability populations are located "
            "relative to SSA office coverage, needed to compare rural and urban access"
        ),
        dataset_ids=[
            "ssa-field-office-locator",
            "ssa-oasdi-beneficiaries-by-state",
            "ssa-ssi-recipients-by-state",
        ],
        coverage_quality="Partial",
        weight=2,
    ),
    _CoverageEntry(
        patterns=[
            r"travel\s*distance", r"distance\s*to\s*(office|ssa)", r"nearest\s*office",
            r"miles?\s*(to|from)\s*office", r"drive\s*time",
        ],
        element="Travel distance to nearest SSA field office",
        description="Distance or travel time between claimant location and nearest field office",
        dataset_ids=[],
        coverage_quality="None",
        weight=2,
    ),
    _CoverageEntry(
        patterns=[
            r"service\s*area\s*boundar", r"office\s*boundar", r"coverage\s*area",
            r"catchment\s*area",
        ],
        element="Field office service area boundaries",
        description="Defined geographic service areas for each SSA field office",
        dataset_ids=[],
        coverage_quality="None",
        weight=1,
    ),
    _CoverageEntry(
        patterns=[
            r"accessib(ility|le)\s*(accommodation|feature|service)",
            r"ada\s*compliance", r"disability\s*access(ib)?", r"physical\s*access",
        ],
        element="Accessibility accommodations at field offices",
        description="ADA compliance status, language services, and physical accessibility features",
        dataset_ids=[],
        coverage_quality="None",
        weight=1,
    ),
    _CoverageEntry(
        patterns=[
            r"disability.*application.*county", r"county.*application",
            r"application.*geographic", r"geographic.*application",
        ],
        element="Disability application counts by county",
        description="Number of disability applications disaggregated to county level",
        dataset_ids=["ssa-disability-applications-decisions"],
        coverage_quality="Proxy",
        weight=1,
    ),
]


# ── Intent knowledge base ──────────────────────────────────────────────────────
# Maps intent patterns → (category, required_data_types, scope, element_ids_to_seed)
# element_ids_to_seed are _CoverageEntry.element values to force-include before
# keyword matching, so meta-questions still surface the right information needs.

@dataclass
class _IntentEntry:
    patterns: list[str]
    category: str
    primary_intent_template: str    # {q} replaced with the question
    required_data_types: list[str]
    scope: str
    seed_elements: list[str]        # element names to force-include in matching
    context_dataset_ids: list[str]  # datasets that provide domain context even when they
                                    # don't directly answer the question


_INTENT_KB: list[_IntentEntry] = [
    _IntentEntry(
        patterns=[r"field\s*office.*demand", r"which.*office.*high", r"busiest.*office",
                  r"office.*service.*demand", r"highest.*demand"],
        category="Access",
        primary_intent_template="Identify which SSA field offices face the highest disability service demand",
        required_data_types=["Office visit volumes", "Staffing levels", "Geographic beneficiary counts"],
        scope="Field office level, national",
        seed_elements=[
            "Field office operational metrics (staffing, volume, wait times)",
            "Office workload and capacity",
            "SSA field office locations and coverage",
        ],
        context_dataset_ids=[
            "ssa-field-office-locator",
            "ssa-oasdi-beneficiaries-by-state",
            "ssa-ssi-recipients-by-state",
            "ssa-odar-pending-cases",
        ],
    ),
    _IntentEntry(
        patterns=[r"access(ib|ibility)", r"maximize.*understanding", r"what.*should.*publish",
                  r"additional.*dataset", r"metrics.*should", r"publish.*first"],
        category="Access",
        primary_intent_template="Determine which SSA datasets or metrics would most improve public understanding of disability service accessibility",
        required_data_types=["Office visit volumes", "Appointment wait times", "Staffing capacity", "Geographic coverage"],
        scope="National, all field offices",
        seed_elements=[
            "Field office operational metrics (staffing, volume, wait times)",
            "Field office appointment and walk-in volume",
            "SSA office staffing levels",
        ],
        context_dataset_ids=[
            "ssa-field-office-locator",
            "ssa-oasdi-beneficiaries-by-state",
            "ssa-ssi-recipients-by-state",
            "ssa-odar-pending-cases",
            "ssa-disability-applications-decisions",
        ],
    ),
    _IntentEntry(
        patterns=[r"racial\s*dispar", r"race.*dispar", r"equity.*race", r"ethnic.*dispar"],
        category="Equity",
        primary_intent_template="Assess whether racial or ethnic disparities exist in SSA disability program outcomes",
        required_data_types=["Race/ethnicity breakdowns", "Allowance rates by demographics", "Application volumes by race"],
        scope="National",
        seed_elements=["Race and ethnicity data", "Disability program allowance rates"],
        context_dataset_ids=[
            "ssa-disability-applications-decisions",
            "ssa-oasdi-beneficiaries-by-state",
            "ssa-disability-research-statistics",
        ],
    ),
    _IntentEntry(
        patterns=[r"wait\s*time.*state", r"processing.*state", r"state.*processing",
                  r"how\s*long.*state", r"state.*backlog"],
        category="Performance",
        primary_intent_template="Compare disability claim processing times or wait times across states",
        required_data_types=["State-level processing times", "Hearing backlog by office", "Application volumes by state"],
        scope="State level",
        seed_elements=["Disability claim processing times", "Geographic disaggregation of outcomes"],
        context_dataset_ids=[
            "ssa-odar-pending-cases",
            "data-gov-ssa-performance",
            "ssa-oasdi-beneficiaries-by-state",
        ],
    ),
    _IntentEntry(
        patterns=[r"income", r"poverty", r"benefit.*adequacy", r"low.?income"],
        category="Finance",
        primary_intent_template="Evaluate SSI benefit adequacy relative to recipient income and poverty levels",
        required_data_types=["Recipient income data", "Benefit payment amounts", "Local cost-of-living indicators"],
        scope="National and state level",
        seed_elements=["Applicant income and economic status", "Benefit amounts by geography and demographics"],
        context_dataset_ids=[
            "ssa-ssi-recipients-by-state",
            "ssa-oasdi-beneficiaries-by-state",
            "ssa-disability-research-statistics",
        ],
    ),
    _IntentEntry(
        patterns=[r"return\s*to\s*work", r"employment.*disab", r"work\s*incentive", r"ticket\s*to\s*work"],
        category="Outcomes",
        primary_intent_template="Measure outcomes of SSA work incentive programs for disability beneficiaries",
        required_data_types=["Ticket to Work participation", "Trial Work Period outcomes", "Return-to-work rates"],
        scope="National",
        seed_elements=["Work incentive program participation and outcomes"],
        context_dataset_ids=[
            "ssa-red-book",
            "ssa-disability-applications-decisions",
        ],
    ),
    # ── Accessibility ──────────────────────────────────────────────────────────
    _IntentEntry(
        patterns=[
            r"rural.*access", r"access.*rural", r"urban.*rural",
            r"rural.*urban", r"rural.*communit", r"rural.*disab",
            r"geographic.*access", r"access.*geographic",
            r"less\s*access", r"underserved.*communit",
            r"service\s*desert", r"service\s*gap",
            r"access\s*to\s*disab", r"disab.*access\s*to\s*service",
        ],
        category="Accessibility",
        primary_intent_template=(
            "Determine whether rural communities have less access to SSA disability services "
            "than urban communities using available public datasets"
        ),
        required_data_types=[
            "Field office locations",
            "Disability population distribution",
            "County-level beneficiary counts",
            "Travel distance to nearest office",
            "Appointment wait times by geography",
        ],
        scope="County and community level, national",
        seed_elements=[
            "Geographic distribution of disability service access",
            "SSA field office locations and coverage",
            "Travel distance to nearest SSA field office",
            "Field office operational metrics (staffing, volume, wait times)",
        ],
        context_dataset_ids=[
            "ssa-field-office-locator",
            "ssa-ssi-recipients-by-state",
            "ssa-oasdi-beneficiaries-by-state",
            "ssa-disability-applications-decisions",
            "ssa-odar-pending-cases",
        ],
    ),
    # ── Geographic equity ──────────────────────────────────────────────────────
    _IntentEntry(
        patterns=[
            r"geographic\s*equit", r"regional\s*dispar",
            r"county.*dispar", r"dispar.*county",
            r"geographic.*dispar", r"dispar.*geographic",
            r"office\s*coverage", r"county\s*coverage",
            r"underserved\s*area", r"underserved\s*region",
        ],
        category="Geographic Equity",
        primary_intent_template=(
            "Assess geographic equity in the distribution of SSA disability services "
            "and identify underserved regions"
        ),
        required_data_types=[
            "County-level beneficiary counts",
            "Field office locations and service areas",
            "Regional application and decision data",
        ],
        scope="County and regional level, national",
        seed_elements=[
            "Geographic distribution of disability service access",
            "SSA field office locations and coverage",
            "Field office service area boundaries",
            "Geographic disaggregation of outcomes",
        ],
        context_dataset_ids=[
            "ssa-field-office-locator",
            "ssa-oasdi-beneficiaries-by-state",
            "ssa-ssi-recipients-by-state",
            "ssa-disability-applications-decisions",
            "ssa-odar-pending-cases",
        ],
    ),
]


# ── Scoring logic ──────────────────────────────────────────────────────────────

_QUALITY_SCORE: dict[str, float] = {
    "Full": 1.0,
    "Partial": 0.6,
    "Proxy": 0.3,
    "None": 0.0,
}


def _compute_weighted_score(elements: list[InformationElement], weights: list[int]) -> float:
    """
    Compute weighted average coverage score from matched elements.

    Elements with higher weights (critical) have proportionally greater impact.
    """
    if not elements:
        return 0.0

    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(
        _QUALITY_SCORE.get(el.coverage_quality, 0.0) * w
        for el, w in zip(elements, weights)
    )
    return round((weighted_sum / total_weight) * 100, 1)


# ── Main engine ────────────────────────────────────────────────────────────────


class AnswerCoverageEngine:
    """
    Deterministic engine that evaluates how well SSA public datasets support
    answering a natural language question.

    Pipeline:
      1. Extract primary intent from the question.
      2. Use intent to seed required information elements (catches meta-questions).
      3. Keyword-match the question against the coverage KB.
      4. Merge seeded + matched entries (deduplicated by element name).
      5. Score, rate, gap-analyse, build structured recommendations.
    """

    def __init__(self, knowledge_base: list[_CoverageEntry] | None = None) -> None:
        self._kb = knowledge_base if knowledge_base is not None else _COVERAGE_KB
        # Build a name→entry index for fast seed lookups
        self._kb_by_element: dict[str, _CoverageEntry] = {e.element: e for e in self._kb}

    # ── Step 1: Intent extraction ──────────────────────────────────────────────

    def _extract_intent(self, question: str) -> IntentAnalysis | None:
        """
        Match the question against the intent KB.

        Returns the first matching IntentAnalysis, or None if no intent matches.
        The intent is used to (a) display what the engine understood, and (b)
        seed required elements before keyword matching begins.
        """
        q = question.lower()
        for entry in _INTENT_KB:
            if any(re.search(p, q) for p in entry.patterns):
                return IntentAnalysis(
                    primary_intent=entry.primary_intent_template,
                    intent_category=entry.category,
                    required_data_types=entry.required_data_types,
                    scope=entry.scope,
                )
        return None

    def _get_seed_entries(self, question: str) -> list[tuple[_CoverageEntry, int]]:
        """
        Return KB entries that the intent KB says are always required for this question,
        regardless of whether the keywords appear explicitly.
        """
        q = question.lower()
        seeded: list[tuple[_CoverageEntry, int]] = []
        for intent_entry in _INTENT_KB:
            if any(re.search(p, q) for p in intent_entry.patterns):
                for element_name in intent_entry.seed_elements:
                    kb_entry = self._kb_by_element.get(element_name)
                    if kb_entry:
                        seeded.append((kb_entry, kb_entry.weight))
        return seeded

    # ── Step 2: Keyword matching ───────────────────────────────────────────────

    def _match_entries(self, question: str) -> list[tuple[_CoverageEntry, int]]:
        """Return (entry, weight) pairs where the entry patterns match the question."""
        question_lower = question.lower()
        matched: list[tuple[_CoverageEntry, int]] = []
        for entry in self._kb:
            if any(re.search(p, question_lower) for p in entry.patterns):
                matched.append((entry, entry.weight))
        return matched

    # ── Step 3: Merge seeded + matched (deduplicate by element name) ───────────

    def _merge_entries(
        self,
        seeded: list[tuple[_CoverageEntry, int]],
        matched: list[tuple[_CoverageEntry, int]],
    ) -> list[tuple[_CoverageEntry, int]]:
        seen: set[str] = set()
        merged: list[tuple[_CoverageEntry, int]] = []
        for entry, weight in seeded + matched:
            if entry.element not in seen:
                merged.append((entry, weight))
                seen.add(entry.element)
        return merged

    # ── Step 4: Build InformationElements ─────────────────────────────────────

    def _build_elements(
        self, matched: list[tuple[_CoverageEntry, int]]
    ) -> list[InformationElement]:
        return [
            InformationElement(
                element=entry.element,
                description=entry.description,
                available=entry.coverage_quality != "None",
                dataset_ids=entry.dataset_ids,
                coverage_quality=entry.coverage_quality,
            )
            for entry, _ in matched
        ]

    # ── Step 5: Gap analysis ───────────────────────────────────────────────────

    def _build_gap_analysis(
        self, elements: list[InformationElement], question: str
    ) -> GapAnalysis:
        critical_gaps = [
            e.element for e in elements
            if not e.available and e.coverage_quality == "None"
        ]
        partial_gaps = [
            e.element for e in elements
            if e.coverage_quality in ("Partial", "Proxy")
        ]

        root_causes: list[str] = []
        if critical_gaps:
            root_causes.append(
                "Some information elements have never been collected or are not publicly released"
            )
        if partial_gaps:
            root_causes.append(
                "Several relevant datasets exist but lack demographic disaggregation, "
                "sub-national detail, or timely update frequency"
            )

        if not critical_gaps:
            impact = (
                "The question can be substantially addressed using existing public data, "
                "though some aspects rely on aggregates rather than granular records."
            )
        elif len(critical_gaps) >= len(elements) // 2:
            impact = (
                "The question cannot be reliably answered from public data alone. "
                f"Critical missing elements — {', '.join(critical_gaps[:3])} — "
                "require data that SSA has not published."
            )
        else:
            impact = (
                f"The question can be partially addressed. The critical gap is: "
                f"{critical_gaps[0]}. "
                "Without this data, any analysis will be incomplete or rely on proxies."
            )

        return GapAnalysis(
            critical_gaps=critical_gaps,
            partial_gaps=partial_gaps,
            root_causes=root_causes,
            impact_on_answer=impact,
        )

    # ── Main evaluate ──────────────────────────────────────────────────────────

    def evaluate(self, question: str) -> AnswerCoverageAssessment:
        """
        Run the full Answer Coverage pipeline against a natural language question.

        Returns a fully populated AnswerCoverageAssessment.
        """
        logger.info(f"Evaluating answer coverage for: {question[:80]}...")

        # 1. Extract intent
        intent = self._extract_intent(question)

        # 2. Seed required elements from intent
        seeded = self._get_seed_entries(question)

        # 3. Keyword-match the question
        matched = self._match_entries(question)

        # 4. Merge (intent seeds first, so they appear at the top)
        all_matched = self._merge_entries(seeded, matched)

        # If nothing matched at all (no intent seed, no keyword hit), return Unsupported
        if not all_matched:
            return AnswerCoverageAssessment(
                question=question,
                intent=None,
                answer_coverage_score=0.0,
                coverage_rating=CoverageRating.UNSUPPORTED,
                required_information_elements=[],
                available_data=[],
                missing_information=[
                    "No matching SSA public dataset topics were identified for this question"
                ],
                gap_analysis=GapAnalysis(
                    critical_gaps=["All required information"],
                    partial_gaps=[],
                    root_causes=["Question may be outside SSA disability program scope"],
                    impact_on_answer="This question cannot be answered from SSA public datasets.",
                ),
                structured_recommendations=[],
                transparency_recommendations=[
                    "Consider whether this question falls within the scope of SSA disability data. "
                    "If so, file a data request with the SSA Open Data Program."
                ],
                potential_impact="Unable to assess — question scope unclear.",
                datasets_consulted=[],
            )

        # 5. Build elements and score
        elements = self._build_elements(all_matched)
        weights = [w for _, w in all_matched]

        score = _compute_weighted_score(elements, weights)
        rating = score_to_coverage_rating(score)

        # 6. Available vs. missing
        missing_information: list[str] = []
        all_dataset_ids: set[str] = set()

        for el in elements:
            if el.available:
                all_dataset_ids.update(el.dataset_ids)
            else:
                missing_information.append(el.element)

        # Collect context dataset IDs from matched intent entries.
        # These are catalog datasets that provide domain context for the question
        # even when they don't directly supply the missing metrics.
        context_dataset_ids: set[str] = set()
        q_lower = question.lower()
        for intent_entry in _INTENT_KB:
            if any(re.search(p, q_lower) for p in intent_entry.patterns):
                context_dataset_ids.update(intent_entry.context_dataset_ids)

        # Merge: direct dataset IDs (from matched elements) take precedence;
        # context IDs fill in when no element-level datasets were found.
        display_dataset_ids = all_dataset_ids | context_dataset_ids

        # Build available_data as short dataset names, and available_data_with_urls
        # as [{name, url}] dicts for tabular rendering in the report.
        from ..services.dataset_catalog_service import get_catalog_service  # local import avoids circular
        available_data_with_sources: list[str] = []
        available_data_with_urls: list[dict] = []
        context_note: str = ""
        try:
            catalog = get_catalog_service()
            all_ds = catalog.list_datasets()
            id_to_name = {ds.dataset_id: ds.name for ds in all_ds}
            id_to_url = {ds.dataset_id: ds.url for ds in all_ds}
            seen: set[str] = set()
            for did in sorted(display_dataset_ids):
                name = id_to_name.get(did, did)
                if name not in seen:
                    available_data_with_sources.append(name)
                    url = id_to_url.get(did, "")
                    available_data_with_urls.append({"name": name, "url": url})
                    seen.add(name)

            # Add a context note when available datasets are contextual only
            # (i.e. none of them directly supply the required metrics)
            if available_data_with_sources and not all_dataset_ids:
                context_note = (
                    "These datasets provide contextual information about disability "
                    "populations and office locations but do not provide direct measures "
                    "of service accessibility."
                )
        except Exception:  # noqa: BLE001
            available_data_with_sources = sorted(display_dataset_ids)
            available_data_with_urls = [{"name": did, "url": ""} for did in sorted(display_dataset_ids)]

        # 7. Gap analysis and recommendations — both sourced from RecommendationService
        gap_analysis = self._build_gap_analysis(elements, question)
        structured_recs: list[Recommendation] = _recommendation_service.for_gaps(elements)
        plain_recs = [r.title for r in structured_recs]

        # 8. Floor rule: Unsupported → Limited when domain context was found.
        #
        #    Unsupported means the engine could not map the question to any known
        #    SSA domain. If the engine successfully extracted intent OR produced
        #    structured recommendations, it *did* find domain context — it knows
        #    what data is needed, what is missing, and what SSA should publish.
        #    That is exactly what Limited means: relevant domain found, major gaps
        #    prevent a complete answer. Leaving it as Unsupported would be wrong.
        if rating == CoverageRating.UNSUPPORTED and (intent is not None or structured_recs):
            rating = CoverageRating.LIMITED

        # 9. Potential impact — intent-specific where available, generic fallback
        intent_category = intent.intent_category.lower() if intent else ""
        if intent_category in ("accessibility", "geographic equity", "access"):
            potential_impact = (
                "Publishing the recommended data elements would enable researchers and "
                "policymakers to directly evaluate whether rural communities face greater "
                "barriers to disability services than urban communities.\n\n"
                "The additional data would support analysis of:\n"
                "- Geographic disparities in service accessibility\n"
                "- Travel burden to SSA field offices\n"
                "- Appointment wait times by region\n"
                "- Alignment of staffing resources with community demand\n"
                "- Potential disability-service deserts and underserved areas\n\n"
                "Implementing these recommendations would markedly improve public understanding "
                "of SSA disability service accessibility. Stakeholders could identify geographic "
                "and demographic disparities in service access, evaluate whether rural and "
                "underserved communities face greater barriers to assistance, and advocate for "
                "targeted service improvements. Greater transparency would strengthen "
                "accountability, support evidence-based policymaking, and help ensure more "
                "equitable access to disability benefits and services."
            )
        elif rating in (CoverageRating.UNSUPPORTED, CoverageRating.LIMITED):
            potential_impact = (
                "Publishing the missing data elements would substantially improve public "
                "ability to evaluate SSA program equity, efficiency, and access — enabling "
                "researchers, advocates, and policymakers to draw evidence-based conclusions."
            )
        elif rating == CoverageRating.PARTIAL:
            potential_impact = (
                "Closing identified gaps would upgrade this question from 'Partial' to 'High' "
                "coverage, enabling more confident public analysis of SSA program outcomes."
            )
        else:
            potential_impact = (
                "Existing data provides strong coverage. Additional granularity or timeliness "
                "improvements would further enhance analytical value."
            )

        return AnswerCoverageAssessment(
            question=question,
            intent=intent,
            answer_coverage_score=score,
            coverage_rating=rating,
            required_information_elements=elements,
            available_data=available_data_with_sources,
            available_data_with_urls=available_data_with_urls,
            available_data_context_note=context_note,
            missing_information=missing_information,
            gap_analysis=gap_analysis,
            structured_recommendations=structured_recs,
            transparency_recommendations=plain_recs,
            potential_impact=potential_impact,
            datasets_consulted=sorted(all_dataset_ids),
        )


# Singleton
_engine: AnswerCoverageEngine | None = None


def get_answer_coverage_engine() -> AnswerCoverageEngine:
    """Return the singleton AnswerCoverageEngine."""
    global _engine
    if _engine is None:
        _engine = AnswerCoverageEngine()
    return _engine
