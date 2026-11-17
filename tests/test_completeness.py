"""
Unit tests for analyze_dataset_completeness tool.

Tests:
- Returns scored analysis for all static datasets
- Geographic, temporal, operational axes are scored 0–100
- Overall score is calculated correctly
- Missing dimensions are listed
- Rating matches score range
- Focus dimensions narrow the analysis
"""

from __future__ import annotations

import pytest

from src.ssa_disability_claims_openlens.models import CompletenessAnalysis
from src.ssa_disability_claims_openlens.services.dataset_analysis_service import (
    DatasetAnalysisService,
)
from src.ssa_disability_claims_openlens.services.dataset_catalog_service import (
    DatasetCatalogService,
)


class TestAnalyzeDatasetCompleteness:
    PROFILED_IDS = [
        "ssa-oasdi-beneficiaries-by-state",
        "ssa-odar-pending-cases",
        "ssa-disability-applications-decisions",
        "ssa-field-office-locator",
        "ssa-disability-research-statistics",
        "ssa-ssi-recipients-by-state",
        "data-gov-ssa-performance",
    ]

    def test_returns_analysis_for_all_profiled_datasets(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        for dataset_id in self.PROFILED_IDS:
            detail = catalog_service.get_dataset_detail(dataset_id)
            assert detail is not None
            analysis = analysis_service.analyze_completeness(detail)
            assert isinstance(analysis, CompletenessAnalysis)
            assert analysis.dataset_id == dataset_id

    def test_scores_are_in_valid_range(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        for dataset_id in self.PROFILED_IDS:
            detail = catalog_service.get_dataset_detail(dataset_id)
            assert detail is not None
            analysis = analysis_service.analyze_completeness(detail)
            assert 0.0 <= analysis.geographic_coverage.score <= 100.0
            assert 0.0 <= analysis.temporal_coverage.score <= 100.0
            assert 0.0 <= analysis.operational_coverage.score <= 100.0
            assert 0.0 <= analysis.completeness_score <= 100.0

    def test_rating_matches_score(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        for dataset_id in self.PROFILED_IDS:
            detail = catalog_service.get_dataset_detail(dataset_id)
            assert detail is not None
            analysis = analysis_service.analyze_completeness(detail)
            if analysis.completeness_score >= 75:
                assert analysis.completeness_rating == "Strong"
            elif analysis.completeness_score >= 50:
                assert analysis.completeness_rating == "Moderate"
            else:
                assert analysis.completeness_rating == "Limited"

    def test_field_office_has_low_operational_score(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        """Field office dataset should have low operational coverage (no wait times/staffing)."""
        detail = catalog_service.get_dataset_detail("ssa-field-office-locator")
        assert detail is not None
        analysis = analysis_service.analyze_completeness(detail)
        assert analysis.operational_coverage.score < 50.0

    def test_applications_dataset_has_low_geographic_score(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        """Applications/decisions dataset is national only — geographic score should be low."""
        detail = catalog_service.get_dataset_detail("ssa-disability-applications-decisions")
        assert detail is not None
        analysis = analysis_service.analyze_completeness(detail)
        assert analysis.geographic_coverage.score < 40.0

    def test_missing_dimensions_are_strings(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        detail = catalog_service.get_dataset_detail("ssa-odar-pending-cases")
        assert detail is not None
        analysis = analysis_service.analyze_completeness(detail)
        assert all(isinstance(d, str) for d in analysis.missing_dimensions)

    def test_analyst_notes_populated(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        detail = catalog_service.get_dataset_detail("ssa-odar-pending-cases")
        assert detail is not None
        analysis = analysis_service.analyze_completeness(detail)
        assert len(analysis.analyst_notes) > 10

    def test_focus_dimensions_affect_score(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        """Focusing on 'temporal' should give a score equal to the temporal axis score."""
        detail = catalog_service.get_dataset_detail("ssa-ssi-recipients-by-state")
        assert detail is not None
        full = analysis_service.analyze_completeness(detail)
        focused = analysis_service.analyze_completeness(detail, focus_dimensions=["temporal"])
        assert focused.completeness_score == full.temporal_coverage.score
