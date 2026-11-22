"""
Grounding tests — the server must never show a URL or fact it cannot trace to a source.

These tests exist because the original catalog contained invented URLs
(e.g. https://www.ssa.gov/appeals/DataSets.html) that no test could catch.

Rules enforced:
  1. Every catalog entry is backed by a Data.gov snapshot record or a current
     manual verification.
  2. Every URL the server can emit (catalog, explain, coverage report) appears in
     the snapshot or a current manual verification — no hand-typed links.
  3. Names, dates and update frequencies equal the snapshot values.
  4. Every dataset_id referenced by any knowledge base exists in the catalog.
  5. The live Data.gov adapter parses the v1 API and reports failures instead of
     silently returning nothing.
"""

from __future__ import annotations

import json
import re
import unittest.mock as mock
from datetime import date, timedelta

import pytest

from src.ssa_disability_claims_openlens.services import (
    answer_coverage_service as acs,
)
from src.ssa_disability_claims_openlens.services import (
    dataset_analysis_service as das,
)
from src.ssa_disability_claims_openlens.services import (
    recommendation_service as rs,
)
from src.ssa_disability_claims_openlens.services.dataset_catalog_service import (
    SNAPSHOT_PATH,
    SOURCES_PATH,
    DataGovAdapter,
    DatasetCatalogService,
    StaticCatalogAdapter,
    map_frequency,
)
from src.ssa_disability_claims_openlens.tools import compare_datasets as cmp

SOURCES = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
SNAPSHOT = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
URL_RE = re.compile(r"https?://[^\s|)>\]]+")


def _allowed_urls() -> set[str]:
    urls: set[str] = set()
    for record in SNAPSHOT["records"].values():
        urls.add(record["datagov_url"])
        for key in ("landing_page", "data_dictionary"):
            if record.get(key):
                urls.add(record[key])
        urls.update(d["url"] for d in record.get("distributions", []))
    for manual in SOURCES["manual"].values():
        urls.add(manual["url"])
    return urls


ALLOWED_URLS = _allowed_urls()

QUESTIONS = [
    "Are there racial disparities in SSA disability allowance rates by state?",
    "Do disability allowance rates vary significantly by state?",
    "How long are people waiting for disability hearing decisions by hearing office?",
    "How long are appointment wait times at SSA field offices?",
    "Do rural communities have less access to SSA disability services than urban communities?",
    "What data should SSA publish first to maximize public understanding of access?",
    "How do average SSDI benefits compare across states?",
    "What are the outcomes of the Ticket to Work program?",
    "What is SSA's performance against its processing time targets?",
]


@pytest.fixture(scope="module")
def static() -> StaticCatalogAdapter:
    return StaticCatalogAdapter()


# ── 1. Every entry is backed by a source ──────────────────────────────────────


class TestSourcesAndSnapshot:
    def test_every_datagov_source_has_a_snapshot_record(self) -> None:
        for dataset_id, slug in SOURCES["datagov"].items():
            record = SNAPSHOT["records"].get(dataset_id)
            assert record is not None, f"{dataset_id}: no snapshot record — run scripts/sync_catalog.py"
            assert record["slug"] == slug, f"{dataset_id}: snapshot slug {record['slug']!r} != {slug!r}"
            assert record["publisher"] == "Social Security Administration"
            assert record["identifier"], f"{dataset_id}: snapshot record has no identifier"

    def test_snapshot_has_no_orphan_records(self) -> None:
        assert set(SNAPSHOT["records"]) == set(SOURCES["datagov"]), (
            "Snapshot and catalog_sources.json disagree — run scripts/sync_catalog.py"
        )

    def test_catalog_contains_exactly_the_sourced_entries(self, static: StaticCatalogAdapter) -> None:
        expected = set(SOURCES["datagov"]) | set(SOURCES["manual"])
        assert set(static.all_dataset_ids()) == expected

    def test_manual_verifications_are_current(self) -> None:
        """Fails when a manual URL check expires — re-check it in a browser and update verified_on."""
        today = date.today()
        for dataset_id, manual in SOURCES["manual"].items():
            for key in ("url", "title", "verified_on", "verified_by", "method"):
                assert manual.get(key), f"{dataset_id}: manual entry missing {key!r}"
            age = (today - date.fromisoformat(manual["verified_on"])).days
            assert age <= int(manual.get("max_age_days", 180)), (
                f"{dataset_id}: manual verification is {age} days old — re-check {manual['url']}"
            )

    def test_every_entry_has_provenance(self, static: StaticCatalogAdapter) -> None:
        for ds in static.fetch_summaries():
            assert ds.provenance, f"{ds.dataset_id}: missing provenance"


# ── 2. Only sourced URLs are ever emitted ─────────────────────────────────────


class TestNoUnsourcedUrls:
    def test_catalog_urls_are_sourced(self, static: StaticCatalogAdapter) -> None:
        for ds in static.fetch_summaries():
            detail = static.fetch_detail(ds.dataset_id)
            assert detail is not None
            emitted = [ds.url, ds.source_record_url, detail.data_dictionary_url, *detail.download_urls]
            for url in filter(None, emitted):
                assert url in ALLOWED_URLS, f"{ds.dataset_id}: unsourced URL {url}"

    def test_every_entry_has_a_url(self, static: StaticCatalogAdapter) -> None:
        for ds in static.fetch_summaries():
            assert ds.url, f"{ds.dataset_id}: no verified URL"

    @pytest.mark.parametrize("question", QUESTIONS)
    def test_coverage_report_urls_are_sourced(self, question: str) -> None:
        assessment = acs.AnswerCoverageEngine().evaluate(question)
        for entry in assessment.available_data_with_urls:
            if entry["url"]:
                assert entry["url"] in ALLOWED_URLS, f"unsourced URL {entry['url']}"
        for url in URL_RE.findall(assessment.format_report()):
            assert url in ALLOWED_URLS, f"report contains unsourced URL {url}"

    def test_previously_invented_urls_are_gone(self, static: StaticCatalogAdapter) -> None:
        invented = {
            "https://www.ssa.gov/appeals/DataSets.html",
            "https://www.ssa.gov/policy/docs/statcomps/disabled_workers/",
            "https://catalog.data.gov/dataset/ssa-annual-performance-report",
        }
        emitted = {ds.url for ds in static.fetch_summaries()}
        assert not emitted & invented


# ── 3. Facts equal the snapshot ───────────────────────────────────────────────


class TestFactsComeFromSnapshot:
    def test_names_dates_frequencies_match_snapshot(self, static: StaticCatalogAdapter) -> None:
        by_id = {ds.dataset_id: ds for ds in static.fetch_summaries()}
        for dataset_id, record in SNAPSHOT["records"].items():
            ds = by_id[dataset_id]
            assert ds.name == record["title"]
            assert ds.description == record["description"]
            expected_date = date.fromisoformat(record["modified"]) if record["modified"] else None
            assert ds.last_updated == expected_date
            freq = map_frequency(record["accrual_periodicity"])
            if record["accrual_periodicity"]:
                assert ds.update_frequency == freq, f"{dataset_id}: frequency differs from record"

    def test_unverified_field_lists_are_flagged(self, static: StaticCatalogAdapter) -> None:
        for dataset_id in static.all_dataset_ids():
            detail = static.fetch_detail(dataset_id)
            assert detail is not None
            if detail.major_fields and not detail.fields_verified:
                assert any("data dictionary" in lim for lim in detail.limitations), dataset_id


# ── Adapter behaviour on bad sources ──────────────────────────────────────────


class TestStaticAdapterSafety:
    def test_missing_snapshot_record_drops_entry(self) -> None:
        adapter = StaticCatalogAdapter(
            sources={"datagov": {"x-dataset": "x-slug"}, "manual": {}},
            snapshot={"records": {}},
            notes={},
        )
        assert adapter.all_dataset_ids() == []

    def test_expired_manual_verification_withholds_url(self) -> None:
        old = (date.today() - timedelta(days=400)).isoformat()
        adapter = StaticCatalogAdapter(
            sources={
                "datagov": {},
                "manual": {
                    "x-manual": {
                        "url": "https://example.gov/page",
                        "title": "X",
                        "verified_on": old,
                        "verified_by": "tester",
                        "method": "browser",
                        "max_age_days": 180,
                    }
                },
            },
            snapshot={"records": {}},
            notes={},
        )
        (summary,) = adapter.fetch_summaries()
        assert summary.url == ""
        assert "expired" in summary.provenance


# ── 4. Knowledge bases only reference real catalog entries ────────────────────


def _kb_dataset_ids() -> dict[str, set[str]]:
    refs: dict[str, set[str]] = {
        "coverage KB": {d for e in acs._COVERAGE_KB for d in e.dataset_ids},
        "intent KB": {d for e in acs._INTENT_KB for d in e.context_dataset_ids},
        "recommendation KB": {
            d for topic in rs._RECOMMENDATION_KB for r in topic["recommendations"] for d in r.affected_datasets
        },
        "generic recommendations": {
            d for r in rs.RecommendationService._generic_recommendations() for d in r.affected_datasets
        },
        "completeness KB": set(das._COMPLETENESS_KB),
        "compare: shared dims": {d for ids in cmp._SHARED_DIMS.values() for d in ids},
        "compare: missing rels": {d for rel in cmp._MISSING_RELS for d in rel["datasets"]},  # type: ignore[attr-defined]
        "compare: integration": {d for opp in cmp._INTEGRATION_OPPS for d in opp["datasets"]},  # type: ignore[attr-defined]
    }
    return refs


@pytest.mark.parametrize("kb_name", list(_kb_dataset_ids()))
def test_knowledge_base_ids_exist_in_catalog(kb_name: str, static: StaticCatalogAdapter) -> None:
    unknown = _kb_dataset_ids()[kb_name] - set(static.all_dataset_ids())
    assert not unknown, f"{kb_name} references datasets not in the catalog: {sorted(unknown)}"


# ── Regression: claims contradicted by the sources ────────────────────────────


class TestGroundedClaims:
    def test_state_allowance_rates_are_recognised_as_published(self) -> None:
        assessment = acs.AnswerCoverageEngine().evaluate(
            "Do disability allowance rates vary significantly by state?"
        )
        allowance = next(
            e for e in assessment.required_information_elements
            if e.element == "Disability program allowance rates"
        )
        assert allowance.available
        assert "ssa-disability-claim-data" in allowance.dataset_ids

    def test_no_recommendation_asks_for_already_published_state_allowance_rates(self) -> None:
        titles = [r.title for topic in rs._RECOMMENDATION_KB for r in topic["recommendations"]]
        assert "Publish state-level disability allowance rates" not in titles

    def test_race_gap_still_reported(self) -> None:
        assessment = acs.AnswerCoverageEngine().evaluate(
            "Are there racial disparities in SSA disability allowance rates by state?"
        )
        assert "Race and ethnicity data" in assessment.gap_analysis.critical_gaps

    def test_initial_processing_times_are_recognised_as_published(self) -> None:
        entry = next(e for e in acs._COVERAGE_KB if e.element == "Disability claim processing times")
        assert "ssa-initial-disability-processing-time" in entry.dataset_ids

    def test_hearing_level_allowances_are_recognised_as_published(self) -> None:
        entry = next(e for e in acs._COVERAGE_KB if e.element == "Disability program allowance rates")
        assert "ssa-alj-disposition-data" in entry.dataset_ids


# ── Gap claims must be backed by recorded searches ────────────────────────────

GAP_EVIDENCE = json.loads(acs.GAP_EVIDENCE_PATH.read_text(encoding="utf-8"))
NONE_ELEMENTS = {e.element for e in acs._COVERAGE_KB if e.coverage_quality == "None"}


class TestGapEvidence:
    def test_every_no_data_claim_has_evidence(self) -> None:
        missing = NONE_ELEMENTS - set(GAP_EVIDENCE["claims"])
        assert not missing, (
            f"Elements rated 'None' without search evidence: {sorted(missing)}. "
            "Add them to data/gap_evidence.json and run scripts/check_gap_claims.py."
        )

    def test_no_orphan_evidence(self) -> None:
        orphans = set(GAP_EVIDENCE["claims"]) - NONE_ELEMENTS
        assert not orphans, f"Evidence for elements no longer rated 'None': {sorted(orphans)}"

    def test_evidence_entries_are_complete(self) -> None:
        for claim, entry in GAP_EVIDENCE["claims"].items():
            assert entry["queries"], f"{claim}: no queries"
            assert entry["verdict"], f"{claim}: no verdict"
            for ident, note in entry.get("reviewed_hits", {}).items():
                assert note.strip(), f"{claim}: reviewed hit {ident} has no note"

    def test_evidence_is_recent(self) -> None:
        age = (date.today() - date.fromisoformat(GAP_EVIDENCE["searched_on"])).days
        assert age <= int(GAP_EVIDENCE["max_age_days"]), (
            f"Gap evidence is {age} days old — run scripts/check_gap_claims.py --stamp"
        )

    def test_report_shows_evidence_for_critical_gaps(self) -> None:
        assessment = acs.AnswerCoverageEngine().evaluate(
            "Are there racial disparities in SSA disability allowance rates by state?"
        )
        assert "Race and ethnicity data" in assessment.gap_analysis.gap_evidence
        assert "*Checked:* Data.gov search" in assessment.format_report()


# ── 5. Live adapter (Data.gov catalog API v1) ─────────────────────────────────

_V1_SEARCH_RESPONSE = {
    "after": None,
    "results": [
        {
            "slug": "dds-accuracy-example",
            "dcat": {
                "title": "Disability Determination Services (DDS) Accuracy",
                "description": "Accuracy rates.",
                "identifier": "US-GOV-SSA-999",
                "modified": "2024-01-02",
                "accrualPeriodicity": "annual",
                "keyword": ["2020", "Accuracy"],
                "landingPage": {"accessURL": "https://www.ssa.gov/data/example.html"},
                "distribution": [{"downloadURL": "https://www.ssa.gov/data/example.csv", "format": "CSV"}],
            },
        },
        {
            "slug": "ssa-disability-claim-data",  # already in the static catalog
            "dcat": {"title": "SSA Disability Claim Data", "identifier": "US-GOV-SSA-308"},
        },
    ],
}


def _mock_client(response: dict | Exception) -> mock.MagicMock:
    client = mock.MagicMock()
    get = client.__enter__.return_value.get
    if isinstance(response, Exception):
        get.side_effect = response
    else:
        get.return_value.json.return_value = response
        get.return_value.raise_for_status.return_value = None
    return client


class TestDataGovAdapterV1:
    def _adapter(self) -> DataGovAdapter:
        return DataGovAdapter(
            "https://catalog.data.gov/api/v1", exclude_slugs={"ssa-disability-claim-data"}
        )

    def test_parses_v1_search_and_excludes_static_slugs(self) -> None:
        adapter = self._adapter()
        with mock.patch("httpx.Client", return_value=_mock_client(_V1_SEARCH_RESPONSE)) as client_cls:
            summaries = adapter.fetch_summaries()
            url, kwargs = client_cls.return_value.__enter__.return_value.get.call_args
        assert url[0] == "https://catalog.data.gov/api/v1/search"
        assert kwargs["params"]["org_slug"] == "ssa"
        assert kwargs["params"]["has_download"] == "true"
        assert [s.dataset_id for s in summaries] == ["datagov-dds-accuracy-example"]
        s = summaries[0]
        assert s.url == "https://www.ssa.gov/data/example.html"
        assert s.last_updated == date(2024, 1, 2)
        assert s.tags == ["Accuracy"]
        assert "US-GOV-SSA-999" in s.provenance
        assert adapter.last_error == ""

    def test_results_are_cached(self) -> None:
        adapter = self._adapter()
        with mock.patch("httpx.Client", return_value=_mock_client(_V1_SEARCH_RESPONSE)) as client_cls:
            adapter.fetch_summaries()
            adapter.fetch_summaries()
            assert client_cls.call_count == 1

    def test_failure_is_reported_not_swallowed(self) -> None:
        adapter = self._adapter()
        with mock.patch("httpx.Client", return_value=_mock_client(Exception("HTTP 404"))):
            assert adapter.fetch_summaries() == []
        assert "unavailable" in adapter.last_error
        service = DatasetCatalogService(static_adapter=StaticCatalogAdapter(), live_adapters=[adapter])
        assert any("unavailable" in note for note in service.source_notes())

    def test_coverage_engine_does_not_call_live_adapter(self) -> None:
        live = mock.MagicMock()
        service = DatasetCatalogService(static_adapter=StaticCatalogAdapter(), live_adapters=[live])
        with mock.patch(
            "src.ssa_disability_claims_openlens.services.dataset_catalog_service.get_catalog_service",
            return_value=service,
        ):
            acs.AnswerCoverageEngine().evaluate("Do disability allowance rates vary by state?")
        live.fetch_summaries.assert_not_called()
