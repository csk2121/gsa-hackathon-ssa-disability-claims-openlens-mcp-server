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
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enumerations ───────────────────────────────────────────────────────────────


class DataSource(str, Enum):
    """Known data source adapters."""

    SSA_OPEN_DATA = "SSA Open Data Portal"
    DATA_GOV = "Data.gov"
    STATIC_CATALOG = "Static Catalog"


class UpdateFrequency(str, Enum):
    """How often a dataset is updated."""

    REAL_TIME = "Real-time"
    DAILY = "Daily"
    WEEKLY = "Weekly"
    MONTHLY = "Monthly"
    QUARTERLY = "Quarterly"
    ANNUALLY = "Annually"
    IRREGULAR = "Irregular"
    UNKNOWN = "Unknown"


class CoverageRating(str, Enum):
    """Qualitative rating of Answer Coverage."""

    COMPLETE = "Complete"       # 90–100 %
    HIGH = "High"               # 75–89 %
    PARTIAL = "Partial"         # 40–74 %
    LIMITED = "Limited"         # 15–39 %
    UNSUPPORTED = "Unsupported"  # 0–14 %


class RecommendationPriority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class FreshnessStatus(str, Enum):
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
    url: str = Field(description="Canonical URL to the dataset landing page")
    tags: list[str] = Field(default_factory=list, description="Subject-matter tags")
    last_updated: Optional[date] = Field(default=None, description="Date of most recent update")


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
    last_updated: Optional[date] = None
    geographic_coverage: str = Field(
        default="National", description="Geographic scope of the data"
    )
    temporal_coverage: str = Field(
        default="Unknown", description="Earliest to latest date range covered"
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
    """Dataset update currency evaluation."""

    dataset_id: str
    dataset_name: str
    last_updated: Optional[date]
    update_frequency: UpdateFrequency
    days_since_update: Optional[int]
    freshness_score: float = Field(ge=0.0, le=100.0)
    freshness_status: FreshnessStatus
    staleness_indicators: list[str]
    analyst_notes: str


# ── Answer Coverage models ─────────────────────────────────────────────────────


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


class GapAnalysis(BaseModel):
    """Structured gap analysis for a question."""

    critical_gaps: list[str] = Field(
        description="Missing information that prevents answering the question"
    )
    partial_gaps: list[str] = Field(
        description="Information available but incomplete or indirect"
    )
    root_causes: list[str] = Field(
        description="Why the gaps exist (e.g., not collected, not published)"
    )
    impact_on_answer: str = Field(description="How the gaps affect answer quality")


class AnswerCoverageAssessment(BaseModel):
    """
    Signature output model: measures how well SSA public datasets support
    answering a specific natural language question.
    """

    question: str = Field(description="The original user question")
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
    missing_information: list[str] = Field(
        description="Information needed but not found in any public dataset"
    )
    gap_analysis: GapAnalysis
    transparency_recommendations: list[str] = Field(
        description="Actionable recommendations to close identified gaps"
    )
    potential_impact: str = Field(
        description="Expected public benefit if gaps are closed"
    )
    datasets_consulted: list[str] = Field(
        description="All dataset IDs evaluated during analysis"
    )

    @field_validator("answer_coverage_score")
    @classmethod
    def round_score(cls, v: float) -> float:
        return round(v, 1)

    def format_report(self) -> str:
        """Return a human-readable Answer Coverage report."""
        lines: list[str] = [
            f"Answer Coverage: {self.coverage_rating.value} ({self.answer_coverage_score:.0f}%)",
            "",
            "Available Data",
            "--------------",
        ]
        for item in self.available_data:
            lines.append(f"- {item}")
        lines += [
            "",
            "Missing Information",
            "-------------------",
        ]
        for item in self.missing_information:
            lines.append(f"- {item}")
        lines += [
            "",
            "Gap Analysis",
            "------------",
            self.gap_analysis.impact_on_answer,
        ]
        if self.gap_analysis.critical_gaps:
            lines.append("\nCritical Gaps:")
            for gap in self.gap_analysis.critical_gaps:
                lines.append(f"  • {gap}")
        lines += [
            "",
            "Transparency Recommendations",
            "----------------------------",
        ]
        for rec in self.transparency_recommendations:
            lines.append(f"- {rec}")
        lines += [
            "",
            "Potential Impact",
            "----------------",
            self.potential_impact,
        ]
        return "\n".join(lines)


# ── Recommendation models ──────────────────────────────────────────────────────


class TransparencyRecommendation(BaseModel):
    """A single actionable transparency improvement recommendation."""

    title: str
    description: str
    affected_datasets: list[str]
    new_data_elements: list[str] = Field(
        default_factory=list,
        description="New fields or metrics that should be published",
    )
    expected_impact: str
    priority: RecommendationPriority
    implementation_effort: str = Field(
        description="Low | Medium | High estimated effort to implement"
    )


class TransparencyImprovementPlan(BaseModel):
    """Full set of prioritized transparency recommendations."""

    context: str = Field(description="Question or topic that motivated the recommendations")
    recommendations: list[TransparencyRecommendation]
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

    query: Optional[str] = Field(
        default=None,
        description=(
            "Optional keyword or topic filter (e.g., 'SSDI', 'field office', 'appeals'). "
            "Leave blank to retrieve the full catalog."
        ),
    )
    source_filter: Optional[DataSource] = Field(
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
            "(e.g., 'ssa-odar-pending-cases')."
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
    focus_area: Optional[str] = Field(
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
    query_applied: Optional[str]
    source_note: str


class ExplainDatasetResult(BaseModel):
    """Output of explain_dataset."""

    dataset: DatasetDetail
    analyst_summary: str = Field(description="One-paragraph plain-English analyst summary")


class AnyToolResult(BaseModel):
    """Generic wrapper for tool results that include raw data."""

    success: bool = True
    data: Any = None
    error: Optional[str] = None
