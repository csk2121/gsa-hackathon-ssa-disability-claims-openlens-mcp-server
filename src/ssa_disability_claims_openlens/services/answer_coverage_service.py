"""
Answer Coverage Engine — the signature capability of SSA Disability Claims OpenLens.

The engine answers one question:
  "How well do available SSA public datasets support answering a user's question?"

Algorithm:
  1. Accept a natural language question.
  2. Extract required information elements (keyword + semantic pattern matching).
  3. Map elements to available datasets via a coverage knowledge base.
  4. Score each element's coverage quality (Full / Partial / Proxy / None).
  5. Compute an aggregate Answer Coverage Score (0–100).
  6. Classify the score into a CoverageRating.
  7. Identify critical and partial gaps.
  8. Generate actionable transparency recommendations.
  9. Return an AnswerCoverageAssessment.

Design decisions:
  - No LLM dependency: the engine uses deterministic pattern matching so it works
    offline and produces reproducible results. This is intentional for a tool that
    must be auditable and explainable.
  - The coverage knowledge base is a maintainable dict — easy to extend as new
    datasets are published.
  - Scoring weights critical elements (high weight) separately from supporting
    elements (lower weight) so a question cannot achieve "High" coverage if its
    core information need is unmet.
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
)
from ..utils import extract_keywords, get_logger, score_to_coverage_rating

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
        patterns=[r"appointment", r"walk.?in", r"office\s*visit", r"in.?person"],
        element="Field office appointment wait times",
        description="Wait times for in-person appointments at SSA field offices",
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
    # ── Staffing / workload ────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"staffing", r"staff\s*level", r"headcount", r"employees?", r"workers?\s*at",
                  r"how\s*many.*staff", r"staff.*work\s*at", r"work\s*at.*office"],
        element="SSA office staffing levels",
        description="Number of adjudicators or staff at field or hearing offices",
        dataset_ids=[],
        coverage_quality="None",
        weight=2,
    ),
    _CoverageEntry(
        patterns=[r"workload", r"case\s*load", r"capacity", r"productivity"],
        element="Office workload and capacity",
        description="Case volume relative to office processing capacity",
        dataset_ids=["ssa-odar-pending-cases"],
        coverage_quality="Proxy",
        weight=1,
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
]


# ── Recommendation knowledge base ─────────────────────────────────────────────
# Maps missing information elements to suggested transparency improvements.

_TRANSPARENCY_REC_KB: dict[str, list[str]] = {
    "Field office appointment wait times": [
        "Publish monthly field office appointment wait time data by office",
        "Report the percentage of visitors served within 30/60 minutes",
    ],
    "SSA office staffing levels": [
        "Publish annual FTE staffing levels by field office and hearing office",
        "Report adjudicator-to-caseload ratios to contextualize processing times",
    ],
    "Race and ethnicity data": [
        "Publish disability application, award, and denial rates disaggregated by race and ethnicity",
        "Report race/ethnicity data at all levels of the appeals process",
        "Partner with Census Bureau to link disability outcomes to demographic data",
    ],
    "Applicant income and economic status": [
        "Publish SSI application and outcome data cross-tabulated with income decile",
        "Report geographic correlation of benefit adequacy with local cost of living",
    ],
    "Work incentive program participation and outcomes": [
        "Publish annual Ticket to Work assignment and return-to-work outcome statistics",
        "Report earnings outcomes for beneficiaries using Trial Work Period provisions",
    ],
    "Office workload and capacity": [
        "Publish monthly caseload-to-staff ratios for field offices and hearing offices",
        "Report hearing office disposition targets and actuals side-by-side",
    ],
}


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
    """

    def __init__(self, knowledge_base: list[_CoverageEntry] | None = None) -> None:
        self._kb = knowledge_base if knowledge_base is not None else _COVERAGE_KB

    def _match_entries(self, question: str) -> list[tuple[_CoverageEntry, int]]:
        """Return (entry, weight) pairs where the entry patterns match the question."""
        question_lower = question.lower()
        matched: list[tuple[_CoverageEntry, int]] = []
        for entry in self._kb:
            if any(re.search(p, question_lower) for p in entry.patterns):
                matched.append((entry, entry.weight))
        return matched

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

        # Build impact statement
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

    def _build_recommendations(
        self, elements: list[InformationElement]
    ) -> list[str]:
        recs: list[str] = []
        for el in elements:
            if not el.available or el.coverage_quality in ("Partial", "Proxy", "None"):
                for rec in _TRANSPARENCY_REC_KB.get(el.element, []):
                    if rec not in recs:
                        recs.append(rec)

        # Generic fallback if no specific recommendations were found
        if not recs:
            recs.append(
                "Consider publishing more granular breakdowns of the relevant datasets "
                "to improve answer coverage for this type of question."
            )
        return recs[:6]  # Limit to 6 to keep output actionable

    def evaluate(self, question: str) -> AnswerCoverageAssessment:
        """
        Run the Answer Coverage Engine against a natural language question.

        Returns a fully populated AnswerCoverageAssessment.
        """
        logger.info(f"Evaluating answer coverage for: {question[:80]}...")

        matched = self._match_entries(question)

        # If nothing matched, return Unsupported with a generic gap note
        if not matched:
            return AnswerCoverageAssessment(
                question=question,
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
                transparency_recommendations=[
                    "Consider whether this question falls within the scope of SSA disability data. "
                    "If so, file a data request with the SSA Open Data Program."
                ],
                potential_impact="Unable to assess — question scope unclear.",
                datasets_consulted=[],
            )

        elements = self._build_elements(matched)
        weights = [w for _, w in matched]

        # Score
        score = _compute_weighted_score(elements, weights)
        rating = score_to_coverage_rating(score)

        # Available vs. missing
        available_data: list[str] = []
        missing_information: list[str] = []
        all_dataset_ids: set[str] = set()

        for el in elements:
            if el.available:
                quality_note = f" ({el.coverage_quality} coverage)" if el.coverage_quality != "Full" else ""
                available_data.append(f"{el.element}{quality_note}")
                all_dataset_ids.update(el.dataset_ids)
            else:
                missing_information.append(el.element)

        # Enrich available_data with dataset names for context
        available_data_with_sources: list[str] = []
        from ..services.dataset_catalog_service import get_catalog_service  # local import avoids circular
        try:
            catalog = get_catalog_service()
            id_to_name = {
                ds.dataset_id: ds.name for ds in catalog.list_datasets()
            }
            for item in available_data:
                available_data_with_sources.append(item)
            # Add a summary of which datasets were used
            used_names = [id_to_name.get(did, did) for did in sorted(all_dataset_ids)]
            if used_names:
                available_data_with_sources.append(
                    f"Source datasets: {', '.join(used_names)}"
                )
        except Exception:  # noqa: BLE001
            available_data_with_sources = available_data

        gap_analysis = self._build_gap_analysis(elements, question)
        recommendations = self._build_recommendations(elements)

        # Potential impact
        if rating in (CoverageRating.UNSUPPORTED, CoverageRating.LIMITED):
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
            answer_coverage_score=score,
            coverage_rating=rating,
            required_information_elements=elements,
            available_data=available_data_with_sources,
            missing_information=missing_information,
            gap_analysis=gap_analysis,
            transparency_recommendations=recommendations,
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
