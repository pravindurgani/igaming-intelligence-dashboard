"""
Unit tests for search functionality.
"""

import pandas as pd
import pytest

from src.search import (
    filter_keywords_with_results,
    format_keyword_option,
    normalize_text,
    parse_keyword_from_option,
    search_articles,
)


class TestNormalizeText:
    """Tests for text normalization.

    Note: The unified normalization now includes camelCase splitting before
    lowercasing to support iGaming/eCricket term matching.
    """

    def test_lowercase_conversion(self):
        """Test that text is converted to lowercase."""
        assert normalize_text("HELLO WORLD") == "hello world"
        # Note: MiXeD CaSe has camelCase boundaries split:
        # M->i (lower->upper): Mi Xe D Ca Se -> "mi xe d ca se"
        assert normalize_text("MiXeD CaSe") == "mi xe d ca se"
        # Simple lowercase without camelCase
        assert normalize_text("SIMPLE") == "simple"

    def test_accent_removal(self):
        """Test that accents are removed."""
        assert normalize_text("café") == "cafe"
        assert normalize_text("naïve") == "naive"
        # São has camelCase boundary S->ã (not triggered since ã is not uppercase)
        assert normalize_text("São Paulo") == "sao paulo"

    def test_whitespace_normalization(self):
        """Test that whitespace is collapsed."""
        assert normalize_text("hello    world") == "hello world"
        assert normalize_text("  hello  world  ") == "hello world"
        assert normalize_text("hello\n\tworld") == "hello world"

    def test_empty_and_none(self):
        """Test handling of empty strings and None."""
        assert normalize_text("") == ""
        assert normalize_text(None) == ""
        assert normalize_text(123) == ""

    def test_igaming_normalization(self):
        """Test iGaming normalization (key feature)."""
        # iGaming splits at camelCase and normalizes
        result = normalize_text("iGaming")
        assert "igaming" in result
        assert "gaming" in result

    def test_ecricket_normalization(self):
        """Test eCricket normalization."""
        result = normalize_text("eCricket")
        assert "ecricket" in result
        assert "cricket" in result


class TestSearchArticles:
    """Tests for article search functionality."""

    @pytest.fixture
    def sample_df(self):
        """Create a sample dataframe for testing."""
        return pd.DataFrame([
            {
                'article_id': '1',
                'source': 'Test Source',
                'title': 'Brazil Gambling Regulation News',
                'link': 'http://example.com/1',
                'category': 'competitor',
                'published_date': '2025-01-01',
                'summary': 'New regulations in Brazil affect gaming industry'
            },
            {
                'article_id': '2',
                'source': 'Test Source',
                'title': 'DraftKings Expands to New Markets',
                'link': 'http://example.com/2',
                'category': 'competitor',
                'published_date': '2025-01-02',
                'summary': 'DraftKings announces expansion plans'
            },
            {
                'article_id': '3',
                'source': 'Test Source',
                'title': 'BETBY Launches New Product',
                'link': 'http://example.com/3',
                'category': 'internal',
                'published_date': '2025-01-03',
                'summary': 'BETBY introduces innovative betting platform'
            },
            {
                'article_id': '4',
                'source': 'Test Source',
                'title': 'UK Betting Market Analysis',
                'link': 'http://example.com/4',
                'category': 'competitor',
                'published_date': '2025-01-04',
                'summary': 'Analysis of UK gambling trends and Brazil market'
            }
        ])

    def test_whole_word_matching(self, sample_df):
        """Test search behavior with word boundaries.

        Note: The unified search uses:
        - Word boundaries for short tokens (< 4 chars)
        - Substring matching for long tokens (>= 4 chars)
        """
        # Should match "Brazil" as whole word
        results = search_articles(sample_df, "Brazil")
        assert len(results) == 2
        assert '1' in results['article_id'].values
        assert '4' in results['article_id'].values

        # "Braz" (4 chars) uses substring matching, so it WILL find "Brazil"
        results = search_articles(sample_df, "Braz")
        assert len(results) == 2  # Substring match finds both Brazil articles

        # But "UK" (2 chars) uses word boundaries
        results = search_articles(sample_df, "UK")
        assert len(results) == 1
        assert '4' in results['article_id'].values

    def test_case_insensitive(self, sample_df):
        """Test that search is case-insensitive."""
        results_lower = search_articles(sample_df, "brazil")
        results_upper = search_articles(sample_df, "BRAZIL")

        # Both should find the same articles
        assert len(results_lower) == len(results_upper) == 2
        assert set(results_lower['article_id']) == set(results_upper['article_id'])

    def test_accent_insensitive(self, sample_df):
        """Test that search handles accents correctly."""
        # Add article with accents
        df_with_accents = pd.concat([
            sample_df,
            pd.DataFrame([{
                'article_id': '5',
                'source': 'Test',
                'title': 'São Paulo Gaming News',
                'link': 'http://example.com/5',
                'category': 'competitor',
                'published_date': '2025-01-05',
                'summary': 'Gaming in São Paulo'
            }])
        ])

        # Both with and without accents should match
        results_with = search_articles(df_with_accents, "São Paulo")
        results_without = search_articles(df_with_accents, "Sao Paulo")

        assert len(results_with) == len(results_without)
        assert '5' in results_with['article_id'].values

    def test_search_both_title_and_summary(self, sample_df):
        """Test that search looks in both title and summary fields."""
        # "Regulation" only in title
        results = search_articles(sample_df, "Regulation")
        assert len(results) == 1
        assert '1' in results['article_id'].values

        # "regulations" only in summary
        results = search_articles(sample_df, "regulations")
        assert len(results) == 1
        assert '1' in results['article_id'].values

    def test_empty_query(self, sample_df):
        """Test handling of empty query."""
        results = search_articles(sample_df, "")
        assert len(results) == 0

    def test_no_matches(self, sample_df):
        """Test query with no matches."""
        results = search_articles(sample_df, "NonexistentKeyword")
        assert len(results) == 0

    def test_empty_dataframe(self):
        """Test search on empty dataframe."""
        empty_df = pd.DataFrame()
        results = search_articles(empty_df, "Brazil")
        assert len(results) == 0
        # Check that required columns exist
        assert 'article_id' in results.columns


class TestFilterKeywordsWithResults:
    """Tests for keyword filtering."""

    @pytest.fixture
    def sample_df(self):
        """Create a sample dataframe for testing."""
        return pd.DataFrame([
            {
                'article_id': '1',
                'source': 'Test',
                'title': 'Brazil Gambling Regulation',
                'link': 'http://example.com/1',
                'category': 'competitor',
                'published_date': '2025-01-01',
                'summary': 'Regulations in Brazil'
            },
            {
                'article_id': '2',
                'source': 'Test',
                'title': 'UK Market Expansion',
                'link': 'http://example.com/2',
                'category': 'competitor',
                'published_date': '2025-01-02',
                'summary': 'Expansion to UK markets'
            },
            {
                'article_id': '3',
                'source': 'Test',
                'title': 'Brazil Sports Betting',
                'link': 'http://example.com/3',
                'category': 'internal',
                'published_date': '2025-01-03',
                'summary': 'Sports betting grows in Brazil'
            }
        ])

    def test_filters_zero_result_keywords(self, sample_df):
        """Test that keywords with 0 results are filtered out."""
        keywords = ["Brazil", "UK", "NonexistentKeyword", "FakeCompany"]
        filtered = filter_keywords_with_results(sample_df, keywords)

        # Only Brazil and UK should appear
        keyword_names = [kw for kw, count in filtered]
        assert "Brazil" in keyword_names
        assert "UK" in keyword_names
        assert "NonexistentKeyword" not in keyword_names
        assert "FakeCompany" not in keyword_names

    def test_includes_counts(self, sample_df):
        """Test that counts are correct."""
        keywords = ["Brazil", "UK"]
        filtered = filter_keywords_with_results(sample_df, keywords)

        counts_dict = {kw: count for kw, count in filtered}
        assert counts_dict["Brazil"] == 2  # Articles 1 and 3
        assert counts_dict["UK"] == 1      # Article 2

    def test_sorted_by_count_then_alpha(self, sample_df):
        """Test that results are sorted by count desc, then alphabetically."""
        keywords = ["UK", "Brazil", "Regulation", "Expansion"]
        filtered = filter_keywords_with_results(sample_df, keywords)

        # Brazil (2) should come before UK (1), Expansion (1), Regulation (1)
        # Among count=1, alphabetical: Expansion, Regulation, UK
        assert filtered[0][0] == "Brazil"
        assert filtered[0][1] == 2

        # Check alphabetical sorting for count=1
        count_one_keywords = [kw for kw, count in filtered if count == 1]
        assert count_one_keywords == sorted(count_one_keywords)

    def test_empty_keywords_list(self, sample_df):
        """Test handling of empty keywords list."""
        filtered = filter_keywords_with_results(sample_df, [])
        assert filtered == []

    def test_all_keywords_have_zero_results(self, sample_df):
        """Test when all keywords have zero results."""
        keywords = ["Nonexistent1", "Nonexistent2", "Nonexistent3"]
        filtered = filter_keywords_with_results(sample_df, keywords)
        assert filtered == []


class TestKeywordFormatting:
    """Tests for keyword option formatting and parsing."""

    def test_format_keyword_option_singular(self):
        """Test formatting with 1 article (singular)."""
        formatted = format_keyword_option("Brazil", 1)
        assert formatted == "Brazil (1 article)"

    def test_format_keyword_option_plural(self):
        """Test formatting with multiple articles (plural)."""
        formatted = format_keyword_option("Brazil", 5)
        assert formatted == "Brazil (5 articles)"

        formatted = format_keyword_option("UK", 0)
        assert formatted == "UK (0 articles)"

    def test_parse_keyword_from_option(self):
        """Test parsing keyword from formatted option."""
        assert parse_keyword_from_option("Brazil (5 articles)") == "Brazil"
        assert parse_keyword_from_option("UK (1 article)") == "UK"
        assert parse_keyword_from_option("Complex Name (12 articles)") == "Complex Name"

    def test_parse_keyword_handles_plain_text(self):
        """Test that parsing handles plain text without count suffix."""
        # Should return as-is if no count suffix
        assert parse_keyword_from_option("Brazil") == "Brazil"
        assert parse_keyword_from_option("No Count Here") == "No Count Here"

    def test_roundtrip_format_parse(self):
        """Test that format -> parse is reversible."""
        original = "Market Expansion"
        formatted = format_keyword_option(original, 10)
        parsed = parse_keyword_from_option(formatted)
        assert parsed == original
