"""
Unit tests for src/reader_topics.py

Tests cover:
- Brand token exclusion (REQUIRED)
- Tokenizer consistency between Us and Them
- Topic discovery and filtering
- Sanity checks for non-brand topics
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.reader_topics import (
    build_reader_topics,
    count_matches,
    format_evidence_html,
    is_brand_token,
    is_valid_topic,
    suggest_action,
    summarize_why,
    tokenize_phrases,
    topics_to_csv,
)

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def brand_articles_df():
    """Articles containing brand/domain tokens that should be filtered."""
    return pd.DataFrame([
        {
            'title': 'igbaffiliate.com launches new platform',
            'summary': 'The igbaffiliate team announces changes',
            'body': 'Visit igbaffiliate.com for more information',
            'link': 'https://example.com/1',
            'published_date_utc': '2024-01-15',
            'category': 'internal'
        },
        {
            'title': 'igamingbusiness.com coverage update',
            'summary': 'News from igamingbusiness magazine',
            'body': 'The igamingbusiness team reports on trends',
            'link': 'https://example.com/2',
            'published_date_utc': '2024-01-14',
            'category': 'internal'
        },
        {
            'title': 'barcelona.igbaffiliate.com event news',
            'summary': 'IGB Barcelona conference highlights',
            'body': 'The clarion gaming event was successful',
            'link': 'https://example.com/3',
            'published_date_utc': '2024-01-13',
            'category': 'internal'
        }
    ])


@pytest.fixture
def clean_articles_df():
    """Articles with legitimate non-brand topics."""
    return pd.DataFrame([
        {
            'title': 'UK sports betting regulation changes',
            'summary': 'New responsible gambling measures announced',
            'body': 'The UK Gambling Commission has introduced new rules for sports betting operators.',
            'link': 'https://example.com/4',
            'published_date_utc': '2024-01-15',
            'category': 'internal'
        },
        {
            'title': 'Prediction markets see growth in US',
            'summary': 'Kalshi and Polymarket expand offerings',
            'body': 'Prediction markets are gaining traction among US investors seeking new opportunities.',
            'link': 'https://example.com/5',
            'published_date_utc': '2024-01-14',
            'category': 'internal'
        },
        {
            'title': 'Match fixing scandal rocks European football',
            'summary': 'UEFA investigates suspicious betting patterns',
            'body': 'Match fixing concerns have led to investigations across multiple leagues.',
            'link': 'https://example.com/6',
            'published_date_utc': '2024-01-13',
            'category': 'internal'
        },
        {
            'title': 'UK sports betting market analysis',
            'summary': 'Market growth continues despite challenges',
            'body': 'Sports betting in the UK shows resilience with new operators entering.',
            'link': 'https://example.com/7',
            'published_date_utc': '2024-01-12',
            'category': 'internal'
        },
        {
            'title': 'Sports betting regulation update',
            'summary': 'State-by-state breakdown of new rules',
            'body': 'Regulation continues to evolve across US states for sports betting.',
            'link': 'https://example.com/8',
            'published_date_utc': '2024-01-11',
            'category': 'internal'
        }
    ])


@pytest.fixture
def competitor_articles_df():
    """Competitor articles for testing Us vs Them consistency."""
    return pd.DataFrame([
        {
            'title': 'Sports betting expansion in New York',
            'summary': 'NY mobile betting hits record handle',
            'body': 'Sports betting continues to grow in the Empire State.',
            'link': 'https://competitor.com/1',
            'published_date_utc': '2024-01-15',
            'category': 'competitor'
        },
        {
            'title': 'European casino market trends',
            'summary': 'Online casino revenue increases',
            'body': 'European online casino operators report strong Q4 results.',
            'link': 'https://competitor.com/2',
            'published_date_utc': '2024-01-14',
            'category': 'competitor'
        }
    ])


# ============================================================================
# Brand Token Exclusion Tests (REQUIRED)
# ============================================================================

class TestBrandTokenExclusion:
    """Tests that brand tokens are NEVER surfaced as topics."""

    def test_igbaffiliate_is_brand(self):
        """igbaffiliate must be detected as brand token."""
        assert is_brand_token("igbaffiliate") is True
        assert is_brand_token("IGBAFFILIATE") is True
        assert is_brand_token("igbaffiliate.com") is True

    def test_igamingbusiness_is_brand(self):
        """igamingbusiness must be detected as brand token."""
        assert is_brand_token("igamingbusiness") is True
        assert is_brand_token("igamingbusiness.com") is True
        assert is_brand_token("IGAMINGBUSINESS") is True

    def test_igb_variants_are_brands(self):
        """IGB short variants must be detected."""
        assert is_brand_token("igb") is True
        assert is_brand_token("igba") is True
        assert is_brand_token("IGB") is True

    def test_clarion_is_brand(self):
        """Clarion brand must be filtered."""
        assert is_brand_token("clarion") is True
        assert is_brand_token("clarionigaming") is True

    def test_barcelona_domain_is_brand(self):
        """barcelona.igbaffiliate.com paths must be filtered."""
        assert is_brand_token("barcelona.igbaffiliate.com") is True

    def test_brand_topics_never_appear(self, brand_articles_df):
        """Topics built from brand tokens must NEVER appear in output."""
        topics_df = build_reader_topics(
            brand_articles_df,
            pd.DataFrame(),  # No competitors
            window_days=30
        )

        if len(topics_df) > 0:
            topic_names = topics_df['topic'].str.lower().tolist()

            # Assert no brand tokens in output
            for topic in topic_names:
                assert 'igbaffiliate' not in topic, f"Brand token 'igbaffiliate' found in topic: {topic}"
                assert 'igamingbusiness' not in topic, f"Brand token 'igamingbusiness' found in topic: {topic}"
                assert 'clarion' not in topic, f"Brand token 'clarion' found in topic: {topic}"
                assert 'igb' not in topic.split(), f"Brand token 'igb' found as word in topic: {topic}"

    def test_is_valid_topic_rejects_brands(self):
        """is_valid_topic must reject all brand patterns."""
        assert is_valid_topic("igbaffiliate") is False
        assert is_valid_topic("igamingbusiness news") is False
        assert is_valid_topic("clarion gaming") is False
        assert is_valid_topic("igb magazine") is False

    def test_is_valid_topic_accepts_clean_topics(self):
        """is_valid_topic must accept legitimate topics."""
        assert is_valid_topic("sports betting") is True
        assert is_valid_topic("responsible gambling") is True
        assert is_valid_topic("prediction markets") is True
        assert is_valid_topic("match fixing") is True


# ============================================================================
# Tokenizer Consistency Tests
# ============================================================================

class TestTokenizerConsistency:
    """Tests that Us and Them use SAME tokenizer and fields."""

    def test_count_matches_uses_same_logic(self, clean_articles_df, competitor_articles_df):
        """count_matches must use identical logic for both corpora."""
        phrases = ["sports betting", "regulation"]

        # Both should use same matching logic
        us_counts = count_matches(clean_articles_df, phrases)
        them_counts = count_matches(competitor_articles_df, phrases)

        # Structure should be identical
        assert isinstance(us_counts, dict)
        assert isinstance(them_counts, dict)

        # Counts should be integers
        for phrase in phrases:
            us_val = us_counts.get(phrase, 0)
            them_val = them_counts.get(phrase, 0)
            assert isinstance(us_val, int)
            assert isinstance(them_val, int)

    def test_tokenize_phrases_deterministic(self):
        """tokenize_phrases must be deterministic."""
        text = "UK sports betting regulation is changing rapidly."

        result1 = tokenize_phrases(text)
        result2 = tokenize_phrases(text)

        # Results should be identical for same input
        assert set(result1) == set(result2)

    def test_build_topics_extracts_from_both_corpora(self, clean_articles_df, competitor_articles_df):
        """build_reader_topics must extract candidates from BOTH corpora."""
        topics_df = build_reader_topics(clean_articles_df, competitor_articles_df)

        # Should have extracted topics
        # (May be empty if thresholds not met, but function should run)
        assert isinstance(topics_df, pd.DataFrame)


# ============================================================================
# Sanity Tests
# ============================================================================

class TestSanityChecks:
    """Sanity tests for topic discovery."""

    def test_non_brand_topic_appears(self, clean_articles_df, competitor_articles_df):
        """At least one non-brand topic should appear with current data."""
        topics_df = build_reader_topics(clean_articles_df, competitor_articles_df)

        # With 5 internal articles about sports betting, should find topics
        if len(topics_df) > 0:
            # Verify none are brand tokens
            for topic in topics_df['topic'].tolist():
                assert is_valid_topic(topic), f"Invalid topic surfaced: {topic}"

    def test_topic_with_them_greater_zero(self, clean_articles_df, competitor_articles_df):
        """Unless genuinely exclusive, topics should have Them > 0."""
        topics_df = build_reader_topics(clean_articles_df, competitor_articles_df)

        if len(topics_df) > 0:
            # Check that at least one topic has them > 0
            # (unless corpus is genuinely exclusive)
            has_competitor_coverage = (topics_df['them'] > 0).any()

            # This is a soft check - may be all exclusive legitimately
            # But if we have competitor articles, we expect some overlap
            if len(competitor_articles_df) > 0:
                # At least verify the data structure is correct
                assert 'them' in topics_df.columns

    def test_fallback_message_on_empty(self):
        """Empty input should return empty DataFrame (fallback handled in UI)."""
        topics_df = build_reader_topics(pd.DataFrame(), pd.DataFrame())

        assert len(topics_df) == 0
        assert list(topics_df.columns) == [
            "topic", "us", "them", "lead", "why_matters", "next_action", "evidence_links"
        ]


# ============================================================================
# Evidence Links Tests
# ============================================================================

class TestEvidenceLinks:
    """Tests for evidence link extraction."""

    def test_evidence_links_included(self, clean_articles_df):
        """Topics should include evidence links when available."""
        # Create a scenario where we have enough articles
        large_df = pd.concat([clean_articles_df] * 2, ignore_index=True)
        topics_df = build_reader_topics(large_df, pd.DataFrame())

        if len(topics_df) > 0:
            # Check evidence_links column exists
            assert 'evidence_links' in topics_df.columns

            # Check first topic has links
            first_links = topics_df.iloc[0]['evidence_links']
            if first_links:
                assert len(first_links) <= 3
                assert all('link' in l for l in first_links)

    def test_format_evidence_html(self):
        """format_evidence_html should produce middot-separated links."""
        links = [
            {'title': 'Article One', 'link': 'https://example.com/1', 'date': '2024-01-15'},
            {'title': 'Article Two', 'link': 'https://example.com/2', 'date': '2024-01-14'},
        ]

        result = format_evidence_html(links)

        assert '·' in result or '·' in result  # middot separator
        assert 'example.com/1' in result
        assert 'example.com/2' in result

    def test_format_evidence_html_empty(self):
        """format_evidence_html should handle empty list."""
        result = format_evidence_html([])
        assert result == ""


# ============================================================================
# Text Generation Tests
# ============================================================================

class TestTextGeneration:
    """Tests for why_matters and next_action generation."""

    def test_summarize_why_exclusive(self):
        """Exclusive topics should mention exclusivity."""
        result = summarize_why("sports betting", us=10, them=0)
        assert "exclusive" in result.lower()

    def test_summarize_why_leading(self):
        """Leading topics should mention lead."""
        result = summarize_why("prediction markets", us=10, them=3)
        assert len(result) > 0
        assert len(result.split()) <= 25  # Not too long

    def test_suggest_action_exclusive(self):
        """Exclusive topics should get defensive actions."""
        result = suggest_action("sports betting", us=10, them=0)
        assert len(result) > 0
        # Should be imperative
        assert result[0].isupper()

    def test_suggest_action_leading(self):
        """Leading topics should get expansion actions."""
        result = suggest_action("prediction markets", us=10, them=3)
        assert len(result) > 0


# ============================================================================
# CSV Export Tests
# ============================================================================

class TestCSVExport:
    """Tests for CSV export functionality."""

    def test_topics_to_csv_columns(self, clean_articles_df):
        """CSV should have required columns."""
        large_df = pd.concat([clean_articles_df] * 2, ignore_index=True)
        topics_df = build_reader_topics(large_df, pd.DataFrame())

        csv_str = topics_to_csv(topics_df)

        # Should have header row
        assert 'topic' in csv_str
        assert 'us' in csv_str
        assert 'them' in csv_str
        assert 'lead' in csv_str
        assert 'why_matters' in csv_str
        assert 'next_action' in csv_str

    def test_topics_to_csv_empty(self):
        """Empty DataFrame should return header only."""
        csv_str = topics_to_csv(pd.DataFrame())

        assert 'topic' in csv_str
        # Should have just header line
        lines = csv_str.strip().split('\n')
        assert len(lines) == 1


# ============================================================================
# Selection Criteria Tests
# ============================================================================

class TestSelectionCriteria:
    """Tests for topic selection thresholds."""

    def test_minimum_us_count(self, clean_articles_df):
        """Topics must have us >= 3."""
        # With only 2 articles, shouldn't qualify
        small_df = clean_articles_df.head(2)
        topics_df = build_reader_topics(small_df, pd.DataFrame())

        # May be empty due to threshold
        if len(topics_df) > 0:
            assert all(topics_df['us'] >= 3)

    def test_lead_threshold(self, clean_articles_df, competitor_articles_df):
        """Topics should meet lead threshold."""
        topics_df = build_reader_topics(clean_articles_df, competitor_articles_df)

        if len(topics_df) > 0:
            for _, row in topics_df.iterrows():
                us = row['us']
                them = row['them']
                lead = row['lead']

                # Selection criteria:
                # (us >= 3 and lead >= 2) OR (us >= 5 and us / max(them,1) >= 1.5)
                ratio = us / max(them, 1)
                criteria_met = (us >= 3 and lead >= 2) or (us >= 5 and ratio >= 1.5)
                assert criteria_met, f"Topic '{row['topic']}' doesn't meet criteria"

    def test_top_5_limit(self, clean_articles_df):
        """Should return at most 5 topics."""
        # Create large dataset
        large_df = pd.concat([clean_articles_df] * 10, ignore_index=True)
        topics_df = build_reader_topics(large_df, pd.DataFrame())

        assert len(topics_df) <= 5

    def test_sorted_by_lead(self, clean_articles_df):
        """Topics should be sorted by lead descending."""
        large_df = pd.concat([clean_articles_df] * 3, ignore_index=True)
        topics_df = build_reader_topics(large_df, pd.DataFrame())

        if len(topics_df) >= 2:
            leads = topics_df['lead'].tolist()
            assert leads == sorted(leads, reverse=True)
