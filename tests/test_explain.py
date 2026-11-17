"""
Unit tests for explain_dataset tool.

Tests:
- Returns full detail for a valid dataset_id
- Returns error for unknown dataset_id
- Major fields are populated with types
- Use cases and limitations are present
- Coverage fields are populated
"""

from __future__ import annotations

import pytest

from src.ssa_disability_claims_openlens.services.dataset_catalog_service import (
    DatasetCatalogService,
)


class TestExplainDataset:
    VALID_ID = "ssa-odar-pending-cases"
    INVALID_ID = "does-not-exist-xyz"

    def test_returns_detail_for_valid_id(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        detail = catalog_service.get_dataset_detail(self.VALID_ID)
        assert detail is not None
        assert detail.dataset_id == self.VALID_ID

    def test_returns_none_for_invalid_id(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        detail = catalog_service.get_dataset_detail(self.INVALID_ID)
        assert detail is None

    def test_major_fields_populated(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        detail = catalog_service.get_dataset_detail(self.VALID_ID)
        assert detail is not None
        assert len(detail.major_fields) > 0
        for field in detail.major_fields:
            assert field.name, "Field must have a name"
            assert field.data_type, "Field must have a data type"
            assert field.description, "Field must have a description"

    def test_use_cases_populated(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        detail = catalog_service.get_dataset_detail(self.VALID_ID)
        assert detail is not None
        assert len(detail.use_cases) >= 2

    def test_limitations_populated(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        detail = catalog_service.get_dataset_detail(self.VALID_ID)
        assert detail is not None
        assert len(detail.limitations) >= 2

    def test_geographic_and_temporal_coverage(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        detail = catalog_service.get_dataset_detail(self.VALID_ID)
        assert detail is not None
        assert detail.geographic_coverage
        assert detail.temporal_coverage

    def test_all_static_datasets_have_detail(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        datasets = catalog_service.list_datasets()
        for ds in datasets:
            detail = catalog_service.get_dataset_detail(ds.dataset_id)
            assert detail is not None, f"Missing detail for {ds.dataset_id}"
            assert detail.purpose, f"Missing purpose for {ds.dataset_id}"

    def test_detail_serializes_cleanly(
        self, catalog_service: DatasetCatalogService
    ) -> None:
        detail = catalog_service.get_dataset_detail(self.VALID_ID)
        assert detail is not None
        d = detail.model_dump(mode="json")
        assert d["dataset_id"] == self.VALID_ID
        assert isinstance(d["major_fields"], list)
        assert isinstance(d["use_cases"], list)
        assert isinstance(d["limitations"], list)
