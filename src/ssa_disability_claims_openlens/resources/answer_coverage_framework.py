"""
Resource: answer_coverage_framework

How Answer Coverage is scored, in plain language. The numbers in this document
(rating thresholds, element points, cap limits) are read from the same settings
and constants the scoring engine uses, so the document cannot drift from the
engine's behaviour. mcp_tests/ also checks the worked example against a live
evaluation.
"""

from __future__ import annotations

from fastmcp import FastMCP

from ..config import get_settings
from ..services.answer_coverage_service import _CRITICAL_CAP, _QUALITY_SCORE

_ELEMENT_MEANINGS = {
    "Full": "A catalogued dataset measures it directly, at the detail the question needs, and is current.",
    "Partial": "Catalogued datasets measure it, but miss a needed level, breakdown or time period.",
    "Proxy": "Only indirect, one-time, historical or discontinued data exists.",
    "None": "No SSA dataset on Data.gov provides it. Backed by recorded Data.gov searches.",
}


def _levels_table() -> str:
    s = get_settings()
    rows = [
        ("Complete", f"{s.coverage_complete_threshold:g} to 100", "The question can be answered directly from public data"),
        ("High", f"{s.coverage_high_threshold:g} to under {s.coverage_complete_threshold:g}", "Most of the information is published; minor gaps remain"),
        ("Partial", f"{s.coverage_partial_threshold:g} to under {s.coverage_high_threshold:g}", "Part of the answer is possible; important gaps remain"),
        ("Limited", f"{s.coverage_limited_threshold:g} to under {s.coverage_partial_threshold:g}", "The information the question needs most is missing or only indirect"),
        ("Unsupported", f"0 to under {s.coverage_limited_threshold:g}", "The question cannot be answered from SSA public data"),
    ]
    lines = ["| Rating | Score | Meaning |", "|--------|-------|---------|"]
    lines += [f"| {r} | {score} | {meaning} |" for r, score, meaning in rows]
    return "\n".join(lines)


def _points_table() -> str:
    lines = ["| Rating | Points | Meaning |", "|--------|--------|---------|"]
    for quality in ("Full", "Partial", "Proxy", "None"):
        lines.append(f"| {quality} | {_QUALITY_SCORE[quality]:g} | {_ELEMENT_MEANINGS[quality]} |")
    return "\n".join(lines)


def _cap_table() -> str:
    lines = [
        "| Best-rated critical element | Highest rating allowed | Score capped at |",
        "|-----------------------------|------------------------|-----------------|",
    ]
    for quality in ("None", "Proxy", "Partial"):
        limit, rating = _CRITICAL_CAP[quality]
        lines.append(f"| {quality} | {rating} | {limit:g} |")
    lines.append("| Full | No cap | No cap |")
    return "\n".join(lines)


def build_framework_doc() -> str:
    """Render the framework document from the engine's live settings and constants."""
    return f"""# Answer Coverage Framework
## SSA Disability Claims OpenLens

Answer Coverage measures how well SSA's public datasets support answering a
question. It rates the data, not the question: a Limited rating means SSA does
not publish what the question needs, and the report says what to publish.

## Coverage Ratings

{_levels_table()}

## How a Question Is Scored

### Step 1: Work out what information the question needs

The question is matched against a curated list of SSA data topics, which
produces a set of information elements. Each element is either:

- **Critical**: the question cannot be answered without it. Counts double.
- **Supporting**: useful context that improves the answer. Counts once.

### Step 2: Rate each element

{_points_table()}

Every rating comes with a written reason that cites the Data.gov records it is
based on. The report shows these in its **How Answer Coverage Was Rated** table.

### Step 3: Take the weighted average

```
Score = sum of (points x weight) / sum of weights x 100
```

### Step 4: The specific element beats the general one

If the question asks for something at a finer level than a broad element
measures, for example decision times *per office* rather than national
processing times, the specific element is the critical one and the broad
element becomes supporting. A national average cannot stand in for the
per-office figure the question asks for.

### Step 5: The critical-element cap

A question cannot be rated higher than its best critical element allows:

{_cap_table()}

Without the cap, well-published background information could make a question
look answerable when its core is not. For example, knowing where every field
office is does not tell you which one has the longest waits. When the cap
lowers a rating, the report ends its **How Answer Coverage Was Rated** section
with a **Why <rating>** line that names the critical elements.

## Worked Example

**Question**: Which field offices have the longest decision wait times?

| Information needed | Type | Rating | Points |
|--------------------|------|--------|--------|
| Disability decision times by field office or DDS | Critical | Proxy | 0.3 |
| Field office operational metrics (staffing, volume, wait times) | Critical | Proxy | 0.3 |
| Disability claim processing times | Supporting (Step 4) | Partial | 0.6 |
| SSA field office locations and coverage | Supporting | Full | 1.0 |

- Weighted average: (0.3 x 2 + 0.3 x 2 + 0.6 + 1.0) / 6 = **46.7**, which alone would be **Partial**.
- Both critical elements are Proxy, so the cap applies: the score becomes **39** and the rating **Limited**.

## Reading the Report

- **Missing Information**: elements that are not published, or are published only indirectly.
- **Gap Analysis**: *Not published* lists elements rated None, each with the Data.gov search
  behind it; *Only partly available* lists elements rated Partial or Proxy. Elements the
  question cannot be answered without are marked *(critical)*.
- **How Answer Coverage Was Rated**: every element, its rating and the reason, citing source records.
- **Transparency Recommendations**: what SSA could publish to close each gap, grouped by category,
  each with the gap it closes and why. The recommend_transparency_improvements tool adds a priority
  and the expected public impact.

## How Recommendations Are Prioritized

A recommendation's priority depends on the gap it closes: how far short of Full the
element is (None, then Proxy, then Partial) and whether it is critical.

| Gap the recommendation closes | Priority |
|-------------------------------|----------|
| Critical, rated None or Proxy | High |
| Supporting, rated None | High |
| Critical, rated Partial | Medium |
| Supporting, rated Proxy | Medium |
| Supporting, rated Partial | Low |

Each gap's strongest recommendation comes first. A second recommendation for the same
gap is a follow-up and drops one level, so the top of the list covers as many gaps as
possible. Every recommendation states the reason for its priority.

## What the Assessment Is Based On

Official dataset metadata (SSA's own Data.gov records), recorded Data.gov
searches for every "no data" claim, and curated analyst notes. Dataset
contents are not downloaded or inspected, so a rating describes what SSA
publishes, not what the numbers inside the datasets say.
"""


def register(mcp: FastMCP) -> None:  # noqa: D103
    @mcp.resource(
        uri="openlens://framework/answer-coverage",
        name="answer_coverage_framework",
        description=(
            "How Answer Coverage is scored: the ratings, how each piece of information is "
            "rated and weighted, the critical-element cap, a worked example and how to read "
            "the report. Read this to understand or explain any coverage rating."
        ),
        mime_type="text/markdown",
    )
    def answer_coverage_framework() -> str:
        """Return the Answer Coverage framework documentation."""
        return build_framework_doc()
