#!/usr/bin/env python3
"""
Test script to verify deduplication and data integrity.
Uses pytest assertions and centralized paths.
"""

import json

# Import centralized paths
import sys
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from paths import LATEST_NEWS_JSON


def test_file_exists():
    """Test that the news JSON file exists."""
    assert LATEST_NEWS_JSON.exists(), f"News JSON not found at {LATEST_NEWS_JSON}. Run main.py first."


def test_article_id_uniqueness():
    """Test that every article has a unique article_id."""
    with open(LATEST_NEWS_JSON, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    assert isinstance(articles, list), "News JSON should be a list of articles"
    assert len(articles) > 0, "News JSON should contain at least one article"

    article_ids = [a['article_id'] for a in articles]
    unique_ids = set(article_ids)

    duplicates = len(article_ids) - len(unique_ids)
    assert duplicates == 0, f"Found {duplicates} duplicate article_id(s). All IDs should be unique."


def test_required_fields():
    """Test that all articles have required fields."""
    required_keys = [
        'article_id',
        'source',
        'title',
        'link',
        'published_date',
        'summary',
        'category',
        'run_timestamp'
    ]

    with open(LATEST_NEWS_JSON, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    for idx, article in enumerate(articles):
        for key in required_keys:
            assert key in article, f"Article {idx} (id: {article.get('article_id', 'unknown')}) missing required key: '{key}'"


def test_published_date_validity():
    """Test that published_date can be parsed as a datetime."""
    with open(LATEST_NEWS_JSON, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    # Extract published dates
    dates = [a['published_date'] for a in articles]

    # Create a pandas Series and attempt to parse
    date_series = pd.Series(dates)

    # This will raise if any date cannot be parsed
    try:
        parsed_dates = pd.to_datetime(date_series, errors='raise')
        assert len(parsed_dates) == len(dates), "All dates should parse successfully"
    except Exception as e:
        pytest.fail(f"Date parsing failed: {e}")


def test_article_id_format():
    """Test that article IDs are valid 16-character hex strings."""
    with open(LATEST_NEWS_JSON, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    for article in articles:
        article_id = article['article_id']
        assert len(article_id) == 16, f"Article ID {article_id} should be 16 characters"
        assert all(c in '0123456789abcdef' for c in article_id), \
            f"Article ID {article_id} should only contain hex characters (0-9, a-f)"


def test_category_values():
    """Test that category field contains valid values."""
    valid_categories = {'competitor', 'internal', 'affiliate'}

    with open(LATEST_NEWS_JSON, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    for article in articles:
        category = article['category']
        assert category in valid_categories, \
            f"Article {article['article_id']} has invalid category: '{category}'. Must be 'competitor', 'internal', or 'affiliate'."


def test_run_timestamp_consistency():
    """Test that all articles share the same run_timestamp."""
    with open(LATEST_NEWS_JSON, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    run_timestamps = set(a['run_timestamp'] for a in articles)
    assert len(run_timestamps) == 1, \
        f"All articles should have the same run_timestamp. Found {len(run_timestamps)}: {run_timestamps}"


if __name__ == "__main__":
    # Run tests with pytest when executed directly
    pytest.main([__file__, "-v"])
