"""
Code evaluators: deterministic checks on one agent answer. No API calls.

Each check returns a CheckResult whose `passed` is None when the check does not
apply to the case (for example, rating_match on a case with no expected rating).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .dataset import EVALUATE, Case
from .records import AgentRun

RATINGS = ("Complete", "High", "Partial", "Limited", "Unsupported")
REPORT_FIDELITY_THRESHOLD = 0.95


@dataclass
class CheckResult:
    name: str
    passed: bool | None
    score: float | None
    detail: str


def _na(name: str, why: str) -> CheckResult:
    return CheckResult(name, None, None, why)


def _result(name: str, passed: bool, detail: str, score: float | None = None) -> CheckResult:
    return CheckResult(name, passed, score if score is not None else float(passed), detail)


def tool_selection(case: Case, run: AgentRun) -> CheckResult:
    """The agent called at least one of the tools the question calls for."""
    if not case.expected_tools:
        return _na("tool_selection", "No tool requirement for this case.")
    called = run.tools_called
    hit = [t for t in case.expected_tools if t in called]
    detail = f"Called: {', '.join(called) or 'no tools'}. Expected one of: {', '.join(case.expected_tools)}."
    return _result("tool_selection", bool(hit), detail)


_RATING_AFTER_HEADING = re.compile(
    r"Answer Coverage[^\n]*\n+\s*\**\s*(" + "|".join(RATINGS) + r")\b", re.IGNORECASE
)
_RATING_ANYWHERE = re.compile(
    r"(?:coverage|rated|rating)\W{0,10}(?:\w+\W{1,3}){0,3}?\**(" + "|".join(RATINGS) + r")\b",
    re.IGNORECASE,
)


def stated_rating(answer: str) -> str | None:
    """The coverage rating the answer states, if any."""
    match = _RATING_AFTER_HEADING.search(answer) or _RATING_ANYWHERE.search(answer)
    return match.group(1).capitalize() if match else None


def rating_match(case: Case, run: AgentRun) -> CheckResult:
    """The answer states exactly the expected coverage rating."""
    if not case.expected_rating:
        return _na("rating_match", "No expected rating for this case.")
    stated = stated_rating(run.answer)
    detail = f"Stated: {stated or 'no rating found'}. Expected: {case.expected_rating}."
    return _result("rating_match", stated == case.expected_rating, detail)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _last_report(run: AgentRun) -> str | None:
    for call in reversed(run.tool_calls):
        if call.name == EVALUATE and not call.is_error:
            try:
                report = json.loads(call.output).get("report")
            except (json.JSONDecodeError, AttributeError):
                return None
            return report if isinstance(report, str) else None
    return None


def report_fidelity(case: Case, run: AgentRun) -> CheckResult:
    """When the coverage tool ran, its report appears in the answer (the tool asks for it verbatim)."""
    report = _last_report(run)
    if report is None:
        return _na("report_fidelity", "evaluate_answer_coverage was not called.")
    answer = _normalise(run.answer)
    lines = [_normalise(line) for line in report.splitlines() if line.strip()]
    kept = sum(1 for line in lines if line in answer)
    share = kept / len(lines) if lines else 1.0
    detail = f"{kept} of {len(lines)} report lines appear in the answer ({share:.0%})."
    return _result("report_fidelity", share >= REPORT_FIDELITY_THRESHOLD, detail, round(share, 3))


_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")
# A numbered item at the start of a line: "1. ", "- 2) ", "**3. ", "### 4. ".
_LIST_MARKER = re.compile(
    r"^\s*(?:[-*]\s+)?(?:#{1,6}\s+)?(?:\*\*|__)?\d+[.)](?:\*\*|__)?\s", re.MULTILINE
)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUMBER.findall(text)}


def _decoded(output: str) -> str:
    """A tool output plus, when it is JSON, its decoded text (so '\\u2013' reads as '–')."""
    try:
        return output + "\n" + json.dumps(json.loads(output), ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return output


def grounded_numbers(case: Case, run: AgentRun) -> CheckResult:
    """Every number in the answer appears in the question or in a tool result.

    The answer's own list numbering is not a claim, and neither is a reference to
    it ("items 2 and 3 overlap"), so the numbers used as list markers are allowed.
    """
    own_items = _numbers(" ".join(_LIST_MARKER.findall(run.answer)))
    answer = _LIST_MARKER.sub(" ", run.answer)
    sources = case.question + "\n" + "\n".join(_decoded(c.output) for c in run.tool_calls)
    invented = sorted(_numbers(answer) - _numbers(sources) - own_items, key=lambda n: (len(n), n))
    if not invented:
        return _result("grounded_numbers", True, "Every number in the answer comes from a tool result.")
    shown = ", ".join(invented[:6]) + (" ..." if len(invented) > 6 else "")
    return _result("grounded_numbers", False, f"Numbers not found in any tool result: {shown}.")


def expectations(case: Case, run: AgentRun) -> CheckResult:
    """Case-specific phrases that must, or must not, appear in the answer."""
    if not case.must_mention and not case.must_not_mention and not case.forbidden_rating:
        return _na("expectations", "No phrase expectations for this case.")
    answer = run.answer.lower()
    missing = [
        phrase for phrase in case.must_mention
        if not any(alt.lower() in answer for alt in phrase.split("|"))
    ]
    forbidden = [phrase for phrase in case.must_not_mention if phrase.lower() in answer]
    problems = (
        [f"missing '{p}'" for p in missing] + [f"contains '{p}'" for p in forbidden]
    )
    if case.forbidden_rating and stated_rating(run.answer) == case.forbidden_rating:
        problems.append(f"states the rating '{case.forbidden_rating}'")
    detail = "; ".join(problems) if problems else "All phrase expectations met."
    return _result("expectations", not problems, detail)


CHECKS = (tool_selection, rating_match, report_fidelity, grounded_numbers, expectations)


def run_checks(case: Case, run: AgentRun) -> list[CheckResult]:
    if run.error:
        return [CheckResult(check.__name__, False, 0.0, f"Agent error: {run.error}") for check in CHECKS]
    return [check(case, run) for check in CHECKS]
