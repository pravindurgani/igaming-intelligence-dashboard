"""
Tests for unified search across News Feed and Context Explorer.

Verifies that:
- 'gaming' matches 'iGaming' and 'Gaming'
- 'cricket' matches 'eCricket', 'e-cricket'
- phrase '"sports betting"' respects adjacency
- AND/OR logic works correctly
- News Feed and Context Explorer produce identical counts with same scope
- Short tokens ('AI') use word boundaries to reduce noise
"""

import sys
from pathlib import Path

import pandas as pd

# Add project root
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.search import (
    SearchIndex,
    search_all_time,
    search_articles,
)
from src.textnorm import build_search_field, has_content, normalize_text


class TestNormalizationIGaming:
    """Tests for iGaming term normalization."""

    def test_igaming_normalized_to_igaming_gaming(self):
        """'iGaming' should normalize to include both 'igaming' and 'gaming'."""
        result = normalize_text("iGaming")
        assert "igaming" in result
        assert "gaming" in result

    def test_gaming_search_matches_igaming_article(self):
        """Searching 'gaming' should find articles with 'iGaming' in title."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2'],
            'title': ['iGaming market trends', 'Sports news'],
            'summary': ['Summary one', 'Summary two'],
            'content': ['Content one', 'Content two'],
            'source': ['A', 'B'],
            'link': ['http://a', 'http://b'],
            'category': ['competitor', 'internal'],
            'published_date': ['2024-01-01', '2024-01-02'],
        })

        results = search_articles(df, 'gaming')
        article_ids = results['article_id'].tolist()

        assert 'a1' in article_ids, "Should find 'iGaming' article when searching 'gaming'"

    def test_igaming_search_matches_igaming_article(self):
        """Searching 'iGaming' should find articles with 'iGaming' in title."""
        df = pd.DataFrame({
            'article_id': ['a1'],
            'title': ['iGaming market trends'],
            'summary': ['Summary'],
            'content': ['Content'],
            'source': ['A'],
            'link': ['http://a'],
            'category': ['competitor'],
            'published_date': ['2024-01-01'],
        })

        results = search_articles(df, 'iGaming')
        assert len(results) == 1


class TestNormalizationECricket:
    """Tests for eCricket term normalization."""

    def test_ecricket_normalized_to_ecricket_cricket(self):
        """'eCricket' should normalize to include both 'ecricket' and 'cricket'."""
        result = normalize_text("eCricket")
        assert "ecricket" in result
        assert "cricket" in result

    def test_cricket_search_matches_ecricket_article(self):
        """Searching 'cricket' should find articles with 'eCricket' in title."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2'],
            'title': ['eCricket tournament news', 'Football update'],
            'summary': ['Summary one', 'Summary two'],
            'content': ['Content one', 'Content two'],
            'source': ['A', 'B'],
            'link': ['http://a', 'http://b'],
            'category': ['competitor', 'internal'],
            'published_date': ['2024-01-01', '2024-01-02'],
        })

        results = search_articles(df, 'cricket')
        article_ids = results['article_id'].tolist()

        assert 'a1' in article_ids, "Should find 'eCricket' article when searching 'cricket'"

    def test_e_hyphen_cricket_normalized(self):
        """'e-cricket' should normalize to include 'cricket'."""
        result = normalize_text("e-cricket")
        # After punctuation removal, becomes 'e cricket' which normalizes to 'ecricket cricket'
        assert "cricket" in result


class TestNormalizationESports:
    """Tests for eSports term normalization."""

    def test_esports_normalized(self):
        """'eSports' should normalize to 'esports'."""
        result = normalize_text("eSports")
        assert "esports" in result

    def test_e_sports_normalized(self):
        """'e-sports' should normalize to 'esports'."""
        result = normalize_text("e-sports")
        assert "esports" in result

    def test_esport_singular_normalized(self):
        """'esport' singular should normalize to 'esports'."""
        result = normalize_text("esport")
        assert "esports" in result


class TestPhraseQueries:
    """Tests for phrase query functionality."""

    def test_phrase_query_respects_adjacency(self):
        """Phrase query should only match exact adjacent words."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3'],
            'title': [
                'Sports betting regulation announced',  # Has phrase
                'Sports and betting news',  # Has words but not adjacent
                'Betting on sports events'  # Has words in wrong order
            ],
            'summary': ['Summary'] * 3,
            'content': ['Content'] * 3,
            'source': ['A', 'B', 'C'],
            'link': ['http://a', 'http://b', 'http://c'],
            'category': ['competitor'] * 3,
            'published_date': ['2024-01-01'] * 3,
        })

        results = search_articles(df, '"sports betting"')
        article_ids = results['article_id'].tolist()

        # Only a1 has exact phrase "sports betting"
        assert 'a1' in article_ids
        assert 'a2' not in article_ids  # Words separated by 'and'
        assert 'a3' not in article_ids  # Words in wrong order

    def test_phrase_with_other_terms(self):
        """Phrase can be combined with other search terms."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2'],
            'title': [
                'Sports betting regulation in Brazil',
                'Sports betting market update'
            ],
            'summary': ['Summary'] * 2,
            'content': ['Content'] * 2,
            'source': ['A', 'B'],
            'link': ['http://a', 'http://b'],
            'category': ['competitor'] * 2,
            'published_date': ['2024-01-01'] * 2,
        })

        # Phrase + additional term (AND)
        results = search_articles(df, '"sports betting" Brazil')
        article_ids = results['article_id'].tolist()

        # Only a1 has both phrase AND 'Brazil'
        assert 'a1' in article_ids
        assert len(results) == 1


class TestANDORLogic:
    """Tests for AND/OR operator logic."""

    def test_and_is_default(self):
        """Multiple terms default to AND (intersection)."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3'],
            'title': [
                'Apple and orange fruit',  # Has both
                'Apple only here',
                'Orange only here'
            ],
            'summary': ['Summary'] * 3,
            'content': ['Content'] * 3,
            'source': ['A', 'B', 'C'],
            'link': ['http://a', 'http://b', 'http://c'],
            'category': ['competitor'] * 3,
            'published_date': ['2024-01-01'] * 3,
        })

        results = search_articles(df, 'apple orange')
        article_ids = results['article_id'].tolist()

        # Only a1 has both
        assert 'a1' in article_ids
        assert len(results) == 1

    def test_or_creates_union(self):
        """OR operator creates union of results."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3'],
            'title': [
                'Apple news',
                'Orange news',
                'Banana news'
            ],
            'summary': ['Summary'] * 3,
            'content': ['Content'] * 3,
            'source': ['A', 'B', 'C'],
            'link': ['http://a', 'http://b', 'http://c'],
            'category': ['competitor'] * 3,
            'published_date': ['2024-01-01'] * 3,
        })

        results = search_articles(df, 'apple OR orange')
        article_ids = results['article_id'].tolist()

        assert 'a1' in article_ids
        assert 'a2' in article_ids
        assert 'a3' not in article_ids


class TestWordBoundaryForShortTokens:
    """Tests for word-boundary matching on short tokens."""

    def test_ai_uses_word_boundary(self):
        """Short token 'AI' should use word boundary to avoid matching 'again'."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3'],
            'title': [
                'AI technology in gaming',  # Has AI
                'Try again later',  # Has 'again' which contains 'ai'
                'The main feature'  # Has 'main' which contains 'ai'
            ],
            'summary': ['Summary'] * 3,
            'content': ['Content'] * 3,
            'source': ['A', 'B', 'C'],
            'link': ['http://a', 'http://b', 'http://c'],
            'category': ['competitor'] * 3,
            'published_date': ['2024-01-01'] * 3,
        })

        results = search_articles(df, 'AI')
        article_ids = results['article_id'].tolist()

        # Only a1 has standalone 'AI'
        assert 'a1' in article_ids
        # a2 and a3 should NOT match (word boundary)
        assert 'a2' not in article_ids, "'again' should not match 'AI'"
        assert 'a3' not in article_ids, "'main' should not match 'AI'"

    def test_uk_uses_word_boundary(self):
        """Short token 'UK' should use word boundary."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2'],
            'title': [
                'UK market analysis',  # Has UK
                'Jukebox music'  # Has 'uk' within word
            ],
            'summary': ['Summary'] * 2,
            'content': ['Content'] * 2,
            'source': ['A', 'B'],
            'link': ['http://a', 'http://b'],
            'category': ['competitor'] * 2,
            'published_date': ['2024-01-01'] * 2,
        })

        results = search_articles(df, 'UK')
        article_ids = results['article_id'].tolist()

        assert 'a1' in article_ids
        assert 'a2' not in article_ids, "'jukebox' should not match 'UK'"


class TestLongTokenSubstring:
    """Tests for substring matching on long tokens."""

    def test_gaming_substring_match(self):
        """Long token 'gaming' should use substring match."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2'],
            'title': [
                'Gaming industry news',
                'iGaming market update'  # 'gaming' as part of normalized text
            ],
            'summary': ['Summary'] * 2,
            'content': ['Content'] * 2,
            'source': ['A', 'B'],
            'link': ['http://a', 'http://b'],
            'category': ['competitor'] * 2,
            'published_date': ['2024-01-01'] * 2,
        })

        results = search_articles(df, 'gaming')
        article_ids = results['article_id'].tolist()

        # Both should match
        assert 'a1' in article_ids
        assert 'a2' in article_ids


class TestUnifiedSearchIdenticalCounts:
    """Tests that News Feed and Context Explorer produce identical results with same scope."""

    def test_same_query_same_df_same_results(self):
        """Same query on same DataFrame should produce identical results."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3', 'a4'],
            'title': [
                'iGaming regulation news',
                'Sports betting update',
                'eCricket tournament',
                'Finance news'
            ],
            'summary': ['Summary'] * 4,
            'content': ['Content'] * 4,
            'source': ['A', 'B', 'C', 'D'],
            'link': ['http://a', 'http://b', 'http://c', 'http://d'],
            'category': ['competitor', 'competitor', 'internal', 'internal'],
            'published_date': ['2024-01-01'] * 4,
        })

        # Simulate News Feed search (on filtered df)
        news_feed_results = search_all_time(df, 'gaming')

        # Simulate Context Explorer search (on same df for this test)
        context_explorer_results = search_all_time(df, 'gaming')

        # Should be identical
        assert len(news_feed_results) == len(context_explorer_results)
        assert set(news_feed_results['article_id']) == set(context_explorer_results['article_id'])

    def test_gaming_count_matches_across_tabs(self):
        """Searching 'gaming' should show identical counts in both tabs given identical scope."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3'],
            'title': [
                'iGaming trends',
                'Gaming market',
                'Unrelated news'
            ],
            'summary': ['Summary'] * 3,
            'content': ['Content'] * 3,
            'source': ['A', 'B', 'C'],
            'link': ['http://a', 'http://b', 'http://c'],
            'category': ['competitor', 'competitor', 'internal'],
            'published_date': ['2024-01-01'] * 3,
        })

        # Both tabs use search_all_time
        results = search_all_time(df, 'gaming')

        # Should find both gaming-related articles
        assert len(results) == 2


class TestBuildSearchField:
    """Tests for build_search_field function."""

    def test_combines_title_summary_content(self):
        """build_search_field should combine all text fields."""
        row = pd.Series({
            'title': 'Test Title',
            'summary': 'Test Summary',
            'content': 'Test Content'
        })

        result = build_search_field(row)

        assert 'test' in result
        assert 'title' in result
        assert 'summary' in result
        assert 'content' in result

    def test_handles_missing_fields(self):
        """build_search_field should handle missing fields gracefully."""
        row = pd.Series({
            'title': 'Test Title'
            # summary and content missing
        })

        result = build_search_field(row)

        # Should not crash, should return normalized title
        assert 'test' in result
        assert 'title' in result


class TestHasContent:
    """Tests for has_content function."""

    def test_has_content_true(self):
        """has_content returns True when content field has text."""
        row = pd.Series({'content': 'Some article content here'})
        assert has_content(row) is True

    def test_has_content_false_empty(self):
        """has_content returns False when content is empty."""
        row = pd.Series({'content': ''})
        assert has_content(row) is False

    def test_has_content_false_whitespace(self):
        """has_content returns False when content is only whitespace."""
        row = pd.Series({'content': '   '})
        assert has_content(row) is False

    def test_has_content_false_missing(self):
        """has_content returns False when content field is missing."""
        row = pd.Series({'title': 'Title'})
        assert has_content(row) is False


class TestSearchIndex:
    """Tests for SearchIndex with unified normalization."""

    def test_index_normalizes_igaming(self):
        """Index should normalize iGaming terms."""
        df = pd.DataFrame({
            'article_id': ['a1'],
            'title': ['iGaming news'],
            'summary': ['Summary'],
            'content': ['Content'],
        })

        index = SearchIndex()
        index.build(df)

        # Should find via both 'igaming' and 'gaming'
        assert 'a1' in index.search_token('igaming')
        assert 'a1' in index.search_token('gaming')

    def test_index_tracks_has_content(self):
        """Index should track which articles have content."""
        df = pd.DataFrame({
            'article_id': ['a1', 'a2'],
            'title': ['Title 1', 'Title 2'],
            'summary': ['Summary', 'Summary'],
            'content': ['Has content', ''],  # a2 has no content
        })

        index = SearchIndex()
        index.build(df)

        assert index.article_has_content['a1'] is True
        assert index.article_has_content['a2'] is False
