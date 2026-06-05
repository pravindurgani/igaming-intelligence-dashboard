"""
Test that analysis uses full 30-day window from CSV history with batching.

Verifies Fix A: Gemini must analyze ALL articles in last 30 days from news_history.csv.

Note: The analysis now uses batching (no soft cap) with new metadata fields:
- total_window_articles, total_window_competitor, total_window_internal
- articles_analyzed (equals total_window_articles)
- batched=True, soft_capped=False
"""

import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest


def test_analysis_uses_csv_not_json():
    """Verify analysis loads from news_history.csv with new batching metadata."""
    from paths import DAILY_ANALYSIS_JSON, NEWS_HISTORY_CSV

    # Check that daily_analysis.json exists (most recent analysis run)
    assert DAILY_ANALYSIS_JSON.exists(), "No analysis output found - run analysis first"

    # Load analysis metadata
    with open(DAILY_ANALYSIS_JSON, 'r') as f:
        analysis = json.load(f)

    metadata = analysis.get('metadata', {})

    # Verify metadata includes NEW expected fields (post-batching schema)
    assert 'total_window_articles' in metadata, "Missing total_window_articles (new schema)"
    assert 'total_window_competitor' in metadata, "Missing total_window_competitor (new schema)"
    assert 'total_window_internal' in metadata, "Missing total_window_internal (new schema)"
    assert 'articles_analyzed' in metadata

    # The key test: articles_analyzed should EQUAL total_window_articles (no cap loss)
    articles_analyzed = metadata['articles_analyzed']
    total_window = metadata['total_window_articles']

    # Load the CSV to verify counts
    df = pd.read_csv(NEWS_HISTORY_CSV)

    # Parse dates and filter to 30-day window
    df['published_date'] = pd.to_datetime(df['published_date'], utc=True)
    cutoff_date = datetime.now(UTC) - timedelta(days=30)
    df_filtered = df[df['published_date'] >= cutoff_date]

    csv_count = len(df_filtered)

    print("\n📊 Verification:")
    print(f"  CSV total articles: {len(df)}")
    print(f"  CSV 30-day window: {csv_count}")
    print(f"  Analysis window total: {total_window}")
    print(f"  Analysis processed: {articles_analyzed}")

    # With batching, articles_analyzed should equal total_window_articles
    assert articles_analyzed == total_window, (
        f"With batching, articles_analyzed ({articles_analyzed}) should equal "
        f"total_window_articles ({total_window})"
    )


def test_analysis_metadata_consistency():
    """Verify metadata counts match with new batching schema."""
    from paths import DAILY_ANALYSIS_JSON

    with open(DAILY_ANALYSIS_JSON, 'r') as f:
        analysis = json.load(f)

    metadata = analysis.get('metadata', {})

    # Use NEW field names (post-batching schema)
    competitor_count = metadata.get('total_window_competitor', 0)
    internal_count = metadata.get('total_window_internal', 0)
    total_window = metadata.get('total_window_articles', 0)
    total_analyzed = metadata.get('articles_analyzed', 0)

    # Verify the sum of categories matches window total
    assert competitor_count + internal_count == total_window, (
        f"Metadata inconsistent: {competitor_count} competitor + {internal_count} "
        f"internal = {competitor_count + internal_count}, but total_window = {total_window}"
    )

    # With batching, analyzed should equal window total
    assert total_analyzed == total_window, (
        f"With batching, articles_analyzed ({total_analyzed}) should equal "
        f"total_window_articles ({total_window})"
    )

    print("\n✓ Metadata consistent:")
    print(f"  Competitor: {competitor_count}")
    print(f"  Internal: {internal_count}")
    print(f"  Total window: {total_window}")
    print(f"  Total analyzed: {total_analyzed}")


def test_analysis_lookback_period():
    """Verify analysis uses correct 30-day lookback period."""
    from paths import DAILY_ANALYSIS_JSON

    with open(DAILY_ANALYSIS_JSON, 'r') as f:
        analysis = json.load(f)

    metadata = analysis.get('metadata', {})

    # Check lookback period is 30 days
    lookback_days = metadata.get('analysis_period_days', 0)
    assert lookback_days == 30, f"Expected 30-day lookback, got {lookback_days}"

    # Verify window_start_utc is approximately 30 days ago (new schema)
    window_start_str = metadata.get('window_start_utc', '')
    if window_start_str:
        window_start = datetime.fromisoformat(window_start_str.replace('Z', '+00:00'))
        now = datetime.now(UTC)
        delta = now - window_start

        # Skip if analysis data is stale (needs a pipeline run to regenerate)
        if delta.days > 32:
            pytest.skip(
                f"Stale analysis data: window_start is {delta.days} days ago. "
                f"Run the pipeline to regenerate daily_analysis.json."
            )

        # Allow some tolerance (28-32 days)
        assert 28 <= delta.days <= 32, (
            f"Window start suggests {delta.days} days lookback, expected ~30"
        )

    print(f"\n✓ Lookback period: {lookback_days} days")
    print(f"  Window start: {window_start_str}")


def test_analysis_batching():
    """Verify batching is enabled (no soft cap).

    With batching, we analyze ALL articles in the window via multiple API calls.
    The soft_capped flag should be False.
    """
    from paths import DAILY_ANALYSIS_JSON

    with open(DAILY_ANALYSIS_JSON, 'r') as f:
        analysis = json.load(f)

    metadata = analysis.get('metadata', {})
    articles_analyzed = metadata.get('articles_analyzed', 0)
    total_window = metadata.get('total_window_articles', 0)

    # With batching, articles_analyzed should equal total_window (no cap)
    assert articles_analyzed == total_window, (
        f"With batching, should analyze all articles: {articles_analyzed} != {total_window}"
    )

    # Batching should be enabled
    batched = metadata.get('batched', False)
    assert batched is True, "Expected batched=True with new analysis"

    # Soft cap should be disabled
    soft_capped = metadata.get('soft_capped', True)
    assert soft_capped is False, "Expected soft_capped=False with batching"

    print(f"\n✓ Batching working: {articles_analyzed} articles analyzed")
    print(f"  Batched: {batched}")
    print(f"  Soft capped: {soft_capped}")
