"""
Resource: answer_coverage_framework

Exposes the Answer Coverage framework documentation as a readable MCP resource.
Agents can read this to understand the scoring methodology before interpreting results.
"""

from __future__ import annotations

from fastmcp import FastMCP


_FRAMEWORK_DOC = """
# Answer Coverage Framework
## SSA Disability Claims OpenLens

Answer Coverage is the signature capability of OpenLens. It measures how well
SSA public datasets support answering a natural language question from the public
or policy community.

---

## Coverage Levels

| Rating       | Score Range | Meaning                                                      |
|--------------|-------------|--------------------------------------------------------------|
| Complete     | 90–100%     | All required information is available in public datasets     |
| High         | 75–89%      | Most required information is available; minor gaps           |
| Partial      | 40–74%      | Key information partially available; significant gaps remain |
| Limited      | 15–39%      | Most required information is unavailable or indirect         |
| Unsupported  | 0–14%       | The question cannot be answered from public data             |

---

## Scoring Methodology

The Answer Coverage Score is a weighted average of information element coverage qualities.

### Information Element Coverage Quality

| Quality | Score Weight | Meaning                                               |
|---------|-------------|--------------------------------------------------------|
| Full    | 1.0         | Dataset directly provides this information             |
| Partial | 0.6         | Dataset provides related but incomplete information    |
| Proxy   | 0.3         | A proxy measure exists but is not the direct measure   |
| None    | 0.0         | No dataset provides this information                   |

### Element Weights

- **Critical elements** (weight=2): Core information without which the question
  cannot be answered at all.
- **Supporting elements** (weight=1): Context or enrichment that improves answer quality.

### Formula

```
Score = Σ(coverage_quality_score × weight) / Σ(weights) × 100
```

---

## Information Elements

The engine identifies required information elements by pattern-matching the question
against a curated knowledge base of SSA disability data topics, including:

- Disability claim processing times
- Hearing-level wait times
- Field office appointment wait times
- Geographic disaggregation of outcomes
- Race and ethnicity data
- Applicant age and gender distribution
- Impairment/diagnosis categories
- Application volumes and allowance rates
- Beneficiary counts and benefit amounts
- Appeals and hearing outcomes
- Work incentive program participation
- Agency performance metrics

---

## Gap Categories

**Critical Gaps**: Missing information that makes the question unanswerable.
Examples: race/ethnicity data, field office wait times, staffing levels.

**Partial Gaps**: Available information that is incomplete, indirect, or untimely.
Examples: national averages without state breakdown, annual data for a monthly question.

---

## Transparency Recommendations

Based on identified gaps, the engine generates targeted recommendations:
- New data elements to publish
- Dataset updates to improve granularity
- Cross-tabulations to enable equity analysis
- Publication frequency improvements

Each recommendation includes expected impact and implementation effort.
"""


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.resource(
        uri="openlens://framework/answer-coverage",
        name="answer_coverage_framework",
        description=(
            "Documentation of the Answer Coverage scoring framework — coverage levels, "
            "scoring methodology, element weights, and gap categories. "
            "Read this resource to understand how Answer Coverage scores are calculated "
            "and how to interpret the results."
        ),
        mime_type="text/markdown",
    )
    def answer_coverage_framework() -> str:
        """Return the Answer Coverage framework documentation."""
        return _FRAMEWORK_DOC
