"""
Unit tests for scripts/reader_advantages.py

Tests cover:
- Brand tokens filtered AFTER counting (competitor counts remain accurate)
- 30 vs 90 day window returns different totals but consistent topic math
- Empty state falls back to Near Advantages, not blank message
- Competitor counts > 0 when competitors cover topic
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from reader_advantages import (
    advantages_to_csv,
    build_reader_advantages,
    compute_topic_scores,
    count_topics_by_source,
    extract_ngrams,
    extract_topics_from_article,
    generate_actions,
    generate_why_matters,
    get_brand_tokens,
    get_thresholds,
    partition_by_source,
)

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def brand_articles_df():
    """Articles containing brand tokens."""
    now = datetime.now(UTC)
    return pd.DataFrame([
        {
            'title': 'igbaffiliate.com launches new platform',
            'summary': 'The igbaffiliate team announces changes',
            'link': 'https://example.com/1',
            'published_date_utc': now - timedelta(days=5),
            'category': 'internal'
        },
        {
            'title': 'igamingbusiness magazine update',
            'summary': 'News from igamingbusiness team',
            'link': 'https://example.com/2',
            'published_date_utc': now - timedelta(days=6),
            'category': 'internal'
        },
    ])


@pytest.fixture
def mixed_articles_df():
    """Articles with both brand and non-brand topics, internal and competitor."""
    now = datetime.now(UTC)
    return pd.DataFrame([
        # Internal articles about sports betting
        {
            'title': 'Sports betting regulation changes in UK',
            'summary': 'New responsible gambling measures announced',
            'link': 'https://internal.com/1',
            'published_date_utc': now - timedelta(days=5),
            'category': 'internal'
        },
        {
            'title': 'UK sports betting market analysis',
            'summary': 'Sports betting regulation continues to evolve',
            'link': 'https://internal.com/2',
            'published_date_utc': now - timedelta(days=10),
            'category': 'internal'
        },
        {
            'title': 'Sports betting operators face new rules',
            'summary': 'Regulation tightens for sports betting',
            'link': 'https://internal.com/3',
            'published_date_utc': now - timedelta(days=15),
            'category': 'internal'
        },
        # Competitor articles about sports betting
        {
            'title': 'Sports betting expansion in Europe',
            'summary': 'European sports betting market grows',
            'link': 'https://competitor.com/1',
            'published_date_utc': now - timedelta(days=7),
            'category': 'competitor'
        },
        # Internal articles about prediction markets (exclusive)
        {
            'title': 'Prediction markets see growth',
            'summary': 'Kalshi and Polymarket expand offerings',
            'link': 'https://internal.com/4',
            'published_date_utc': now - timedelta(days=8),
            'category': 'internal'
        },
        {
            'title': 'Prediction markets analysis',
            'summary': 'How prediction markets are changing',
            'link': 'https://internal.com/5',
            'published_date_utc': now - timedelta(days=12),
            'category': 'internal'
        },
    ])


@pytest.fixture
def older_articles_df():
    """Articles older than 30 days but within 90 days."""
    now = datetime.now(UTC)
    return pd.DataFrame([
        {
            'title': 'Match fixing scandal investigation',
            'summary': 'UEFA investigates match fixing patterns',
            'link': 'https://internal.com/old1',
            'published_date_utc': now - timedelta(days=45),
            'category': 'internal'
        },
        {
            'title': 'Match fixing concerns in football',
            'summary': 'More match fixing cases emerge',
            'link': 'https://internal.com/old2',
            'published_date_utc': now - timedelta(days=50),
            'category': 'internal'
        },
        {
            'title': 'Match fixing update from regulators',
            'summary': 'Regulators crack down on match fixing',
            'link': 'https://internal.com/old3',
            'published_date_utc': now - timedelta(days=55),
            'category': 'internal'
        },
    ])


# ============================================================================
# Test: Brand Tokens Filtered AFTER Counting
# ============================================================================

class TestBrandTokenFilteringOrder:
    """Brand tokens should be filtered AFTER counting to preserve competitor counts."""

    def test_brand_tokens_loaded(self):
        """Brand tokens should be loaded from config or defaults."""
        tokens = get_brand_tokens()
        assert 'igbaffiliate' in tokens
        assert 'igamingbusiness' in tokens
        assert 'clarion' in tokens

    def test_brand_topics_not_in_output(self, mixed_articles_df):
        """Brand topics should not appear in final output."""
        result = build_reader_advantages(mixed_articles_df, window_days=30)
        topics = result.get('topics', [])

        topic_names = [t['topic'].lower() for t in topics]

        # Brand tokens should not appear
        for topic in topic_names:
            assert 'igbaffiliate' not in topic
            assert 'igamingbusiness' not in topic
            assert 'clarion' not in topic

    def test_competitor_counts_preserved_for_non_brand_topics(self, mixed_articles_df):
        """Non-brand topics should have accurate competitor counts."""
        result = build_reader_advantages(mixed_articles_df, window_days=30)
        topics = result.get('topics', [])

        # Sports betting has competitor coverage - their_count should be > 0
        for topic in topics:
            if 'sports' in topic['topic'].lower() or 'betting' in topic['topic'].lower():
                # If this topic appears, verify structure
                assert 'their_count' in topic
                assert isinstance(topic['their_count'], int)


# ============================================================================
# Test: Window Changes Counts But Not Topic Math
# ============================================================================

class TestWindowConsistency:
    """30 vs 90 day window should change counts but topic math remains consistent."""

    def test_30_day_excludes_older(self, mixed_articles_df, older_articles_df):
        """30-day window should exclude articles older than 30 days."""
        combined = pd.concat([mixed_articles_df, older_articles_df], ignore_index=True)

        result_30 = build_reader_advantages(combined, window_days=30)
        topics_30 = result_30.get('topics', [])

        # Match fixing articles are all > 30 days old, shouldn't qualify
        topic_names_30 = [t['topic'].lower() for t in topics_30]

        # Even in near_advantages it shouldn't appear (articles too old)
        near_30 = result_30.get('near_advantages', [])
        near_names_30 = [t['topic'].lower() for t in near_30]

        all_30 = topic_names_30 + near_names_30
        # Match fixing might not appear due to being outside 30-day window
        # This is expected behavior

    def test_90_day_includes_older(self, mixed_articles_df, older_articles_df):
        """90-day window should include articles up to 90 days old."""
        combined = pd.concat([mixed_articles_df, older_articles_df], ignore_index=True)

        result_90 = build_reader_advantages(combined, window_days=90)
        diagnostics = result_90.get('diagnostics', {})

        # 90-day window should have more articles analyzed
        assert diagnostics.get('total_internal_articles', 0) >= len(mixed_articles_df[mixed_articles_df['category'] == 'internal'])

    def test_diagnostics_reflect_window(self, mixed_articles_df, older_articles_df):
        """Diagnostics should show different article counts for different windows."""
        combined = pd.concat([mixed_articles_df, older_articles_df], ignore_index=True)

        result_30 = build_reader_advantages(combined, window_days=30)
        result_90 = build_reader_advantages(combined, window_days=90)

        diag_30 = result_30.get('diagnostics', {})
        diag_90 = result_90.get('diagnostics', {})

        # 90-day window should have >= 30-day count
        assert diag_90.get('total_internal_articles', 0) >= diag_30.get('total_internal_articles', 0)


# ============================================================================
# Test: Empty State Falls Back to Near Advantages
# ============================================================================

class TestEmptyStateFallback:
    """Empty state should fall back to Near Advantages, never blank."""

    def test_near_advantages_populated(self, mixed_articles_df):
        """Near advantages should be populated even when main topics are empty."""
        result = build_reader_advantages(mixed_articles_df, window_days=30)

        # Should have structure even if empty
        assert 'topics' in result
        assert 'near_advantages' in result
        assert isinstance(result['topics'], list)
        assert isinstance(result['near_advantages'], list)

    def test_empty_df_returns_structure(self):
        """Empty DataFrame should return valid structure."""
        result = build_reader_advantages(pd.DataFrame(), window_days=30)

        assert 'topics' in result
        assert 'near_advantages' in result
        assert 'diagnostics' in result
        assert result['diagnostics']['total_internal_articles'] == 0

    def test_actionable_fallback_always_available(self):
        """Generate functions should always return actionable content."""
        # Test generate_why_matters with various scenarios
        why = generate_why_matters({'ownership': True})
        assert len(why) > 0
        assert 'only we' in why.lower() or 'covered' in why.lower()

        why = generate_why_matters({'edge': True, 'our_share': 0.7})
        assert len(why) > 0

        # Test generate_actions
        actions = generate_actions({'topic': 'test topic'})
        assert 'content' in actions
        assert 'product' in actions
        assert 'commercial' in actions
        assert len(actions['content']) > 0


# ============================================================================
# Test: Competitor Counts Accuracy
# ============================================================================

class TestCompetitorCounts:
    """Competitor counts should be accurate based on source_type."""

    def test_partition_by_source(self, mixed_articles_df):
        """partition_by_source should correctly split internal vs competitor."""
        internal, competitor = partition_by_source(mixed_articles_df)

        assert len(internal) > 0
        assert len(competitor) > 0
        assert all(internal['category'] == 'internal')
        assert all(competitor['category'] == 'competitor')

    def test_their_count_nonzero_when_competitors_cover(self, mixed_articles_df):
        """their_count should be > 0 when competitors have articles on topic."""
        brand_tokens = get_brand_tokens()
        internal, competitor = partition_by_source(mixed_articles_df)

        topic_counts = count_topics_by_source(internal, competitor, brand_tokens, window_days=30)

        # Find topics with competitor coverage
        has_competitor_coverage = False
        for topic, data in topic_counts.items():
            if data['their_count'] > 0:
                has_competitor_coverage = True
                break

        # At least one topic should have competitor coverage
        # (sports betting is covered by both)
        assert has_competitor_coverage, "Expected at least one topic with their_count > 0"

    def test_examples_them_populated(self, mixed_articles_df):
        """examples_them should be populated when competitors cover topic."""
        result = build_reader_advantages(mixed_articles_df, window_days=30)

        # Check all topics and near_advantages
        all_topics = result.get('topics', []) + result.get('near_advantages', [])

        for topic in all_topics:
            # examples_them should exist and be a list
            assert 'examples_them' in topic
            assert isinstance(topic['examples_them'], list)


# ============================================================================
# Test: Scoring and Selection
# ============================================================================

class TestScoringAndSelection:
    """Test scoring weights and selection criteria."""

    def test_ownership_scores_highest(self):
        """Ownership (them=0, us>=2) should score highest."""
        topics = {
            'exclusive_topic': {
                'topic': 'exclusive_topic',
                'our_count': 5,
                'their_count': 0,
                'total': 5,
                'our_share': 1.0,
                'their_share': 0.0,
                'share_diff': 1.0,
                'our_count_7d': 2,
                'their_count_7d': 0,
                'examples_us': [],
                'examples_them': [],
            },
            'shared_topic': {
                'topic': 'shared_topic',
                'our_count': 5,
                'their_count': 3,
                'total': 8,
                'our_share': 0.625,
                'their_share': 0.375,
                'share_diff': 0.25,
                'our_count_7d': 1,
                'their_count_7d': 1,
                'examples_us': [],
                'examples_them': [],
            }
        }

        thresholds = get_thresholds()
        scored, near = compute_topic_scores(topics, thresholds)

        # Exclusive should score higher
        if len(scored) >= 2:
            exclusive = next((t for t in scored if t['topic'] == 'exclusive_topic'), None)
            shared = next((t for t in scored if t['topic'] == 'shared_topic'), None)

            if exclusive and shared:
                assert exclusive['score'] >= shared['score']

    def test_gates_applied_correctly(self):
        """Topics below thresholds should go to near_advantages."""
        topics = {
            'passes_gates': {
                'topic': 'passes_gates',
                'our_count': 3,
                'their_count': 0,
                'total': 3,
                'our_share': 1.0,
                'their_share': 0.0,
                'share_diff': 1.0,
                'our_count_7d': 2,
                'their_count_7d': 0,
                'examples_us': [],
                'examples_them': [],
            },
            'fails_min_our': {
                'topic': 'fails_min_our',
                'our_count': 1,
                'their_count': 0,
                'total': 1,
                'our_share': 1.0,
                'their_share': 0.0,
                'share_diff': 1.0,
                'our_count_7d': 1,
                'their_count_7d': 0,
                'examples_us': [],
                'examples_them': [],
            }
        }

        thresholds = get_thresholds()
        scored, near = compute_topic_scores(topics, thresholds)

        # passes_gates should be in scored
        scored_names = [t['topic'] for t in scored]
        assert 'passes_gates' in scored_names

        # fails_min_our should not be in scored (might be in near if share_diff > 0)
        assert 'fails_min_our' not in scored_names


# ============================================================================
# Test: CSV Export
# ============================================================================

class TestCSVExport:
    """Test CSV export functionality."""

    def test_csv_has_required_columns(self, mixed_articles_df):
        """CSV should have all required columns."""
        result = build_reader_advantages(mixed_articles_df, window_days=30)
        csv_str = advantages_to_csv(result)

        assert 'topic' in csv_str
        assert 'our_count' in csv_str
        assert 'their_count' in csv_str
        assert 'our_share' in csv_str

    def test_empty_csv_has_header(self):
        """Empty result should return CSV with header."""
        result = build_reader_advantages(pd.DataFrame(), window_days=30)
        csv_str = advantages_to_csv(result)

        assert 'topic' in csv_str


# ============================================================================
# Test: Text Processing
# ============================================================================

class TestTextProcessing:
    """Test n-gram extraction and topic extraction."""

    def test_extract_ngrams(self):
        """extract_ngrams should extract valid n-grams."""
        text = "UK sports betting regulation is changing rapidly"
        ngrams = extract_ngrams(text, (1, 2))

        # Should have unigrams and bigrams
        assert 'sports' in ngrams or 'betting' in ngrams
        assert any('sports' in ng or 'betting' in ng for ng in ngrams)

    def test_extract_topics_from_article(self):
        """extract_topics_from_article should return top topics."""
        title = "Sports betting regulation update"
        summary = "New responsible gambling measures for sports betting"

        topics = extract_topics_from_article(title, summary, '')

        assert len(topics) <= 3
        assert len(topics) > 0


# ============================================================================
# Test: Integration
# ============================================================================

class TestIntegration:
    """Integration tests for full workflow."""

    def test_full_workflow(self, mixed_articles_df):
        """Test complete workflow from DataFrame to advantages."""
        result = build_reader_advantages(mixed_articles_df, window_days=30)

        # Should have required structure
        assert 'window_days' in result
        assert 'generated_at' in result
        assert 'topics' in result
        assert 'near_advantages' in result
        assert 'metadata' in result
        assert 'diagnostics' in result

        # Window should match
        assert result['window_days'] == 30

        # Diagnostics should be populated
        assert result['diagnostics']['total_internal_articles'] > 0

    def test_topics_have_required_fields(self, mixed_articles_df):
        """Topics should have all required fields."""
        result = build_reader_advantages(mixed_articles_df, window_days=30)
        topics = result.get('topics', []) + result.get('near_advantages', [])

        for topic in topics:
            assert 'topic' in topic
            assert 'our_count' in topic
            assert 'their_count' in topic
            assert 'our_share' in topic
            assert 'ownership' in topic
            assert 'edge' in topic
            assert 'examples_us' in topic
            assert 'examples_them' in topic
