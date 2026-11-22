"""
Unit tests for compare_datasets tool.

Tests:
- Finds shared dimensions between overlapping datasets
- Identifies missing relationships
- Finds integration opportunities
- Handles datasets with no shared dimensions
- Rejects fewer than 2 dataset IDs
- Rejects duplicate dataset IDs
"""

from __future__ import annotations

import pytest

from src.ssa_disability_claims_openlens.models import CompareDatasetsInput
from src.ssa_disability_claims_openlens.tools.compare_datasets import (
    _INTEGRATION_OPPS,
    _MISSING_RELS,
    _SHARED_DIMS,
)


class TestCompareDatasets:
    def test_input_requires_two_datasets(self) -> None:
        with pytest.raises(ValueError):
            CompareDatasetsInput(dataset_ids=["only-one"])

    def test_input_rejects_duplicates(self) -> None:
        with pytest.raises(ValueError, match="unique"):
            CompareDatasetsInput(dataset_ids=["ssa-hearing-office-workload", "ssa-hearing-office-workload"])

    def test_shared_dims_kb_populated(self) -> None:
        assert len(_SHARED_DIMS) >= 5, "Expected at least 5 shared dimension entries"

    def test_known_state_dimension_present(self) -> None:
        assert "state" in _SHARED_DIMS
        assert "ssa-oasdi-beneficiaries-by-state" in _SHARED_DIMS["state"]

    def test_missing_rels_kb_populated(self) -> None:
        assert len(_MISSING_RELS) >= 3

    def test_missing_rel_has_required_fields(self) -> None:
        for rel in _MISSING_RELS:
            assert "datasets" in rel
            assert "description" in rel
            assert "missing_field" in rel
            assert "impact" in rel

    def test_integration_opps_kb_populated(self) -> None:
        assert len(_INTEGRATION_OPPS) >= 3

    def test_integration_opp_has_required_fields(self) -> None:
        for opp in _INTEGRATION_OPPS:
            assert "datasets" in opp
            assert "title" in opp
            assert "description" in opp
            assert "expected_benefit" in opp

    def test_state_dimension_includes_multiple_datasets(self) -> None:
        """State dimension should appear in at least 4 datasets for meaningful comparison."""
        state_datasets = _SHARED_DIMS.get("state", [])
        assert len(state_datasets) >= 4

    def test_all_dim_dataset_refs_valid_ids(self) -> None:
        """All dataset IDs referenced in shared dims should exist in static catalog."""
        from src.ssa_disability_claims_openlens.services.dataset_catalog_service import (
            StaticCatalogAdapter,
        )
        adapter = StaticCatalogAdapter()
        valid_ids = set(adapter.all_dataset_ids())
        for dim_name, dim_datasets in _SHARED_DIMS.items():
            for did in dim_datasets:
                assert did in valid_ids, (
                    f"Dataset ID '{did}' in dim '{dim_name}' not found in static catalog"
                )
