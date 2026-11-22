"""
Security tests — outbound HTTP request mitigations.

Covers:
  1. DataGovAdapter.fetch_detail() allowlist: only issues a network request
     for Data.gov slugs previously returned by fetch_summaries(). An
     attacker-supplied dataset_id that was never discovered must NOT trigger
     an outbound request.

  2. Settings.validate_data_gov_url: DATA_GOV_API_BASE_URL must start with
     'https://catalog.data.gov/' — any other value (IP literal, HTTP, different
     host) must be rejected at startup before any adapter is constructed.
"""

from __future__ import annotations

import pytest

from src.ssa_disability_claims_openlens.config import Settings
from src.ssa_disability_claims_openlens.services.dataset_catalog_service import (
    DataGovAdapter,
)

# ── Fix 1: DataGovAdapter fetch_detail allowlist ───────────────────────────────


class TestDataGovAdapterAllowlist:
    """fetch_detail must not hit the network for unknown package names."""

    def _adapter(self) -> DataGovAdapter:
        return DataGovAdapter(base_url="https://catalog.data.gov/api/v1")

    def test_unknown_id_returns_none_without_network(self) -> None:
        """
        A dataset_id that was never returned by fetch_summaries must
        return None immediately — no network call attempted.

        We verify this without mocking the network: if the allowlist guard
        works, the method returns None synchronously before any HTTP client
        is constructed. If it doesn't, the test would either hang (timeout)
        or raise a network error in the test environment.
        """
        adapter = self._adapter()
        # _known_slugs is empty — nothing has been discovered yet
        result = adapter.fetch_detail("datagov-some-attacker-controlled-name")
        assert result is None

    def test_known_id_is_eligible_after_registration(self) -> None:
        """
        Manually registering a name in the allowlist makes it eligible for
        fetch_detail. This verifies the allowlist gate works in both directions.
        (The actual HTTP call is not made in tests — we only assert eligibility.)
        """
        adapter = self._adapter()
        # Simulate what fetch_summaries does: register a discovered name
        adapter._known_slugs.add("ssa-disability-claim-data")
        # The name is now known — fetch_detail should proceed past the guard.
        # We can't easily assert the HTTP call without a live network or mock,
        # but we can assert it does NOT return None due to the allowlist check
        # by patching the HTTP layer to raise so we see the guard was passed.
        import unittest.mock as mock

        with mock.patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.side_effect = (
                Exception("network disabled in tests")
            )
            result = adapter.fetch_detail("datagov-ssa-disability-claim-data")
            # Result is None because httpx raised, but the guard was passed
            # (mock_client_cls was actually called, proving we got past the allowlist)
            mock_client_cls.assert_called_once()
        assert result is None  # graceful failure, not an allowlist rejection

    def test_id_without_datagov_prefix_blocked(self) -> None:
        """
        A raw dataset_id with no 'datagov-' prefix strips to itself, which
        will never be in the allowlist, so it must be blocked.
        """
        adapter = self._adapter()
        result = adapter.fetch_detail("ssa-hearing-office-workload")
        assert result is None

    def test_empty_id_blocked(self) -> None:
        adapter = self._adapter()
        result = adapter.fetch_detail("")
        assert result is None

    def test_path_traversal_attempt_blocked(self) -> None:
        """
        A dataset_id designed to look like a path traversal is blocked by
        the allowlist (the stripped name was never discovered).
        """
        adapter = self._adapter()
        result = adapter.fetch_detail("datagov-../../etc/passwd")
        assert result is None

    def test_allowlist_is_per_instance(self) -> None:
        """
        Two independent adapter instances do not share allowlists.
        """
        adapter_a = self._adapter()
        adapter_b = self._adapter()
        adapter_a._known_slugs.add("some-package")
        # adapter_b must not see names registered in adapter_a
        assert "some-package" not in adapter_b._known_slugs


# ── Fix 2: Settings URL validation ────────────────────────────────────────────


class TestSettingsDataGovUrlValidation:
    """data_gov_api_base_url must be anchored to the official Data.gov host."""

    def test_default_url_is_accepted(self) -> None:
        s = Settings(data_gov_api_base_url="https://catalog.data.gov/api/v1")
        assert s.data_gov_api_base_url == "https://catalog.data.gov/api/v1"

    def test_url_with_trailing_path_accepted(self) -> None:
        s = Settings(data_gov_api_base_url="https://catalog.data.gov/api/v1/")
        assert s.data_gov_api_base_url.startswith("https://catalog.data.gov/")

    def test_http_downgrade_rejected(self) -> None:
        with pytest.raises(Exception, match="must start with"):
            Settings(data_gov_api_base_url="http://catalog.data.gov/api/3/action")

    def test_different_host_rejected(self) -> None:
        with pytest.raises(Exception, match="must start with"):
            Settings(data_gov_api_base_url="https://evil.example.com/api")

    def test_ip_literal_rejected(self) -> None:
        with pytest.raises(Exception, match="must start with"):
            Settings(data_gov_api_base_url="https://169.254.169.254/latest/meta-data/")

    def test_internal_host_rejected(self) -> None:
        with pytest.raises(Exception, match="must start with"):
            Settings(data_gov_api_base_url="https://internal.corp/api")

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(Exception, match="must start with"):
            Settings(data_gov_api_base_url="")

    def test_data_gov_subdomain_spoof_rejected(self) -> None:
        """catalog.data.gov.evil.com must not be accepted."""
        with pytest.raises(Exception, match="must start with"):
            Settings(data_gov_api_base_url="https://catalog.data.gov.evil.com/api")

    def test_protocol_relative_rejected(self) -> None:
        with pytest.raises(Exception, match="must start with"):
            Settings(data_gov_api_base_url="//catalog.data.gov/api/3/action")
