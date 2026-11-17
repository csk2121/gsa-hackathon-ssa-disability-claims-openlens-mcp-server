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

import pytest

from src.ssa_disability_claims_openlens.models import DataSource, DiscoverDatasetsResult
from src.ssa_disability_claims_openlens.services.dataset_catalog_service import (
    DatasetCatalogService,
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
        assert "ssa-odar-pending-cases" in ids
        assert "ssa-field-office-locator" in ids
        assert "ssa-disability-applications-decisions" in ids
