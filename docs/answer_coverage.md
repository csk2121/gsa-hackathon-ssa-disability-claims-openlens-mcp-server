# Answer Coverage Framework

## What Is Answer Coverage?

**Answer Coverage** measures how well available SSA public datasets support answering a user's natural language question.

It answers the meta-question: *"Can public data answer this?"*

---

## Why It Matters

The absence of data is not obvious. Without a systematic framework, analysts and researchers:

1. Invest time building analyses only to discover the data is unavailable
2. Use proxy metrics without understanding how far they are from the ideal measure
3. Cannot quantify the cost of data gaps to program transparency
4. Cannot prioritize which new data elements would have the highest impact

Answer Coverage makes data gaps **visible, measurable, and actionable**.

---

## Coverage Levels

| Rating       | Score Range | Meaning                                                      |
|--------------|-------------|--------------------------------------------------------------|
| **Complete** | 90–100%     | All required information is available in public datasets     |
| **High**     | 75–89%      | Most required information is available; minor gaps           |
| **Partial**  | 40–74%      | Key information partially available; significant gaps remain |
| **Limited**  | 15–39%      | Most required information is unavailable or indirect only    |
| **Unsupported** | 0–14%   | The question cannot be answered from public data             |

---

## Scoring Methodology

### Step 1: Extract Required Information Elements

The engine analyzes the question using pattern matching against a curated knowledge base of SSA disability data topics. Each matched topic yields an **Information Element** — an atomic piece of information needed to answer the question.

**Examples of information elements:**
- Disability claim processing times
- Race and ethnicity breakdown
- Field office appointment wait times
- State-level application volumes

### Step 2: Assess Coverage Quality for Each Element

Each element is scored on a four-level quality scale:

| Quality | Weight | Meaning |
|---------|--------|---------|
| **Full** | 1.0 | A dataset directly provides this information |
| **Partial** | 0.6 | A dataset provides related but incomplete data |
| **Proxy** | 0.3 | A proxy measure exists but is not the direct measure |
| **None** | 0.0 | No dataset provides this information |

### Step 3: Apply Element Weights

Elements are weighted by criticality:

- **Critical elements** (weight=2): Core information without which the question cannot be answered
- **Supporting elements** (weight=1): Context or enrichment that improves answer quality

### Step 4: Compute Weighted Score

```
Score = Σ(coverage_quality_score × weight) / Σ(weights) × 100
```

### Step 5: Classify and Explain

The numeric score is mapped to a qualitative CoverageRating. The engine then:
- Lists **available data** with coverage quality notes
- Lists **missing information** elements
- Generates a **gap analysis** with critical/partial gaps, root causes, and impact
- Produces **transparency recommendations** for closing identified gaps
- Estimates **potential impact** of closing the gaps

---

## Gap Categories

### Critical Gaps
Information that is entirely absent from published SSA datasets. Without this data, the question cannot be answered. Examples:
- Race and ethnicity data in disability adjudication
- Field office appointment wait times
- Staffing levels at field or hearing offices

### Partial Gaps
Information that is available but incomplete, indirect, or untimely. Examples:
- National processing time averages (but no state breakdown)
- Annual application volumes (but no monthly granularity)
- Hearing office pending cases (but no processing time distribution)

---

## Coverage Knowledge Base

The engine uses a curated knowledge base mapping question topics to dataset coverage. This is maintained in [`services/answer_coverage_service.py`](../src/ssa_disability_claims_openlens/services/answer_coverage_service.py).

### Covered Topics

| Topic | Available Coverage | Datasets |
|-------|--------------------|----------|
| Disability claim processing times | Partial | ODAR Pending Cases, Performance Report |
| Hearing-level wait times | Partial | ODAR Pending Cases |
| Field office appointment wait times | **None** | *(not published)* |
| Geographic disaggregation | Partial | Beneficiary, SSI, ODAR |
| Field office locations | Full | Field Office Locator |
| SSA staffing levels | **None** | *(not published)* |
| Allowance rates | Partial | Applications/Decisions |
| Application volumes | Full | Applications/Decisions |
| Race and ethnicity | **None** | *(not published)* |
| Age distribution | Partial | Applications/Decisions, Research Statistics |
| Gender distribution | Partial | Research Statistics |
| Impairment categories | Partial | Applications/Decisions |
| Beneficiary counts | Full | OASDI Beneficiaries, SSI Recipients |
| Benefit amounts | Partial | OASDI Beneficiaries, Research Statistics |
| Return to work outcomes | Proxy | Red Book |
| Agency performance metrics | Partial | Performance Report |

---

## Example Outputs

### High Coverage Question
> "How many SSDI beneficiaries are there by state?"

```
Answer Coverage: Partial (65%)

Available Data: Beneficiary counts (Full), Geographic disaggregation (Partial)
Missing Information: County-level for some states (suppressed)
```

### Low Coverage Question
> "Are there racial disparities in disability allowance rates?"

```
Answer Coverage: Limited (20%)

Available Data: Allowance rates by impairment (Partial)
Missing Information: Race and ethnicity data

Gap Analysis: Critical gap — race/ethnicity not published at any decision level.
This question cannot be answered from SSA public data.
```

---

## Extending the Framework

To add coverage for a new data topic:

1. Add an entry to `_COVERAGE_KB` in [`answer_coverage_service.py`](../src/ssa_disability_claims_openlens/services/answer_coverage_service.py)
2. Add a dataset to the static catalog in [`dataset_catalog_service.py`](../src/ssa_disability_claims_openlens/services/dataset_catalog_service.py)
3. Add a benchmark case to [`eval/benchmark_questions.yaml`](../eval/benchmark_questions.yaml)
4. Run `python eval/phoenix_evals.py` to verify the update
