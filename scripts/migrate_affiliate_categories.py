#!/usr/bin/env python3
"""
One-time migration script to update article categories in existing data.

This script updates articles from affiliate sources to have category='affiliate'
instead of 'competitor'. Run this once after updating sources.json to ensure
existing data has the correct categories.

Usage:
    python scripts/migrate_affiliate_categories.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import json

import pandas as pd

from paths import LATEST_NEWS_JSON, NEWS_HISTORY_CSV

# Affiliate sources that should have category='affiliate'
# These are competitor affiliates (not part of the tracked portfolio)
AFFILIATE_SOURCES = {
    "iGaming Afrika",
    "Gambling Insider",
    "North Star Network",
    "Game Lounge",
    "iGaming Expert",
    "Gaming and Co",
}

# Sources that should stay as 'internal' (tracked portfolio brands)
INTERNAL_SOURCES = {
    "iGaming Business",
    "iGB Affiliate",  # Portfolio affiliate brand - counts as internal
    "GGB Magazine"
}


def migrate_csv():
    """Update categories in news_history.csv."""
    if not NEWS_HISTORY_CSV.exists():
        print(f"CSV file not found: {NEWS_HISTORY_CSV}")
        return False

    print(f"Reading {NEWS_HISTORY_CSV}...")
    df = pd.read_csv(NEWS_HISTORY_CSV)

    original_categories = df['category'].value_counts().to_dict()
    print("\nBefore migration:")
    for cat, count in original_categories.items():
        print(f"  {cat}: {count}")

    # Update affiliate sources (but NOT iGB Affiliate which is internal)
    affiliate_mask = (
        df['source'].isin(AFFILIATE_SOURCES) &
        ~df['source'].isin(INTERNAL_SOURCES)
    )
    updated_count = affiliate_mask.sum()
    df.loc[affiliate_mask, 'category'] = 'affiliate'

    new_categories = df['category'].value_counts().to_dict()
    print("\nAfter migration:")
    for cat, count in new_categories.items():
        print(f"  {cat}: {count}")

    print(f"\nUpdated {updated_count} articles to 'affiliate' category")

    # Save
    df.to_csv(NEWS_HISTORY_CSV, index=False)
    print(f"✓ Saved to {NEWS_HISTORY_CSV}")

    return True


def migrate_json():
    """Update categories in latest_competitor_news.json."""
    if not LATEST_NEWS_JSON.exists():
        print(f"JSON file not found: {LATEST_NEWS_JSON}")
        return False

    print(f"\nReading {LATEST_NEWS_JSON}...")
    with open(LATEST_NEWS_JSON, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    updated_count = 0
    for article in articles:
        source = article.get('source', '')
        if source in AFFILIATE_SOURCES and source not in INTERNAL_SOURCES:
            if article.get('category') != 'affiliate':
                article['category'] = 'affiliate'
                updated_count += 1

    print(f"Updated {updated_count} articles to 'affiliate' category")

    # Save
    with open(LATEST_NEWS_JSON, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"✓ Saved to {LATEST_NEWS_JSON}")

    return True


def main():
    print("=" * 70)
    print("AFFILIATE CATEGORY MIGRATION")
    print("=" * 70)
    print("\nThis script updates existing article categories to include 'affiliate'")
    print(f"Affiliate sources: {', '.join(sorted(AFFILIATE_SOURCES - INTERNAL_SOURCES))}")
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
        print("✅ MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print("\nCategory filter now includes:")
        print("  • competitor - Competitor news sources")
        print("  • affiliate  - Affiliate/partner sources")
        print("  • internal   - Tracked portfolio brands")
    else:
        print("\n⚠️ Migration completed with warnings")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
