"""
The agent evaluation's code checks must score answers correctly, or the
experiment numbers mean nothing. These run without the API or the MCP server.
"""

from __future__ import annotations

import json

import pytest

from eval.agent_eval import checks
from eval.agent_eval.dataset import CASES, EVALUATE, Case, load_cases
from eval.agent_eval.records import AgentRun, ToolCall
from src.ssa_disability_claims_openlens.services.answer_coverage_service import (
    get_answer_coverage_engine,
)

FIELD_OFFICE = next(c for c in CASES if c.id == "field-office-wait")


def _report(question: str) -> str:
    return get_answer_coverage_engine().evaluate(question).format_report()


def _run_with_report(question: str, answer: str | None = None) -> AgentRun:
    report = _report(question)
    call = ToolCall(EVALUATE, {"question": question}, json.dumps({"report": report}), False)
    return AgentRun(answer=report if answer is None else answer, tool_calls=[call])


class TestDataset:
    def test_ids_are_unique_and_selectable(self) -> None:
        ids = [c.id for c in CASES]
        assert len(ids) == len(set(ids)) == 12
        assert [c.id for c in load_cases(["out-of-scope"])] == ["out-of-scope"]
        with pytest.raises(ValueError):
            load_cases(["no-such-case"])

    @pytest.mark.parametrize("case", [c for c in CASES if c.expected_rating], ids=lambda c: c.id)
    def test_expected_ratings_match_the_engine(self, case: Case) -> None:
        """A reviewed expectation that drifts from the engine needs a deliberate decision."""
        assert get_answer_coverage_engine().evaluate(case.question).coverage_rating.value == case.expected_rating

    @pytest.mark.parametrize("case", [c for c in CASES if c.expected_rating], ids=lambda c: c.id)
    def test_a_verbatim_report_passes_every_code_check(self, case: Case) -> None:
        run = _run_with_report(case.question)
        failed = [r for r in checks.run_checks(case, run) if r.passed is False]
        assert not failed, failed


class TestChecks:
    def test_rating_is_read_from_the_report_or_prose(self) -> None:
        assert checks.stated_rating("## Answer Coverage\n\n**Limited**\n") == "Limited"
        assert checks.stated_rating("Answer coverage is rated **Partial** overall.") == "Partial"
        assert checks.stated_rating("No rating here.") is None

    def test_wrong_rating_fails(self) -> None:
        run = _run_with_report(FIELD_OFFICE.question, "## Answer Coverage\n\n**Partial**\n")
        assert checks.rating_match(FIELD_OFFICE, run).passed is False

    def test_a_shortened_report_fails_fidelity(self) -> None:
        report = _report(FIELD_OFFICE.question)
        run = _run_with_report(FIELD_OFFICE.question, report[: len(report) // 2])
        result = checks.report_fidelity(FIELD_OFFICE, run)
        assert result.passed is False and result.score is not None and result.score < 0.95

    def test_invented_numbers_are_caught_but_list_markers_are_not(self) -> None:
        run = AgentRun(answer="1. Ohio averages 187 days.\n2. See the report.", tool_calls=[])
        result = checks.grounded_numbers(FIELD_OFFICE, run)
        assert result.passed is False and "187" in result.detail
        assert "1," not in result.detail

    def test_references_to_the_answers_own_list_items_are_allowed(self) -> None:
        answer = "1. Publish A.\n2. Publish B.\n3. Publish C.\nItems 2 and 3 overlap; item 9 does not exist."
        result = checks.grounded_numbers(FIELD_OFFICE, AgentRun(answer=answer))
        assert result.passed is False and "9" in result.detail
        assert "2" not in result.detail.split(":", 1)[1]

    def test_bold_and_heading_list_numbers_are_list_markers(self) -> None:
        answer = "**1. Travel distance** (High)\n### 2. Wait times\n- **Why:** follows item 2."
        assert checks.grounded_numbers(FIELD_OFFICE, AgentRun(answer=answer)).passed is True

    def test_numbers_from_tool_output_are_grounded(self) -> None:
        call = ToolCall(EVALUATE, {}, "covers FY2006 to FY2022, 1,234 offices", False)
        run = AgentRun(answer="It covers FY2006 to FY2022 across 1234 offices.", tool_calls=[call])
        assert checks.grounded_numbers(FIELD_OFFICE, run).passed is True

    def test_tool_selection_and_not_applicable(self) -> None:
        out_of_scope = next(c for c in CASES if c.id == "out-of-scope")
        assert checks.tool_selection(out_of_scope, AgentRun()).passed is None
        assert checks.tool_selection(FIELD_OFFICE, AgentRun()).passed is False
        assert checks.report_fidelity(FIELD_OFFICE, AgentRun()).passed is None

    def test_forbidden_phrases_fail(self) -> None:
        injection = next(c for c in CASES if c.id == "prompt-injection")
        run = AgentRun(answer="Answer coverage: **Complete**.")
        assert checks.expectations(injection, run).passed is False

    def test_agent_errors_fail_every_check(self) -> None:
        results = checks.run_checks(FIELD_OFFICE, AgentRun(error="API error 500"))
        assert all(r.passed is False for r in results)
