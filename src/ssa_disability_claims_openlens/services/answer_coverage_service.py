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

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
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
from ..utils import get_logger, score_to_coverage_rating

_recommendation_service = RecommendationService()

logger = get_logger(__name__)

# ── Gap-claim evidence ─────────────────────────────────────────────────────────
# Every element rated "None" must have an entry in data/gap_evidence.json recording
# the Data.gov searches that found no SSA dataset for it (enforced by
# tests/test_catalog_grounding.py; re-checked by scripts/check_gap_claims.py).

GAP_EVIDENCE_PATH = Path(__file__).resolve().parent.parent / "data" / "gap_evidence.json"


def _load_gap_evidence() -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.loads(GAP_EVIDENCE_PATH.read_text(encoding="utf-8"))
        return data
    except FileNotFoundError:
        logger.error(f"Gap evidence file missing: {GAP_EVIDENCE_PATH}")
        return {}


_GAP_EVIDENCE = _load_gap_evidence()


def _evidence_note(element: str) -> str:
    """One-line description of how the absence of `element` was checked."""
    claim = _GAP_EVIDENCE.get("claims", {}).get(element)
    if not claim:
        return ""
    queries = ", ".join(f"'{q}'" for q in claim.get("queries", []))
    return (
        f"Data.gov search of SSA datasets with downloads ({queries}) on "
        f"{_GAP_EVIDENCE.get('searched_on', 'unknown date')}. {claim.get('verdict', '')}"
    ).strip()


# ── Coverage knowledge base ────────────────────────────────────────────────────
# Maps semantic topic patterns → information element specifications.
#
# Rating rubric (enforced by tests/test_catalog_grounding.py):
#   Full    — a catalogued dataset directly measures the element at the granularity
#             the question needs, and is current.
#   Partial — catalogued datasets measure it, but miss a needed level, breakdown,
#             distribution or time period.
#   Proxy   — only indirect, one-time, historical or discontinued data exists.
#   None    — no SSA dataset on Data.gov provides it; backed by recorded searches
#             in data/gap_evidence.json.
# Full/Partial/Proxy entries must list datasets; None entries must list none.
# Every entry states its rationale, which the report shows to the user.
#
# Fields:
#   patterns:         regex fragments matched against the normalised question
#   exclude_patterns: if any matches, the entry is skipped (avoids false matches)
#   element / description / dataset_ids / coverage_quality / weight (2 = critical)
#   rationale:        why this rating, citing the datasets' source records
#   refines:          broader elements this entry measures at the level the question
#                     asks for. When both are included, the broader ones become
#                     supporting (weight 1), so e.g. a national average cannot stand in
#                     for the per-office figure the question actually needs.

@dataclass
class _CoverageEntry:
    patterns: list[str]
    element: str
    description: str
    dataset_ids: list[str]
    coverage_quality: str          # Full | Partial | Proxy | None
    rationale: str
    weight: int = 1                # 1 = supporting, 2 = critical
    exclude_patterns: list[str] = field(default_factory=list)
    refines: list[str] = field(default_factory=list)


# Questions about how long *decisions* take at a local office (field office or state
# DDS). Shared by the coverage entry and the intent entry below. Appointment, walk-in
# and phone waits are service waits, not decision times, and hearing offices have
# their own element ("Hearing-level wait times").
_DECISION_WORDS = r"(decision|decide|processing|wait|delay|backlog|pending)"
_OFFICE_DECISION_TIME_PATTERNS: list[str] = [
    rf"(field|dds|local)\s*office.*{_DECISION_WORDS}",
    rf"{_DECISION_WORDS}.*(field|dds|local)\s*office",
    rf"\bdds\b.*{_DECISION_WORDS}",
    rf"{_DECISION_WORDS}.*\bdds\b",
    rf"disability\s*determination\s*service.*{_DECISION_WORDS}",
]
_OFFICE_DECISION_TIME_EXCLUDES: list[str] = [
    r"appointment", r"walk.?in", r"in.?person", r"visit", r"lobby", r"phone",
    r"hearing\s*office",
]


_COVERAGE_KB: list[_CoverageEntry] = [
    # ── Processing / wait times ────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"wait\s*(time|period)", r"processing\s*time", r"how\s*long",
                  r"days?\s*(to|for)\s*(decide|decision|process)", r"backlog",
                  # "number of days an initial decision takes", "how many months to a decision"
                  r"\b(days?|weeks?|months?)\b[^.?!]{0,40}\b(decision|decide|process)",
                  r"how\s*many\s*(days|weeks|months)",
                  r"\b(decision|claim)s?\b[^.?!]{0,30}\btakes?\b"],
        exclude_patterns=[r"appointment"],
        element="Disability claim processing times",
        description="Average or distribution of days from application to decision",
        dataset_ids=[
            "ssa-initial-disability-processing-time",
            "ssa-reconsideration-processing-time",
            "ssa-hearing-office-workload",
            "ssa-hearing-wait-time",
        ],
        coverage_quality="Partial",
        rationale=(
            "Average processing times are published for initial claims (US-GOV-SSA-1409), "
            "reconsiderations (US-GOV-SSA-1768) and hearings (US-GOV-SSA-303, -304), but only "
            "as averages, with no state breakdown described for initial claims."
        ),
        weight=2,
    ),
    _CoverageEntry(
        patterns=_OFFICE_DECISION_TIME_PATTERNS,
        exclude_patterns=_OFFICE_DECISION_TIME_EXCLUDES,
        element="Disability decision times by field office or DDS",
        description=(
            "Time to a disability decision for claims taken at each field office, or decided "
            "by each state Disability Determination Services (DDS) office"
        ),
        dataset_ids=[
            "ssa-initial-disability-processing-time",
            "ssa-state-agency-workload-data",
            "ssa-hearing-office-workload",
            "ssa-field-office-claims-pending",
        ],
        coverage_quality="Proxy",
        rationale=(
            "No dataset reports decision times per field office or per DDS. Initial-claim times "
            "are national averages (US-GOV-SSA-1409), state agency data has pending counts by "
            "state but no times (US-GOV-SSA-307), field office claims pending is one national "
            "count per year, all claim types combined, ending FY2022 (US-GOV-SSA-435), and "
            "per-office times exist only for hearing offices (US-GOV-SSA-303), which are not "
            "mapped to field offices."
        ),
        weight=2,
        refines=["Disability claim processing times"],
    ),
    _CoverageEntry(
        patterns=[r"hearing\s*(wait|time|backlog|delay)", r"appeal.*wait", r"odar", r"\boho\b"],
        element="Hearing-level wait times",
        description="Time from request for hearing to hearing office decision",
        dataset_ids=["ssa-hearing-office-workload", "ssa-hearing-wait-time"],
        coverage_quality="Partial",
        rationale=(
            "Average processing time per hearing office and average months to a hearing are "
            "published monthly (US-GOV-SSA-303, -304); no distributions."
        ),
        weight=2,
    ),
    _CoverageEntry(
        patterns=[
            r"entire\s*(disability\s*)?process", r"end.to.end", r"from\s*application\s*to",
            r"final\s*decision", r"ultimately", r"after\s*all\s*appeal", r"all\s*(decision\s*)?levels?",
            r"eventually\s*(approved|allowed|denied)", r"overall\s*(approval|allowance)",
        ],
        element="Linked claim history across decision levels",
        description=(
            "Following the same claims from application through reconsideration and hearing, "
            "needed for final approval rates and end-to-end waiting times"
        ),
        dataset_ids=[
            "ssa-state-agency-workload-data",
            "ssa-alj-disposition-data",
            "ssa-initial-disability-processing-time",
            "ssa-reconsideration-processing-time",
            "ssa-hearing-wait-time",
        ],
        coverage_quality="Proxy",
        rationale=(
            "Each decision level publishes its own counts and average times for different groups "
            "of claims (US-GOV-SSA-307, -299, -1409, -1768, -304). They cannot be linked to follow "
            "the same claims, so final rates and total waits can only be approximated."
        ),
        weight=2,
    ),
    _CoverageEntry(
        patterns=[r"appointment", r"walk.?in", r"office\s*visit", r"in.?person",
                  r"walk.?in\s*traffic", r"appointment\s*volume", r"visitor"],
        element="Field office appointment and walk-in volume",
        description="Volume of in-person visits and appointments at SSA field offices",
        dataset_ids=["ssa-field-office-visitors", "ssa-field-office-visitor-counts-2016"],
        coverage_quality="Proxy",
        rationale=(
            "Average daily visitors is published (US-GOV-SSA-434), but per-office visitor counts "
            "exist only for FY2016 (US-GOV-SSA-1917), and appointment volumes are not published."
        ),
        weight=2,
    ),
    _CoverageEntry(
        patterns=[r"appointment.*wait", r"wait.*appointment", r"appointment\s*(delay|backlog)"],
        element="Field office appointment wait times",
        description="Time to get a field office appointment, per office and current",
        dataset_ids=["ssa-field-office-appointments-21-days"],
        coverage_quality="Proxy",
        rationale=(
            "Only a discontinued series exists: the share of claims appointments scheduled within "
            "21 days, FY2005–2015 (US-GOV-SSA-431). No current or per-office wait times."
        ),
        weight=2,
    ),
    # ── Geographic analysis ────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"\bstate\b", r"geographic", r"region", r"\bcounty\b", r"\blocal\b", r"\barea\b",
                  r"part\s*of\s*the\s*country", r"across\s*the\s*country"],
        element="Geographic disaggregation of outcomes",
        description="Disability outcomes broken down by state or sub-state geography",
        dataset_ids=[
            "ssa-disability-claim-data",
            "ssa-state-agency-workload-data",
            "ssa-oasdi-beneficiaries-by-state",
            "ssa-ssi-recipients-by-state",
        ],
        coverage_quality="Partial",
        rationale=(
            "Claims and allowances are published by state (US-GOV-SSA-307, -308) and beneficiaries "
            "by state and county (US-GOV-SSA-3378, -3414); claim outcomes stop at state level."
        ),
        weight=1,
    ),
    _CoverageEntry(
        patterns=[r"field\s*office", r"office\s*location", r"access\s*to\s*ssa", r"service\s*desert"],
        element="SSA field office locations and coverage",
        description="Geographic distribution of SSA field offices",
        dataset_ids=["ssa-field-office-locator"],
        coverage_quality="Full",
        rationale=(
            "Locations, phone numbers and hours of every field office are published and updated "
            "quarterly (US-GOV-SSA-1733)."
        ),
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
        dataset_ids=[
            "ssa-field-office-visitor-counts-2016",
            "ssa-field-office-employee-counts-2016",
            "ssa-title2-claim-receipts-by-field-office-2016",
            "ssa-field-office-visitors",
            "ssa-field-office-claims-pending",
            "ssa-field-office-telephone-service",
        ],
        coverage_quality="Proxy",
        rationale=(
            "Per-office staffing, visitor and Title II disability claim receipt counts exist for "
            "FY2016 only (FOIA releases US-GOV-SSA-1917, -1918, -1919). Current series — daily "
            "visitors (US-GOV-SSA-434), claims pending (US-GOV-SSA-435) and phone answer and busy "
            "rates (US-GOV-SSA-1414) — are national totals with no per-office figures."
        ),
        weight=2,
    ),
    # ── Staffing / workload ────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"staffing", r"staff\s*level", r"headcount", r"employee", r"worker\s*at",
                  r"how\s*many.*staff", r"staff.*work\s*at", r"work\s*at.*office",
                  r"staff.*capacity", r"office.*staff"],
        element="SSA office staffing levels",
        description="Number of adjudicators or staff at field or hearing offices",
        dataset_ids=["ssa-field-office-employee-counts-2016"],
        coverage_quality="Proxy",
        rationale=(
            "Field office employee counts were released once, for FY2016 (US-GOV-SSA-1918); no "
            "hearing office staffing data is in the catalog."
        ),
        weight=2,
    ),
    _CoverageEntry(
        patterns=[r"workload", r"case\s*load", r"capacity", r"productivity",
                  r"demand", r"service\s*volume", r"busiest", r"highest.*demand",
                  r"demand.*office", r"office.*demand"],
        element="Office workload and capacity",
        description="Case volume relative to office processing capacity",
        dataset_ids=[
            "ssa-hearing-office-workload",
            "ssa-state-agency-workload-data",
            "ssa-title2-claim-receipts-by-field-office-2016",
        ],
        coverage_quality="Proxy",
        rationale=(
            "Workload volumes are published for hearing offices (US-GOV-SSA-303) and state agencies "
            "(US-GOV-SSA-307), but without staffing or capacity to relate them to. Field office "
            "claim receipts and staffing can be paired only for FY2016 (US-GOV-SSA-1919, -1918)."
        ),
        weight=2,
    ),
    # ── Demographics ───────────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"age\s*group", r"age\s*of\s*applicant", r"older\s*worker", r"young\s*(disabled|applicant)",
                  r"\bby\s*age\b"],
        element="Applicant age distribution",
        description="Age breakdown of disability applicants and recipients",
        dataset_ids=["ssa-di-annual-statistical-report"],
        coverage_quality="Partial",
        rationale=(
            "The SSDI Annual Statistical Report gives demographic statistics on beneficiaries "
            "(US-GOV-SSA-1667); applicant age is not in the claim-level datasets."
        ),
        weight=1,
    ),
    _CoverageEntry(
        patterns=[r"\bsex\b", r"\bgender\b", r"\bmen\b", r"\bwomen\b", r"\bmale\b", r"\bfemale\b"],
        element="Gender disaggregation",
        description="Disability outcomes broken down by gender",
        dataset_ids=["ssa-di-annual-statistical-report"],
        coverage_quality="Partial",
        rationale=(
            "Beneficiary demographics are in the SSDI Annual Statistical Report (US-GOV-SSA-1667); "
            "no claim-level dataset is described with a sex breakdown."
        ),
        weight=1,
    ),
    _CoverageEntry(
        patterns=[r"\brace\b", r"ethnic", r"racial", r"minority", r"hispanic", r"\bblack\b", r"\bwhite\b"],
        element="Race and ethnicity data",
        description="Disability application, award, and denial rates by race/ethnicity",
        dataset_ids=[],
        coverage_quality="None",
        rationale="No SSA dataset on Data.gov reports race or ethnicity (see search evidence).",
        weight=2,
    ),
    _CoverageEntry(
        patterns=[r"income", r"poverty", r"low.income", r"economic", r"socioeconomic",
                  r"adequa", r"cost\s*of\s*living", r"living\s*cost", r"afford", r"basic\s*need"],
        element="Income and economic status of applicants and recipients",
        description=(
            "Income, assets and living costs of applicants and recipients, needed to judge "
            "program access and benefit adequacy"
        ),
        dataset_ids=["ssa-nscf"],
        coverage_quality="Proxy",
        rationale=(
            "The only source is a one-time 2001–2002 survey of SSI children and families, including "
            "applicants (US-GOV-SSA-328). No adult or current data on applicant or recipient income."
        ),
        weight=2,
    ),
    # ── Impairments ────────────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"impairment", r"diagnos", r"condition", r"disease", r"mental\s*(health|disorder)",
                  r"musculoskeletal", r"disability\s*type"],
        element="Impairment/diagnosis categories",
        description="Distribution of disabilities by medical category",
        dataset_ids=["ssa-di-annual-statistical-report"],
        coverage_quality="Partial",
        rationale=(
            "Beneficiary statistics are in the SSDI Annual Statistical Report (US-GOV-SSA-1667); "
            "no claim-level dataset is described with diagnosis categories."
        ),
        weight=1,
    ),
    # ── Program outcomes ───────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"allowance", r"approval", r"\bapproved\b", r"\ballowed\b", r"award\s*rate",
                  r"denial\s*rate", r"favorable"],
        element="Disability program allowance rates",
        description="Percentage of applications approved at each decision level",
        dataset_ids=["ssa-disability-claim-data", "ssa-state-agency-workload-data", "ssa-alj-disposition-data"],
        coverage_quality="Partial",
        rationale=(
            "Allowances are published by state for initial and reconsideration decisions "
            "(US-GOV-SSA-307, -308) and by judge and hearing office for hearings (US-GOV-SSA-299); "
            "the levels are not linked and nothing goes below state level."
        ),
        weight=2,
    ),
    _CoverageEntry(
        patterns=[r"denial\s*reason", r"reason.*(denied|denial)", r"why.*(denied|rejected)",
                  r"(denied|denial).*because", r"technical\s*denial", r"basis\s*for\s*denial"],
        element="Reasons for claim denials",
        description="Why claims are denied (medical vs. technical reasons, by category)",
        dataset_ids=[],
        coverage_quality="None",
        rationale="No SSA dataset on Data.gov reports denial reasons (see search evidence).",
        weight=2,
    ),
    _CoverageEntry(
        patterns=[r"application\s*(volume|count|number|trend)", r"applicant", r"\bfiled\b",
                  r"how\s*many.*appl"],
        element="Application volumes",
        description="Number of disability applications submitted over time",
        dataset_ids=["ssa-disability-claim-data", "ssa-state-agency-workload-data"],
        coverage_quality="Full",
        rationale=(
            "Initial claim receipts are published by state, monthly from October 2000 "
            "(US-GOV-SSA-307) and by fiscal year (US-GOV-SSA-308)."
        ),
        weight=1,
    ),
    _CoverageEntry(
        patterns=[r"benefit\s*(amount|level|adequacy)", r"monthly\s*payment", r"average\s*benefit",
                  r"payment\s*amount"],
        element="Benefit amounts by geography and demographics",
        description="Average disability benefit payments",
        dataset_ids=["ssa-oasdi-beneficiaries-by-state", "ssa-di-annual-statistical-report"],
        coverage_quality="Partial",
        rationale=(
            "Benefit statistics are in the state/county and annual SSDI reports (US-GOV-SSA-3378, "
            "-1667); which amount breakdowns they include has not been checked against the tables."
        ),
        weight=1,
    ),
    _CoverageEntry(
        patterns=[r"beneficiar(y|ies)", r"recipient", r"enrolled", r"on\s*(ssdi|ssi)\b"],
        element="Beneficiary/recipient counts",
        description="Number of people currently receiving disability benefits",
        dataset_ids=["ssa-oasdi-beneficiaries-by-state", "ssa-ssi-recipients-by-state"],
        coverage_quality="Full",
        rationale=(
            "Beneficiary and recipient counts are published annually by state and county "
            "(US-GOV-SSA-3378, -3414)."
        ),
        weight=1,
    ),
    # ── Appeals ────────────────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"appeal", r"reconsider", r"hearing", r"\balj\b", r"administrative\s*law"],
        element="Appeals and hearing outcomes",
        description="Results and processing metrics for disability appeal hearings",
        dataset_ids=[
            "ssa-alj-disposition-data",
            "ssa-hearing-office-workload",
            "ssa-hearing-wait-time",
            "ssa-state-agency-workload-data",
        ],
        coverage_quality="Partial",
        rationale=(
            "Hearing outcomes by judge and office (US-GOV-SSA-299), hearing workloads and waits "
            "(US-GOV-SSA-303, -304) and reconsideration outcomes by state (US-GOV-SSA-307) are "
            "published; Appeals Council and court outcomes are not in the catalog."
        ),
        weight=1,
    ),
    # ── Employment / return to work ────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"ticket\s*to\s*work", r"work\s*incentive", r"\bsga\b", r"trial\s*work",
                  r"employment\s*network"],
        element="Work incentive program participation",
        description="Participation in SSA work incentive programs such as Ticket to Work",
        dataset_ids=["ssa-ticket-to-work-fy11-17", "ssa-national-beneficiary-survey", "ssa-red-book"],
        coverage_quality="Partial",
        rationale=(
            "Ticket assignments were released for FY2011–2017 only (US-GOV-SSA-1915); survey "
            "statistics on program participation exist for 2015 and 2019 (US-GOV-SSA-3379)."
        ),
        weight=1,
    ),
    _CoverageEntry(
        patterns=[r"return\s*to\s*work", r"back\s*to\s*work", r"employment\s*outcome",
                  r"(work|working|employed)\s*after", r"leave\s*the\s*rolls",
                  r"stop.*benefit.*work", r"\bemployment\b"],
        element="Return-to-work outcomes",
        description="How many beneficiaries work, earn above thresholds, or leave benefits because of work",
        dataset_ids=["ssa-di-ssi-participants-employment-2015", "ssa-national-beneficiary-survey"],
        coverage_quality="Proxy",
        rationale=(
            "Only one-time descriptive sources exist: a 2015 chartbook on work activity before and "
            "after award (US-GOV-SSA-2278) and survey statistics for 2015 and 2019 "
            "(US-GOV-SSA-3379). No ongoing outcome series."
        ),
        weight=2,
    ),
    # ── Performance metrics ────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"performance", r"target", r"\bgoal", r"accuracy", r"customer\s*satisfaction"],
        element="Agency performance metrics",
        description="SSA operational performance against official targets",
        dataset_ids=[
            "ssa-initial-disability-processing-time",
            "ssa-dds-accuracy",
            "ssa-reconsideration-processing-time",
            "ssa-hearing-wait-time",
        ],
        coverage_quality="Partial",
        rationale=(
            "Processing times (US-GOV-SSA-1409, -1768, -304) and DDS decision accuracy "
            "(US-GOV-SSA-344) are published; performance targets are not in the catalog."
        ),
        weight=1,
    ),
    # ── SSI-specific ───────────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"\bssi\b", r"supplemental\s*security\s*income"],
        element="SSI program data",
        description="Supplemental Security Income recipient and payment data",
        dataset_ids=["ssa-ssi-recipients-by-state"],
        coverage_quality="Partial",
        rationale=(
            "Recipients, federal payments and state supplementation are published annually by "
            "state and county (US-GOV-SSA-3414); no monthly or recipient-level detail."
        ),
        weight=1,
    ),
    # ── SSDI-specific ──────────────────────────────────────────────────────────
    _CoverageEntry(
        patterns=[r"\bssdi\b", r"disability\s*insurance", r"title\s*ii"],
        element="SSDI program data",
        description="Social Security Disability Insurance beneficiary data",
        dataset_ids=["ssa-oasdi-beneficiaries-by-state", "ssa-di-annual-statistical-report"],
        coverage_quality="Partial",
        rationale=(
            "Beneficiaries are published by state and county (US-GOV-SSA-3378) and in the annual "
            "SSDI report (US-GOV-SSA-1667); both are annual."
        ),
        weight=1,
    ),
    # ── Accessibility / geographic equity ─────────────────────────────────────
    _CoverageEntry(
        patterns=[
            r"rural", r"urban", r"geographic\s*equit", r"regional\s*dispar",
            r"underserved", r"service\s*gap", r"service\s*desert", r"county\s*coverage",
            r"office\s*coverage", r"less\s*access", r"access.*rural", r"rural.*access",
            r"sparse", r"relative\s*to\s*(the\s*)?(disab|population|beneficiar)",
            r"office.*per\s*(capita|beneficiar|person)",
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
        rationale=(
            "Office locations (US-GOV-SSA-1733) can be joined to county beneficiary counts "
            "(US-GOV-SSA-3378, -3414), but there are no service areas, travel times or "
            "per-office demand to measure access directly."
        ),
        weight=2,
    ),
    _CoverageEntry(
        patterns=[
            r"travel\s*distance", r"distance\s*to\s*(office|ssa)", r"nearest\s*office",
            r"miles?\s*(to|from)\s*office", r"drive\s*time", r"travel\s*time",
        ],
        element="Travel distance to nearest SSA field office",
        description="Distance or travel time between claimant location and nearest field office",
        dataset_ids=[],
        coverage_quality="None",
        rationale="No SSA dataset on Data.gov reports travel distance or time (see search evidence).",
        weight=2,
    ),
    _CoverageEntry(
        patterns=[
            r"service\s*area\s*boundar", r"office\s*boundar", r"coverage\s*area",
            r"catchment\s*area", r"service\s*area",
        ],
        element="Field office service area boundaries",
        description="Defined geographic service areas for each SSA field office",
        dataset_ids=[],
        coverage_quality="None",
        rationale="No SSA dataset on Data.gov defines field office service areas (see search evidence).",
        weight=1,
    ),
    _CoverageEntry(
        patterns=[
            r"accessib(ility|le)\s*(accommodation|feature|service)",
            r"ada\s*compliance", r"disability\s*access(ib)?", r"physical\s*access",
            r"wheelchair", r"interpreter", r"language\s*service",
        ],
        element="Accessibility accommodations at field offices",
        description="ADA compliance status, language services, and physical accessibility features",
        dataset_ids=[],
        coverage_quality="None",
        rationale=(
            "No SSA dataset on Data.gov describes accessibility or accommodations at field offices; "
            "only national interpreter call counts exist (see search evidence)."
        ),
        weight=1,
    ),
    _CoverageEntry(
        patterns=[
            r"disability.*application.*county", r"county.*application",
            r"application.*geographic", r"geographic.*application",
        ],
        element="Disability application counts by county",
        description="Number of disability applications disaggregated to county level",
        dataset_ids=["ssa-disability-claim-data", "ssa-state-agency-workload-data"],
        coverage_quality="Proxy",
        rationale=(
            "Applications are published by state only (US-GOV-SSA-307, -308), a proxy for "
            "county detail."
        ),
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
    exclude_patterns: list[str] = field(default_factory=list)
    premise_note: str = ""          # shown when the question rests on a common misconception


def _intent_matches(entry: _IntentEntry, variants: tuple[str, str]) -> bool:
    return _matches(entry.patterns, variants) and not _matches(entry.exclude_patterns, variants)


_INTENT_KB: list[_IntentEntry] = [
    # First, so "Which field offices have the highest backlog?" is read as a question
    # about decision times rather than service demand.
    _IntentEntry(
        patterns=_OFFICE_DECISION_TIME_PATTERNS,
        exclude_patterns=_OFFICE_DECISION_TIME_EXCLUDES,
        category="Performance",
        primary_intent_template="Rank SSA offices by how long disability decisions take",
        required_data_types=[
            "Decision times by the office that decides the claim",
            "Pending claims by office",
            "Mapping of field offices to the offices that decide their claims",
        ],
        scope="Field office level",
        seed_elements=[
            "Disability decision times by field office or DDS",
            "Disability claim processing times",
        ],
        context_dataset_ids=[
            "ssa-hearing-office-workload",
            "ssa-hearing-wait-time",
            "ssa-state-agency-workload-data",
        ],
        premise_note=(
            "Field offices take disability applications and check non-medical eligibility, "
            "but they do not make the medical decision. Initial and reconsideration decisions "
            "are made by each state's Disability Determination Services (DDS), and appeals by "
            "hearing offices, so decision times belong to those offices."
        ),
    ),
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
            "ssa-hearing-office-workload",
        ],
    ),
    _IntentEntry(
        # "What should SSA publish?" — a data publication roadmap question.
        # Distinct from assessing current coverage: the user wants a prioritised
        # list of new datasets/metrics, not a scorecard of what already exists.
        patterns=[
            r"maximize.*understanding", r"what.*should.*publish",
            r"additional.*dataset", r"metrics.*should", r"publish.*first",
            r"what.*data.*should", r"should.*publish.*first", r"prioriti[sz]e.*publish",
            r"what.*new.*dataset", r"data.*gap.*publish", r"publish.*to.*improve",
        ],
        category="Policy",
        primary_intent_template=(
            "Identify which new SSA datasets or metrics, if published, would most "
            "improve public understanding of disability service accessibility"
        ),
        required_data_types=[
            "Field office appointment wait times",
            "Field office visit volumes",
            "Staffing levels by office",
            "Geographic beneficiary-to-office ratios",
        ],
        scope="National, all field offices and hearing offices",
        seed_elements=[
            "Field office operational metrics (staffing, volume, wait times)",
            "Field office appointment and walk-in volume",
            "SSA office staffing levels",
            "Travel distance to nearest SSA field office",
        ],
        context_dataset_ids=[
            "ssa-field-office-locator",
            "ssa-oasdi-beneficiaries-by-state",
            "ssa-ssi-recipients-by-state",
            "ssa-hearing-office-workload",
            "ssa-disability-claim-data",
        ],
    ),
    _IntentEntry(
        # "Assess current coverage" — a scorecard question about what SSA has now.
        # Distinct from the publication roadmap: the user wants to know how well
        # existing datasets support answering an accessibility question.
        patterns=[
            r"assess.*ability", r"ability.*dataset", r"current.*dataset.*support",
            r"support.*understanding", r"how\s*well.*dataset", r"dataset.*support.*understanding",
            r"access(ib|ibility)",
        ],
        category="Access",
        primary_intent_template=(
            "Assess how well current SSA public datasets support public understanding "
            "of disability service accessibility"
        ),
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
            "ssa-hearing-office-workload",
            "ssa-disability-claim-data",
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
            "ssa-disability-claim-data",
            "ssa-state-agency-workload-data",
            "ssa-di-annual-statistical-report",
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
            "ssa-hearing-office-workload",
            "ssa-hearing-wait-time",
            "ssa-state-agency-workload-data",
        ],
    ),
    _IntentEntry(
        patterns=[r"income", r"poverty", r"benefit.*adequacy", r"low.?income"],
        category="Finance",
        primary_intent_template="Evaluate SSI benefit adequacy relative to recipient income and poverty levels",
        required_data_types=["Recipient income data", "Benefit payment amounts", "Local cost-of-living indicators"],
        scope="National and state level",
        seed_elements=["Income and economic status of applicants and recipients", "Benefit amounts by geography and demographics"],
        context_dataset_ids=[
            "ssa-ssi-recipients-by-state",
            "ssa-oasdi-beneficiaries-by-state",
        ],
    ),
    _IntentEntry(
        patterns=[r"return\s*to\s*work", r"employment.*disab", r"work\s*incentive", r"ticket\s*to\s*work"],
        category="Outcomes",
        primary_intent_template="Measure outcomes of SSA work incentive programs for disability beneficiaries",
        required_data_types=["Ticket to Work participation", "Trial Work Period outcomes", "Return-to-work rates"],
        scope="National",
        seed_elements=["Work incentive program participation", "Return-to-work outcomes"],
        context_dataset_ids=[
            "ssa-red-book",
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
            "ssa-disability-claim-data",
            "ssa-hearing-office-workload",
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
            "ssa-disability-claim-data",
            "ssa-hearing-office-workload",
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
        for el, w in zip(elements, weights, strict=True)
    )
    return round((weighted_sum / total_weight) * 100, 1)


# Rubric rule: a question cannot be rated higher than its best *critical* element
# allows. If every critical element is only Proxy/None, the answer is at most
# Limited; if the best critical element is Partial, at most Partial. Supporting
# elements that happen to be fully covered cannot lift the rating past this.
_CRITICAL_CAP: dict[str, tuple[float, str]] = {
    "None": (39.0, "Limited"),
    "Proxy": (39.0, "Limited"),
    "Partial": (74.0, "Partial"),
}
_QUALITY_ORDER = ["None", "Proxy", "Partial", "Full"]


def _apply_critical_cap(
    score: float, elements: list[InformationElement], weights: list[int]
) -> tuple[float, str]:
    """
    Return (score, note) after applying the critical-element cap.

    The note explains the capped rating in plain language for the report's
    "How Answer Coverage Was Rated" section; it is empty when no cap applies.
    """
    critical = [el for el, w in zip(elements, weights, strict=True) if w == 2]
    if not critical:
        return score, ""
    best = max((el.coverage_quality for el in critical), key=_QUALITY_ORDER.index)
    cap = _CRITICAL_CAP.get(best)
    if cap is None or score <= cap[0]:
        return score, ""
    return cap[0], _cap_explanation(critical, best, cap[1], score_to_coverage_rating(score).value)


_AVAILABILITY_PHRASE: dict[str, str] = {
    "None": "not published at all (rated None)",
    "Proxy": "only available indirectly (rated Proxy)",
    "Partial": "only partly available (rated Partial)",
}
_COUNT_WORDS = {1: "one thing", 2: "two things", 3: "three things"}


def _lower_first(text: str) -> str:
    """Lowercase the first letter for use mid-sentence, leaving acronyms like 'SSA' alone."""
    if len(text) > 1 and text[0].isupper() and text[1].islower():
        return text[0].lower() + text[1:]
    return text


def _cap_explanation(
    critical: list[InformationElement], best: str, capped: str, uncapped: str
) -> str:
    """Plain-language reason a question's rating was capped, for the report."""
    names = [_lower_first(el.element) for el in critical]
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    count = _COUNT_WORDS.get(len(names), f"{len(names)} things")
    verb = "is" if len(names) == 1 else "are"
    # "at best" only when the critical items are not all rated the same.
    hedge = "" if all(el.coverage_quality == best for el in critical) else "at best "
    return (
        f"The {count} this question needs most, {listed}, {verb} {hedge}"
        f"{_AVAILABILITY_PHRASE[best]}. The rating can't be higher than that, so it is "
        f"{capped}. The other information is better covered and would bring the average "
        f"up to {uncapped}, but it can't make up for what's missing."
    )


# ── Question normalisation and scope ───────────────────────────────────────────

_SINGULAR_EXCEPTIONS = {
    "ssi", "ssdi", "status", "access", "process", "business", "analysis", "basis",
    "less", "across", "address", "class", "gross", "progress", "this", "his", "has",
    "was", "does", "is", "its", "yes", "us", "as", "always", "perhaps", "whereas",
}


def _singular(word: str) -> str:
    if len(word) <= 3 or word in _SINGULAR_EXCEPTIONS or word.endswith(("ss", "us", "is")):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "xes", "sses")):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def normalise_question(question: str) -> tuple[str, str]:
    """Return the question lower-cased, and the same text with plurals singularised."""
    lowered = " ".join(question.lower().split())
    return lowered, re.sub(r"[a-z]+", lambda m: _singular(m.group(0)), lowered)


def _matches(patterns: list[str], variants: tuple[str, str]) -> bool:
    return any(re.search(p, v) for p in patterns for v in variants)


def _entry_matches(entry: _CoverageEntry, variants: tuple[str, str]) -> bool:
    return _matches(entry.patterns, variants) and not _matches(entry.exclude_patterns, variants)


# A named state ("in Ohio") asks for state-level detail just as "by state" does.
# Used for scope only: a state name alone does not make a question about SSA data.
_US_STATES = (
    "alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|"
    "georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|"
    "massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|"
    "new hampshire|new jersey|new mexico|new york|north carolina|north dakota|ohio|oklahoma|"
    "oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|utah|"
    "vermont|virginia|washington|west virginia|wisconsin|wyoming|district of columbia|puerto rico"
)

_SCOPE_RULES: list[tuple[str, str]] = [
    (r"hearing\s*office|\balj\b|\bjudge", "Hearing office level"),
    (r"field\s*office", "Field office level"),
    (r"\bzip\b|census\s*tract", "ZIP / sub-county level"),
    (r"\bcounty\b|\blocal\b|\brural\b|\burban\b|\bcommunity\b", "County level"),
    (rf"\bstate\b|\b(?:{_US_STATES})\b", "State level"),
    (r"\bregion", "Regional level"),
]


def detect_scope(variants: tuple[str, str]) -> str:
    """Geographic or organisational scope named in the question, if any."""
    return ", ".join(label for pattern, label in _SCOPE_RULES if _matches([pattern], variants))


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
        variants = normalise_question(question)
        for entry in _INTENT_KB:
            if _intent_matches(entry, variants):
                return IntentAnalysis(
                    primary_intent=entry.primary_intent_template,
                    intent_category=entry.category,
                    required_data_types=entry.required_data_types,
                    # The scope the question names wins over the intent's default.
                    scope=detect_scope(variants) or entry.scope,
                    premise_note=entry.premise_note,
                )
        return None

    def _get_seed_entries(self, question: str) -> list[tuple[_CoverageEntry, int]]:
        """
        Return KB entries that the intent KB says are always required for this question,
        regardless of whether the keywords appear explicitly.
        """
        variants = normalise_question(question)
        seeded: list[tuple[_CoverageEntry, int]] = []
        for intent_entry in _INTENT_KB:
            if _intent_matches(intent_entry, variants):
                for element_name in intent_entry.seed_elements:
                    kb_entry = self._kb_by_element.get(element_name)
                    if kb_entry:
                        seeded.append((kb_entry, kb_entry.weight))
        return seeded

    # ── Step 2: Keyword matching ───────────────────────────────────────────────

    def _match_entries(self, question: str) -> list[tuple[_CoverageEntry, int]]:
        """Return (entry, weight) pairs where the entry patterns match the question."""
        variants = normalise_question(question)
        return [(entry, entry.weight) for entry in self._kb if _entry_matches(entry, variants)]

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

    @staticmethod
    def _apply_refinements(
        entries: list[tuple[_CoverageEntry, int]],
    ) -> list[tuple[_CoverageEntry, int]]:
        """Demote broader elements to supporting when a more specific one is included."""
        refined = {name for entry, _ in entries for name in entry.refines}
        return [(entry, 1 if entry.element in refined else w) for entry, w in entries]

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
                rationale=entry.rationale,
            )
            for entry, _ in matched
        ]

    # ── Step 5: Gap analysis ───────────────────────────────────────────────────

    def _build_gap_analysis(
        self, elements: list[InformationElement], weights: list[int]
    ) -> GapAnalysis:
        # "Critical" means weight 2 (the question cannot be answered without it),
        # the same meaning the framework and the cap use. Whether an element is
        # published is a separate question: an unpublished element can be supporting.
        critical = {e.element for e, w in zip(elements, weights, strict=True) if w == 2}
        not_published = [
            e.element for e in elements
            if not e.available and e.coverage_quality == "None"
        ]
        partly_available = [
            e.element for e in elements
            if e.coverage_quality in ("Partial", "Proxy")
        ]
        critical_missing = [g for g in not_published if g in critical]
        supporting_missing = [g for g in not_published if g not in critical]
        proxy_critical = [
            e.element for e, w in zip(elements, weights, strict=True)
            if w == 2 and e.coverage_quality == "Proxy"
        ]
        # The rating is capped by the BEST critical element (see _apply_critical_cap),
        # so the impact statement follows the same rule.
        usable_critical = [
            e.element for e, w in zip(elements, weights, strict=True)
            if w == 2 and e.coverage_quality in ("Full", "Partial")
        ]

        root_causes: list[str] = []
        if not_published:
            root_causes.append(
                "Some information is not in any SSA dataset on Data.gov (see the search "
                "evidence under each item that is not published)"
            )
        if partly_available:
            root_causes.append(
                "Several relevant datasets exist but lack demographic disaggregation, "
                "sub-national detail, or timely update frequency"
            )

        also_missing = (
            f" Supporting information is also not published: {', '.join(supporting_missing[:3])}."
            if supporting_missing else ""
        )
        if critical_missing and not usable_critical:
            impact = (
                "The question cannot be reliably answered from public data. Information it "
                f"depends on most is not published: {', '.join(critical_missing[:3])}."
                + also_missing
            )
        elif critical_missing:
            impact = (
                "The question can only be partly answered from public data. Some information "
                f"it depends on most is not published: {', '.join(critical_missing[:3])}. "
                f"Other critical information is at least partly available "
                f"({', '.join(usable_critical[:3])}), so part of the answer is possible."
                + also_missing
            )
        elif proxy_critical:
            impact = (
                "The question can only be partly answered from public data. Information it "
                "depends on most is only available indirectly (one-time, historical or "
                f"discontinued data): {', '.join(proxy_critical[:3])}." + also_missing
            )
        elif supporting_missing:
            impact = (
                "The question can be partly answered from public data. Supporting "
                f"information is not published: {', '.join(supporting_missing[:3])}. "
                "Without it the answer will be incomplete."
            )
        else:
            impact = (
                "The question can be substantially addressed using existing public data, "
                "though some aspects rely on aggregates rather than granular records."
            )

        return GapAnalysis(
            critical_gaps=not_published,
            partial_gaps=partly_available,
            critical_elements=[e.element for e in elements if e.element in critical],
            root_causes=root_causes,
            impact_on_answer=impact,
            gap_evidence={g: _evidence_note(g) for g in not_published if _evidence_note(g)},
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

        # 4. Merge (intent seeds first, so they appear at the top), then let specific
        #    elements demote the broader ones they refine.
        all_matched = self._apply_refinements(self._merge_entries(seeded, matched))

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

        # No intent category matched, but the question maps to known information
        # elements: describe it generically so the scope and data needs are shown.
        if intent is None:
            intent = IntentAnalysis(
                primary_intent="Determine whether SSA public data can answer this question",
                intent_category="General",
                required_data_types=[el.element for el in elements],
                scope=detect_scope(normalise_question(question)) or "National",
            )

        score = _compute_weighted_score(elements, weights)
        score, rating_note = _apply_critical_cap(score, elements, weights)
        rating = score_to_coverage_rating(score)

        # 6. Available vs. missing
        missing_information: list[str] = []
        all_dataset_ids: set[str] = set()

        for el, w in zip(elements, weights, strict=True):
            if el.available:
                all_dataset_ids.update(el.dataset_ids)
            else:
                missing_information.append(el.element)
            # A critical element with only indirect data is still missing for the
            # purpose of answering the question, even though some data exists.
            if el.available and w == 2 and el.coverage_quality == "Proxy":
                missing_information.append(
                    f"{el.element} (only indirect, one-time or discontinued data)"
                )

        # Collect context dataset IDs from matched intent entries.
        # These are catalog datasets that provide domain context for the question
        # even when they don't directly supply the missing metrics.
        context_dataset_ids: set[str] = set()
        variants = normalise_question(question)
        for intent_entry in _INTENT_KB:
            if _intent_matches(intent_entry, variants):
                context_dataset_ids.update(intent_entry.context_dataset_ids)

        # Merge: direct dataset IDs (from matched elements) take precedence;
        # context IDs fill in when no element-level datasets were found.
        display_dataset_ids = all_dataset_ids | context_dataset_ids

        # Build available_data as short dataset names, and available_data_with_urls
        # as [{name, url}] dicts for tabular rendering in the report.
        from ..services.dataset_catalog_service import (
            get_catalog_service,  # local import avoids circular
        )
        available_data_with_sources: list[str] = []
        available_data_with_urls: list[dict[str, str]] = []
        context_note: str = ""
        try:
            catalog = get_catalog_service()
            all_ds = catalog.list_datasets(include_live=False)
            id_to_name = {ds.dataset_id: ds.name for ds in all_ds}
            id_to_url = {ds.dataset_id: ds.url for ds in all_ds}
            id_to_provenance = {ds.dataset_id: ds.provenance for ds in all_ds}
            seen: set[str] = set()
            for did in sorted(display_dataset_ids):
                name = id_to_name.get(did, did)
                if name not in seen:
                    available_data_with_sources.append(name)
                    available_data_with_urls.append({
                        "name": name,
                        "url": id_to_url.get(did, ""),
                        "provenance": id_to_provenance.get(did, ""),
                    })
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
        gap_analysis = self._build_gap_analysis(elements, weights)
        structured_recs: list[Recommendation] = _recommendation_service.for_gaps(
            elements, weights=weights
        )
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
        if intent_category == "policy":
            potential_impact = (
                "Publishing the recommended datasets and metrics would give the public, "
                "researchers, and policymakers the evidence base they currently lack.\n\n"
                "The highest-priority publications to maximise public understanding are:\n"
                "- Monthly field office appointment and walk-in volumes — reveals demand patterns\n"
                "- Average appointment wait times by field office — directly measures service access\n"
                "- FTE staffing levels by field office — links capacity to demand\n"
                "- Travel distance from beneficiary ZIP codes to nearest office — quantifies geographic barriers\n\n"
                "Taken together, these four datasets would transform public understanding of SSA "
                "disability service accessibility. Stakeholders could identify which communities "
                "face the longest waits and furthest travel, evaluate whether staffing matches "
                "local demand, and build an evidence-based case for resource allocation and "
                "office expansion."
            )
        elif intent_category in ("accessibility", "geographic equity", "access"):
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
            rating_note=rating_note,
        )


# Singleton
_engine: AnswerCoverageEngine | None = None


def get_answer_coverage_engine() -> AnswerCoverageEngine:
    """Return the singleton AnswerCoverageEngine."""
    global _engine
    if _engine is None:
        _engine = AnswerCoverageEngine()
    return _engine
