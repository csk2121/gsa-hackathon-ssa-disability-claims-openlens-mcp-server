# Architecture — SSA Disability Claims OpenLens

## Overview

OpenLens is a **Model Context Protocol (MCP) server** built in Python using FastMCP. It follows
a layered architecture with clean separation between the MCP protocol layer, business logic services,
and data source adapters.

## Layer Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MCP Protocol Layer                           │
│                                                                     │
│   7 Tools  │  3 Prompts  │  4 Resources  │  FastMCP (stdio)        │
│                                                                     │
│   app.py                                                            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                       Business Logic Layer                          │
│                                                                     │
│   DatasetCatalogService    AnswerCoverageEngine                    │
│   DatasetAnalysisService   RecommendationService                   │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                        Data Adapter Layer                           │
│                                                                     │
│   StaticCatalogAdapter (always available)                          │
│   DataGovAdapter (live CKAN API, optional)                         │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Static catalog as the foundation
The curated static catalog ensures the server is fully functional in air-gapped environments
and returns deterministic, reproducible results. Live adapters (Data.gov) enrich the catalog
when the network is available.

### 2. Deterministic Answer Coverage Engine
The engine uses pattern matching against a curated knowledge base — no LLM dependency.
This ensures the server produces auditable, reproducible coverage scores that can be
regression-tested.

### 3. Services are independent of FastMCP
All business logic lives in `services/` and has no FastMCP imports. Tools are thin wrappers
that validate input, call a service, and format the output. This enables isolated unit testing
without an MCP runtime.

### 4. Pydantic models for all inputs and outputs
Every tool input and output is a Pydantic v2 model. This provides runtime validation,
auto-documentation, and clean JSON serialization.

## File Map

```
src/ssa_disability_claims_openlens/
├── __init__.py
├── app.py          # FastMCP instance, wires all tools/prompts/resources
├── config.py       # Settings from environment variables (singleton)
├── models.py       # All Pydantic v2 models
├── utils.py        # Shared pure utilities (logging, scoring, keywords)
│
├── tools/
│   ├── discover_disability_datasets.py
│   ├── explain_dataset.py
│   ├── compare_datasets.py
│   ├── analyze_dataset_completeness.py
│   ├── assess_dataset_freshness.py
│   ├── evaluate_answer_coverage.py        ← SIGNATURE TOOL
│   └── recommend_transparency_improvements.py
│
├── prompts/
│   ├── openlens_dataset_advisor.py
│   ├── transparency_reviewer.py
│   └── answer_coverage_evaluator.py
│
├── resources/
│   ├── disability_datasets.py
│   ├── field_office_datasets.py
│   ├── answer_coverage_framework.py
│   └── transparency_recommendations.py
│
└── services/
    ├── dataset_catalog_service.py    # Catalog + adapters
    ├── answer_coverage_service.py    # Answer Coverage Engine
    ├── dataset_analysis_service.py   # Completeness + freshness
    └── recommendation_service.py    # Transparency recommendations
```

## Data Flow: evaluate_answer_coverage

```
User question (natural language)
         │
         ▼
AnswerCoverageEngine.evaluate()
         │
         ├─── _match_entries() ──────────► _COVERAGE_KB (pattern matching)
         │                                 Returns matched (entry, weight) pairs
         │
         ├─── _build_elements() ─────────► List[InformationElement]
         │                                 available=True/False, quality, datasets
         │
         ├─── _compute_weighted_score() ─► 0–100 float
         │
         ├─── score_to_coverage_rating() ► CoverageRating enum
         │
         ├─── _build_gap_analysis() ─────► GapAnalysis
         │                                 critical_gaps, partial_gaps, impact
         │
         └─── _build_recommendations() ──► List[str] (from _TRANSPARENCY_REC_KB)
                        │
                        ▼
         AnswerCoverageAssessment (Pydantic model)
                        │
                        ▼
         MCP Tool response (JSON)
```
