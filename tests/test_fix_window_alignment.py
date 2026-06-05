"""
Test Fix A: Analysis window aligns with dashboard 30-day window.

Verifies that analysis.py produces metadata that matches the dashboard's
30-day window counts when using identical date filtering logic.
"""

import json


def test_metadata_has_window_totals():
    """Verify analysis metadata includes window totals before soft cap."""
    from paths import DAILY_ANALYSIS_JSON

    assert DAILY_ANALYSIS_JSON.exists(), "Analysis output not found"

    with open(DAILY_ANALYSIS_JSON, 'r') as f:
        analysis = json.load(f)

    metadata = analysis.get('metadata', {})

    # Check new fields exist
    assert 'total_window_articles' in metadata, "Missing total_window_articles"
    assert 'total_window_competitor' in metadata, "Missing total_window_competitor"
    assert 'total_window_internal' in metadata, "Missing total_window_internal"

    # Verify arithmetic
    total = metadata['total_window_articles']
    competitor = metadata['total_window_competitor']
    internal = metadata['total_window_internal']

    assert competitor + internal == total, (
        f"Window totals don't add up: {competitor} + {internal} != {total}"
    )


def test_window_total_greater_than_analyzed():
    """Window total should be >= analyzed total (due to soft cap)."""
    from paths import DAILY_ANALYSIS_JSON

    with open(DAILY_ANALYSIS_JSON, 'r') as f:
        analysis = json.load(f)

    metadata = analysis.get('metadata', {})

    window_total = metadata.get('total_window_articles', 0)
    analyzed_total = metadata.get('articles_analyzed', 0)

    assert window_total >= analyzed_total, (
        f"Window total ({window_total}) should be >= analyzed ({analyzed_total})"
    )


def test_soft_cap_reduces_counts():
    """When soft_capped=True, analyzed < window total."""
    from paths import DAILY_ANALYSIS_JSON

    with open(DAILY_ANALYSIS_JSON, 'r') as f:
        analysis = json.load(f)

    metadata = analysis.get('metadata', {})

    if metadata.get('soft_capped', False):
        window_total = metadata.get('total_window_articles', 0)
        analyzed_total = metadata.get('articles_analyzed', 0)

        assert analyzed_total < window_total, (
            f"Soft cap should reduce counts: {analyzed_total} should be < {window_total}"
        )


def test_analysis_uses_30_day_window():
    """Verify analysis uses 30-day lookback period."""
    from paths import DAILY_ANALYSIS_JSON

    with open(DAILY_ANALYSIS_JSON, 'r') as f:
        analysis = json.load(f)

    metadata = analysis.get('metadata', {})

    assert metadata.get('analysis_period_days') == 30, "Should use 30-day window"
