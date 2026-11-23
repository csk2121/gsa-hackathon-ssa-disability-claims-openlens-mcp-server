"""
Claude Code backend: the agent and the judges run as headless Claude Code
(`claude -p`) on the user's Claude subscription instead of the paid API.

Each question starts a fresh `claude -p` session connected only to the
OpenLens MCP server (--strict-mcp-config), with no built-in tools, no settings
files and no saved session, and the versioned system prompt in place of
Claude Code's own. The stream-json output gives every tool call and result, so
the same code checks apply.

ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN are removed from the child
environment: Claude Code prefers an API key over the subscription login.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .records import AgentRun, ToolCall

ROOT = Path(__file__).resolve().parents[2]
SERVER_NAME = "openlens"
TOOL_PREFIX = f"mcp__{SERVER_NAME}__"
QUESTION_TIMEOUT_S = 600
JUDGE_TIMEOUT_S = 300


class ClaudeCodeError(RuntimeError):
    pass


def claude_executable() -> str:
    """The claude binary: CLAUDE_CODE_BIN, else the native exe behind the npm shim."""
    if env := os.environ.get("CLAUDE_CODE_BIN"):
        return env
    found = shutil.which("claude")
    if not found:
        raise ClaudeCodeError("Claude Code CLI not found. Install it or set CLAUDE_CODE_BIN.")
    path = Path(found)
    # On Windows the npm shim is a .cmd file, which mangles JSON arguments; use the exe.
    native = path.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    return str(native) if native.is_file() else found


def _child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    env["MCP_TIMEOUT"] = "90000"  # the server takes ~10s to import on this machine
    return env


_WORKDIR: Path | None = None


def _workdir() -> Path:
    """A neutral working directory (no CLAUDE.md) holding the MCP config."""
    global _WORKDIR
    if _WORKDIR is None:
        _WORKDIR = Path(tempfile.mkdtemp(prefix="openlens-eval-"))
        config = {"mcpServers": {SERVER_NAME: {"command": sys.executable, "args": [str(ROOT / "main.py")]}}}
        (_WORKDIR / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
    return _WORKDIR


_COMMON = ["--strict-mcp-config", "--setting-sources", "", "--no-session-persistence"]


async def _run(args: list[str], stdin: bytes | None, timeout: float) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        claude_executable(), *args,
        cwd=str(_workdir()),
        env=_child_env(),
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin), timeout)
    except TimeoutError:
        proc.kill()
        raise ClaudeCodeError(f"claude -p timed out after {timeout:.0f}s") from None
    if proc.returncode and not out.strip():
        raise ClaudeCodeError(f"claude -p exited {proc.returncode}: {err.decode(errors='replace')[:300]}")
    return out


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


async def run_question(question: str, prompt_file: Path, model: str) -> AgentRun:
    """Answer one question in a fresh headless Claude Code session."""
    run = AgentRun()
    args = [
        "-p", question,
        "--output-format", "stream-json", "--verbose",
        "--model", model,
        "--system-prompt-file", str(prompt_file),
        "--mcp-config", str(_workdir() / "mcp.json"),
        "--allowedTools", f"mcp__{SERVER_NAME}",
        "--tools", "",
        *_COMMON,
    ]
    start = time.perf_counter()
    try:
        out = await _run(args, None, QUESTION_TIMEOUT_S)
    except ClaudeCodeError as exc:
        run.error = str(exc)
        run.wall_s = round(time.perf_counter() - start, 2)
        return run
    run.wall_s = round(time.perf_counter() - start, 2)

    pending: dict[str, tuple[str, dict[str, Any]]] = {}
    result: dict[str, Any] | None = None
    for line in out.decode("utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            servers = {s.get("name"): s.get("status") for s in event.get("mcp_servers", [])}
            if servers.get(SERVER_NAME) != "connected":
                run.error = f"MCP server not connected: {servers.get(SERVER_NAME)}"
        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    name = str(block.get("name", "")).removeprefix(TOOL_PREFIX)
                    pending[block.get("id", "")] = (name, block.get("input") or {})
        elif kind == "user":
            content = event.get("message", {}).get("content", [])
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_result" and block.get("tool_use_id") in pending:
                    name, tool_input = pending.pop(block["tool_use_id"])
                    run.tool_calls.append(
                        ToolCall(name, tool_input, _text_of(block.get("content")), bool(block.get("is_error")))
                    )
        elif kind == "result":
            result = event

    if result is None:
        run.error = run.error or "No result event from claude -p."
        return run
    usage = result.get("usage") or {}
    run.answer = result.get("result") or ""
    run.latency_s = round((result.get("duration_ms") or 0) / 1000, 2)
    run.turns = result.get("num_turns") or 0
    run.cost_usd = float(result.get("total_cost_usd") or 0.0)
    run.input_tokens = (
        (usage.get("input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0)
    )
    run.output_tokens = usage.get("output_tokens") or 0
    run.stop_reason = result.get("stop_reason") or result.get("subtype") or ""
    if result.get("is_error") and not run.error:
        run.error = f"claude -p reported an error: {result.get('subtype')}: {str(result.get('result'))[:200]}"
    return run


async def ask_json(prompt: str, schema: dict[str, Any], model: str) -> dict[str, Any]:
    """One structured judge call: the prompt goes in on stdin, the verdict comes back as JSON."""
    args = [
        "-p",
        "--output-format", "json",
        "--model", model,
        "--tools", "",
        "--json-schema", json.dumps(schema),
        *_COMMON,
    ]
    out = await _run(args, prompt.encode("utf-8"), JUDGE_TIMEOUT_S)
    try:
        data = json.loads(out.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ClaudeCodeError(f"Unreadable judge output: {exc}") from None
    verdict = data.get("structured_output")
    if not isinstance(verdict, dict):
        raise ClaudeCodeError(f"No structured verdict: {str(data.get('result'))[:200]}")
    return verdict
