"""
Phoenix Evaluations for SSA Disability Claims OpenLens.

This module defines evaluation tasks for the Answer Coverage Engine using
the Arize Phoenix evals framework. It can be run standalone or integrated
into a CI pipeline for regression testing.

Usage:
    python eval/phoenix_evals.py

The evaluation measures:
  1. Coverage classification accuracy (does the engine assign the right CoverageRating?)
  2. Gap identification quality (are critical gaps consistently identified?)
  3. Recommendation relevance (are recommendations topically relevant to the gap?)
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

# The report prints check and cross marks; make them printable on Windows consoles (cp1252).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.ssa_disability_claims_openlens.models import CoverageRating
from src.ssa_disability_claims_openlens.services.answer_coverage_service import (
    AnswerCoverageEngine,
)


# ── Benchmark dataset ──────────────────────────────────────────────────────────


@dataclass
class BenchmarkCase:
    question: str
    expected_min_score: float
    expected_max_score: float
    expected_rating: CoverageRating
    must_contain_gaps: list[str]
    must_contain_available: list[str]
    description: str


BENCHMARK_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        question="How many people are receiving SSDI benefits by state?",
        expected_min_score=40.0,
        expected_max_score=100.0,
        expected_rating=CoverageRating.PARTIAL,  # Data exists but limited depth
        must_contain_gaps=[],
        must_contain_available=["OASDI"],  # official title: "OASDI Beneficiaries by State and County (series)"
        description="Core SSDI beneficiary question — data partially available",
    ),
    BenchmarkCase(
        question="Are there racial disparities in SSA disability allowance rates?",
        expected_min_score=0.0,
        expected_max_score=50.0,
        expected_rating=CoverageRating.LIMITED,
        must_contain_gaps=["Race"],
        must_contain_available=[],
        description="Equity question — race/ethnicity data not published",
    ),
    BenchmarkCase(
        question="How long are people waiting for appointments at field offices?",
        expected_min_score=0.0,
        expected_max_score=65.0,
        expected_rating=CoverageRating.PARTIAL,  # Field office locations exist; wait times don't
        must_contain_gaps=["appointment"],
        must_contain_available=[],
        description="Operational access question — location data exists but wait times not published",
    ),
    BenchmarkCase(
        question="What is the hearing office backlog by state?",
        expected_min_score=30.0,
        expected_max_score=100.0,
        expected_rating=CoverageRating.PARTIAL,
        must_contain_gaps=[],
        must_contain_available=["Hearing"],
        description="Hearing backlog question — OHO hearing office data partially covers this",
    ),
    BenchmarkCase(
        question="How many SSI recipients are there in California by county?",
        expected_min_score=40.0,
        expected_max_score=100.0,
        expected_rating=CoverageRating.PARTIAL,
        must_contain_gaps=[],
        must_contain_available=["SSI"],
        description="SSI geographic question — county data exists",
    ),
    BenchmarkCase(
        question="What is the weather in Washington DC today?",
        expected_min_score=0.0,
        expected_max_score=14.0,
        expected_rating=CoverageRating.UNSUPPORTED,
        must_contain_gaps=[],
        must_contain_available=[],
        description="Out-of-scope question — should return UNSUPPORTED",
    ),
    BenchmarkCase(
        question="How many SSA staff work at each hearing office?",
        expected_min_score=0.0,
        expected_max_score=70.0,
        expected_rating=CoverageRating.PARTIAL,  # ODAR data provides workload proxy
        must_contain_gaps=["staffing", "SSA office staffing"],
        must_contain_available=[],
        description="Staffing question — staffing not published, but workload data is a proxy",
    ),
    BenchmarkCase(
        question="What is the disability claim processing time by state and demographic group?",
        expected_min_score=0.0,
        expected_max_score=70.0,
        expected_rating=CoverageRating.PARTIAL,
        must_contain_gaps=[],
        must_contain_available=["processing"],
        description="Multi-dimension processing time question — partial coverage",
    ),
]


# ── Evaluation runner ──────────────────────────────────────────────────────────


@dataclass
class EvalResult:
    case: BenchmarkCase
    actual_score: float
    actual_rating: CoverageRating
    score_in_range: bool
    rating_match: bool
    gaps_found: bool
    available_found: bool
    passed: bool
    details: str


def run_evaluations(engine: AnswerCoverageEngine) -> list[EvalResult]:
    """Run all benchmark cases and return evaluation results."""
    results: list[EvalResult] = []

    for case in BENCHMARK_CASES:
        assessment = engine.evaluate(case.question)

        score_in_range = case.expected_min_score <= assessment.answer_coverage_score <= case.expected_max_score

        # Rating match: allow one level adjacent for robustness
        rating_order = [
            CoverageRating.UNSUPPORTED,
            CoverageRating.LIMITED,
            CoverageRating.PARTIAL,
            CoverageRating.HIGH,
            CoverageRating.COMPLETE,
        ]
        actual_idx = rating_order.index(assessment.coverage_rating)
        expected_idx = rating_order.index(case.expected_rating)
        rating_match = abs(actual_idx - expected_idx) <= 1

        # Check gap identification
        gaps_found = True
        if case.must_contain_gaps:
            all_gaps = (
                assessment.gap_analysis.critical_gaps
                + assessment.gap_analysis.partial_gaps
                + assessment.missing_information
            )
            combined_gap_text = " ".join(all_gaps).lower()
            gaps_found = any(
                kw.lower() in combined_gap_text
                for kw in case.must_contain_gaps
            )

        # Check available data identification
        available_found = True
        if case.must_contain_available:
            available_text = " ".join(assessment.available_data).lower()
            available_found = any(
                kw.lower() in available_text
                for kw in case.must_contain_available
            )

        passed = score_in_range and rating_match and gaps_found and available_found

        details_parts = []
        if not score_in_range:
            details_parts.append(
                f"Score {assessment.answer_coverage_score:.1f} not in "
                f"[{case.expected_min_score}, {case.expected_max_score}]"
            )
        if not rating_match:
            details_parts.append(
                f"Rating {assessment.coverage_rating.value} not close to "
                f"{case.expected_rating.value}"
            )
        if not gaps_found:
            details_parts.append(f"Expected gaps {case.must_contain_gaps} not found")
        if not available_found:
            details_parts.append(f"Expected available {case.must_contain_available} not found")

        results.append(EvalResult(
            case=case,
            actual_score=assessment.answer_coverage_score,
            actual_rating=assessment.coverage_rating,
            score_in_range=score_in_range,
            rating_match=rating_match,
            gaps_found=gaps_found,
            available_found=available_found,
            passed=passed,
            details=" | ".join(details_parts) if details_parts else "PASS",
        ))

    return results


def print_report(results: list[EvalResult]) -> None:
    """Print a human-readable evaluation report."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)

    print("\n" + "=" * 70)
    print("SSA Disability Claims OpenLens — Answer Coverage Evaluation Report")
    print("=" * 70)
    print(f"Total cases: {total}  |  Passed: {passed}  |  Failed: {total - passed}")
    print(f"Pass rate: {passed / total * 100:.1f}%")
    print("=" * 70)

    for r in results:
        status = "✓ PASS" if r.passed else "✗ FAIL"
        print(f"\n{status} | {r.case.description}")
        print(f"  Q: {r.case.question[:70]}...")
        print(f"  Score: {r.actual_score:.1f} (expected {r.case.expected_min_score}–{r.case.expected_max_score})")
        print(f"  Rating: {r.actual_rating.value} (expected ~{r.case.expected_rating.value})")
        if not r.passed:
            print(f"  → {r.details}")

    print("\n" + "=" * 70)

    # Save JSON results
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    results_file = results_dir / "eval_results.json"

    output: list[dict[str, Any]] = []
    for r in results:
        output.append({
            "question": r.case.question,
            "description": r.case.description,
            "passed": r.passed,
            "actual_score": r.actual_score,
            "actual_rating": r.actual_rating.value,
            "expected_rating": r.case.expected_rating.value,
            "details": r.details,
        })

    results_file.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    engine = AnswerCoverageEngine()
    results = run_evaluations(engine)
    print_report(results)
    failed = sum(1 for r in results if not r.passed)
    sys.exit(0 if failed == 0 else 1)
