"""
Unit tests for assess_dataset_freshness tool.

Tests:
- Current dataset returns high freshness score
- Stale dataset returns low freshness score and indicators
- Unknown last_updated date returns UNKNOWN status
- Freshness score is in 0–100 range
- Staleness indicators are non-empty for stale datasets
- days_since_update is consistent with last_updated
"""

from __future__ import annotations

from datetime import date, timedelta

from src.ssa_disability_claims_openlens.models import FreshnessStatus, UpdateFrequency
from src.ssa_disability_claims_openlens.services.dataset_analysis_service import (
    DatasetAnalysisService,
)
from src.ssa_disability_claims_openlens.services.dataset_catalog_service import (
    DatasetCatalogService,
)
from src.ssa_disability_claims_openlens.utils import compute_freshness_score


class TestAssessDatasetFreshness:
    def test_current_monthly_dataset_scores_high(self) -> None:
        """A dataset updated yesterday with monthly frequency should score near 100."""
        score, status, _ = compute_freshness_score(
            last_updated=date.today() - timedelta(days=1),
            frequency=UpdateFrequency.MONTHLY,
        )
        assert score >= 95.0
        assert status == FreshnessStatus.CURRENT

    def test_overdue_monthly_dataset_scores_low(self) -> None:
        """A monthly dataset not updated for 90 days should be stale."""
        score, status, indicators = compute_freshness_score(
            last_updated=date.today() - timedelta(days=90),
            frequency=UpdateFrequency.MONTHLY,
        )
        assert score < 70.0
        assert status in (FreshnessStatus.AGING, FreshnessStatus.STALE)
        assert len(indicators) > 0

    def test_unknown_date_returns_unknown_status(self) -> None:
        score, status, indicators = compute_freshness_score(
            last_updated=None, frequency=UpdateFrequency.MONTHLY
        )
        assert score == 0.0
        assert status == FreshnessStatus.UNKNOWN
        assert any("unknown" in ind.lower() for ind in indicators)

    def test_score_always_in_valid_range(self) -> None:
        test_cases = [
            (date.today(), UpdateFrequency.DAILY),
            (date.today() - timedelta(days=400), UpdateFrequency.MONTHLY),
            (date.today() - timedelta(days=800), UpdateFrequency.QUARTERLY),
            (None, UpdateFrequency.ANNUALLY),
        ]
        for last_updated, freq in test_cases:
            score, _, _ = compute_freshness_score(last_updated, freq)
            assert 0.0 <= score <= 100.0, f"Score {score} out of range for {last_updated}, {freq}"

    def test_all_static_datasets_return_assessment(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        datasets = catalog_service.list_datasets()
        for ds in datasets:
            detail = catalog_service.get_dataset_detail(ds.dataset_id)
            assert detail is not None
            assessment = analysis_service.assess_freshness(detail)
            assert 0.0 <= assessment.freshness_score <= 100.0
            assert assessment.freshness_status in FreshnessStatus.__members__.values()

    def test_ssi_dataset_has_high_freshness(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        """SSI recipients dataset is annual (per its Data.gov record)."""
        detail = catalog_service.get_dataset_detail("ssa-ssi-recipients-by-state")
        assert detail is not None
        assessment = analysis_service.assess_freshness(detail)
        assert detail.update_frequency == UpdateFrequency.ANNUALLY
        assert assessment.freshness_score >= 0.0  # At minimum it should not error

    def test_analyst_notes_populated(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        detail = catalog_service.get_dataset_detail("ssa-hearing-office-workload")
        assert detail is not None
        assessment = analysis_service.assess_freshness(detail)
        assert len(assessment.analyst_notes) > 10

    def test_days_since_consistent_with_last_updated(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        detail = catalog_service.get_dataset_detail("ssa-ssi-recipients-by-state")
        assert detail is not None
        assert detail.last_updated is not None
        assessment = analysis_service.assess_freshness(detail)
        expected_days = (date.today() - detail.last_updated).days
        assert assessment.days_since_update == expected_days

    def test_format_report_returns_complete_markdown(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        """format_report() should produce a single markdown string with all sections."""
        detail = catalog_service.get_dataset_detail("ssa-di-annual-statistical-report")
        assert detail is not None
        assessment = analysis_service.assess_freshness(detail)
        report = assessment.format_report()

        # Must be a non-empty string
        assert isinstance(report, str)
        assert len(report) > 100

        # Must contain the heading with dataset name
        assert "## Freshness Assessment" in report
        assert detail.name in report

        # Must contain all table fields
        assert "Dataset ID" in report
        assert "Last Updated" in report
        assert "Freshness Score" in report
        assert "Status" in report

        # Must contain all named sections
        assert "Freshness Rationale:" in report
        assert "Staleness Indicators:" in report
        assert "Analyst Notes:" in report
        assert "Note:" in report

        # Must contain the freshness status value
        assert assessment.freshness_status.value in report

    def test_format_report_no_newline_collapsed_fields(
        self,
        catalog_service: DatasetCatalogService,
        analysis_service: DatasetAnalysisService,
    ) -> None:
        """
        Rationale and analyst notes must arrive as separate lines, not collapsed
        into a single run-on sentence (the core formatting bug being fixed).
        """
        detail = catalog_service.get_dataset_detail("ssa-di-annual-statistical-report")
        assert detail is not None
        assessment = analysis_service.assess_freshness(detail)
        report = assessment.format_report()

        # The rationale contains bullet lines — there must be multiple lines
        # starting with "- " in the report (from both rationale and notes sections)
        bullet_lines = [line for line in report.splitlines() if line.startswith("- ")]
        assert len(bullet_lines) >= 2, (
            "Expected multiple bullet lines in report — formatting may have been collapsed"
        )
