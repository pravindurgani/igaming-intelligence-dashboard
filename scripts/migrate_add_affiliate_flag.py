#!/usr/bin/env python3
"""
Add is_affiliate column to existing news_history.csv and update categories.

This migration:
1. Adds is_affiliate boolean column based on source name
2. Updates category to 'competitor' for affiliate sources (not 'affiliate')
3. Keeps iGB Affiliate as 'internal' (Clarion's affiliate brand)

Run once after updating sources.json with is_affiliate field.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json

from paths import LATEST_NEWS_JSON, NEWS_HISTORY_CSV

# Sources that are affiliate-focused (regardless of category)
AFFILIATE_SOURCES = {
    "iGaming Afrika",
    "iGaming Expert",
    "Gambling Insider",
    "Game Lounge",
    "Gaming and Co",
    "North Star Network",
    "iGB Affiliate"  # Clarion's affiliate brand
}

# Affiliate sources that should be category='competitor' (external affiliates)
AFFILIATE_COMPETITOR_SOURCES = {
    "iGaming Afrika",
    "iGaming Expert",
    "Gambling Insider",
    "Game Lounge",
    "Gaming and Co",
    "North Star Network"
}

# Sources that should be category='internal' (Clarion brands)
INTERNAL_SOURCES = {
    "iGaming Business",
    "iGB Affiliate",
    "GGB Magazine"
}


def migrate_csv():
    """Update news_history.csv with is_affiliate column and fix categories."""
    if not NEWS_HISTORY_CSV.exists():
        print(f"CSV file not found: {NEWS_HISTORY_CSV}")
        return False

    print(f"Reading {NEWS_HISTORY_CSV}...")
    df = pd.read_csv(NEWS_HISTORY_CSV)
    print(f"Loaded {len(df)} articles")

    # Show before state
    print("\nBefore migration:")
    print("  Category distribution:")
    for cat, count in df['category'].value_counts().items():
        print(f"    {cat}: {count}")

    # Add is_affiliate column
    df['is_affiliate'] = df['source'].isin(AFFILIATE_SOURCES)

    # Fix categories: affiliate sources should be 'competitor' (not 'affiliate')
    df.loc[df['source'].isin(AFFILIATE_COMPETITOR_SOURCES), 'category'] = 'competitor'

    # Fix categories: internal sources should be 'internal'
    df.loc[df['source'].isin(INTERNAL_SOURCES), 'category'] = 'internal'

    # Show after state
    print("\nAfter migration:")
    print("  Category distribution:")
    for cat, count in df['category'].value_counts().items():
        print(f"    {cat}: {count}")
    print("  is_affiliate distribution:")
    print(f"    True: {df['is_affiliate'].sum()}")
    print(f"    False: {(~df['is_affiliate']).sum()}")

    # Save
    df.to_csv(NEWS_HISTORY_CSV, index=False)
    print(f"\n✓ Saved to {NEWS_HISTORY_CSV}")

    return True


def migrate_json():
    """Update latest_competitor_news.json with is_affiliate field and fix categories."""
    if not LATEST_NEWS_JSON.exists():
        print(f"JSON file not found: {LATEST_NEWS_JSON}")
        return False

    print(f"\nReading {LATEST_NEWS_JSON}...")
    with open(LATEST_NEWS_JSON, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    print(f"Loaded {len(articles)} articles")

    updated_count = 0
    for article in articles:
        source = article.get('source', '')

        # Add is_affiliate
        article['is_affiliate'] = source in AFFILIATE_SOURCES

        # Fix category for affiliate competitor sources
        if source in AFFILIATE_COMPETITOR_SOURCES:
            if article.get('category') != 'competitor':
                article['category'] = 'competitor'
                updated_count += 1

        # Fix category for internal sources
        if source in INTERNAL_SOURCES:
            if article.get('category') != 'internal':
                article['category'] = 'internal'
                updated_count += 1

    print(f"Updated {updated_count} article categories")

    # Save
    with open(LATEST_NEWS_JSON, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"✓ Saved to {LATEST_NEWS_JSON}")

    return True


def main():
    print("=" * 70)
    print("ADD is_affiliate COLUMN AND FIX CATEGORIES")
    print("=" * 70)
    print("\nThis script:")
    print("  1. Adds 'is_affiliate' boolean column based on source name")
    print("  2. Updates category to 'competitor' for external affiliate sources")
    print("  3. Keeps iGB Affiliate as 'internal' (Clarion's affiliate brand)")
    print()

    success = True

    # Migrate CSV
    if not migrate_csv():
        success = False

    # Migrate JSON
    if not migrate_json():
        success = False

    if success:
        print("\n" + "=" * 70)
        print("MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print("\nNew dual classification system:")
        print("  - category: 'competitor' | 'internal' (for analysis)")
        print("  - is_affiliate: true | false (for filtering affiliate-focused sources)")
    else:
        print("\n⚠️ Migration completed with warnings")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
