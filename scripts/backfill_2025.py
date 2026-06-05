#!/usr/bin/env python3
"""
One-time backfill script to fetch historical articles since Jan 1, 2025.

This script fetches more articles per source to build up historical data.
Run once to populate history, then use regular pipeline for ongoing updates.

Usage:
    python scripts/backfill_2025.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
from datetime import datetime

import pandas as pd

from paths import NEWS_HISTORY_CSV
from scripts.main import NewsAggregator


def backfill_since_date(start_date: str = "2025-01-01", max_articles_per_source: int = 100):
    """
    Backfill articles from all sources since start_date.

    Note: Google News RSS doesn't support explicit date range queries,
    but we fetch more articles and filter by date.

    Args:
        start_date: ISO date string (YYYY-MM-DD) to start from
        max_articles_per_source: Maximum articles to fetch per source
    """
    print(f"🔄 Starting backfill from {start_date}...")
    print(f"   Max articles per source: {max_articles_per_source}")

    aggregator = NewsAggregator()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")

    # Load existing history
    try:
        existing_df = pd.read_csv(NEWS_HISTORY_CSV)
        existing_ids = set(existing_df['article_id'].astype(str))
        print(f"   Existing articles: {len(existing_df)}")
    except FileNotFoundError:
        existing_df = pd.DataFrame()
        existing_ids = set()
        print("   No existing history file, creating new one")

    # Load sources config
    sources_config = aggregator._load_sources_config()

    all_new_articles = []

    # Process Google News proxy sources (from unified sources array)
    google_sources = sources_config.get('google_news_proxy', {}).get('sources', [])
    print(f"\n📰 Processing {len(google_sources)} Google News sources...")

    for source_config in google_sources:
        source_name = source_config.get('name', 'Unknown')
        domain = source_config.get('domain', '')
        category = source_config.get('category', 'competitor')
        is_affiliate = source_config.get('is_affiliate', False)

        print(f"\n   → {source_name} ({domain}) [{category}] {'[affiliate]' if is_affiliate else ''}")

        try:
            articles = aggregator.fetch_via_google_news(
                source=source_name,
                site_domain=domain,
                category=category,
                is_affiliate=is_affiliate
            )

            # Filter to new articles since start_date
            new_count = 0
            for article in articles[:max_articles_per_source]:
                article_id = str(article.get('article_id', ''))

                # Skip if already exists
                if article_id in existing_ids:
                    continue

                # Check date
                pub_date = article.get('published_date')
                if pub_date:
                    try:
                        article_dt = pd.to_datetime(pub_date)
                        if article_dt.tz_localize(None) if article_dt.tzinfo else article_dt >= start_dt:
                            all_new_articles.append(article)
                            existing_ids.add(article_id)
                            new_count += 1
                    except Exception:
                        # Include articles with unparseable dates
                        all_new_articles.append(article)
                        existing_ids.add(article_id)
                        new_count += 1

            print(f"      Found {new_count} new articles")

        except Exception as e:
            print(f"      ❌ Error: {str(e)[:50]}")

        # Rate limiting to avoid getting blocked
        time.sleep(1.5)

    # Process direct RSS sources
    direct_sources = sources_config.get('direct_rss', {}).get('sources', [])
    if direct_sources:
        print(f"\n📰 Processing {len(direct_sources)} direct RSS sources...")

        for source_config in direct_sources:
            source_name = source_config.get('name', 'Unknown')
            url = source_config.get('url', '')
            category = source_config.get('category', 'competitor')
            is_affiliate = source_config.get('is_affiliate', False)

            print(f"\n   → {source_name} {'[affiliate]' if is_affiliate else ''}")

            try:
                articles = aggregator.fetch_direct_rss(
                    source=source_name,
                    url=url,
                    category=category,
                    is_affiliate=is_affiliate
                )

                new_count = 0
                for article in articles[:max_articles_per_source]:
                    article_id = str(article.get('article_id', ''))

                    if article_id in existing_ids:
                        continue

                    pub_date = article.get('published_date')
                    if pub_date:
                        try:
                            article_dt = pd.to_datetime(pub_date)
                            if article_dt.tz_localize(None) if article_dt.tzinfo else article_dt >= start_dt:
                                all_new_articles.append(article)
                                existing_ids.add(article_id)
                                new_count += 1
                        except Exception:
                            all_new_articles.append(article)
                            existing_ids.add(article_id)
                            new_count += 1

                print(f"      Found {new_count} new articles")

            except Exception as e:
                print(f"      ❌ Error: {str(e)[:50]}")

            time.sleep(1.0)

    # Save results
    if all_new_articles:
        new_df = pd.DataFrame(all_new_articles)

        if len(existing_df) > 0:
            combined = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined = new_df

        # Deduplicate just in case
        combined = combined.drop_duplicates(subset=['article_id'], keep='first')

        # Sort by date descending
        try:
            combined['published_date'] = pd.to_datetime(combined['published_date'], errors='coerce')
            combined = combined.sort_values('published_date', ascending=False)
        except Exception:
            pass

        # Save
        combined.to_csv(NEWS_HISTORY_CSV, index=False)

        print("\n✅ Backfill complete!")
        print(f"   New articles added: {len(all_new_articles)}")
        print(f"   Total articles in history: {len(combined)}")

        # Show breakdown by category
        if 'category' in combined.columns:
            print("\n   By category:")
            for cat, count in combined['category'].value_counts().items():
                print(f"      {cat}: {count}")

        # Show breakdown by source
        if 'source' in combined.columns:
            print("\n   Top sources:")
            for source, count in combined['source'].value_counts().head(10).items():
                print(f"      {source}: {count}")
    else:
        print("\n⚠️ No new articles found")

    return all_new_articles


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill articles since a specific date")
    parser.add_argument(
        '--start-date',
        default='2025-01-01',
        help='Start date in YYYY-MM-DD format (default: 2025-01-01)'
    )
    parser.add_argument(
        '--max-per-source',
        type=int,
        default=100,
        help='Maximum articles per source (default: 100)'
    )

    args = parser.parse_args()

    backfill_since_date(args.start_date, args.max_per_source)
