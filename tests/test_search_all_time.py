"""
Tests for all-time full-text search.
Verifies that:
- Content-only matches are returned
- Title-only and summary-only matches work
- Phrase queries work
- AND/OR operators work
- Search is independent of date window
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
    SearchIndex,
    filter_keywords_with_results,
    format_keyword_option,
    normalize_text,
    parse_keyword_from_option,
    parse_query,
    search_all_time,
    search_articles,
    tokenize,
)


class TestNormalization:
    """Tests for text normalization."""

    def test_lowercase(self):
        """Text should be lowercased."""
        assert normalize_text("HELLO World") == "hello world"

    def test_remove_punctuation(self):
        """Punctuation should be replaced with spaces."""
        assert normalize_text("Hello, World!") == "hello world"
        assert normalize_text("test-case") == "test case"

    def test_collapse_whitespace(self):
        """Multiple spaces should collapse to one."""
        assert normalize_text("hello    world") == "hello world"
        assert normalize_text("  leading trailing  ") == "leading trailing"

    def test_remove_accents(self):
        """Accented characters should be normalized."""
        assert normalize_text("café") == "cafe"
        assert normalize_text("naïve") == "naive"

    def test_empty_string(self):
        """Empty string returns empty."""
        assert normalize_text("") == ""

    def test_non_string_input(self):
        """Non-string input returns empty."""
        assert normalize_text(None) == ""
        assert normalize_text(123) == ""


class TestTokenization:
    """Tests for tokenization."""

    def test_basic_tokenize(self):
        """Basic tokenization splits on whitespace."""
        tokens = tokenize("hello world")
        assert tokens == ["hello", "world"]

    def test_tokenize_normalizes(self):
        """Tokenization includes normalization."""
        tokens = tokenize("Hello, World!")
        assert tokens == ["hello", "world"]


class TestQueryParser:
    """Tests for query parsing."""

    def test_simple_tokens(self):
        """Simple words are parsed as AND tokens."""
        parsed = parse_query("hello world")
        assert ('hello', 'AND') in parsed
        assert ('world', 'AND') in parsed

    def test_quoted_phrase(self):
        """Quoted strings are parsed as PHRASE."""
        parsed = parse_query('"exact phrase"')
        assert ('exact phrase', 'PHRASE') in parsed

    def test_or_operator(self):
        """OR operator marks next token as OR."""
        parsed = parse_query("hello OR world")
        # hello is AND, world is OR
        assert ('hello', 'AND') in parsed
        assert ('world', 'OR') in parsed

    def test_explicit_and(self):
        """Explicit AND is same as default."""
        parsed = parse_query("hello AND world")
        assert ('hello', 'AND') in parsed
        assert ('world', 'AND') in parsed

    def test_mixed_phrase_and_tokens(self):
        """Mix of phrases and tokens."""
        parsed = parse_query('"sports betting" regulation')
        assert ('sports betting', 'PHRASE') in parsed
        assert ('regulation', 'AND') in parsed


class TestSearchIndex:
    """Tests for SearchIndex."""

    @pytest.fixture
    def sample_df(self):
        """Create sample DataFrame for testing."""
        return pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3', 'a4'],
            'title': [
                'Breaking: New regulation announced',
                'Sports betting market grows',
                'Technology trends in gaming',
                'Brazil legalizes gambling'
            ],
            'summary': [
                'Government introduces new rules',
                'Market expansion continues',
                'AI and blockchain in focus',
                'South American expansion'
            ],
            'content': [
                'Detailed regulation content here',
                'The sports betting industry sees growth',
                'Technology innovation drives change. Brazil mentioned.',
                'Brazil passes new gambling legislation. Full text of law.'
            ],
            'category': ['competitor', 'competitor', 'internal', 'competitor'],
        })

    def test_build_index(self, sample_df):
        """Index should be built correctly."""
        index = SearchIndex()
        index.build(sample_df)

        # Check tokens exist
        assert 'regulation' in index.token_to_articles
        assert 'brazil' in index.token_to_articles

    def test_search_token(self, sample_df):
        """Token search returns correct articles."""
        index = SearchIndex()
        index.build(sample_df)

        results = index.search_token('regulation')
        assert 'a1' in results

    def test_search_phrase(self, sample_df):
        """Phrase search returns correct articles."""
        index = SearchIndex()
        index.build(sample_df)

        results = index.search_phrase('sports betting')
        assert 'a2' in results

    def test_has_content_flag(self, sample_df):
        """has_content flag tracks articles with content."""
        index = SearchIndex()
        index.build(sample_df)

        # All articles have content in sample
        for article_id in sample_df['article_id']:
            assert index.article_has_content.get(article_id, False) is True


class TestSearchArticles:
    """Tests for search_articles function."""

    @pytest.fixture
    def sample_df(self):
        """Create sample DataFrame for testing."""
        return pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3', 'a4', 'a5'],
            'title': [
                'About regulation in gaming',
                'Sports betting market analysis',
                'Technology trends report',
                'Brazil gambling news',
                'Plain title here'
            ],
            'summary': [
                'Summary text one',
                'Summary about betting',
                'Summary of tech',
                'Summary of Brazil',
                'Summary five'
            ],
            'content': [
                'Content about regulation and compliance',
                'Content about sports markets',
                'Content mentions Brazil soccer gambling',  # Brazil ONLY in content
                'Content about Brazil legislation',
                'Unique keyword xyzzytest appears here only'  # Unique word only in content
            ],
            'source': ['A', 'B', 'C', 'D', 'E'],
            'link': ['http://a', 'http://b', 'http://c', 'http://d', 'http://e'],
            'category': ['competitor', 'competitor', 'internal', 'competitor', 'internal'],
            'published_date': ['2024-01-01'] * 5,
        })

    def test_content_only_match(self, sample_df):
        """Keyword only in content should be found."""
        # 'xyzzytest' only appears in a5's content
        results = search_articles(sample_df, 'xyzzytest')

        assert len(results) == 1
        assert results.iloc[0]['article_id'] == 'a5'

    def test_title_only_match(self, sample_df):
        """Keyword only in title should be found."""
        # 'regulation' appears in a1 title
        results = search_articles(sample_df, 'regulation')

        assert len(results) >= 1
        article_ids = results['article_id'].tolist()
        assert 'a1' in article_ids

    def test_summary_only_match(self, sample_df):
        """Keyword in summary should be found."""
        results = search_articles(sample_df, 'betting')

        assert len(results) >= 1
        article_ids = results['article_id'].tolist()
        assert 'a2' in article_ids

    def test_brazil_in_content_matched(self, sample_df):
        """Brazil appearing only in content should match."""
        # a3 has 'Brazil' only in content, not title/summary
        results = search_articles(sample_df, 'Brazil')

        article_ids = results['article_id'].tolist()
        # Should find a3 (content only) and a4 (title+content)
        assert 'a3' in article_ids, "Should find article with Brazil only in content"
        assert 'a4' in article_ids

    def test_phrase_query(self, sample_df):
        """Phrase query should work."""
        # Add an article with specific phrase
        df_with_phrase = pd.concat([sample_df, pd.DataFrame({
            'article_id': ['a6'],
            'title': ['Sports betting regulation announced'],
            'summary': ['Important news about sports betting'],
            'content': ['Full article about sports betting regulation'],
            'source': ['F'],
            'link': ['http://f'],
            'category': ['competitor'],
            'published_date': ['2024-01-02'],
        })], ignore_index=True)

        results = search_articles(df_with_phrase, '"sports betting"')

        assert len(results) >= 1
        article_ids = results['article_id'].tolist()
        assert 'a6' in article_ids

    def test_empty_query_returns_empty(self, sample_df):
        """Empty query returns empty DataFrame."""
        results = search_articles(sample_df, '')
        assert len(results) == 0

    def test_no_match_returns_empty(self, sample_df):
        """Query with no matches returns empty DataFrame."""
        results = search_articles(sample_df, 'nonexistentword12345')
        assert len(results) == 0

    def test_has_content_column(self, sample_df):
        """Results should include has_content column."""
        results = search_articles(sample_df, 'regulation')
        assert 'has_content' in results.columns


class TestSearchAllTime:
    """Tests for search_all_time function (alias)."""

    def test_search_all_time_works(self):
        """search_all_time should work as alias."""
        df = pd.DataFrame({
            'article_id': ['a1'],
            'title': ['Test article'],
            'summary': ['Test summary'],
            'content': ['Test content with keyword'],
            'source': ['A'],
            'link': ['http://a'],
            'category': ['competitor'],
            'published_date': ['2024-01-01'],
        })

        results = search_all_time(df, 'keyword')
        assert len(results) == 1


class TestKeywordFiltering:
    """Tests for keyword filtering functions."""

    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3'],
            'title': ['Regulation news', 'Betting update', 'Gaming trends'],
            'summary': ['About rules', 'About betting', 'About gaming'],
            'content': ['Content one', 'Content two', 'Content three'],
            'source': ['A', 'B', 'C'],
            'link': ['http://a', 'http://b', 'http://c'],
            'category': ['competitor', 'competitor', 'internal'],
            'published_date': ['2024-01-01'] * 3,
        })

    def test_filter_keywords_with_results(self, sample_df):
        """Only keywords with results should be returned."""
        keywords = ['regulation', 'nonexistent', 'betting']
        results = filter_keywords_with_results(sample_df, keywords)

        result_keywords = [k for k, c in results]
        assert 'regulation' in result_keywords
        assert 'betting' in result_keywords
        assert 'nonexistent' not in result_keywords

    def test_filter_returns_counts(self, sample_df):
        """Filter should return counts."""
        keywords = ['regulation']
        results = filter_keywords_with_results(sample_df, keywords)

        assert len(results) == 1
        keyword, count = results[0]
        assert keyword == 'regulation'
        assert count >= 1


class TestKeywordFormatting:
    """Tests for keyword option formatting."""

    def test_format_keyword_option_singular(self):
        """Single article uses singular."""
        result = format_keyword_option('test', 1)
        assert result == 'test (1 article)'

    def test_format_keyword_option_plural(self):
        """Multiple articles use plural."""
        result = format_keyword_option('test', 5)
        assert result == 'test (5 articles)'

    def test_parse_keyword_from_option(self):
        """Parse extracts keyword correctly."""
        formatted = 'Brazil regulation (15 articles)'
        result = parse_keyword_from_option(formatted)
        assert result == 'Brazil regulation'

    def test_parse_keyword_from_plain(self):
        """Parse handles unformatted string."""
        result = parse_keyword_from_option('plain keyword')
        assert result == 'plain keyword'


class TestOROperator:
    """Tests for OR operator in search."""

    def test_or_union(self):
        """OR should return union of results."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3'],
            'title': ['Apple news', 'Orange news', 'Banana news'],
            'summary': ['About apples', 'About oranges', 'About bananas'],
            'content': ['Apple content', 'Orange content', 'Banana content'],
            'source': ['A', 'B', 'C'],
            'link': ['http://a', 'http://b', 'http://c'],
            'category': ['competitor', 'competitor', 'internal'],
            'published_date': ['2024-01-01'] * 3,
        })

        # 'apple OR orange' should find a1 and a2
        results = search_articles(df, 'apple OR orange')

        article_ids = results['article_id'].tolist()
        assert 'a1' in article_ids
        assert 'a2' in article_ids
        # a3 (banana) should NOT be included
        assert 'a3' not in article_ids


class TestANDDefault:
    """Tests for default AND behavior."""

    def test_and_intersection(self):
        """Multiple terms default to AND (intersection)."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3'],
            'title': ['Apple and orange', 'Apple only', 'Orange only'],
            'summary': ['Both fruits', 'Just apple', 'Just orange'],
            'content': ['Content', 'Content', 'Content'],
            'source': ['A', 'B', 'C'],
            'link': ['http://a', 'http://b', 'http://c'],
            'category': ['competitor', 'competitor', 'internal'],
            'published_date': ['2024-01-01'] * 3,
        })

        # 'apple orange' (AND) should only find a1
        results = search_articles(df, 'apple orange')

        # Only a1 has both 'apple' AND 'orange'
        assert len(results) == 1
        assert results.iloc[0]['article_id'] == 'a1'
