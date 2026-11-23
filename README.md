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

Available Data
--------------
| Sl.# | Data | Web Link | Source Record |
|------|------|----------|---------------|
| 1 | Field Office Contact Information | https://www.ssa.gov/data/FO-RS-Address-Open-Close-Time-App-Devs.html | Data.gov record US-GOV-SSA-1733 |
| 2 | OASDI Beneficiaries by State and County (series) | https://www.ssa.gov/policy/docs/statcomps/oasdi_sc/index.html | Data.gov record US-GOV-SSA-3378 |
| 3 | Hearing Office Workload Data - Current Report | https://www.ssa.gov/appeals/DataSets/02_HO_Workload_Data.html | Data.gov record US-GOV-SSA-303 |
| 4 | SSI Recipients by State and County (series) | https://www.ssa.gov/policy/docs/statcomps/ssi_sc/index.html | Data.gov record US-GOV-SSA-3414 |

Every link comes from the dataset's official Data.gov metadata record — see [docs/datasets.md](docs/datasets.md#how-the-catalog-is-grounded).

Missing Information
-------------------
- Field office operational metrics (staffing, volume, wait times)
- Field office appointment and walk-in volume
- SSA office staffing levels

Gap Analysis
------------
**Only partly available** (published in part, or only indirectly):
- Field office operational metrics (staffing, volume, wait times) (critical)
- Field office appointment and walk-in volume (critical)
- SSA office staffing levels (critical)

_(critical): the question cannot be answered without this information._

**Impact**: The question can only be partly answered from public data. Information it
depends on most is only available indirectly (one-time, historical or discontinued data).

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

### Local / stdio Deployment

```
┌─────────────────────────────────────────────────────────────────┐
│                   MCP Client (AI Agent / Bob)                   │
└──────────────────────────────┬──────────────────────────────────┘
                               │ stdio / MCP Protocol
┌──────────────────────────────▼──────────────────────────────────┐
│              SSA Disability Claims OpenLens MCP Server          │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                       app.py (FastMCP)                  │    │
│  │                                                         │    │
│  │   7 Tools         3 Prompts         4 Resources         │    │
│  └──────┬────────────────┬────────────────┬───────────────┘    │
│         │                │                │                     │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐            │
│  │  services/  │  │  prompts/   │  │ resources/  │            │
│  │             │  │             │  │             │             │
│  │ catalog     │  │ advisor     │  │ datasets    │             │
│  │ coverage    │  │ reviewer    │  │ framework   │             │
│  │ analysis    │  │ evaluator   │  │ recs        │             │
│  │ recommend.  │  └─────────────┘  └─────────────┘            │
│  └──────┬──────┘                                              │
│         │                                                      │
│  ┌──────▼────────────────────────────────────────────────┐    │
│  │                  Dataset Adapters                      │    │
│  │   StaticCatalogAdapter │ DataGovAdapter (live)         │    │
│  └───────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                    │                        │
           SSA Open Data Portal         Data.gov API
```

### watsonx Orchestrate Deployment

```
┌─────────────────────────────────────────────────────────────────┐
│                        End User                                 │
│              (watsonx Orchestrate Agent Chat UI)                │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                  watsonx Orchestrate Platform                   │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │               ssa_openlens_agent (native)                 │  │
│  │   LLM: watsonx/meta-llama/llama-3-3-70b-instruct          │  │
│  │   Style: react_core  │  hide_reasoning: true              │  │
│  └──────────────────────────────┬────────────────────────────┘  │
│                                 │ MCP tool calls                 │
│  ┌──────────────────────────────▼────────────────────────────┐  │
│  │          ssa-disability-claims-openlens (toolkit)         │  │
│  │                                                           │  │
│  │  discover_disability_datasets                             │  │
│  │  explain_dataset                                          │  │
│  │  compare_datasets                                         │  │
│  │  analyze_dataset_completeness                             │  │
│  │  assess_dataset_freshness                                 │  │
│  │  evaluate_answer_coverage                                 │  │
│  │  recommend_transparency_improvements                      │  │
│  └──────────────────────────────┬────────────────────────────┘  │
└─────────────────────────────────┼───────────────────────────────┘
                                  │ MCP stdio
┌─────────────────────────────────▼───────────────────────────────┐
│              SSA Disability Claims OpenLens MCP Server          │
│                        (python main.py)                         │
└─────────────────────────────────┬───────────────────────────────┘
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
- *"Explain the Hearing Office Workload dataset"*
- *"What are the limitations of the SSI Recipients by State dataset?"*
- *"What fields are in ssa-disability-claim-data?"*

---

### `compare_datasets`
Compare two or more datasets to identify shared dimensions, missing join relationships, and integration opportunities.

**Example prompts:**
- *"Compare ssa-oasdi-beneficiaries-by-state and ssa-ssi-recipients-by-state"*
- *"Can I join the hearing office workload and hearing wait time datasets?"*

---

### `analyze_dataset_completeness`
Evaluate a dataset's geographic, temporal, and operational coverage. Returns a scored completeness analysis.

**Example prompts:**
- *"How complete is the SSA disability applications dataset?"*
- *"What geographic coverage gaps exist in the hearing office workload dataset?"*

---

### `assess_dataset_freshness`
Evaluate how current a dataset is relative to its stated update frequency. Returns a structured freshness report with six sections:

| Section | Description |
|---------|-------------|
| **Summary Table** | Dataset ID, last updated, update frequency, days since update, freshness score (0–100), status |
| **Freshness Rationale** | Deterministic natural-language explanation of why the status and score were assigned |
| **Staleness Indicators** | Specific flags triggered by the dataset's age |
| **Analyst Notes** | Action-oriented guidance for the analyst based on the freshness status |
| **Assessment Note** | Disclaimer clarifying scores are based on catalog metadata, not a live SSA source query |

**Freshness statuses:** Current | Aging | Stale | Unknown

**Example prompts:**
- *"Is the SSA Disability Claim Data dataset up to date?"*
- *"Assess the freshness of the SSA State Agency Workload Data dataset"*
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

## Deployment

### Local (stdio)

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

# Run the server
python main.py
```

### watsonx Orchestrate

Requires the [watsonx Orchestrate ADK CLI](https://developer.watson-orchestrate.ibm.com/getting_started/installing) (`orchestrate`).

```bash
# 1. Add and activate your environment
orchestrate env add --name <env-name> --url <instance-url> --type ibm_iam
orchestrate env activate <env-name> --api-key <ibm-cloud-api-key>

# 2. Import the MCP toolkit
orchestrate toolkits add \
  --kind mcp \
  --name ssa-disability-claims-openlens \
  --description "SSA Disability Claims OpenLens MCP server" \
  --package-root . \
  --command "python main.py" \
  --tools "*"

# 3. Import the agent
orchestrate agents import -f deploy/agent.yaml
```

The agent (`ssa_openlens_agent`) will be available immediately in the watsonx Orchestrate Agent Chat UI.

---

## Quick Start

### Prerequisites
- Python 3.12+
- pip

### Run tests

```bash
pytest tests/ -v
```

### Run evaluations

Two levels, both written up in [docs/evaluation_results.md](docs/evaluation_results.md):

```bash
# 1. Engine benchmark: the Answer Coverage engine alone. Free, deterministic, CI-friendly.
python eval/engine_benchmark.py

# 2. Agent evaluation: a Claude agent answers the 12-question openlens-eval-0 test set
#    through the real MCP server over stdio, scored by code checks and LLM judges.
python -m eval.agent_eval.run --check-setup    # server and dataset; no model calls
python -m eval.agent_eval.run --prompt v01     # an experiment
python -m eval.agent_eval.run --prompt v02     # compare a second system prompt
```

By default the agent and judges run as headless Claude Code (`claude -p`) on the
Claude subscription the CLI is signed in with, so no API credit is needed. Each
question gets a fresh session connected only to this MCP server, with no built-in
tools. `--backend api` uses the Messages API instead (`pip install -e ".[eval]"`
and `ANTHROPIC_API_KEY` in `.env`).

Each experiment is saved to `eval/results/agent/<name>.json`, and
`eval/results/agent/report.html` charts the experiments side by side:

| Evaluator | Type | What it checks |
|-----------|------|----------------|
| Right tool | Code | The agent called the tool the question calls for |
| Rating matches | Code | The stated coverage rating equals the expected one exactly |
| Report shown in full | Code | The coverage report reached the user unaltered (95%+ of its lines) |
| No invented numbers | Code | Every number in the answer came from a tool result |
| Case expectations | Code | Phrases each case must, or must not, contain (e.g. the DDS premise note) |
| Correctness | LLM judge | The answer agrees with the case's reference answer |
| Grounding | LLM judge | Every factual claim is supported by the tool results, and stays in scope |

The test set covers the demo questions plus out-of-scope, fabrication-bait and
prompt-injection cases.

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
├── deploy/
│   ├── agent.yaml                   # watsonx Orchestrate agent definition
│   └── requirements.txt             # Minimal runtime dependencies for deployment
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
│   └── services/                    # Business logic
│       ├── dataset_catalog_service.py
│       ├── answer_coverage_service.py
│       ├── dataset_analysis_service.py
│       └── recommendation_service.py
│
├── tests/                           # Pytest unit tests
├── eval/                            # Evaluation
│   ├── engine_benchmark.py          # engine-only benchmark
│   ├── agent_eval/                  # Claude agent over MCP: dataset, agent, checks, judges, report
│   └── benchmark_questions.yaml
└── docs/                            # Documentation
```

---

## Coverage Levels & Freshness

### Answer Coverage Ratings

| Rating | Meaning |
|--------|---------|
| Complete | Directly answerable from existing public datasets |
| High | Most information available; minor gaps remain |
| Partial | Relevant datasets support part of the analysis; some critical gaps |
| Limited | Relevant datasets found, but major gaps prevent a complete answer |
| Unsupported | No relevant datasets found; question outside known SSA domain |

### Freshness Statuses

| Status | Meaning |
|--------|---------|
| Current | Dataset is within its expected refresh interval |
| Aging | Dataset has exceeded its refresh interval by up to 50% |
| Stale | Dataset has significantly exceeded its refresh interval |
| Unknown | Last update date is unavailable — freshness cannot be assessed |

---

## Datasets Covered

| Dataset | Data.gov record | Frequency |
|---------|-----------------|-----------|
| OASDI Beneficiaries by State and County (series) | US-GOV-SSA-3378 | Annual |
| SSI Recipients by State and County (series) | US-GOV-SSA-3414 | Annual |
| Annual Statistical Report on the SSDI Program | US-GOV-SSA-1667 | Annual |
| SSA Disability Claim Data (state allowance rates) | US-GOV-SSA-308 | Annual |
| SSA State Agency Workload Data | US-GOV-SSA-307 | Monthly |
| Hearing Office Workload Data | US-GOV-SSA-303 | Monthly |
| Average Wait Time Until Hearing Held | US-GOV-SSA-304 | Monthly |
| Field Office Contact Information | US-GOV-SSA-1733 | Quarterly |
| Field Office Visitors (Average Daily) | US-GOV-SSA-434 | Annual |
| Initial disability claim average processing time | US-GOV-SSA-1409 | Monthly |
| Disability reconsideration average processing time | US-GOV-SSA-1768 | Annual |
| ALJ Disposition Data (hearing-level allowances) | US-GOV-SSA-299 | Monthly |
| DDS Accuracy | US-GOV-SSA-344 | Annual |
| Ticket to Work FY11-17 | US-GOV-SSA-1915 | One-time |
| National Beneficiary Survey: Disability Statistics | US-GOV-SSA-3379 | Irregular |
| 2016 Field Office Employee Counts | US-GOV-SSA-1918 | One-time |
| 2016 Field Office Visitor Counts | US-GOV-SSA-1917 | One-time |
| Field office claims appointments scheduled within 21 days, FY2005–2015 | US-GOV-SSA-431 | Discontinued |
| Field Office Claims Pending (national, FY2006–2022) | US-GOV-SSA-435 | Annual |
| Field Office Telephone Service (national answer and busy rates) | US-GOV-SSA-1414 | Monthly |
| 2016 Title 2 Claim Receipts by Field Office | US-GOV-SSA-1919 | One-time |
| DI & SSI Program Participants: Characteristics & Employment, 2015 | US-GOV-SSA-2278 | One-time |
| National Survey of SSI Children and Families (2001–2002) | US-GOV-SSA-328 | One-time |
| Red Book: A Guide to Work Incentives | none (manually checked link) | — |

Names, links, dates and frequencies come from each dataset's Data.gov record. See [docs/datasets.md](docs/datasets.md) for how to add a dataset.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built for the GSA Hackathon — SSA Disability Claims OpenLens MCP Server*
