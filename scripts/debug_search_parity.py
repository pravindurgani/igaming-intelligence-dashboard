#!/usr/bin/env python3
"""
Debug utility to verify search parity between News Feed and Context Explorer.

Runs the same query through both pipelines and reports any differences.

Usage:
    python scripts/debug_search_parity.py "gaming"
    python scripts/debug_search_parity.py "cricket" --window 30
    python scripts/debug_search_parity.py "regulation" --verbose
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from paths import NEWS_HISTORY_CSV
from src.config import SEARCH_FIELDS_DEFAULT
from src.search import search_all_time


def load_data() -> pd.DataFrame:
    """Load the full news history CSV."""
    df = pd.read_csv(NEWS_HISTORY_CSV)

    # Parse dates
    if 'published_date' in df.columns:
        df['published_date'] = pd.to_datetime(df['published_date'], utc=True, errors='coerce')

    # Ensure article_id is string
    if 'article_id' in df.columns:
        df['article_id'] = df['article_id'].astype(str)

    return df


def get_window_filtered_df(df: pd.DataFrame, window_days: int) -> pd.DataFrame:
    """Filter DataFrame to the specified window (simulates News Feed)."""
    now = datetime.now(UTC)
    start_date = now - timedelta(days=window_days)

    mask = (df['published_date'] >= start_date) & (df['published_date'] <= now)
    return df[mask].copy()


def search_news_feed_pipeline(
    df_full: pd.DataFrame,
    query: str,
    window_days: int = 30
) -> tuple[set[str], pd.DataFrame]:
    """
    Simulate News Feed search pipeline.

    1. Filter df to window
    2. Run search_all_time on filtered df

    Returns:
        Tuple of (set of article_ids, DataFrame of results)
    """
    # Step 1: Filter to window (like News Feed does)
    filtered_df = get_window_filtered_df(df_full, window_days)

    # Step 2: Search on filtered df
    results = search_all_time(filtered_df, query, search_fields=SEARCH_FIELDS_DEFAULT)

    article_ids = set(results['article_id'].astype(str)) if not results.empty else set()
    return article_ids, results


def search_context_explorer_pipeline(
    df_full: pd.DataFrame,
    query: str,
    window_days: int = 30
) -> tuple[set[str], pd.DataFrame]:
    """
    Simulate Context Explorer search pipeline.

    1. Run search_all_time on FULL df (ALL TIME)
    2. Optionally filter results to window for comparison

    Returns:
        Tuple of (set of article_ids within window, DataFrame of all results)
    """
    # Step 1: Search on full df (ALL TIME)
    all_results = search_all_time(df_full, query, search_fields=SEARCH_FIELDS_DEFAULT)

    if all_results.empty:
        return set(), all_results

    # Step 2: Filter to window for fair comparison with News Feed
    now = datetime.now(UTC)
    start_date = now - timedelta(days=window_days)

    # Parse dates in results if needed
    if 'published_date' in all_results.columns:
        all_results['published_date'] = pd.to_datetime(
            all_results['published_date'], utc=True, errors='coerce'
        )

        mask = (all_results['published_date'] >= start_date) & (all_results['published_date'] <= now)
        window_results = all_results[mask]
    else:
        window_results = all_results

    article_ids = set(window_results['article_id'].astype(str)) if not window_results.empty else set()
    return article_ids, all_results


def compute_parity_diff(
    news_feed_ids: set[str],
    context_explorer_ids: set[str]
) -> dict[str, Any]:
    """
    Compute the symmetric difference and parity metrics.

    Returns:
        Dict with parity analysis results
    """
    only_in_news_feed = news_feed_ids - context_explorer_ids
    only_in_context_explorer = context_explorer_ids - news_feed_ids
    symmetric_diff = news_feed_ids.symmetric_difference(context_explorer_ids)
    intersection = news_feed_ids.intersection(context_explorer_ids)

    return {
        'news_feed_count': len(news_feed_ids),
        'context_explorer_count': len(context_explorer_ids),
        'intersection_count': len(intersection),
        'symmetric_diff_count': len(symmetric_diff),
        'only_in_news_feed': only_in_news_feed,
        'only_in_context_explorer': only_in_context_explorer,
        'is_parity': len(symmetric_diff) == 0,
    }


def get_article_details(df: pd.DataFrame, article_ids: set[str], limit: int = 25) -> list[dict]:
    """Get title and details for a set of article IDs."""
    if not article_ids:
        return []

    df_filtered = df[df['article_id'].astype(str).isin(article_ids)].head(limit)

    details = []
    for _, row in df_filtered.iterrows():
        details.append({
            'article_id': str(row.get('article_id', '')),
            'title': str(row.get('title', ''))[:80],
            'published_date': str(row.get('published_date', ''))[:10],
            'category': str(row.get('category', '')),
        })

    return details


def run_parity_check(
    query: str,
    window_days: int = 30,
    verbose: bool = False
) -> dict[str, Any]:
    """
    Run full parity check for a query.

    Args:
        query: Search query string
        window_days: Window size in days
        verbose: Whether to print detailed output

    Returns:
        Dict with full parity analysis
    """
    # Load data
    df_full = load_data()

    if verbose:
        print(f"\n{'='*60}")
        print(f"Search Parity Check: '{query}'")
        print(f"Window: {window_days} days")
        print(f"Total articles in CSV: {len(df_full)}")
        print(f"{'='*60}")

    # Run both pipelines
    news_feed_ids, news_feed_results = search_news_feed_pipeline(df_full, query, window_days)
    context_explorer_ids, context_explorer_results = search_context_explorer_pipeline(df_full, query, window_days)

    # Compute parity
    parity = compute_parity_diff(news_feed_ids, context_explorer_ids)

    if verbose:
        print("\n📊 Results:")
        print(f"  News Feed (windowed):     {parity['news_feed_count']} articles")
        print(f"  Context Explorer (in window): {parity['context_explorer_count']} articles")
        print(f"  Intersection:             {parity['intersection_count']} articles")
        print(f"  Symmetric difference:     {parity['symmetric_diff_count']} articles")

        if parity['is_parity']:
            print("\n✅ PARITY ACHIEVED - Both pipelines return identical results!")
        else:
            print(f"\n❌ PARITY MISMATCH - {parity['symmetric_diff_count']} differing articles")

            if parity['only_in_news_feed']:
                print(f"\n  Only in News Feed ({len(parity['only_in_news_feed'])}):")
                details = get_article_details(df_full, parity['only_in_news_feed'])
                for d in details[:10]:
                    print(f"    - [{d['article_id']}] {d['title']}")

            if parity['only_in_context_explorer']:
                print(f"\n  Only in Context Explorer ({len(parity['only_in_context_explorer'])}):")
                details = get_article_details(df_full, parity['only_in_context_explorer'])
                for d in details[:10]:
                    print(f"    - [{d['article_id']}] {d['title']}")

    # Add article details for UI display
    parity['news_feed_only_details'] = get_article_details(df_full, parity['only_in_news_feed'])
    parity['context_explorer_only_details'] = get_article_details(df_full, parity['only_in_context_explorer'])

    return parity


def run_batch_parity_check(queries: list[str], window_days: int = 30) -> dict[str, dict]:
    """Run parity check for multiple queries."""
    results = {}

    print(f"\n{'='*60}")
    print("Batch Parity Check")
    print(f"Queries: {queries}")
    print(f"Window: {window_days} days")
    print(f"{'='*60}\n")

    all_pass = True
    for query in queries:
        parity = run_parity_check(query, window_days, verbose=False)
        results[query] = parity

        status = "✅ PASS" if parity['is_parity'] else f"❌ FAIL ({parity['symmetric_diff_count']} diff)"
        print(f"  '{query}': {status} (NF={parity['news_feed_count']}, CE={parity['context_explorer_count']})")

        if not parity['is_parity']:
            all_pass = False

    print(f"\n{'='*60}")
    if all_pass:
        print("✅ ALL QUERIES PASS - Search parity verified!")
    else:
        print("❌ SOME QUERIES FAILED - Check output above")
    print(f"{'='*60}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Debug search parity between News Feed and Context Explorer'
    )
    parser.add_argument('query', nargs='?', help='Search query to test')
    parser.add_argument('--window', type=int, default=30, help='Window size in days (default: 30)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--batch', action='store_true',
                       help='Run batch test with standard queries (gaming, cricket, regulation)')

    args = parser.parse_args()

    if args.batch or not args.query:
        # Run batch test with standard queries
        standard_queries = ['gaming', 'cricket', 'regulation', 'Brazil', 'AI']
        run_batch_parity_check(standard_queries, args.window)
    else:
        # Run single query test
        run_parity_check(args.query, args.window, verbose=True)


if __name__ == '__main__':
    main()
