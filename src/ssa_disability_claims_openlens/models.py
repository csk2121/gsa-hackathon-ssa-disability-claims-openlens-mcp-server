"""
Pydantic v2 models for SSA Disability Claims OpenLens.

All inputs and outputs for MCP tools are strongly typed here.
Domain models are grouped logically:
  - Dataset catalog models
  - Analysis models
  - Answer Coverage models
  - Recommendation models
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# ── Enumerations ───────────────────────────────────────────────────────────────


class DataSource(StrEnum):
    """Known data source adapters."""

    SSA_OPEN_DATA = "SSA Open Data Portal"
    DATA_GOV = "Data.gov"
    STATIC_CATALOG = "Static Catalog"


class UpdateFrequency(StrEnum):
    """How often a dataset is updated."""

    REAL_TIME = "Real-time"
    DAILY = "Daily"
    WEEKLY = "Weekly"
    MONTHLY = "Monthly"
    QUARTERLY = "Quarterly"
    ANNUALLY = "Annually"
    IRREGULAR = "Irregular"
    UNKNOWN = "Unknown"


class CoverageRating(StrEnum):
    """
    Qualitative rating of Answer Coverage.

    Unsupported — No relevant datasets found; engine could not map the question
                  to any known SSA domain.
    Limited     — Relevant datasets found, but major gaps prevent a complete
                  answer. The engine has enough domain context to identify what
                  is missing and recommend what should be published.
    Partial     — Relevant datasets support part of the analysis; some critical
                  information is unavailable or only proxy-covered.
    High        — Most information is available; minor gaps remain.
    Complete    — Directly answerable from existing public datasets.
    """

    COMPLETE = "Complete"        # 90–100
    HIGH = "High"                # 75–89
    PARTIAL = "Partial"          # 40–74
    LIMITED = "Limited"          # 15–39
    UNSUPPORTED = "Unsupported"  # 0–14  AND no domain match / no intent found


class RecommendationPriority(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class FreshnessStatus(StrEnum):
    CURRENT = "Current"
    AGING = "Aging"
    STALE = "Stale"
    UNKNOWN = "Unknown"


# ── Dataset catalog models ─────────────────────────────────────────────────────


class DatasetSummary(BaseModel):
    """Lightweight dataset summary returned by discovery."""

    dataset_id: str = Field(description="Unique slug identifying the dataset")
    name: str = Field(description="Human-readable dataset name")
    description: str = Field(description="Plain-English description of dataset contents")
    source: DataSource = Field(description="Origin portal for this dataset")
    update_frequency: UpdateFrequency = Field(description="How often the dataset is refreshed")
    url: str = Field(
        description=(
            "Landing page URL taken from the dataset's official metadata record. "
            "Empty when no verified URL exists — never a constructed or guessed link."
        )
    )
    tags: list[str] = Field(default_factory=list, description="Subject-matter tags")
    last_updated: date | None = Field(default=None, description="Date of most recent update")
    provenance: str = Field(
        default="",
        description="Where the name, URL, dates and frequency came from (e.g. a Data.gov record id)",
    )
    source_record_url: str = Field(
        default="", description="Link to the official metadata record (e.g. the Data.gov dataset page)"
    )


class DatasetField(BaseModel):
    """Describes a single field/column within a dataset."""

    name: str
    data_type: str
    description: str
    example_values: list[str] = Field(default_factory=list)
    is_key_field: bool = False


class DatasetDetail(BaseModel):
    """Full dataset explanation returned by explain_dataset."""

    dataset_id: str
    name: str
    purpose: str = Field(description="Why this dataset exists and who it serves")
    major_fields: list[DatasetField] = Field(description="Key fields in the dataset")
    use_cases: list[str] = Field(description="Practical analysis use cases")
    limitations: list[str] = Field(description="Known gaps, caveats, and restrictions")
    source: DataSource
    update_frequency: UpdateFrequency
    url: str
    last_updated: date | None = None
    geographic_coverage: str = Field(
        default="National", description="Geographic scope of the data"
    )
    temporal_coverage: str = Field(
        default="Unknown", description="Earliest to latest date range covered"
    )
    provenance: str = Field(
        default="",
        description="Where the name, URL, dates and frequency came from (e.g. a Data.gov record id)",
    )
    source_record_url: str = Field(
        default="", description="Link to the official metadata record (e.g. the Data.gov dataset page)"
    )
    download_urls: list[str] = Field(
        default_factory=list, description="Download links listed in the official metadata record"
    )
    data_dictionary_url: str = Field(
        default="", description="Data dictionary link from the official metadata record, if any"
    )
    fields_verified: bool = Field(
        default=False,
        description=(
            "True only when major_fields were checked against the publisher's data dictionary. "
            "False means the field list is a summary of the metadata description."
        ),
    )


# ── Comparison models ──────────────────────────────────────────────────────────


class SharedDimension(BaseModel):
    """A dimension (field or concept) shared across multiple datasets."""

    dimension: str
    present_in: list[str] = Field(description="Dataset IDs where this dimension appears")
    notes: str = ""


class MissingRelationship(BaseModel):
    """An analytic relationship that cannot be formed due to missing join keys."""

    description: str
    datasets_involved: list[str]
    missing_field: str
    impact: str


class IntegrationOpportunity(BaseModel):
    """Potential value that could be unlocked by joining two or more datasets."""

    title: str
    datasets: list[str]
    description: str
    expected_benefit: str


class DatasetComparison(BaseModel):
    """Result of comparing multiple datasets side-by-side."""

    datasets_compared: list[str]
    shared_dimensions: list[SharedDimension]
    missing_relationships: list[MissingRelationship]
    integration_opportunities: list[IntegrationOpportunity]
    summary: str


# ── Completeness models ────────────────────────────────────────────────────────


class CoverageAxis(BaseModel):
    """Coverage score along a single dimension (geographic, temporal, etc.)."""

    axis: str
    score: float = Field(ge=0.0, le=100.0)
    details: str
    gaps: list[str] = Field(default_factory=list)


class CompletenessAnalysis(BaseModel):
    """Dataset completeness evaluation result."""

    dataset_id: str
    dataset_name: str
    geographic_coverage: CoverageAxis
    temporal_coverage: CoverageAxis
    operational_coverage: CoverageAxis
    missing_dimensions: list[str]
    completeness_score: float = Field(ge=0.0, le=100.0, description="Overall 0–100 completeness")
    completeness_rating: str
    analyst_notes: str


# ── Freshness models ───────────────────────────────────────────────────────────


class FreshnessAssessment(BaseModel):
    """Catalog Freshness Assessment — evaluates dataset currency based on catalog metadata."""

    dataset_id: str
    dataset_name: str
    last_updated: date | None
    update_frequency: UpdateFrequency
    days_since_update: int | None
    freshness_score: float = Field(ge=0.0, le=100.0)
    freshness_status: FreshnessStatus
    freshness_rationale: str
    staleness_indicators: list[str]
    analyst_notes: str
    assessment_note: str = Field(
        default=(
            "Freshness calculations are based on the dataset metadata currently "
            "maintained within the OpenLens catalog. They reflect the last_updated "
            "date recorded in the catalog, not a live query to the SSA data source."
        ),
        description="Disclaimer clarifying that freshness is measured from catalog metadata, not a live source check.",
    )

    def format_report(self) -> str:
        """
        Return a human-readable Freshness Assessment report.

        Uses the same markdown conventions as AnswerCoverageAssessment.format_report()
        so that the LLM instruction for both tools is identical: copy the report verbatim.
        """
        lines: list[str] = [
            f"## Freshness Assessment — {self.dataset_name}",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| **Dataset ID** | {self.dataset_id} |",
            f"| **Last Updated** | {self.last_updated if self.last_updated else 'Unknown'} |",
            f"| **Update Frequency** | {self.update_frequency.value} |",
            f"| **Days Since Update** | {self.days_since_update if self.days_since_update is not None else 'Unknown'} days |",
            f"| **Freshness Score** | {round(self.freshness_score)} / 100 |",
            f"| **Status** | {self.freshness_status.value} |",
            "",
            "**Freshness Rationale:**",
            "",
            self.freshness_rationale,
            "",
            "**Staleness Indicators:**",
            "",
        ]
        if self.staleness_indicators:
            for indicator in self.staleness_indicators:
                lines.append(f"- {indicator}")
        else:
            lines.append("None")

        lines += [
            "",
            "**Analyst Notes:**",
            "",
            self.analyst_notes,
            "",
            f"> **Note:** {self.assessment_note}",
        ]
        return "\n".join(lines)


# ── Answer Coverage models ─────────────────────────────────────────────────────


class IntentAnalysis(BaseModel):
    """
    Primary intent extracted from the user's question before dataset matching.

    Identifies what the user is fundamentally trying to understand so that
    dataset matching and gap analysis are anchored to the real information need
    rather than raw keyword hits.
    """

    primary_intent: str = Field(description="One-sentence statement of what the user wants to know")
    intent_category: str = Field(
        description=(
            "High-level category: Access | Equity | Outcomes | Performance | "
            "Demographics | Finance | Policy | Unknown"
        )
    )
    required_data_types: list[str] = Field(
        description="The types of data logically required to answer the question"
    )
    scope: str = Field(
        description="Geographic or programmatic scope inferred from the question"
    )
    premise_note: str = Field(
        default="",
        description="Correction shown when the question rests on a common misconception",
    )


class InformationElement(BaseModel):
    """An atomic piece of information required to answer a question."""

    element: str = Field(description="Name of the required information")
    description: str = Field(description="Why this element is needed")
    available: bool = Field(description="Whether any dataset provides this element")
    dataset_ids: list[str] = Field(
        default_factory=list,
        description="Datasets that partially or fully supply this element",
    )
    coverage_quality: str = Field(
        default="None",
        description="Quality of coverage: Full | Partial | Proxy | None",
    )
    rationale: str = Field(
        default="",
        description="Why this element received its rating, citing the datasets' source records",
    )


class GapAnalysis(BaseModel):
    """Structured gap analysis for a question."""

    critical_gaps: list[str] = Field(
        description=(
            "Information not published in any SSA dataset (rated None). The name is kept "
            "for compatibility: whether the question depends on it most is in critical_elements."
        )
    )
    partial_gaps: list[str] = Field(
        description="Information available but incomplete or indirect (rated Partial or Proxy)"
    )
    critical_elements: list[str] = Field(
        default_factory=list,
        description="Elements the question cannot be answered without (weighted double)",
    )
    root_causes: list[str] = Field(
        description="Why the gaps exist (e.g., not collected, not published)"
    )
    impact_on_answer: str = Field(description="How the gaps affect answer quality")
    gap_evidence: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "For each critical gap, how its absence was checked (searches run against "
            "SSA's Data.gov catalog, and when)"
        ),
    )


class Recommendation(BaseModel):
    """
    A single transparency recommendation — the unified model used by both
    evaluate_answer_coverage and recommend_transparency_improvements.

    Every recommendation originates from RecommendationService so both tools
    return identical, deterministic results for the same input.
    """

    title: str = Field(description="Short action title for the recommendation")
    closes_gap: str = Field(description="The missing information element this recommendation addresses")
    also_closes: list[str] = Field(
        default_factory=list,
        description="Other information elements the same publication would also close",
    )
    category: str = Field(
        description=(
            "Recommendation category: Operational Metrics | Demographic Data | "
            "Geographic Detail | Temporal Granularity | Program Outcomes | Access Data | "
            "Performance | Finance"
        )
    )
    justification: str = Field(description="Why publishing this data would improve public understanding")
    priority: RecommendationPriority = Field(description="High | Medium | Low")
    priority_reason: str = Field(
        default="",
        description="Why it has this priority: how much the question depends on the gap it closes",
    )
    affected_datasets: list[str] = Field(
        default_factory=list,
        description="Existing dataset IDs this recommendation would extend or complement",
    )
    expected_impact: str = Field(
        default="",
        description="Expected public benefit once this data is published",
    )


# Keep a backward-compatible alias so any external code using RecommendationItem still works.
RecommendationItem = Recommendation


class AnswerCoverageAssessment(BaseModel):
    """
    Signature output model: measures how well SSA public datasets support
    answering a specific natural language question.
    """

    question: str = Field(description="The original user question")
    intent: IntentAnalysis | None = Field(
        default=None,
        description="Extracted primary intent before dataset matching",
    )
    answer_coverage_score: float = Field(
        ge=0.0, le=100.0,
        description="0–100 score representing dataset support for the question",
    )
    coverage_rating: CoverageRating = Field(
        description="Qualitative label: Complete | High | Partial | Limited | Unsupported"
    )
    required_information_elements: list[InformationElement] = Field(
        description="Information elements needed to answer the question"
    )
    available_data: list[str] = Field(
        description="Datasets and fields that contribute to answering"
    )
    available_data_with_urls: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Available datasets with web links. Each entry has 'name' and 'url' keys. "
            "Used to render the tabular Available Data section in the report."
        ),
    )
    available_data_context_note: str = Field(
        default="",
        description=(
            "Optional note clarifying the role of available datasets when they provide "
            "domain context but do not directly supply the required metrics."
        ),
    )
    missing_information: list[str] = Field(
        description="Information needed but not found in any public dataset"
    )
    gap_analysis: GapAnalysis
    structured_recommendations: list[Recommendation] = Field(
        default_factory=list,
        description=(
            "Unified Recommendation objects from RecommendationService. "
            "Each has title, closes_gap, category, justification, priority, "
            "affected_datasets, and expected_impact."
        ),
    )
    transparency_recommendations: list[str] = Field(
        description="Plain-text recommendation titles (derived from structured_recommendations)"
    )
    potential_impact: str = Field(
        description="Expected public benefit if gaps are closed"
    )
    datasets_consulted: list[str] = Field(
        description="All dataset IDs evaluated during analysis"
    )
    rating_note: str = Field(
        default="",
        description="Explanation when a rubric rule (e.g. the critical-element cap) adjusted the rating",
    )

    @field_validator("answer_coverage_score")
    @classmethod
    def round_score(cls, v: float) -> float:
        return round(v, 1)

    def format_report(self) -> str:
        """
        Return a human-readable OpenLens Assessment report.

        Uses ATX headings (## / ###) throughout — these are unambiguous in every
        markdown renderer and cannot be accidentally merged or dropped by an LLM
        reproducing the text, unlike underline-style headings (--- / ===).
        """
        lines: list[str] = [
            "# SSA Disability Claims OpenLens Assessment",
            "",
            "## Question",
            "",
            self.question,
            "",
        ]

        # Intent block — only shown when intent was successfully extracted
        if self.intent:
            lines += [
                "## Intent",
                "",
                f"**Primary intent**: {self.intent.primary_intent}  ",
                f"**Category**: {self.intent.intent_category}  ",
                f"**Scope**: {self.intent.scope}  ",
                f"**Required data**: {', '.join(self.intent.required_data_types)}",
                "",
            ]
            if self.intent.premise_note:
                lines += [f"**Note on the question**: {self.intent.premise_note}", ""]

        lines += [
            "## Answer Coverage",
            "",
            f"**{self.coverage_rating.value}**",
            "",
            "## Available Data",
            "",
        ]
        if self.available_data_with_urls:
            # Markdown pipe table — renders correctly in any proportional-font renderer
            lines.append("| Sl.# | Data | Web Link | Source Record |")
            lines.append("|------|------|----------|---------------|")
            for idx, entry in enumerate(self.available_data_with_urls, start=1):
                name = entry.get("name", "")
                url = entry.get("url", "") or "_(no verified link)_"
                provenance = entry.get("provenance", "") or "_(unverified)_"
                lines.append(f"| {idx} | {name} | {url} | {provenance} |")
        else:
            display_available = [
                item for item in self.available_data
                if not item.startswith("Source datasets:")
            ]
            for item in display_available:
                lines.append(f"- {item}")

        if self.available_data_context_note:
            lines.append(f"\n{self.available_data_context_note}")

        lines += [
            "",
            "## Missing Information",
            "",
        ]
        for item in self.missing_information:
            lines.append(f"- {item}")

        lines += [
            "",
            "## Gap Analysis",
            "",
        ]
        critical = set(self.gap_analysis.critical_elements)

        def _gap_line(g: str) -> str:
            return f"- {g} (critical)" if g in critical else f"- {g}"

        if self.gap_analysis.critical_gaps:
            lines.append("**Not published** (no SSA dataset on Data.gov provides it):")
            lines.append("")
            for g in self.gap_analysis.critical_gaps:
                lines.append(_gap_line(g))
                evidence = self.gap_analysis.gap_evidence.get(g)
                if evidence:
                    lines.append(f"  - *Checked:* {evidence}")
            lines.append("")
        if self.gap_analysis.partial_gaps:
            lines.append("**Only partly available** (published in part, or only indirectly):")
            lines.append("")
            for g in self.gap_analysis.partial_gaps:
                lines.append(_gap_line(g))
            lines.append("")
        if critical & set(self.gap_analysis.critical_gaps + self.gap_analysis.partial_gaps):
            lines.append("_(critical): the question cannot be answered without this information._")
            lines.append("")
        lines.append(f"**Impact**: {self.gap_analysis.impact_on_answer}")

        # Per-element rating rationale — makes every judgement call visible.
        if self.required_information_elements:
            lines += [
                "",
                "## How Answer Coverage Was Rated",
                "",
                "| Information needed | Rating | Why |",
                "|--------------------|--------|-----|",
            ]
            for el in self.required_information_elements:
                why = (el.rationale or "No rationale recorded.").replace("|", "/")
                lines.append(f"| {el.element} | {el.coverage_quality} | {why} |")
            lines += [
                "",
                "_Full: measured directly at the needed detail. Partial: measured but missing a "
                "level, breakdown or period. Proxy: only indirect, one-time or discontinued data. "
                "None: no SSA dataset found (searches recorded)._",
            ]
            if self.rating_note:
                lines += ["", f"**Why {self.coverage_rating.value}**: {self.rating_note}"]

        # Structured recommendations grouped by category, numbered globally
        if self.structured_recommendations:
            lines += ["", "## Transparency Recommendations", ""]
            by_category: dict[str, list[Recommendation]] = {}
            for r in self.structured_recommendations:
                by_category.setdefault(r.category, []).append(r)
            global_idx = 1
            for category, recs in by_category.items():
                lines.append(f"**[{category}]**")
                lines.append("")
                for r in recs:
                    lines.append(f"{global_idx}. {r.title}")
                    lines.append(f"   **Closes gap**: {r.closes_gap}")
                    lines.append(f"   **Justification**: {r.justification}")
                    lines.append("")
                    global_idx += 1
        else:
            lines += ["", "## Transparency Recommendations", ""]
            for idx, rec in enumerate(self.transparency_recommendations, start=1):
                lines.append(f"{idx}. {rec}")

        lines += [
            "",
            "## Potential Impact",
            "",
            self.potential_impact,
        ]

        lines += [
            "",
            "---",
            "_Assessment basis: official dataset metadata (SSA's Data.gov records), recorded "
            "Data.gov searches for each gap, and curated analyst notes. Dataset contents were "
            "not downloaded or inspected._",
        ]
        return "\n".join(lines)


# ── Recommendation models ──────────────────────────────────────────────────────


# TransparencyRecommendation is now an alias for the unified Recommendation model.
# This preserves backward compatibility with any code that imports TransparencyRecommendation.
TransparencyRecommendation = Recommendation


class TransparencyImprovementPlan(BaseModel):
    """Full set of prioritized transparency recommendations from RecommendationService."""

    context: str = Field(description="Question or topic that motivated the recommendations")
    recommendations: list[Recommendation]
    total_recommendations: int
    high_priority_count: int
    executive_summary: str

    @model_validator(mode="after")
    def set_counts(self) -> TransparencyImprovementPlan:
        self.total_recommendations = len(self.recommendations)
        self.high_priority_count = sum(
            1 for r in self.recommendations if r.priority == RecommendationPriority.HIGH
        )
        return self


# ── Tool input schemas ─────────────────────────────────────────────────────────


class DiscoverDatasetsInput(BaseModel):
    """Input for discover_disability_datasets tool."""

    query: str | None = Field(
        default=None,
        description=(
            "Optional keyword or topic filter (e.g., 'SSDI', 'field office', 'appeals'). "
            "Leave blank to retrieve the full catalog."
        ),
    )
    source_filter: DataSource | None = Field(
        default=None,
        description="Restrict results to a specific data source portal.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Filter by subject-matter tags (e.g., ['appeals', 'geographic']).",
    )


class ExplainDatasetInput(BaseModel):
    """Input for explain_dataset tool."""

    dataset_id: str = Field(
        description=(
            "Unique dataset slug from discover_disability_datasets "
            "(e.g., 'ssa-hearing-office-workload')."
        )
    )


class CompareDatasetsInput(BaseModel):
    """Input for compare_datasets tool."""

    dataset_ids: list[str] = Field(
        min_length=2,
        description="Two or more dataset IDs to compare side-by-side.",
    )

    @field_validator("dataset_ids")
    @classmethod
    def unique_ids(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("dataset_ids must be unique")
        return v


class AnalyzeCompletenessInput(BaseModel):
    """Input for analyze_dataset_completeness tool."""

    dataset_id: str = Field(description="Dataset slug to evaluate for completeness.")
    focus_dimensions: list[str] = Field(
        default_factory=list,
        description=(
            "Optional list of dimensions to focus on "
            "(e.g., ['geographic', 'temporal', 'demographic'])."
        ),
    )


class AssessFreshnessInput(BaseModel):
    """Input for assess_dataset_freshness tool."""

    dataset_id: str = Field(description="Dataset slug to evaluate for update currency.")


class EvaluateAnswerCoverageInput(BaseModel):
    """Input for evaluate_answer_coverage tool — the signature tool."""

    question: str = Field(
        min_length=10,
        description=(
            "A natural language question that an analyst or the public might want to answer "
            "using SSA public data (e.g., 'How long are people waiting for disability "
            "decisions by state?')."
        ),
    )
    include_recommendations: bool = Field(
        default=True,
        description="Whether to include transparency improvement recommendations in the output.",
    )


class RecommendTransparencyInput(BaseModel):
    """Input for recommend_transparency_improvements tool."""

    context: str = Field(
        min_length=10,
        description=(
            "A question, topic, or answer coverage assessment result that provides context "
            "for generating targeted transparency recommendations."
        ),
    )
    focus_area: str | None = Field(
        default=None,
        description=(
            "Optional focus area to scope recommendations "
            "(e.g., 'processing times', 'geographic equity', 'demographic data')."
        ),
    )
    max_recommendations: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of recommendations to return.",
    )


# ── Tool output wrappers ───────────────────────────────────────────────────────


class DiscoverDatasetsResult(BaseModel):
    """Output of discover_disability_datasets."""

    datasets: list[DatasetSummary]
    total_found: int
    query_applied: str | None
    source_note: str


class ExplainDatasetResult(BaseModel):
    """Output of explain_dataset."""

    dataset: DatasetDetail
    analyst_summary: str = Field(description="One-paragraph plain-English analyst summary")


class AnyToolResult(BaseModel):
    """Generic wrapper for tool results that include raw data."""

    success: bool = True
    data: Any = None
    error: str | None = None
