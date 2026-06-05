"""
Tests for gaps dropdown functionality.
Verifies that:
- Dropdown excludes zero-hit keywords
- Counts in dropdown equal actual search results
- Formatting and parsing work correctly
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

# Add project root
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.search import (
    build_keyword_index,
    filter_keywords_with_results,
    format_keyword_option,
    parse_keyword_from_option,
    search_articles,
)


class TestDropdownExclusion:
    """Tests for excluding zero-hit keywords from dropdown."""

    @pytest.fixture
    def sample_df(self):
        """Create sample DataFrame for testing."""
        return pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3', 'a4', 'a5'],
            'title': [
                'Regulation in gaming industry',
                'Sports betting market growth',
                'Technology trends update',
                'Brazil gambling news',
                'UK market analysis'
            ],
            'summary': [
                'Summary about regulation',
                'Betting industry expands',
                'Tech innovation focus',
                'Brazil legalizes gambling',
                'UK market overview'
            ],
            'content': [
                'Content about compliance',
                'Sports betting content',
                'Tech content here',
                'Brazil legislation text',
                'UK content analysis'
            ],
            'source': ['A', 'B', 'C', 'D', 'E'],
            'link': ['http://a', 'http://b', 'http://c', 'http://d', 'http://e'],
            'category': ['competitor', 'competitor', 'internal', 'competitor', 'internal'],
            'published_date': ['2024-01-01'] * 5,
        })

    def test_excludes_zero_hit_keywords(self, sample_df):
        """Keywords with zero results should be excluded."""
        # Mix of real keywords and fake ones
        candidate_keywords = [
            'regulation',      # Has results
            'nonexistent123',  # No results
            'Brazil',          # Has results
            'xyzzynotfound',   # No results
            'betting'          # Has results
        ]

        results = filter_keywords_with_results(sample_df, candidate_keywords)
        result_keywords = [k for k, c in results]

        # Real keywords should be present
        assert 'regulation' in result_keywords
        assert 'Brazil' in result_keywords
        assert 'betting' in result_keywords

        # Fake keywords should be excluded
        assert 'nonexistent123' not in result_keywords
        assert 'xyzzynotfound' not in result_keywords

    def test_only_nonzero_counts(self, sample_df):
        """All returned keywords should have count > 0."""
        keywords = ['regulation', 'fake1', 'fake2', 'Brazil']
        results = filter_keywords_with_results(sample_df, keywords)

        for keyword, count in results:
            assert count > 0, f"Keyword '{keyword}' has zero count but was returned"


class TestDropdownCountAccuracy:
    """Tests for count accuracy in dropdown."""

    @pytest.fixture
    def sample_df(self):
        """Create sample DataFrame with known counts."""
        return pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3', 'a4', 'a5'],
            'title': [
                'Gaming regulation news',
                'Gaming market update',
                'Gaming technology',
                'Sports news',
                'Finance news'
            ],
            'summary': ['Summary'] * 5,
            'content': ['Content'] * 5,
            'source': ['A', 'B', 'C', 'D', 'E'],
            'link': ['http://a', 'http://b', 'http://c', 'http://d', 'http://e'],
            'category': ['competitor'] * 5,
            'published_date': ['2024-01-01'] * 5,
        })

    def test_counts_match_search_results(self, sample_df):
        """Counts in dropdown should match actual search results."""
        keywords = ['gaming', 'sports', 'finance']
        dropdown_results = filter_keywords_with_results(sample_df, keywords)

        for keyword, dropdown_count in dropdown_results:
            # Run actual search
            search_results = search_articles(sample_df, keyword)
            actual_count = len(search_results)

            assert dropdown_count == actual_count, (
                f"Dropdown count ({dropdown_count}) != search count ({actual_count}) "
                f"for keyword '{keyword}'"
            )

    def test_gaming_appears_three_times(self, sample_df):
        """'gaming' should match 3 articles."""
        results = filter_keywords_with_results(sample_df, ['gaming'])

        assert len(results) == 1
        keyword, count = results[0]
        assert keyword == 'gaming'
        assert count == 3


class TestDropdownFormatting:
    """Tests for dropdown option formatting."""

    def test_format_single_article(self):
        """Single article uses singular form."""
        result = format_keyword_option('regulation', 1)
        assert result == 'regulation (1 article)'

    def test_format_multiple_articles(self):
        """Multiple articles use plural form."""
        result = format_keyword_option('Brazil', 15)
        assert result == 'Brazil (15 articles)'

    def test_format_large_count(self):
        """Large counts format correctly."""
        result = format_keyword_option('gaming', 1234)
        assert result == 'gaming (1234 articles)'

    def test_parse_extracts_keyword(self):
        """Parser extracts keyword from formatted string."""
        formatted = 'Brazil regulation (42 articles)'
        result = parse_keyword_from_option(formatted)
        assert result == 'Brazil regulation'

    def test_parse_handles_plain_text(self):
        """Parser handles unformatted input."""
        result = parse_keyword_from_option('plain text')
        assert result == 'plain text'

    def test_parse_handles_whitespace(self):
        """Parser handles extra whitespace."""
        result = parse_keyword_from_option('  keyword  ')
        assert result == 'keyword'

    def test_parse_handles_singular(self):
        """Parser handles singular article form."""
        formatted = 'test (1 article)'
        result = parse_keyword_from_option(formatted)
        assert result == 'test'


class TestDropdownSorting:
    """Tests for dropdown sorting."""

    @pytest.fixture
    def sample_df(self):
        """Create sample DataFrame with varying match counts."""
        return pd.DataFrame({
            'article_id': [f'a{i}' for i in range(10)],
            'title': [
                'Alpha topic here',    # alpha: 1
                'Beta topic one',      # beta: 3
                'Beta topic two',
                'Beta topic three',
                'Gamma topic one',     # gamma: 2
                'Gamma topic two',
                'Delta topic only',    # delta: 1
                'Other news',
                'More news',
                'Final news',
            ],
            'summary': ['Summary'] * 10,
            'content': ['Content'] * 10,
            'source': ['A'] * 10,
            'link': [f'http://a{i}' for i in range(10)],
            'category': ['competitor'] * 10,
            'published_date': ['2024-01-01'] * 10,
        })

    def test_sorted_by_count_descending(self, sample_df):
        """Results should be sorted by count (highest first)."""
        keywords = ['alpha', 'beta', 'gamma', 'delta']
        results = filter_keywords_with_results(sample_df, keywords)

        # Extract counts
        counts = [c for k, c in results]

        # Verify descending order
        assert counts == sorted(counts, reverse=True), (
            f"Counts not in descending order: {counts}"
        )

    def test_alphabetical_tiebreak(self, sample_df):
        """Same-count keywords should be alphabetized."""
        # alpha and delta both have count=1
        keywords = ['alpha', 'delta']
        results = filter_keywords_with_results(sample_df, keywords)

        if len(results) == 2:
            # Both have count 1, should be alphabetical
            keywords_only = [k for k, c in results]
            assert keywords_only == ['alpha', 'delta'], (
                f"Same-count keywords not alphabetized: {keywords_only}"
            )


class TestKeywordIndex:
    """Tests for keyword index building."""

    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3'],
            'title': ['Test one', 'Test two', 'Different'],
            'summary': ['Summary one', 'Summary two', 'Other summary'],
            'content': ['Content one', 'Content two', 'Other content'],
            'source': ['A', 'B', 'C'],
            'link': ['http://a', 'http://b', 'http://c'],
            'category': ['competitor', 'competitor', 'internal'],
            'published_date': ['2024-01-01'] * 3,
        })

    def test_build_keyword_index(self, sample_df):
        """Keyword index should map keywords to article IDs."""
        keywords = ['test', 'different']
        index = build_keyword_index(sample_df, keywords)

        # 'test' should match a1 and a2
        assert 'test' in index
        assert 'a1' in index['test']
        assert 'a2' in index['test']

        # 'different' should match a3
        assert 'different' in index
        assert 'a3' in index['different']

    def test_index_includes_content_matches(self, sample_df):
        """Index should include content-only matches."""
        # Add article with keyword only in content
        df_extended = pd.concat([sample_df, pd.DataFrame({
            'article_id': ['a4'],
            'title': ['Plain title'],
            'summary': ['Plain summary'],
            'content': ['This has uniqueword99 in content only'],
            'source': ['D'],
            'link': ['http://d'],
            'category': ['competitor'],
            'published_date': ['2024-01-02'],
        })], ignore_index=True)

        keywords = ['uniqueword99']
        index = build_keyword_index(df_extended, keywords)

        assert 'uniqueword99' in index
        assert 'a4' in index['uniqueword99']
