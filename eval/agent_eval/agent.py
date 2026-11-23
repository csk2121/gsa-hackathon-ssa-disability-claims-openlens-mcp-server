"""
The agent under test: Claude answering a question with the OpenLens MCP tools.

The server runs as a real stdio subprocess (`python main.py`), the same way
Claude Code starts it, so the evaluation exercises the actual MCP protocol,
input schemas and error handling. The loop is written by hand rather than with
the SDK tool runner because the evaluators need every tool call, its input and
its full output recorded.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import TracebackType
from typing import Any

import anthropic
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from .records import AgentRun, ToolCall

ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = Path(__file__).parent / "prompts"

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TURNS = 10
# Claude Sonnet 5.5 may decline a request on safety grounds; the server-side
# fallback retries it on another model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def load_system_prompt(version: str) -> str:
    path = PROMPTS_DIR / f"system_prompt_{version}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"No system prompt {path.name} in {PROMPTS_DIR}")
    return path.read_text(encoding="utf-8").strip()


class OpenLensSession:
    """One MCP connection to the server, shared by every question in an experiment."""

    def __init__(self) -> None:
        log_dir = ROOT / "eval" / "results" / "agent"
        log_dir.mkdir(parents=True, exist_ok=True)
        transport = PythonStdioTransport(
            script_path=ROOT / "main.py",
            cwd=str(ROOT),
            log_file=log_dir / "server.log",  # the server's stderr logging, kept off the console
        )
        self.mcp = Client(transport)
        self.tools: list[dict[str, Any]] = []

    async def __aenter__(self) -> OpenLensSession:
        await self.mcp.__aenter__()
        self.tools = [
            {"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
            for t in await self.mcp.list_tools()
        ]
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.mcp.__aexit__(exc_type, exc, tb)

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Run one tool call; tool errors come back as text, never raise."""
        result = await self.mcp.call_tool(name, arguments, raise_on_error=False)
        text = "\n".join(getattr(block, "text", "") for block in result.content)
        return text, bool(result.is_error)


async def run_question(
    session: OpenLensSession,
    client: anthropic.AsyncAnthropic,
    question: str,
    system_prompt: str,
    model: str = DEFAULT_MODEL,
) -> AgentRun:
    """Answer one question, recording every tool call, token count and the latency."""
    run = AgentRun()
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    start = time.perf_counter()
    try:
        for _ in range(MAX_TURNS):
            response = await client.beta.messages.create(
                model=model,
                max_tokens=16000,
                system=system_prompt,
                tools=session.tools,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
                output_config={"effort": "medium"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
            run.turns += 1
            run.input_tokens += (
                response.usage.input_tokens
                + (response.usage.cache_read_input_tokens or 0)
                + (response.usage.cache_creation_input_tokens or 0)
            )
            run.output_tokens += response.usage.output_tokens
            run.stop_reason = response.stop_reason or ""

            # Append the full content unchanged: thinking blocks must be replayed as-is.
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "pause_turn":
                continue
            if response.stop_reason != "tool_use":
                run.answer = "\n".join(b.text for b in response.content if b.type == "text")
                break

            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                args = dict(block.input) if isinstance(block.input, dict) else {}
                output, is_error = await session.call(block.name, args)
                run.tool_calls.append(ToolCall(block.name, args, output, is_error))
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                    "is_error": is_error,
                })
            # All results go back in one user message, so parallel calls stay parallel.
            messages.append({"role": "user", "content": results})
        else:
            run.error = f"Stopped after {MAX_TURNS} turns without a final answer."
    except anthropic.APIStatusError as exc:
        run.error = f"API error {exc.status_code}: {exc.message}"
    except anthropic.APIConnectionError as exc:
        run.error = f"API connection error: {exc}"
    run.latency_s = round(time.perf_counter() - start, 2)
    return run
