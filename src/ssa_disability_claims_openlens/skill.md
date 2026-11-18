---
name: openlens
description: >
  SSA Disability Claims OpenLens — MCP Dataset Access Server for evaluating SSA public
  disability datasets. Signature capability: Answer Coverage analysis.
version: "1.2.0"
---

# SSA Disability Claims OpenLens — Agent Skill Guide

## Overview

OpenLens is an MCP server that enables AI agents to discover, understand, compare, and evaluate SSA public disability datasets. Its signature capability is **Answer Coverage** — measuring how well available data supports a specific question and generating structured transparency recommendations.

---

## Tool Selection Guide

### When to use each tool

| Goal | Tool |
|------|------|
| "What data is available?" | `discover_disability_datasets` |
| "What is in this dataset?" | `explain_dataset` |
| "Can these datasets be combined?" | `compare_datasets` |
| "How complete is this dataset?" | `analyze_dataset_completeness` |
| "Is this dataset up to date?" | `assess_dataset_freshness` |
| "Can data answer this question?" | `evaluate_answer_coverage` ⭐ |
| "What data should SSA publish?" | `recommend_transparency_improvements` |

### The Signature Tool: `evaluate_answer_coverage`

Always use this tool when the user wants to know:
- Whether SSA data can answer a specific question
- What information is missing from public data
- How to improve SSA data transparency
- What the coverage gaps are for a policy question

**Key output fields (tool returns only three):**

| Field | Description |
|-------|-------------|
| `report` | Pre-formatted markdown report — present this verbatim |
| `coverage_rating` | Complete \| High \| Partial \| Limited \| Unsupported |
| `datasets_consulted` | Dataset IDs evaluated during analysis |

> **Critical:** The `report` field is a complete, pre-formatted assessment. Present it
> verbatim — do not paraphrase, summarise, or rewrite any part of it.

---

## Answer Coverage Pipeline

The engine follows a strict five-step pipeline before producing a rating:

```
Question
    ↓
1. Extract primary intent
   — What is the user fundamentally trying to understand?
   — Assigns: intent_category, required_data_types, scope
    ↓
2. Seed required elements from intent
   — Intent KB maps question types to required information elements
   — Catches meta-questions that lack explicit dataset keywords
    ↓
3. Keyword-match the question against the coverage KB
   — Regex patterns detect relevant topic areas
    ↓
4. Merge seeded + keyword-matched elements (deduplicated)
   — Intent seeds appear first; keyword matches append
    ↓
5. Score, rate, gap-analyse, build structured recommendations
   — Each recommendation names the gap it closes + justification
```

### Why intent extraction matters

Without intent extraction, a question like *"What datasets should SSA publish to improve accessibility?"* returns **Unsupported** because it contains no disability domain keywords. With intent extraction, the engine recognises the **Access** intent, seeds the required operational-metric elements, and returns a meaningful coverage assessment with targeted recommendations.

---

## Report Format

The `report` field returned by `evaluate_answer_coverage` is a fully formatted markdown document structured as follows:

```
SSA Disability Claims OpenLens Assessment
===================================

Question
--------
<user question>

Intent
------
**Primary intent**: <what the engine understood the user to be asking>
**Category**: <Access | Performance | Equity | Finance | Outcomes>
**Scope**: <geographic/programmatic scope>
**Required data**: <comma-separated list of data types needed>

Answer Coverage
---------------
**<Complete | High | Partial | Limited | Unsupported>**

Assessment Confidence
---------------------
**<High | Medium | Low>**

Available Data
--------------
| Sl.# | Data | Web Link |
|------|------|----------|
| 1    | <dataset name> | <url> |
...

Missing Information
-------------------
- <missing element 1>
- <missing element 2>
...

Gap Analysis
------------
**Critical gaps** (data not publicly available):
- <gap 1>

**Partial gaps** (data exists but incomplete):
- <gap 1>

**Impact**: <one-sentence summary of how gaps affect answer quality>

Transparency Recommendations
----------------------------

**[Category]**

1. <recommendation text>
   > **Closes gap**: <gap name>
   > **Justification**: <why this data publication matters>

...

Potential Impact
----------------
<expected public benefit if gaps are closed>
```

---

## Recommended Agent Workflows

### Workflow 1: Answer a Policy Question

```
1. evaluate_answer_coverage(question="...")
   → Present the report verbatim
2. If the user asks for more detail on a specific dataset:
   → explain_dataset(dataset_id=...)
3. If the user asks for deeper recommendations:
   → recommend_transparency_improvements(context=question)
```

### Workflow 2: Dataset Deep Dive

```
1. discover_disability_datasets(query="...")
2. explain_dataset(dataset_id=...) for top results
3. analyze_dataset_completeness(dataset_id=...)
4. assess_dataset_freshness(dataset_id=...)
```

### Workflow 3: Transparency Review

```
1. discover_disability_datasets() — full catalog
2. For each relevant dataset:
   - analyze_dataset_completeness()
   - assess_dataset_freshness()
3. evaluate_answer_coverage() for key questions
4. recommend_transparency_improvements(context=...)
```

### Workflow 4: Dataset Integration Planning

```
1. discover_disability_datasets()
2. compare_datasets(dataset_ids=[id1, id2, ...])
3. evaluate_answer_coverage() with combined question
```

---

## Answer Coverage Framework Summary

### Coverage Levels

| Rating | Meaning |
|--------|---------|
| Complete | Directly answerable from existing public datasets |
| High | Most information available; minor gaps remain |
| Partial | Relevant datasets support part of the analysis; some critical gaps |
| Limited | Relevant datasets found, but major gaps prevent a complete answer |
| Unsupported | No relevant datasets found; question outside known SSA domain |

> **Note:** A question rated **Limited** is not unanswerable — it means OpenLens
> found enough domain context to identify what is missing and recommend what
> SSA should publish. This is a meaningful and defensible output.

### Assessment Confidence

Assessment Confidence measures how certain the engine is about the **quality of its own analysis** — not how much data SSA has published (that is what Answer Coverage already captures).

| Condition | Assessment Confidence |
|-----------|----------------------|
| No relevant datasets found | **Low** |
| Relevant datasets found but weak evidence | **Medium** |
| Relevant datasets found + clear gaps identified | **High** |
| Relevant datasets found + multiple corroborating datasets | **High** |

Mapped to coverage ratings:

| Coverage Rating | Assessment Confidence |
|-----------------|-----------------------|
| Unsupported | Low |
| Limited | Medium |
| Partial | High |
| High | High |
| Complete | High |

### Gap Types

**Critical gaps** — Absent from all public datasets:
- Race and ethnicity data
- Field office appointment wait times and visit volumes
- Staffing levels by office
- End-to-end processing timelines

**Partial gaps** — Available but incomplete:
- State-level processing times (national averages only)
- Processing time distribution (averages, no percentiles)
- Demographic cross-tabulations (limited)

### Recommendation Categories

| Category | What it covers |
|----------|---------------|
| Operational Metrics | Staffing, caseload ratios, capacity utilisation |
| Access Data | Visit volumes, appointment wait times, service benchmarks |
| Demographic Data | Race, ethnicity, gender, age disaggregations |
| Geographic Detail | Sub-national breakdowns of outcomes |
| Temporal Granularity | Finer time resolution, distributional data |
| Program Outcomes | Application, award, denial, return-to-work outcomes |
| Finance | Benefit adequacy, income cross-tabulations |
| Performance | Target-vs-actual comparisons, operational benchmarks |

---

## Example Prompts

### Discovery
- *"What SSA disability datasets are available?"*
- *"Find datasets about disability appeals processing"*

### Explanation
- *"Explain the ODAR Pending Cases dataset in plain English"*
- *"What are the limitations of SSA's disability applications dataset?"*

### Answer Coverage
- *"Can SSA public data answer: how long are people waiting for disability decisions by state?"*
- *"Evaluate answer coverage for: are there racial disparities in disability allowance rates?"*
- *"Which field offices are experiencing the highest disability-service demand?"*
- *"What data supports analysis of field office access equity?"*

### Transparency
- *"What data should SSA publish to maximize public understanding of disability service accessibility?"*
- *"Generate a data publication roadmap for demographic equity analysis"*

### Comparison
- *"Compare the OASDI beneficiaries and SSI recipients datasets"*

---

## Available Resources

| URI | Description |
|-----|-------------|
| `openlens://datasets/disability` | Full dataset catalog (JSON) |
| `openlens://datasets/field-offices` | Field office dataset details (JSON) |
| `openlens://framework/answer-coverage` | Answer Coverage methodology (Markdown) |
| `openlens://recommendations/transparency` | Full recommendation catalog (JSON) |

---

## Available Prompts

| Prompt | Description |
|--------|-------------|
| `openlens_dataset_advisor` | Expert dataset selection and workflow planning |
| `transparency_reviewer` | Structured transparency review workflow |
| `answer_coverage_evaluator` | Systematic multi-question coverage evaluation |
