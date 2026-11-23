"""
End-to-end MCP protocol tests: every tool, resource and prompt the server
advertises must be listed, callable and return well-formed content.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import Client

EXPECTED_TOOLS = {
    "discover_disability_datasets",
    "explain_dataset",
    "compare_datasets",
    "analyze_dataset_completeness",
    "assess_dataset_freshness",
    "evaluate_answer_coverage",
    "recommend_transparency_improvements",
}
EXPECTED_RESOURCES = {
    "openlens://datasets/disability",
    "openlens://datasets/field-offices",
    "openlens://framework/answer-coverage",
    "openlens://recommendations/transparency",
}
EXPECTED_PROMPTS = {
    "openlens_dataset_advisor": "analysis_question",
    "transparency_reviewer": "program_area",
    "answer_coverage_evaluator": "questions",
}
ROOT = Path(__file__).resolve().parents[1]


def _tool_json(result: object) -> dict:
    """Parse the JSON text a tool returned."""
    content = result.content  # type: ignore[attr-defined]
    assert content and content[0].type == "text"
    return json.loads(content[0].text)


# ── Server identity and capabilities ──────────────────────────────────────────


async def test_server_advertises_tools_resources_and_prompts(client: Client) -> None:
    assert client.server_info.name == "SSA Disability Claims OpenLens"
    caps = client.server_capabilities
    assert caps.tools is not None
    assert caps.resources is not None
    assert caps.prompts is not None
    assert client.instructions and "evaluate_answer_coverage" in client.instructions


# ── Tools ─────────────────────────────────────────────────────────────────────


async def test_lists_exactly_the_expected_tools(client: Client) -> None:
    tools = await client.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for tool in tools:
        assert tool.description and len(tool.description) > 40, tool.name
        assert tool.input_schema.get("type") == "object", tool.name


async def test_signature_tool_returns_a_report(client: Client) -> None:
    result = await client.call_tool(
        "evaluate_answer_coverage",
        {"question": "Which field offices have the longest decision wait times?"},
    )
    report = _tool_json(result)["report"]
    assert "## Answer Coverage" in report
    assert "US-GOV-SSA-435" in report  # newly catalogued dataset is cited


async def test_discover_falls_back_to_static_catalog_when_offline(client: Client) -> None:
    data = _tool_json(await client.call_tool("discover_disability_datasets", {"query": "field office"}))
    ids = {d["dataset_id"] for d in data["datasets"]}
    assert "ssa-field-office-claims-pending" in ids
    assert all(not i.startswith("datagov-") for i in ids), "live results must be absent offline"


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("explain_dataset", {"dataset_id": "ssa-state-agency-workload-data"}),
        ("assess_dataset_freshness", {"dataset_id": "ssa-hearing-office-workload"}),
        ("analyze_dataset_completeness", {"dataset_id": "ssa-field-office-locator"}),
        ("compare_datasets", {"dataset_ids": [
            "ssa-title2-claim-receipts-by-field-office-2016",
            "ssa-field-office-employee-counts-2016",
        ]}),
        ("recommend_transparency_improvements", {
            "context": "Field office decision wait times are not published per office.",
            "max_recommendations": 3,
        }),
    ],
)
async def test_each_tool_is_callable(client: Client, tool: str, args: dict) -> None:
    data = _tool_json(await client.call_tool(tool, args))
    assert "error" not in data, data.get("error")


async def test_unknown_dataset_id_is_an_error_result(client: Client) -> None:
    result = await client.call_tool(
        "explain_dataset", {"dataset_id": "ssa-no-such-dataset"}, raise_on_error=False
    )
    assert result.is_error
    assert "not found" in result.content[0].text


# ── Resources ─────────────────────────────────────────────────────────────────


async def test_lists_and_reads_every_resource(client: Client) -> None:
    resources = await client.list_resources()
    assert {str(r.uri) for r in resources} == EXPECTED_RESOURCES
    for resource in resources:
        contents = await client.read_resource(str(resource.uri))
        text = contents[0].text  # type: ignore[union-attr]
        assert text, resource.uri
        if resource.mime_type == "application/json":
            parsed = json.loads(text)
            assert not (isinstance(parsed, dict) and "error" in parsed), resource.uri


# ── Prompts ───────────────────────────────────────────────────────────────────


async def test_lists_and_renders_every_prompt(client: Client) -> None:
    prompts = await client.list_prompts()
    assert {p.name for p in prompts} == set(EXPECTED_PROMPTS)
    for prompt in prompts:
        arg = EXPECTED_PROMPTS[prompt.name]
        assert [a.name for a in prompt.arguments or []] == [arg]
        result = await client.get_prompt(prompt.name, {arg: "SSDI hearing backlogs"})
        assert len(result.messages) == 1
        message = result.messages[0]
        assert message.role == "user"
        assert "SSDI hearing backlogs" in message.content.text  # type: ignore[union-attr]


async def test_prompts_work_without_an_argument(client: Client) -> None:
    """Hosts such as the Claude Code VS Code extension run a prompt picked from
    the menu without asking for arguments, so each prompt must still render and
    tell the model to ask the user for the missing input."""
    for prompt in await client.list_prompts():
        arg = (prompt.arguments or [None])[0]
        assert arg is not None and not arg.required, prompt.name
        assert arg.description, prompt.name
        result = await client.get_prompt(prompt.name, {})
        text = result.messages[0].content.text  # type: ignore[union-attr]
        assert "ask the user" in text, prompt.name


async def test_advisor_prompt_asks_for_the_report_verbatim(client: Client) -> None:
    result = await client.get_prompt("openlens_dataset_advisor", {"analysis_question": "Wait times by state?"})
    text = result.messages[0].content.text  # type: ignore[union-attr]
    assert "evaluate_answer_coverage" in text
    assert "verbatim" in text and "Write nothing before it" in text


# ── Published metadata matches the running server ────────────────────────────


async def test_manifest_matches_server(client: Client) -> None:
    yaml = pytest.importorskip("yaml")
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    caps = manifest["capabilities"]
    assert set(caps["tools"]) == {t.name for t in await client.list_tools()}
    assert set(caps["prompts"]) == {p.name for p in await client.list_prompts()}
    assert set(caps["resources"]) == {r.name for r in await client.list_resources()}
