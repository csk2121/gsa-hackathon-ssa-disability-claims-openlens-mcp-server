"""
Unit tests for discover_disability_datasets tool.

Tests:
- Returns all datasets with no filter
- Keyword search narrows results
- Source filter works correctly
- Tag filter works correctly
- Empty query returns all datasets
- Result structure matches DiscoverDatasetsResult schema
"""

from __future__ import annotations

import unittest.mock as mock

from src.ssa_disability_claims_openlens.models import (
    DatasetSummary,
    DataSource,
    DiscoverDatasetsResult,
)
from src.ssa_disability_claims_openlens.services.dataset_catalog_service import (
    DataGovAdapter,
    DatasetCatalogService,
    StaticCatalogAdapter,
)


class TestDiscoverDatasets:
    def test_returns_all_datasets_with_no_filter(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        datasets = catalog_service.list_datasets()
        assert len(datasets) >= 7, "Static catalog should have at least 7 datasets"

    def test_keyword_search_narrows_results(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        all_datasets = catalog_service.list_datasets()
        filtered = catalog_service.list_datasets(query="ODAR hearing")
        assert len(filtered) < len(all_datasets)
        assert any("odar" in ds.dataset_id or "hearing" in ds.name.lower() for ds in filtered)

    def test_source_filter_ssa_only(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        datasets = catalog_service.list_datasets(source_filter=DataSource.SSA_OPEN_DATA.value)
        assert all(ds.source == DataSource.SSA_OPEN_DATA for ds in datasets)
        assert len(datasets) > 0

    def test_source_filter_data_gov(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        # Data.gov datasets are in static catalog too
        datasets = catalog_service.list_datasets(source_filter=DataSource.DATA_GOV.value)
        assert all(ds.source == DataSource.DATA_GOV for ds in datasets)

    def test_tag_filter_returns_matching_datasets(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        datasets = catalog_service.list_datasets(tags=["appeals"])
        assert len(datasets) >= 1
        for ds in datasets:
            assert any("appeals" in tag.lower() for tag in ds.tags)

    def test_all_datasets_have_required_fields(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        datasets = catalog_service.list_datasets()
        for ds in datasets:
            assert ds.dataset_id, f"Missing dataset_id on {ds}"
            assert ds.name, f"Missing name on {ds}"
            assert ds.description, f"Missing description on {ds}"
            assert ds.source, f"Missing source on {ds}"
            assert ds.update_frequency, f"Missing update_frequency on {ds}"
            assert ds.url, f"Missing url on {ds}"

    def test_result_serializes_to_dict(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        datasets = catalog_service.list_datasets()
        result = DiscoverDatasetsResult(
            datasets=datasets,
            total_found=len(datasets),
            query_applied=None,
            source_note="Test",
        )
        d = result.model_dump(mode="json")
        assert d["total_found"] == len(datasets)
        assert isinstance(d["datasets"], list)

    def test_no_duplicate_dataset_ids(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        datasets = catalog_service.list_datasets()
        ids = [ds.dataset_id for ds in datasets]
        assert len(ids) == len(set(ids)), "Dataset IDs must be unique"

    def test_known_dataset_present(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        datasets = catalog_service.list_datasets()
        ids = {ds.dataset_id for ds in datasets}
        assert "ssa-hearing-office-workload" in ids
        assert "ssa-field-office-locator" in ids
        assert "ssa-disability-claim-data" in ids


# ── Query synonyms and live search ────────────────────────────────────────────


def _live_summary(slug: str, title: str) -> DatasetSummary:
    summary = DataGovAdapter._summary_from_result({
        "slug": slug,
        "dcat": {
            "title": title,
            "identifier": "US-GOV-SSA-0",
            "description": "d",
            "landingPage": {"accessURL": f"https://www.ssa.gov/data/{slug}.html"},
        },
    })
    assert summary is not None
    return summary


def _live_service() -> tuple[DatasetCatalogService, DataGovAdapter]:
    adapter = DataGovAdapter("https://catalog.data.gov/api/v1")
    return DatasetCatalogService(static_adapter=StaticCatalogAdapter(), live_adapters=[adapter]), adapter


class TestDiscoveryQueries:
    def test_backlog_finds_datasets_that_say_pending(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        ids = {ds.dataset_id for ds in catalog_service.list_datasets(query="backlog")}
        assert {"ssa-hearing-office-workload", "ssa-state-agency-workload-data"} <= ids

    def test_query_is_sent_to_data_gov_with_synonyms(self) -> None:
        service, adapter = _live_service()
        found = [
            _live_summary("field-office-claims-pending", "Field Office Claims Pending"),
            _live_summary("hearing-office-workload-data-march-2019", "Hearing Office Workload Data - March 2019"),
        ]
        with mock.patch.object(adapter, "search", return_value=found) as search, \
             mock.patch.object(adapter, "fetch_summaries") as fetch:
            datasets = service.list_datasets(query="backlog")
        search.assert_called_once_with("backlog OR pending")
        fetch.assert_not_called()
        names = [ds.name for ds in datasets]
        assert "Field Office Claims Pending" in names
        assert "Hearing Office Workload Data - March 2019" not in names  # archived edition

    def test_generic_query_falls_back_to_default_live_search(self) -> None:
        service, adapter = _live_service()
        with mock.patch.object(adapter, "search") as search, \
             mock.patch.object(adapter, "fetch_summaries", return_value=[]) as fetch:
            service.list_datasets(query="disability")
        search.assert_not_called()
        fetch.assert_called_once()
