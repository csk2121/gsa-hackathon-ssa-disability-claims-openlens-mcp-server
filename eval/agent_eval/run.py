"""
Run one experiment: the agent answers every case, then each answer is scored.

    python -m eval.agent_eval.run --check-setup           # server and dataset; no model calls
    python -m eval.agent_eval.run --prompt v01            # full experiment
    python -m eval.agent_eval.run --prompt v02 --cases rural-access,field-office-wait

Backends:
  claude-code  (default) headless Claude Code (`claude -p`) on the Claude
               subscription the CLI is signed in with. No API credit needed.
  api          the Messages API; needs ANTHROPIC_API_KEY with credit (.env).

Results go to eval/results/agent/<name>.json and the report is rebuilt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .agent import DEFAULT_MODEL, PROMPTS_DIR, ROOT, OpenLensSession
from .checks import CheckResult, run_checks
from .dataset import DATASET_NAME, Case, load_cases
from .judges import DEFAULT_JUDGE_MODEL, JUDGES, Ask, api_asker, claude_code_asker
from .records import AgentRun

RESULTS_DIR = ROOT / "eval" / "results" / "agent"

# USD per million tokens (input, output), for the API backend's cost estimate.
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-haiku-5-5": (0.10, 0.50),
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

Answer = Callable[[Case], Awaitable[AgentRun]]


def _summarise(records: list[dict[str, Any]], model: str, backend: str) -> dict[str, Any]:
    evaluators: dict[str, dict[str, float]] = {}
    for rec in records:
        for res in rec["checks"] + rec["judges"]:
            if res["passed"] is None:
                continue
            stats = evaluators.setdefault(res["name"], {"applicable": 0, "passed": 0, "score_sum": 0.0})
            stats["applicable"] += 1
            stats["passed"] += int(res["passed"])
            stats["score_sum"] += res["score"]
    for stats in evaluators.values():
        stats["score"] = round(stats.pop("score_sum") / stats["applicable"], 3)

    n = len(records) or 1
    input_tokens = sum(r["run"]["input_tokens"] for r in records)
    output_tokens = sum(r["run"]["output_tokens"] for r in records)
    if backend == "claude-code":
        cost = sum(r["run"]["cost_usd"] for r in records)  # Claude Code's API-equivalent figure
    else:
        price_in, price_out = PRICES.get(model, (0.0, 0.0))
        cost = (input_tokens * price_in + output_tokens * price_out) / 1e6
    passed = sum(1 for r in records if r["passed"])
    return {
        "cases": len(records),
        "cases_passed": passed,
        "pass_rate": round(passed / n, 3),
        "evaluators": evaluators,
        "avg_latency_s": round(sum(r["run"]["latency_s"] for r in records) / n, 2),
        "avg_tokens": round((input_tokens + output_tokens) / n),
        "avg_tool_calls": round(sum(len(r["run"]["tool_calls"]) for r in records) / n, 2),
        "agent_cost_usd": round(cost, 4),
        "cost_is_billed": backend == "api",
        "errors": sum(1 for r in records if r["run"]["error"]),
    }


def _record(case: Case, run: AgentRun, results: list[CheckResult]) -> dict[str, Any]:
    judge_names = {j.__name__ for j in JUDGES}
    applicable = [r for r in results if r.passed is not None]
    return {
        "id": case.id,
        "capability": case.capability,
        "question": case.question,
        "passed": bool(applicable) and all(r.passed for r in applicable),
        "run": {**asdict(run), "tools_called": run.tools_called},
        "checks": [asdict(r) for r in results if r.name not in judge_names],
        "judges": [asdict(r) for r in results if r.name in judge_names],
    }


async def _evaluate(
    cases: list[Case], answer: Answer, ask: Ask | None, concurrency: int
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(concurrency)

    async def one(case: Case) -> dict[str, Any]:
        async with semaphore:
            run = await answer(case)
            results = run_checks(case, run)
            if ask is not None and not run.error:
                results += await asyncio.gather(*(judge(ask, case, run) for judge in JUDGES))
        record = _record(case, run, results)
        marks = " ".join(
            f"{r.name}={'pass' if r.passed else 'FAIL'}" for r in results if r.passed is not None
        )
        status = "ERROR" if run.error else "PASS" if record["passed"] else "FAIL"
        print(f"  {status:5} {case.id:26} {run.latency_s:5.1f}s  {marks}", flush=True)
        if run.error:
            print(f"        {run.error[:200]}", flush=True)
        return record

    return list(await asyncio.gather(*(one(c) for c in cases)))


async def run_experiment(args: argparse.Namespace) -> Path:
    cases = load_cases(args.cases.split(",") if args.cases else None, args.limit)
    prompt_file = PROMPTS_DIR / f"system_prompt_{args.prompt}.txt"
    if not prompt_file.is_file():
        raise SystemExit(f"No system prompt {prompt_file.name} in {PROMPTS_DIR}")
    system_prompt = prompt_file.read_text(encoding="utf-8").strip()
    name = args.name or f"{args.prompt}-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    print(
        f"Experiment {name}: {len(cases)} cases, prompt {args.prompt}, "
        f"agent {args.model}, backend {args.backend}",
        flush=True,
    )
    started = datetime.now(UTC)

    if args.backend == "claude-code":
        from . import claude_code

        async def answer_cc(case: Case) -> AgentRun:
            return await claude_code.run_question(case.question, prompt_file, args.model)

        ask = None if args.no_judges else claude_code_asker(args.judge_model)
        records = await _evaluate(cases, answer_cc, ask, args.concurrency)
    else:
        import anthropic

        from .agent import run_question

        client = anthropic.AsyncAnthropic()
        ask = None if args.no_judges else api_asker(client, args.judge_model)
        async with OpenLensSession() as session:

            async def answer_api(case: Case) -> AgentRun:
                return await run_question(session, client, case.question, system_prompt, args.model)

            records = await _evaluate(cases, answer_api, ask, args.concurrency)

    experiment = {
        "name": name,
        "dataset": DATASET_NAME,
        "prompt_version": args.prompt,
        "backend": args.backend,
        "agent_model": args.model,
        "judge_model": None if args.no_judges else args.judge_model,
        "started_at": started.isoformat(timespec="seconds"),
        "summary": _summarise(records, args.model, args.backend),
        "cases": records,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name}.json"
    path.write_text(json.dumps(experiment, indent=2), encoding="utf-8")

    s = experiment["summary"]
    cost_label = "agent cost" if s["cost_is_billed"] else "API-equivalent agent cost (not billed)"
    print(
        f"\n{s['cases_passed']}/{s['cases']} cases passed ({s['pass_rate']:.0%}) | "
        f"avg latency {s['avg_latency_s']}s | avg tokens {s['avg_tokens']} | "
        f"{cost_label} ${s['agent_cost_usd']}"
    )
    for evaluator, stats in s["evaluators"].items():
        print(f"  {evaluator:18} {stats['passed']:>2}/{stats['applicable']:<2} score {stats['score']:.2f}")
    print(f"Saved {path.relative_to(ROOT)}")
    return path


def rescore_saved() -> int:
    """Re-run the code checks on every saved experiment's answers (judge verdicts are kept).

    The checks are deterministic, so after a check changes this puts every
    experiment on the same footing without calling a model again.
    """
    from dataclasses import fields

    from .records import ToolCall

    cases = {c.id: c for c in load_cases()}
    run_fields = {f.name for f in fields(AgentRun)}
    for path in sorted(RESULTS_DIR.glob("*.json")):
        experiment = json.loads(path.read_text(encoding="utf-8"))
        if "cases" not in experiment:
            continue
        records = []
        for rec in experiment["cases"]:
            saved = {k: v for k, v in rec["run"].items() if k in run_fields}
            saved["tool_calls"] = [ToolCall(**t) for t in saved.get("tool_calls", [])]
            run = AgentRun(**saved)
            judges = [CheckResult(**j) for j in rec["judges"]]
            records.append(_record(cases[rec["id"]], run, run_checks(cases[rec["id"]], run) + judges))
        experiment["cases"] = records
        experiment["summary"] = _summarise(records, experiment["agent_model"], experiment.get("backend", "api"))
        path.write_text(json.dumps(experiment, indent=2), encoding="utf-8")
        s = experiment["summary"]
        print(f"Rescored {path.name}: {s['cases_passed']}/{s['cases']} cases pass")
    return 0


async def check_setup(backend: str) -> int:
    cases = load_cases()
    prompts = sorted(p.stem.removeprefix("system_prompt_") for p in PROMPTS_DIR.glob("system_prompt_*.txt"))
    print(f"Dataset {DATASET_NAME}: {len(cases)} cases")
    print(f"System prompts: {', '.join(prompts)}")
    async with OpenLensSession() as session:
        print(f"MCP server over stdio: {len(session.tools)} tools ({', '.join(t['name'] for t in session.tools)})")
        output, is_error = await session.call("evaluate_answer_coverage", {"question": cases[1].question})
        print(f"Tool call evaluate_answer_coverage: {'error' if is_error else 'ok'} ({len(output)} chars)")
    if backend == "claude-code":
        from .claude_code import ClaudeCodeError, claude_executable

        try:
            print(f"Claude Code CLI: {claude_executable()}")
        except ClaudeCodeError as exc:
            print(f"Claude Code CLI: NOT FOUND ({exc})")
            return 1
        return 0 if not is_error else 1
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(f"ANTHROPIC_API_KEY: {'found' if has_key else 'NOT SET (add it to .env)'}")
    return 0 if has_key and not is_error else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", choices=("claude-code", "api"), default="claude-code")
    parser.add_argument("--prompt", default="v01", help="System prompt version (eval/agent_eval/prompts)")
    parser.add_argument("--name", help="Experiment name (default: <prompt>-<UTC timestamp>)")
    parser.add_argument("--cases", help="Comma-separated case ids to run (default: all)")
    parser.add_argument("--limit", type=int, help="Run only the first N cases")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Agent model (default {DEFAULT_MODEL})")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help=f"Judge model (default {DEFAULT_JUDGE_MODEL})")
    parser.add_argument("--concurrency", type=int, default=3, help="Questions answered at once")
    parser.add_argument("--no-judges", action="store_true", help="Skip the LLM judges (code checks only)")
    parser.add_argument("--check-setup", action="store_true", help="Check server and dataset; no model calls")
    parser.add_argument("--rescore", action="store_true", help="Re-run code checks on saved experiments; no model calls")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    if args.rescore:
        rescore_saved()
        from .report import build_report

        build_report()
        return 0
    if args.check_setup:
        return asyncio.run(check_setup(args.backend))
    if args.backend == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Add it to the project's .env file.", file=sys.stderr)
        return 2
    asyncio.run(run_experiment(args))

    from .report import build_report

    build_report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
