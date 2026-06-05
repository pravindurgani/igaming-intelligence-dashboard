"""
Test Fix C: Full-text search across title, summary, AND content.

Verifies that Context Explorer searches all fields including article body content,
ensuring no keyword hits are missed.
"""

import pandas as pd

from src.search import filter_keywords_with_results, search_articles


def test_search_includes_content_field():
    """Verify search_articles searches 'content' field by default."""
    test_data = pd.DataFrame([
        {
            'article_id': 'a1',
            'source': 'Test',
            'title': 'About regulation',
            'summary': 'Summary text',
            'content': 'Deep dive into Brazil gambling laws',  # Keyword only here
            'link': 'http://example.com/1',
            'category': 'competitor',
            'published_date': '2025-12-15'
        },
        {
            'article_id': 'a2',
            'source': 'Test',
            'title': 'Different topic',
            'summary': 'Different topic summary',
            'content': 'Other content',
            'link': 'http://example.com/2',
            'category': 'competitor',
            'published_date': '2025-12-14'
        }
    ])

    # Search for "Brazil" - should find a1 even though it's only in content
    results = search_articles(test_data, 'Brazil')

    assert len(results) == 1, "Should find article with 'Brazil' in content"
    assert results.iloc[0]['article_id'] == 'a1', "Should match the right article"


def test_search_matches_title_only():
    """Title-only matches still work."""
    test_data = pd.DataFrame([
        {
            'article_id': 'a1',
            'source': 'Test',
            'title': 'AI regulation updates',
            'summary': 'Summary',
            'content': 'Content',
            'link': 'http://example.com/1',
            'category': 'competitor',
            'published_date': '2025-12-15'
        }
    ])

    results = search_articles(test_data, 'regulation')

    assert len(results) == 1, "Should match title keyword"


def test_search_matches_summary_only():
    """Summary-only matches still work."""
    test_data = pd.DataFrame([
        {
            'article_id': 'a1',
            'source': 'Test',
            'title': 'News update',
            'summary': 'Discusses DraftKings expansion',
            'content': 'Other text',
            'link': 'http://example.com/1',
            'category': 'competitor',
            'published_date': '2025-12-15'
        }
    ])

    results = search_articles(test_data, 'DraftKings')

    assert len(results) == 1, "Should match summary keyword"


def test_search_combines_all_fields():
    """Keyword in ANY field should match."""
    test_data = pd.DataFrame([
        {
            'article_id': 'a1',
            'title': 'AI mentioned here',
            'summary': 'No keyword',
            'content': 'No keyword',
            'link': 'http://example.com/1',
            'category': 'competitor',
            'published_date': '2025-12-15'
        },
        {
            'article_id': 'a2',
            'title': 'Different',
            'summary': 'AI mentioned here',
            'content': 'No keyword',
            'link': 'http://example.com/2',
            'category': 'competitor',
            'published_date': '2025-12-14'
        },
        {
            'article_id': 'a3',
            'title': 'Different',
            'summary': 'Different',
            'content': 'AI mentioned here',
            'link': 'http://example.com/3',
            'category': 'competitor',
            'published_date': '2025-12-13'
        }
    ])

    results = search_articles(test_data, 'AI')

    assert len(results) == 3, "Should find keyword in any field"


def test_content_field_missing_graceful_fallback():
    """When content field missing, search title+summary without error."""
    test_data = pd.DataFrame([
        {
            'article_id': 'a1',
            'source': 'Test',
            'title': 'Brazil regulation',
            'summary': 'Summary',
            # No 'content' field
            'link': 'http://example.com/1',
            'category': 'competitor',
            'published_date': '2025-12-15'
        }
    ])

    # Should not raise error, should search title+summary
    results = search_articles(test_data, 'Brazil')

    assert len(results) == 1, "Should find keyword in title despite missing content field"


def test_filter_keywords_uses_content():
    """filter_keywords_with_results searches content field."""
    test_data = pd.DataFrame([
        {
            'article_id': 'a1',
            'title': 'News',
            'summary': 'Summary',
            'content': 'Exclusive Brazil coverage here',
            'link': 'http://example.com/1',
            'category': 'competitor',
            'published_date': '2025-12-15'
        },
        {
            'article_id': 'a2',
            'title': 'Different',
            'summary': 'Different',
            'content': 'Other topic',
            'link': 'http://example.com/2',
            'category': 'competitor',
            'published_date': '2025-12-14'
        }
    ])

    keywords = ['Brazil', 'NotFound', 'AI']
    keyword_counts = filter_keywords_with_results(test_data, keywords)

    # Should find Brazil (1 match), exclude NotFound (0), exclude AI (0)
    assert len(keyword_counts) == 1, "Should only include keywords with results"
    assert keyword_counts[0][0] == 'Brazil', "Should be Brazil"
    assert keyword_counts[0][1] == 1, "Should have count of 1"


def test_case_insensitive_content_search():
    """Content search should be case-insensitive."""
    test_data = pd.DataFrame([
        {
            'article_id': 'a1',
            'title': 'News',
            'summary': 'Summary',
            'content': 'BRAZIL market analysis',
            'link': 'http://example.com/1',
            'category': 'competitor',
            'published_date': '2025-12-15'
        }
    ])

    results = search_articles(test_data, 'brazil')

    assert len(results) == 1, "Case-insensitive search should find BRAZIL"
