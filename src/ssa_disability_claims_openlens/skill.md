---
name: openlens
description: >
  SSA Disability Claims OpenLens — MCP Dataset Access Server for evaluating SSA public
  disability datasets. Signature capability: Answer Coverage analysis.
version: "1.0.0"
---

# SSA Disability Claims OpenLens — Agent Skill Guide

## Overview

OpenLens is an MCP server that enables AI agents to discover, understand, compare, and evaluate SSA public disability datasets. Its signature capability is **Answer Coverage** — measuring how well available data supports a specific question.

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

**Key output fields:**
- `answer_coverage_score`: 0–100 numeric score
- `coverage_rating`: Complete | High | Partial | Limited | Unsupported
- `available_data`: What datasets/fields exist
- `missing_information`: What's not published
- `gap_analysis.critical_gaps`: Gaps that make the question unanswerable
- `transparency_recommendations`: Actionable improvements
- `formatted_report`: Pre-formatted human-readable report

---

## Recommended Agent Workflows

### Workflow 1: Answer a Policy Question

```
1. evaluate_answer_coverage(question="...")
2. If score < 75: recommend_transparency_improvements(context=question)
3. If datasets_consulted is non-empty: explain_dataset(dataset_id=...) for key datasets
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

| Rating | Score | Meaning |
|--------|-------|---------|
| Complete | 90–100% | All required information available |
| High | 75–89% | Most information available; minor gaps |
| Partial | 40–74% | Key information partially available |
| Limited | 15–39% | Most information unavailable |
| Unsupported | 0–14% | Cannot be answered from public data |

### Gap Types

**Critical gaps** — Absent from all public datasets:
- Race and ethnicity data
- Field office appointment wait times
- Staffing levels
- End-to-end processing timelines

**Partial gaps** — Available but incomplete:
- State-level processing times (national only)
- Processing time distribution (averages only)
- Demographic cross-tabulations (limited)

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
- *"What data supports analysis of field office access equity?"*

### Transparency
- *"What data should SSA publish to improve transparency on processing times?"*
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
