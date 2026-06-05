"""
Test Context Explorer functionality.

Verifies Fix B: Context Explorer uses correct 'published_date' column.
"""

import pandas as pd
import pytest

from src.search import search_articles


def test_search_returns_published_date_column():
    """Verify search_articles() returns DataFrame with 'published_date' column."""
    # Create test DataFrame
    test_data = pd.DataFrame([
        {
            'article_id': 'test1',
            'source': 'Test Source',
            'title': 'Test Article about AI',
            'summary': 'This article discusses AI technology',
            'link': 'https://example.com/1',
            'category': 'competitor',
            'published_date': '2025-12-15 10:00'
        },
        {
            'article_id': 'test2',
            'source': 'Another Source',
            'title': 'Different Topic',
            'summary': 'Something else entirely',
            'link': 'https://example.com/2',
            'category': 'internal',
            'published_date': '2025-12-14 15:30'
        }
    ])

    # Search for 'AI'
    results = search_articles(test_data, 'AI')

    # Verify column exists
    assert 'published_date' in results.columns, (
        "search_articles() must return 'published_date' column"
    )

    # Verify no 'date' column (this was the bug)
    assert 'date' not in results.columns, (
        "search_articles() should NOT return 'date' column"
    )

    # Verify we got expected results
    assert len(results) == 1
    assert results.iloc[0]['title'] == 'Test Article about AI'
    assert results.iloc[0]['published_date'] == '2025-12-15 10:00'


def test_article_display_handles_published_date():
    """Simulate Context Explorer article display logic."""
    # Create test results DataFrame matching search_articles() output
    results = pd.DataFrame([
        {
            'article_id': 'test1',
            'source': 'Test Source',
            'title': 'Test Article',
            'link': 'https://example.com/1',
            'category': 'competitor',
            'published_date': '2025-12-15 10:00'
        }
    ])

    # Simulate dashboard display logic (lines 1936, 1946)
    for _, article in results.iterrows():
        # This should NOT raise KeyError
        date_str = article.get('published_date', 'No date')
        assert date_str == '2025-12-15 10:00'

        # Verify accessing 'date' would fail (as it did before fix)
        with pytest.raises(KeyError):
            _ = article['date']


def test_empty_published_date_fallback():
    """Verify fallback when published_date is missing."""
    results = pd.DataFrame([
        {
            'article_id': 'test1',
            'source': 'Test Source',
            'title': 'Test Article',
            'link': 'https://example.com/1',
            'category': 'competitor'
            # Note: no published_date
        }
    ])

    for _, article in results.iterrows():
        # Should return fallback value
        date_str = article.get('published_date', 'No date')
        assert date_str == 'No date'


def test_search_output_schema():
    """Verify search_articles() output schema matches expectations."""
    test_data = pd.DataFrame([
        {
            'article_id': 'test1',
            'source': 'Test Source',
            'title': 'Keyword match',
            'summary': 'Summary text',
            'link': 'https://example.com/1',
            'category': 'competitor',
            'published_date': '2025-12-15'
        }
    ])

    results = search_articles(test_data, 'keyword')

    # Verify all required columns present
    # Note: 'has_content' column was added to indicate whether article has body content
    expected_columns = ['article_id', 'source', 'title', 'link', 'category', 'published_date', 'has_content']
    for col in expected_columns:
        assert col in results.columns, f"Missing required column: {col}"

    # Verify no extra unexpected columns
    assert set(results.columns) == set(expected_columns), (
        f"Unexpected columns in output: {set(results.columns) - set(expected_columns)}"
    )
