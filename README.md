# SSA Disability Claims OpenLens

**An MCP Dataset Access Server for evaluating SSA public disability data**

> *OpenLens does not simply discover datasets. OpenLens evaluates how effectively available SSA datasets support a user's question, identifies information gaps, and recommends opportunities to improve transparency and public understanding.*

---

## Problem Statement

The Social Security Administration (SSA) publishes dozens of disability program datasets — but finding the right data, understanding its limitations, and knowing what it *cannot* tell you requires deep institutional knowledge. Analysts, researchers, and advocates routinely:

- Discover that the data they need **doesn't exist** only after investing significant research effort
- Use datasets whose **geographic, temporal, or demographic coverage** is insufficient for their question
- Miss opportunities to **link or combine** datasets for richer analysis
- Lack a systematic way to **measure the gap** between what public data supports and what policy questions demand

**SSA Disability Claims OpenLens** solves this by turning dataset discovery into a question-answerable evaluation.

---

## Solution Overview

OpenLens is a production-quality **MCP (Model Context Protocol) Dataset Access Server** built in Python. It enables AI agents to:

| Capability | Description |
|------------|-------------|
| **Discover** | Find SSA disability datasets by keyword, source, or topic |
| **Understand** | Get plain-English explanations of dataset contents and limitations |
| **Compare** | Identify shared dimensions and integration opportunities across datasets |
| **Evaluate** | Score dataset completeness and freshness |
| **Assess Coverage** | Measure how well datasets support answering a specific question |
| **Recommend** | Generate prioritized transparency improvement recommendations |

### Signature Capability: Answer Coverage

The `evaluate_answer_coverage` tool is the heart of OpenLens. It accepts a natural language question and returns a pre-formatted `report` field that must be presented verbatim. Example output:

```
SSA Disability Claims OpenLens Assessment
===================================

Question
--------
Which SSA field offices have the highest disability service demand?

Intent
------
**Primary intent**: Identify which SSA field offices face the highest disability service demand
**Category**: Access
**Scope**: Field office level, national
**Required data**: Office visit volumes, Staffing levels, Geographic beneficiary counts

Answer Coverage
---------------
**Limited**

Assessment Confidence
---------------------
**Medium**

Available Data
--------------
| Sl.# | Data | Web Link |
|------|------|----------|
| 1 | SSA Field Office Locations | https://www.ssa.gov/locator/ |
| 2 | OASDI Beneficiaries by State and County | https://www.ssa.gov/policy/docs/statcomps/oasdi_sc/ |
| 3 | ODAR Pending Cases by Hearing Office | https://www.ssa.gov/appeals/DataSets.html |
| 4 | SSI Recipients by State and County | https://www.ssa.gov/policy/docs/statcomps/ssi_sc/ |

Missing Information
-------------------
- Field office operational metrics (staffing, volume, wait times)
- Field office appointment and walk-in volume
- SSA office staffing levels

Gap Analysis
------------
**Critical gaps** (data not publicly available):
- Field office operational metrics (staffing, volume, wait times)

**Partial gaps** (data exists but incomplete):
- Office workload and capacity

**Impact**: The question cannot be reliably answered from public data alone.
Critical missing elements require data that SSA has not published.

Transparency Recommendations
----------------------------

**[Operational Metrics]**

1. Publish monthly field office visit volumes and appointment counts
   **Closes gap**: Field office operational metrics (staffing, volume, wait times)
   **Justification**: Without visit volume data, it is impossible to rank offices
   by demand or identify where resources are insufficient.

**[Access Data]**

1. Publish average appointment wait times by field office
   **Closes gap**: Field office operational metrics (staffing, volume, wait times)
   **Justification**: Wait times are the most direct indicator of service
   accessibility and demand pressure at the office level.

Potential Impact
----------------
Publishing the missing data elements would substantially improve public ability
to evaluate SSA program equity, efficiency, and access.
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   MCP Client (AI Agent / Bob)                   │
└──────────────────────────────┬──────────────────────────────────┘
                               │ stdio / MCP Protocol
┌──────────────────────────────▼──────────────────────────────────┐
│              SSA Disability Claims OpenLens MCP Server           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                       app.py (FastMCP)                   │    │
│  │                                                          │    │
│  │   7 Tools         3 Prompts         4 Resources          │    │
│  └──────┬────────────────┬────────────────┬────────────────┘    │
│         │                │                │                      │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐             │
│  │   services/  │  │  prompts/   │  │ resources/  │             │
│  │             │  │             │  │             │              │
│  │ catalog     │  │ advisor     │  │ datasets    │              │
│  │ coverage    │  │ reviewer    │  │ framework   │              │
│  │ analysis    │  │ evaluator   │  │ recs        │              │
│  │ recommend.  │  └─────────────┘  └─────────────┘             │
│  └──────┬──────┘                                               │
│         │                                                       │
│  ┌──────▼─────────────────────────────────────────────────┐    │
│  │                  Dataset Adapters                        │    │
│  │   StaticCatalogAdapter │ DataGovAdapter (live)           │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                    │                        │
           SSA Open Data Portal         Data.gov API
```

---

## Tools

### `discover_disability_datasets`
Find SSA disability-related public datasets. Supports keyword search, source filtering, and tag filtering.

**Example prompts:**
- *"What disability datasets are available?"*
- *"Find datasets about disability appeals"*
- *"Show me SSA Open Data Portal datasets tagged 'geographic'"*

---

### `explain_dataset`
Explain a dataset's purpose, major fields, use cases, and limitations in plain English.

**Example prompts:**
- *"Explain the ODAR Pending Cases dataset"*
- *"What are the limitations of the SSI Recipients by State dataset?"*
- *"What fields are in ssa-disability-applications-decisions?"*

---

### `compare_datasets`
Compare two or more datasets to identify shared dimensions, missing join relationships, and integration opportunities.

**Example prompts:**
- *"Compare ssa-oasdi-beneficiaries-by-state and ssa-ssi-recipients-by-state"*
- *"Can I join the ODAR and performance datasets?"*

---

### `analyze_dataset_completeness`
Evaluate a dataset's geographic, temporal, and operational coverage. Returns a scored completeness analysis.

**Example prompts:**
- *"How complete is the SSA disability applications dataset?"*
- *"What geographic coverage gaps exist in the ODAR dataset?"*

---

### `assess_dataset_freshness`
Evaluate how current a dataset is relative to its stated update frequency.

**Example prompts:**
- *"Is the ODAR Pending Cases dataset up to date?"*
- *"How stale is the disability applications dataset?"*

---

### `evaluate_answer_coverage` ⭐ SIGNATURE TOOL
Evaluate how well SSA public datasets support answering a natural language question. Returns a 0–100 score, coverage rating, available data, missing information, gap analysis, and recommendations.

**Coverage levels:** Complete | High | Partial | Limited | Unsupported

**Tool returns three fields:** `report` (verbatim markdown), `coverage_rating`, `datasets_consulted`

**Example prompts:**
- *"Can SSA data answer: how long are people waiting for disability decisions by state?"*
- *"Evaluate answer coverage for: are there racial disparities in disability allowance rates?"*
- *"What data is available to answer questions about field office access equity?"*

---

### `recommend_transparency_improvements`
Generate prioritized, actionable recommendations for improving SSA public data transparency.

**Example prompts:**
- *"What data should SSA publish to improve answer coverage for processing time questions?"*
- *"Recommend transparency improvements for the field office access topic"*
- *"Generate a data publication roadmap for demographic equity analysis"*

---

## Quick Start

### Prerequisites
- Python 3.12+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/gsa-hackathon-ssa-disability-claims-openlens-mcp-server.git
cd gsa-hackathon-ssa-disability-claims-openlens-mcp-server

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env
```

### Run the server

```bash
python main.py
```

### Run tests

```bash
pytest tests/ -v
```

### Run evaluations

```bash
python eval/phoenix_evals.py
```

---

## Configuration

See [`.env.example`](.env.example) for all configuration options. The server runs with sensible defaults and requires no mandatory environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENLENS_LOG_LEVEL` | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |
| `DATA_GOV_API_KEY` | *(empty)* | Optional Data.gov API key (improves rate limits) |
| `COVERAGE_HIGH_THRESHOLD` | `75` | Min score for "High" coverage rating |
| `COVERAGE_PARTIAL_THRESHOLD` | `40` | Min score for "Partial" coverage rating |

---

## Project Structure

```
├── main.py                          # Entry point
├── pyproject.toml                   # Project metadata and dependencies
├── requirements.txt                 # Pinned requirements
├── Dockerfile                       # Container build
├── manifest.yaml                    # MCP server manifest
├── server.json                      # MCP registration config
│
├── src/ssa_disability_claims_openlens/
│   ├── app.py                       # FastMCP app factory (wires everything)
│   ├── config.py                    # Settings from environment variables
│   ├── models.py                    # All Pydantic v2 models
│   ├── utils.py                     # Shared utilities
│   ├── routes.py                    # Alternate registration helper
│   │
│   ├── tools/                       # 7 MCP tools
│   ├── prompts/                     # 3 MCP prompts
│   ├── resources/                   # 4 MCP resources
│   └── services/                    # Business logic (services)
│       ├── dataset_catalog_service.py
│       ├── answer_coverage_service.py
│       ├── dataset_analysis_service.py
│       └── recommendation_service.py
│
├── tests/                           # Pytest unit tests
├── eval/                            # Evaluation benchmarks
│   ├── phoenix_evals.py
│   └── benchmark_questions.yaml
└── docs/                            # Documentation
```

---

## Coverage Levels & Assessment Confidence

### Answer Coverage Ratings

| Rating | Meaning |
|--------|---------|
| Complete | Directly answerable from existing public datasets |
| High | Most information available; minor gaps remain |
| Partial | Relevant datasets support part of the analysis; some critical gaps |
| Limited | Relevant datasets found, but major gaps prevent a complete answer |
| Unsupported | No relevant datasets found; question outside known SSA domain |

### Assessment Confidence

Measures how certain the engine is about the **quality of its own analysis** — not how much data SSA has published.

| Condition | Assessment Confidence |
|-----------|----------------------|
| No relevant datasets found (Unsupported) | **Low** |
| Relevant datasets found but weak evidence (Limited) | **Medium** |
| Relevant datasets found + clear gaps identified (Partial) | **High** |
| Relevant datasets found + multiple corroborating datasets (High / Complete) | **High** |

---

## Datasets Covered

| Dataset | Source | Frequency |
|---------|--------|-----------|
| OASDI Beneficiaries by State and County | SSA Open Data | Annual |
| ODAR Pending Cases by Hearing Office | SSA Open Data | Monthly |
| SSI/SSDI Applications and Decisions | SSA Open Data | Annual |
| SSA Field Office Locations | SSA Open Data | Quarterly |
| SSA Disability Research Statistics | SSA Open Data | Annual |
| SSI Recipients by State and County | SSA Open Data | Monthly |
| SSA Red Book — Work Incentives | SSA Open Data | Annual |
| SSA Annual Performance Report | Data.gov | Annual |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built for the GSA Hackathon — SSA Disability Claims OpenLens MCP Server*
