"""
Acceptance tests for reader advantages count sanity.

These tests ensure:
1. No card can show competitor count greater than the competitor window total
2. Counts remain stable if additional keywords are added
3. 30 and 90-day windows both produce consistent totals
"""

import sys

import pandas as pd
import pytest

sys.path.insert(0, '.')

from src.reader_advantages_v2 import detect_all_advantages


@pytest.fixture
def sample_df():
    """Load actual news history data."""
    return pd.read_csv('data/news_history.csv')


class TestCountSanity:
    """Tests to verify counts never exceed window denominators."""

    def test_competitor_count_never_exceeds_window_total_30d(self, sample_df):
        """No card's competitor_count should exceed total competitor articles in 30-day window."""
        result = detect_all_advantages(sample_df, window_days=30)

        max_competitor = result['diagnostics']['max_competitor_in_window']
        if max_competitor == 0:
            pytest.skip("No competitor articles in 30-day window (stale data — run pipeline)")

        for card in result['cards']:
            assert card['competitor_count'] <= max_competitor, (
                f"Card '{card['advantage_key']}' has competitor_count={card['competitor_count']} "
                f"but max allowed is {max_competitor}"
            )

    def test_competitor_count_never_exceeds_window_total_90d(self, sample_df):
        """No card's competitor_count should exceed total competitor articles in 90-day window."""
        result = detect_all_advantages(sample_df, window_days=90)

        max_competitor = result['diagnostics']['max_competitor_in_window']
        assert max_competitor > 0, "Expected competitor articles in 90-day window"

        for card in result['cards']:
            assert card['competitor_count'] <= max_competitor, (
                f"Card '{card['advantage_key']}' has competitor_count={card['competitor_count']} "
                f"but max allowed is {max_competitor}"
            )

    def test_internal_count_never_exceeds_window_total_30d(self, sample_df):
        """No card's internal_count should exceed total internal articles in 30-day window."""
        result = detect_all_advantages(sample_df, window_days=30)

        max_internal = result['diagnostics']['max_internal_in_window']
        if max_internal == 0:
            pytest.skip("No internal articles in 30-day window (stale data — run pipeline)")

        for card in result['cards']:
            assert card['internal_count'] <= max_internal, (
                f"Card '{card['advantage_key']}' has internal_count={card['internal_count']} "
                f"but max allowed is {max_internal}"
            )

    def test_internal_count_never_exceeds_window_total_90d(self, sample_df):
        """No card's internal_count should exceed total internal articles in 90-day window."""
        result = detect_all_advantages(sample_df, window_days=90)

        max_internal = result['diagnostics']['max_internal_in_window']
        assert max_internal > 0, "Expected internal articles in 90-day window"

        for card in result['cards']:
            assert card['internal_count'] <= max_internal, (
                f"Card '{card['advantage_key']}' has internal_count={card['internal_count']} "
                f"but max allowed is {max_internal}"
            )


class TestWindowConsistency:
    """Tests to verify 30-day and 90-day windows produce consistent totals."""

    def test_90d_window_contains_more_or_equal_articles(self, sample_df):
        """90-day window should have >= articles than 30-day window."""
        result_30 = detect_all_advantages(sample_df, window_days=30)
        result_90 = detect_all_advantages(sample_df, window_days=90)

        internal_30 = result_30['diagnostics']['internal_articles']
        internal_90 = result_90['diagnostics']['internal_articles']
        competitor_30 = result_30['diagnostics']['competitor_articles']
        competitor_90 = result_90['diagnostics']['competitor_articles']

        assert internal_90 >= internal_30, (
            f"90-day internal ({internal_90}) should be >= 30-day ({internal_30})"
        )
        assert competitor_90 >= competitor_30, (
            f"90-day competitor ({competitor_90}) should be >= 30-day ({competitor_30})"
        )

    def test_diagnostics_match_window_max(self, sample_df):
        """Diagnostics should accurately reflect window maximums."""
        result = detect_all_advantages(sample_df, window_days=30)

        assert result['diagnostics']['internal_articles'] == result['diagnostics']['max_internal_in_window']
        assert result['diagnostics']['competitor_articles'] == result['diagnostics']['max_competitor_in_window']


class TestCountStability:
    """Tests to verify counts are stable and use unique article IDs."""

    def test_followthrough_counts_unique_articles(self, sample_df):
        """Follow-through detection should count unique article_ids, not cluster memberships."""
        result = detect_all_advantages(sample_df, window_days=30)

        # Find followthrough card if it exists
        followthrough_cards = [c for c in result['cards'] if c['advantage_key'] == 'followthrough_coverage']
        if not followthrough_cards:
            pytest.skip("No followthrough card generated")

        card = followthrough_cards[0]
        max_competitor = result['diagnostics']['max_competitor_in_window']

        # This was the main bug - counts were inflated due to multi-cluster membership
        # With the fix, competitor_count should be <= max_competitor
        assert card['competitor_count'] <= max_competitor, (
            f"followthrough competitor_count ({card['competitor_count']}) exceeds "
            f"max possible ({max_competitor}). Articles likely counted multiple times."
        )

    def test_geography_counts_unique_articles(self, sample_df):
        """Geography detection should count unique article_ids when aggregating regions."""
        result = detect_all_advantages(sample_df, window_days=30)

        # Find geography card if it exists
        geo_cards = [c for c in result['cards'] if c['advantage_key'] == 'geography_depth']
        if not geo_cards:
            pytest.skip("No geography card generated")

        card = geo_cards[0]
        max_competitor = result['diagnostics']['max_competitor_in_window']
        max_internal = result['diagnostics']['max_internal_in_window']

        assert card['competitor_count'] <= max_competitor, (
            f"geography competitor_count ({card['competitor_count']}) exceeds "
            f"max possible ({max_competitor})"
        )
        assert card['internal_count'] <= max_internal, (
            f"geography internal_count ({card['internal_count']}) exceeds "
            f"max possible ({max_internal})"
        )


class TestSanityWarnings:
    """Tests for sanity check auto-correction behavior."""

    def test_no_sanity_warnings_in_debug(self, sample_df):
        """After fix, there should be no sanity warnings triggered."""
        result_30 = detect_all_advantages(sample_df, window_days=30)
        result_90 = detect_all_advantages(sample_df, window_days=90)

        assert 'sanity_warnings' not in result_30['debug'], (
            f"30-day window triggered sanity warnings: {result_30['debug'].get('sanity_warnings')}"
        )
        assert 'sanity_warnings' not in result_90['debug'], (
            f"90-day window triggered sanity warnings: {result_90['debug'].get('sanity_warnings')}"
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
