#!/usr/bin/env python3
"""
Regression Test Suite for Data Integrity
Tests critical defects identified in defect hunt (P0-1, P0-2, P0-3)
"""

import hashlib
import sys
from pathlib import Path

import pandas as pd
import pytest

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

from main import NewsAggregator, normalize_url

from paths import NEWS_HISTORY_CSV


class TestArticleIDGeneration:
    """Test P0-1: article_id generation must be deterministic and consistent"""

    def test_article_id_deterministic(self):
        """Same URL must always produce same article_id"""
        agg = NewsAggregator()
        url = "https://example.com/article/"
        source = "Test Source"

        id1 = agg.generate_article_id(source, url)
        id2 = agg.generate_article_id(source, url)

        assert id1 == id2, f"article_id generation not deterministic: {id1} vs {id2}"

    def test_article_id_uses_normalize_url(self):
        """article_id generation must use normalize_url, not strip_tracking_params"""
        agg = NewsAggregator()
        source = "Test Source"

        # Test URLs that normalize differently between the two functions
        test_urls = [
            "https://example.com/article/",
            "https://example.com/article?utm_source=test&id=123",
            "https://EXAMPLE.COM/Article/",  # Case sensitivity
        ]

        for url in test_urls:
            # Generate article_id
            article_id = agg.generate_article_id(source, url)

            # Manually compute expected ID using normalize_url
            normalized = normalize_url(url)
            expected_id = hashlib.sha256(f"{source.lower()}|{normalized}".encode()).hexdigest()[:16]

            assert article_id == expected_id, (
                f"article_id uses wrong normalization for {url}\n"
                f"  Expected (normalize_url): {expected_id}\n"
                f"  Got: {article_id}"
            )

    def test_normalization_consistency(self):
        """Verify normalize_url produces consistent output"""
        test_cases = [
            ("https://example.com/", "https://example.com/"),
            ("https://EXAMPLE.com/", "https://example.com/"),  # Lowercase domain
            ("https://example.com/?utm_source=test", "https://example.com/"),  # Remove tracking
            # Note: normalize_url preserves root domain without trailing slash when no path
            ("https://example.com#anchor", "https://example.com"),  # Remove fragment, no trailing slash for root
        ]

        for input_url, expected_output in test_cases:
            result = normalize_url(input_url)
            assert result == expected_output, (
                f"normalize_url({input_url}) = {result}, expected {expected_output}"
            )


class TestCSVIntegrity:
    """Test P0-3: CSV must not contain duplicate URLs"""

    def test_no_duplicate_urls(self):
        """CSV must not contain duplicate URLs (normalized)"""
        if not NEWS_HISTORY_CSV.exists():
            pytest.skip("CSV file doesn't exist yet")

        df = pd.read_csv(NEWS_HISTORY_CSV)
        df['link_norm'] = df['link'].str.lower().str.strip()

        # Check for duplicates
        duplicates = df[df.duplicated('link_norm', keep=False)]

        if len(duplicates) > 0:
            # Show sample duplicates for debugging
            dup_urls = duplicates.groupby('link_norm').size().sort_values(ascending=False)
            sample = dup_urls.head(5)
            error_msg = (
                f"Found {len(duplicates)} duplicate URL entries in CSV\n"
                f"Top duplicates:\n{sample}\n"
                f"This indicates P0-3 fix is not working correctly"
            )
            pytest.fail(error_msg)

    def test_article_id_uniqueness(self):
        """All article_ids in CSV must be unique"""
        if not NEWS_HISTORY_CSV.exists():
            pytest.skip("CSV file doesn't exist yet")

        df = pd.read_csv(NEWS_HISTORY_CSV)

        duplicates = df[df.duplicated('article_id', keep=False)]

        if len(duplicates) > 0:
            dup_ids = duplicates['article_id'].unique()
            pytest.fail(
                f"Found {len(duplicates)} rows with duplicate article_ids\n"
                f"Duplicate IDs: {list(dup_ids[:5])}"
            )

    def test_no_null_critical_fields(self):
        """Critical fields must never be null"""
        if not NEWS_HISTORY_CSV.exists():
            pytest.skip("CSV file doesn't exist yet")

        df = pd.read_csv(NEWS_HISTORY_CSV)

        critical_fields = ['article_id', 'title', 'link', 'source']

        for field in critical_fields:
            null_count = df[field].isna().sum()
            assert null_count == 0, f"Found {null_count} null values in critical field '{field}'"


class TestAtomicWrites:
    """Test P0-2: CSV writes must be atomic"""

    def test_csv_write_uses_temp_file(self):
        """Verify that CSV write creates temp file first"""
        # This is a code inspection test
        import inspect

        from main import NewsAggregator

        # Get source code of save_to_history method
        source = inspect.getsource(NewsAggregator.save_to_history)

        # Check for temp file pattern
        assert '.tmp' in source or 'temp' in source.lower(), (
            "save_to_history() doesn't appear to use temp file pattern for atomic write"
        )

        # Check for os.replace or os.rename
        assert 'os.replace' in source or 'os.rename' in source, (
            "save_to_history() doesn't use atomic rename operation"
        )


class TestRepeatedRuns:
    """Test repeatability: running pipeline twice should be idempotent"""

    @pytest.mark.slow
    def test_second_run_no_duplicates(self):
        """
        Running scraper twice with same data should not create duplicates.
        This is an integration test that requires actual execution.
        """
        # This would require mocking the RSS feeds to return same data
        # For now, document the expected behavior
        pytest.skip("Integration test - requires mock RSS feeds")


class TestDataQuality:
    """General data quality checks"""

    def test_timestamp_format_consistency(self):
        """All timestamps must be in consistent format (naive UTC)"""
        if not NEWS_HISTORY_CSV.exists():
            pytest.skip("CSV file doesn't exist yet")

        df = pd.read_csv(NEWS_HISTORY_CSV)

        if 'scrape_timestamp' in df.columns:
            # Check no timestamps have timezone info
            sample = df['scrape_timestamp'].dropna().head(100)

            for ts in sample:
                ts_str = str(ts)
                # Check for timezone indicators (more precise check)
                # Valid naive format: YYYY-MM-DD HH:MM (no timezone offset)
                has_tz = any([
                    '+' in ts_str and ':' in ts_str.split('+')[-1] and len(ts_str.split('+')[-1]) > 2,
                    'UTC' in ts_str.upper(),
                    'Z' == ts_str[-1],  # ISO format with Z suffix
                    'T' in ts_str and ('Z' in ts_str or '+' in ts_str[-6:] or '-' in ts_str[-6:])
                ])

                assert not has_tz, (
                    f"Timestamp has timezone info: {ts_str}\n"
                    f"All timestamps should be naive UTC format (YYYY-MM-DD HH:MM)"
                )

    def test_csv_not_corrupted(self):
        """CSV file must be parseable and not corrupted"""
        if not NEWS_HISTORY_CSV.exists():
            pytest.skip("CSV file doesn't exist yet")

        try:
            df = pd.read_csv(NEWS_HISTORY_CSV)

            # Basic sanity checks
            assert len(df) > 0, "CSV is empty"
            assert len(df.columns) > 5, "CSV has too few columns"

        except Exception as e:
            pytest.fail(f"CSV file is corrupted or unparseable: {str(e)}")


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v", "--tb=short"])
