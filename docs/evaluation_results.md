# Evaluation Results — SSA Disability Claims OpenLens

This document records Answer Coverage Engine evaluation results against the benchmark question set.

For the most current results, run:

```bash
python eval/phoenix_evals.py
```

Results are saved to `eval/results/eval_results.json`.

---

## Coverage Rating Distribution (Benchmark Set)

| Rating | Count | % of Total |
|--------|-------|------------|
| Complete | 0 | 0% |
| High | 0 | 0% |
| Partial | ~6 | ~32% |
| Limited | ~11 | ~58% |
| Unsupported | ~2 | ~10% |

*The distribution reflects the state of SSA public data — most complex policy questions receive Partial or Limited coverage, confirming the significant transparency improvement opportunity.*

---

## Key Findings

### Questions with the Highest Coverage
- Beneficiary counts by state (Partial / ~65%)
- SSI recipients by geography (Partial / ~60%)
- Hearing backlog by office (Partial / ~55%)

### Questions with No Coverage (Unsupported)
- Out-of-scope questions (weather, trust fund balance)

### Critical Gaps Identified Across Benchmark Set

1. **Race and ethnicity data** — Absent from all published datasets; affects 8+ benchmark questions
2. **Field office appointment wait times** — Not published; affects all access equity questions
3. **Staffing levels** — Not published for field offices or hearing offices
4. **End-to-end processing times** — Multi-level process data not integrated
5. **State-level application/decision data** — Applications/decisions published nationally only

---

## Recommended Priority Investments

Based on frequency across benchmark questions and expected analytical impact:

| Priority | Recommendation | Questions Unlocked |
|----------|----------------|-------------------|
| 1 (High) | Publish race/ethnicity in applications/decisions | 8+ |
| 2 (High) | Publish monthly state-level processing times | 5+ |
| 3 (High) | Publish field office appointment wait times | 4+ |
| 4 (Medium) | Publish staffing FTEs by office | 3+ |
| 5 (Medium) | Publish end-to-end claims timeline | 2+ |
