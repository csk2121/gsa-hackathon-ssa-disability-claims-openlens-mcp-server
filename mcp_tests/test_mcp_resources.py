"""
Resource content must match the engine: the framework document describes the
scoring the engine actually does, and the field office resource lists every
field office dataset in the catalog.
"""

from __future__ import annotations

import json
import re

import pytest
from fastmcp import Client

from src.ssa_disability_claims_openlens.services import answer_coverage_service as acs
from src.ssa_disability_claims_openlens.services.dataset_catalog_service import get_catalog_service

FIELD_OFFICE_IDS = {
    "ssa-field-office-locator",
    "ssa-field-office-visitors",
    "ssa-field-office-visitor-counts-2016",
    "ssa-field-office-employee-counts-2016",
    "ssa-field-office-appointments-21-days",
    "ssa-field-office-claims-pending",
    "ssa-field-office-telephone-service",
    "ssa-title2-claim-receipts-by-field-office-2016",
}


async def _read(client: Client, uri: str) -> str:
    return (await client.read_resource(uri))[0].text  # type: ignore[union-attr]


# ── Field office resource ─────────────────────────────────────────────────────


async def test_field_office_resource_lists_every_field_office_dataset(client: Client) -> None:
    data = json.loads(await _read(client, "openlens://datasets/field-offices"))
    ids = {d["dataset_id"] for d in data["datasets"]}
    assert ids == FIELD_OFFICE_IDS
    assert data["dataset_count"] == len(FIELD_OFFICE_IDS)
    assert "do not make the medical decision" in data["summary"]


def test_field_office_marker_matches_every_catalogued_field_office_dataset() -> None:
    """A new field office dataset whose ID lacks the marker would be silently left out."""
    catalog = get_catalog_service()
    tagged = {
        i for i in catalog.get_all_dataset_ids()
        if "field office" in " ".join(catalog._static._catalog[i]["tags"]).lower()
    }
    assert tagged == FIELD_OFFICE_IDS


# ── Framework resource ────────────────────────────────────────────────────────


async def test_framework_documents_the_critical_cap(client: Client) -> None:
    doc = await _read(client, "openlens://framework/answer-coverage")
    assert "critical-element cap" in doc.lower()
    for quality, (limit, rating) in acs._CRITICAL_CAP.items():
        assert f"| {quality} | {rating} | {limit:g} |" in doc
    for quality, points in acs._QUALITY_SCORE.items():
        assert f"| {quality} | {points:g} |" in doc
    assert "How Answer Coverage Was Rated" in doc
    assert "Assessment Confidence" not in doc
    assert "implementation effort" not in doc.lower()


async def test_framework_worked_example_matches_the_engine(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    original = acs._apply_critical_cap

    def spy(score, elements, weights):  # type: ignore[no-untyped-def]
        seen["raw"] = score
        seen["rows"] = {e.element: (e.coverage_quality, w) for e, w in zip(elements, weights, strict=True)}
        return original(score, elements, weights)

    monkeypatch.setattr(acs, "_apply_critical_cap", spy)
    assessment = acs.get_answer_coverage_engine().evaluate(
        "Which field offices have the longest decision wait times?"
    )
    doc = await _read(client, "openlens://framework/answer-coverage")
    example = doc.split("## Worked Example", 1)[1].split("## Reading the Report", 1)[0]

    for element, (quality, weight) in seen["rows"].items():  # type: ignore[union-attr]
        kind = "Critical" if weight == 2 else "Supporting"
        row = next(line for line in example.splitlines() if line.startswith(f"| {element} |"))
        assert kind in row and f"| {quality} |" in row, row

    assert f"**{seen['raw']:g}**" in example
    assert f"score becomes **{assessment.answer_coverage_score:g}**" in example
    assert f"rating **{assessment.coverage_rating.value}**" in example


async def test_framework_priority_table_matches_the_engine(client: Client) -> None:
    from src.ssa_disability_claims_openlens.models import RecommendationPriority
    from src.ssa_disability_claims_openlens.services import recommendation_service as rs

    doc = await _read(client, "openlens://framework/answer-coverage")
    rows = re.findall(r"^\| (Critical|Supporting), rated (\w+)(?: or (\w+))? \| (\w+) \|$", doc, re.M)
    assert len(rows) == 5
    seen = set()
    for kind, q1, q2, expected in rows:
        for quality in filter(None, (q1, q2)):
            weight = 2 if kind == "Critical" else 1
            priority, _ = rs._gap_priority(quality, weight, 0, RecommendationPriority.HIGH)
            assert priority.value == expected, (kind, quality)
            seen.add((quality, weight))
    assert seen == {(q, w) for q in rs._GAP_SEVERITY for w in (1, 2)}


async def test_framework_score_ranges_match_settings(client: Client) -> None:
    doc = await _read(client, "openlens://framework/answer-coverage")
    assert re.search(r"\| Limited \| 15 to under 40 \|", doc)
    assert re.search(r"\| Partial \| 40 to under 75 \|", doc)
