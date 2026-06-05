#!/usr/bin/env python3
"""
Tests for domain blocklist functionality.

Ensures that blocked domains (e.g., icegaming.com) are filtered at ingestion
and never appear in the news history.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.main import BLOCKED_DOMAINS, is_blocked, normalize_domain


class TestNormalizeDomain:
    """Test domain normalization for blocklist matching."""

    def test_basic_domain(self):
        """Test extraction of basic domain."""
        assert normalize_domain("https://icegaming.com/path") == "icegaming.com"

    def test_uppercase_domain(self):
        """Test case normalization (uppercase to lowercase)."""
        assert normalize_domain("https://ICEGAMING.com/path") == "icegaming.com"

    def test_www_prefix(self):
        """Test removal of www. prefix."""
        assert normalize_domain("https://www.icegaming.com/x?y=1") == "icegaming.com"

    def test_subdomain(self):
        """Test subdomain preservation."""
        assert normalize_domain("https://news.icegaming.com/article") == "news.icegaming.com"

    def test_with_port(self):
        """Test port stripping."""
        assert normalize_domain("https://icegaming.com:8080/path") == "icegaming.com"

    def test_http_protocol(self):
        """Test HTTP (non-HTTPS) URLs."""
        assert normalize_domain("http://icegaming.com/path") == "icegaming.com"

    def test_query_params(self):
        """Test URLs with query parameters."""
        assert normalize_domain("https://icegaming.com/news?utm_source=twitter") == "icegaming.com"

    def test_invalid_url(self):
        """Test invalid URL returns empty string."""
        assert normalize_domain("not-a-url") == ""

    def test_empty_string(self):
        """Test empty string returns empty string."""
        assert normalize_domain("") == ""


class TestIsBlocked:
    """Test blocklist matching logic."""

    def test_exact_match(self):
        """Test exact domain match is blocked."""
        assert is_blocked("https://icegaming.com/news") is True

    def test_www_variant(self):
        """Test www. variant is blocked."""
        assert is_blocked("https://www.icegaming.com/news") is True

    def test_subdomain(self):
        """Test subdomain is blocked."""
        assert is_blocked("https://sub.icegaming.com/x") is True

    def test_multiple_subdomains(self):
        """Test nested subdomains are blocked."""
        assert is_blocked("https://news.events.icegaming.com/article") is True

    def test_uppercase_url(self):
        """Test case-insensitive blocking."""
        assert is_blocked("https://ICEGAMING.COM/news") is True

    def test_unblocked_domain(self):
        """Test non-blocked domain is allowed."""
        assert is_blocked("https://example.com/x") is False

    def test_similar_domain_not_blocked(self):
        """Test similar but different domain is not blocked."""
        assert is_blocked("https://icegaming-news.com/article") is False

    def test_partial_match_not_blocked(self):
        """Test partial domain match is not blocked."""
        assert is_blocked("https://myicegaming.com/article") is False

    def test_http_protocol(self):
        """Test HTTP URLs are also blocked."""
        assert is_blocked("http://icegaming.com/news") is True

    def test_with_query_params(self):
        """Test URLs with query parameters are blocked."""
        assert is_blocked("https://icegaming.com/news?id=123&utm_source=twitter") is True

    def test_invalid_url(self):
        """Test invalid URL is not blocked (returns False)."""
        assert is_blocked("not-a-url") is False

    def test_empty_url(self):
        """Test empty URL is not blocked."""
        assert is_blocked("") is False


class TestBlockedDomains:
    """Test BLOCKED_DOMAINS configuration."""

    def test_blocklist_exists(self):
        """Test BLOCKED_DOMAINS set exists and is not empty."""
        assert BLOCKED_DOMAINS is not None
        assert len(BLOCKED_DOMAINS) > 0

    def test_icegaming_in_blocklist(self):
        """Test icegaming.com is in the blocklist."""
        assert "icegaming.com" in BLOCKED_DOMAINS

    def test_blocklist_is_set(self):
        """Test BLOCKED_DOMAINS is a set (for O(1) lookup)."""
        assert isinstance(BLOCKED_DOMAINS, set)


class TestBlocklistIntegration:
    """Integration tests for blocklist behavior."""

    def test_all_blocked_domains_are_caught(self):
        """Test that all domains in BLOCKED_DOMAINS are caught by is_blocked."""
        for domain in BLOCKED_DOMAINS:
            test_url = f"https://{domain}/article"
            assert is_blocked(test_url) is True, f"Domain {domain} should be blocked"

    def test_common_news_sites_not_blocked(self):
        """Test that common legitimate news sites are not blocked."""
        legitimate_sites = [
            "https://sbcnews.co.uk/article",
            "https://igamingbusiness.com/news",
            "https://igamingfuture.com/article",
            "https://next.io/news",
            "https://egrmagazine.com/article"
        ]

        for url in legitimate_sites:
            assert is_blocked(url) is False, f"Legitimate site {url} should not be blocked"


# Optional: Integration test with actual CSV (if history file exists)
class TestHistoryIntegrity:
    """Test that blocked domains never appear in history."""

    def test_history_has_no_blocked_domains(self):
        """
        Integration test: Verify news_history.csv contains no blocked domains.
        This test is skipped if the history file doesn't exist.
        """
        import pandas as pd

        from paths import NEWS_HISTORY_CSV

        if not NEWS_HISTORY_CSV.exists():
            pytest.skip("History file not found - skipping integration test")

        df = pd.read_csv(NEWS_HISTORY_CSV)

        if 'link' not in df.columns or df.empty:
            pytest.skip("History file has no links - skipping integration test")

        # Check all links in history
        for idx, row in df.iterrows():
            link = row.get('link', '')
            if pd.notna(link) and link:
                assert not is_blocked(str(link)), \
                    f"Blocked domain found in history at row {idx}: {link}"

    def test_history_has_no_ice_gaming_source(self):
        """
        Integration test: Verify news_history.csv contains no ICE Gaming source entries.
        This test is skipped if the history file doesn't exist.
        """
        import pandas as pd

        from paths import NEWS_HISTORY_CSV

        if not NEWS_HISTORY_CSV.exists():
            pytest.skip("History file not found - skipping integration test")

        df = pd.read_csv(NEWS_HISTORY_CSV)

        if 'source' not in df.columns or df.empty:
            pytest.skip("History file has no source column - skipping integration test")

        # Check no ICE Gaming sources
        ice_sources = df[df['source'] == 'ICE Gaming']
        assert len(ice_sources) == 0, \
            f"Found {len(ice_sources)} ICE Gaming entries in history (should be 0)"
