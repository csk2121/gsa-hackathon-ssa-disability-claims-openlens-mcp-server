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

### Step 1: Normalise the Question

The question is lower-cased and also matched in a form with plurals singularised
("counties" → "county", "offices" → "office"), so wording variations reach the same
elements. Program names such as SSI and SSDI are left untouched. The geographic or
organisational scope the question names (state, county, hearing office, field office,
ZIP, region) is detected from its wording and reported as the scope.

### Step 2: Extract Required Information Elements

The engine matches the question against a curated knowledge base of SSA disability
data topics. Each matched topic yields an **Information Element** — an atomic piece of
information needed to answer the question. An intent category (Equity, Access, Policy, …)
can also force-include the elements a type of question always needs. Elements can
declare exclusion patterns so that, for example, "appointment wait times" does not
match claim processing times.

### Step 3: Rate Each Element Against the Rubric

| Rating | Score | Rule |
|--------|-------|------|
| **Full** | 1.0 | A catalogued dataset directly measures the element at the detail the question needs, and is current |
| **Partial** | 0.6 | Catalogued datasets measure it, but miss a needed level, breakdown, distribution or period |
| **Proxy** | 0.3 | Only indirect, one-time, historical or discontinued data exists |
| **None** | 0.0 | No SSA dataset on Data.gov provides it — backed by recorded searches in `data/gap_evidence.json` |

Every element carries a written rationale citing the Data.gov records behind its rating,
and the report shows it in a **How Answer Coverage Was Rated** table. When the
critical-element cap (below) lowers the rating, that section ends with a **Why
&lt;rating&gt;** line naming the critical elements and the rating the plain average would
have given. Tests enforce the
rubric: Full/Partial/Proxy elements must cite catalogued datasets, None elements must
cite none and must have search evidence, and every rationale must cite a record id or
the search evidence.

### Step 4: Weight and Score

- **Critical elements** (weight 2): core information without which the question cannot be answered
- **Supporting elements** (weight 1): context that improves the answer

```
Score = Σ(rating score × weight) / Σ(weights) × 100
```

When a question asks for something at a finer level than a broad element measures,
the specific element **refines** the broad one, and the broad one becomes supporting.
For example, "Which field offices have the longest decision wait times?" needs
*Disability decision times by field office or DDS* (Proxy); the national
*Disability claim processing times* (Partial) is still shown, but as context, so a
national average cannot lift a per-office question to Partial.

### Step 5: Apply the Critical-Element Cap

A question cannot be rated higher than its best critical element allows. If every
critical element is Proxy or None, the rating is at most **Limited**; if the best
critical element is Partial, at most **Partial**. Fully covered supporting elements
(such as office locations) therefore cannot make an unanswerable question look
answerable. When the cap applies, the report says so under the rating.

### Step 6: Classify and Explain

The score is mapped to a Coverage Rating. The report then lists the available datasets
with their links and source records, the missing information, the gap analysis (with
the search evidence under each element that is not published, and critical elements marked), the per-element ratings and reasons,
recommendations linked to the gaps they close, and the potential impact.

**Missing Information** lists every element rated None, and every critical element
rated Proxy (marked "only indirect, one-time or discontinued data"): some data exists,
but not enough to answer the question. The impact statement says the question can only
be partly answered whenever a critical element is Proxy.

Some questions rest on a common misconception. When the matched intent has a note on
the question (for example, that field offices do not make the medical decision on
disability claims), the report shows it under **Intent**.

The rating never depends on the network: it uses only the grounded catalog.

### Assessment Basis

Every report ends by stating its basis: SSA's Data.gov metadata records, recorded
Data.gov searches for each gap, and curated analyst notes. Dataset contents are not
downloaded or inspected — OpenLens assesses what SSA's published data *describes*.

---

## Coverage Knowledge Base

Maintained in [`services/answer_coverage_service.py`](../src/ssa_disability_claims_openlens/services/answer_coverage_service.py).
This table is generated from the code (32 elements).

| Information element | Rating | Weight | Why |
|---------------------|--------|--------|-----|
| Disability claim processing times | Partial | Critical | Average processing times are published for initial claims (US-GOV-SSA-1409), reconsiderations (US-GOV-SSA-1768) and hearings (US-GOV-SSA-303, -304), but only as averages, with no state breakdown described for initial claims. |
| Disability decision times by field office or DDS | **Proxy** | Critical | No dataset reports decision times per field office or per DDS. Initial-claim times are national averages (US-GOV-SSA-1409), state agency data has pending counts by state but no times (US-GOV-SSA-307), field office claims pending is one national count per year, all claim types combined, ending FY2022 (US-GOV-SSA-435), and per-office times exist only for hearing offices (US-GOV-SSA-303), which are not mapped to field offices. |
| Hearing-level wait times | Partial | Critical | Average processing time per hearing office and average months to a hearing are published monthly (US-GOV-SSA-303, -304); no distributions. |
| Linked claim history across decision levels | **Proxy** | Critical | Each decision level publishes its own counts and average times for different groups of claims (US-GOV-SSA-307, -299, -1409, -1768, -304). They cannot be linked to follow the same claims, so final rates and total waits can only be approximated. |
| Field office appointment and walk-in volume | **Proxy** | Critical | Average daily visitors is published (US-GOV-SSA-434), but per-office visitor counts exist only for FY2016 (US-GOV-SSA-1917), and appointment volumes are not published. |
| Field office appointment wait times | **Proxy** | Critical | Only a discontinued series exists: the share of claims appointments scheduled within 21 days, FY2005–2015 (US-GOV-SSA-431). No current or per-office wait times. |
| Geographic disaggregation of outcomes | Partial | Supporting | Claims and allowances are published by state (US-GOV-SSA-307, -308) and beneficiaries by state and county (US-GOV-SSA-3378, -3414); claim outcomes stop at state level. |
| SSA field office locations and coverage | Full | Supporting | Locations, phone numbers and hours of every field office are published and updated quarterly (US-GOV-SSA-1733). |
| Field office operational metrics (staffing, volume, wait times) | **Proxy** | Critical | Per-office staffing, visitor and Title II disability claim receipt counts exist for FY2016 only (FOIA releases US-GOV-SSA-1917, -1918, -1919). Current series — daily visitors (US-GOV-SSA-434), claims pending (US-GOV-SSA-435) and phone answer and busy rates (US-GOV-SSA-1414) — are national totals with no per-office figures. |
| SSA office staffing levels | **Proxy** | Critical | Field office employee counts were released once, for FY2016 (US-GOV-SSA-1918); no hearing office staffing data is in the catalog. |
| Office workload and capacity | **Proxy** | Critical | Workload volumes are published for hearing offices (US-GOV-SSA-303) and state agencies (US-GOV-SSA-307), but without staffing or capacity to relate them to. Field office claim receipts and staffing can be paired only for FY2016 (US-GOV-SSA-1919, -1918). |
| Applicant age distribution | Partial | Supporting | The SSDI Annual Statistical Report gives demographic statistics on beneficiaries (US-GOV-SSA-1667); applicant age is not in the claim-level datasets. |
| Gender disaggregation | Partial | Supporting | Beneficiary demographics are in the SSDI Annual Statistical Report (US-GOV-SSA-1667); no claim-level dataset is described with a sex breakdown. |
| Race and ethnicity data | **None** | Critical | No SSA dataset on Data.gov reports race or ethnicity (see search evidence). |
| Income and economic status of applicants and recipients | **Proxy** | Critical | The only source is a one-time 2001–2002 survey of SSI children and families, including applicants (US-GOV-SSA-328). No adult or current data on applicant or recipient income. |
| Impairment/diagnosis categories | Partial | Supporting | Beneficiary statistics are in the SSDI Annual Statistical Report (US-GOV-SSA-1667); no claim-level dataset is described with diagnosis categories. |
| Disability program allowance rates | Partial | Critical | Allowances are published by state for initial and reconsideration decisions (US-GOV-SSA-307, -308) and by judge and hearing office for hearings (US-GOV-SSA-299); the levels are not linked and nothing goes below state level. |
| Reasons for claim denials | **None** | Critical | No SSA dataset on Data.gov reports denial reasons (see search evidence). |
| Application volumes | Full | Supporting | Initial claim receipts are published by state, monthly from October 2000 (US-GOV-SSA-307) and by fiscal year (US-GOV-SSA-308). |
| Benefit amounts by geography and demographics | Partial | Supporting | Benefit statistics are in the state/county and annual SSDI reports (US-GOV-SSA-3378, -1667); which amount breakdowns they include has not been checked against the tables. |
| Beneficiary/recipient counts | Full | Supporting | Beneficiary and recipient counts are published annually by state and county (US-GOV-SSA-3378, -3414). |
| Appeals and hearing outcomes | Partial | Supporting | Hearing outcomes by judge and office (US-GOV-SSA-299), hearing workloads and waits (US-GOV-SSA-303, -304) and reconsideration outcomes by state (US-GOV-SSA-307) are published; Appeals Council and court outcomes are not in the catalog. |
| Work incentive program participation | Partial | Supporting | Ticket assignments were released for FY2011–2017 only (US-GOV-SSA-1915); survey statistics on program participation exist for 2015 and 2019 (US-GOV-SSA-3379). |
| Return-to-work outcomes | **Proxy** | Critical | Only one-time descriptive sources exist: a 2015 chartbook on work activity before and after award (US-GOV-SSA-2278) and survey statistics for 2015 and 2019 (US-GOV-SSA-3379). No ongoing outcome series. |
| Agency performance metrics | Partial | Supporting | Processing times (US-GOV-SSA-1409, -1768, -304) and DDS decision accuracy (US-GOV-SSA-344) are published; performance targets are not in the catalog. |
| SSI program data | Partial | Supporting | Recipients, federal payments and state supplementation are published annually by state and county (US-GOV-SSA-3414); no monthly or recipient-level detail. |
| SSDI program data | Partial | Supporting | Beneficiaries are published by state and county (US-GOV-SSA-3378) and in the annual SSDI report (US-GOV-SSA-1667); both are annual. |
| Geographic distribution of disability service access | Partial | Critical | Office locations (US-GOV-SSA-1733) can be joined to county beneficiary counts (US-GOV-SSA-3378, -3414), but there are no service areas, travel times or per-office demand to measure access directly. |
| Travel distance to nearest SSA field office | **None** | Critical | No SSA dataset on Data.gov reports travel distance or time (see search evidence). |
| Field office service area boundaries | **None** | Supporting | No SSA dataset on Data.gov defines field office service areas (see search evidence). |
| Accessibility accommodations at field offices | **None** | Supporting | No SSA dataset on Data.gov describes accessibility or accommodations at field offices; only national interpreter call counts exist (see search evidence). |
| Disability application counts by county | **Proxy** | Supporting | Applications are published by state only (US-GOV-SSA-307, -308), a proxy for county detail. |

---

## Measuring the Engine

`eval/benchmark_questions.yaml` holds reviewed benchmark questions with the expected
rating and the datasets that must be cited; `tests/test_benchmark.py` runs every one.
Expectations are reviewed against the grounded catalog, with the reason recorded in
the YAML — when the catalog or rubric changes, re-review the expectation rather than
tuning patterns until the numbers match. `tests/test_rubric_and_matching.py` checks
that paraphrases of key questions reach the same core elements.

---

## Extending the Framework

To add coverage for a new data topic:

1. Find the dataset on Data.gov, add it to `data/catalog_sources.json`, run `python scripts/sync_catalog.py`, and add curated notes in `dataset_catalog_service.py`
2. Add an entry to `_COVERAGE_KB` with a rating, a rationale citing the record, and patterns
3. If you rate an element **None**, add its searches to `data/gap_evidence.json` and run `python scripts/check_gap_claims.py`
4. Add a benchmark question to `eval/benchmark_questions.yaml` and run `pytest`
