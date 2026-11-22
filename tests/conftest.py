"""
Shared pytest fixtures and configuration for the OpenLens test suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ── FastMCP stub — allows tests to run without the fastmcp package installed ──
try:
    import fastmcp  # noqa: F401
except ImportError:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "fastmcp", Path(__file__).parent / "fastmcp_mock.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    sys.modules["fastmcp"] = mod

from src.ssa_disability_claims_openlens.services.answer_coverage_service import (
    AnswerCoverageEngine,
)
from src.ssa_disability_claims_openlens.services.dataset_analysis_service import (
    DatasetAnalysisService,
)
from src.ssa_disability_claims_openlens.services.dataset_catalog_service import (
    DatasetCatalogService,
    StaticCatalogAdapter,
)
from src.ssa_disability_claims_openlens.services.recommendation_service import (
    RecommendationService,
)


@pytest.fixture
def catalog_service() -> DatasetCatalogService:
    """Return a DatasetCatalogService using only the static adapter (no network)."""
    return DatasetCatalogService(static_adapter=StaticCatalogAdapter(), live_adapters=[])


@pytest.fixture
def coverage_engine() -> AnswerCoverageEngine:
    """Return an AnswerCoverageEngine with the default knowledge base."""
    return AnswerCoverageEngine()


@pytest.fixture
def analysis_service() -> DatasetAnalysisService:
    """Return a DatasetAnalysisService."""
    return DatasetAnalysisService()


@pytest.fixture
def recommendation_service() -> RecommendationService:
    """Return a RecommendationService."""
    return RecommendationService()
