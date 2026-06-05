#!/usr/bin/env python3
"""
Cleanup script to ensure ALL articles have category = 'competitor' or 'internal'.
Fixes test failures where competitor + internal != total.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json

import pandas as pd

from paths import LATEST_NEWS_JSON, NEWS_HISTORY_CSV

# Correct category for each source
SOURCE_CATEGORIES = {
    # Competitors (external)
    "Next.io": "competitor",
    "SiGMA World": "competitor",
    "EGR Global": "competitor",
    "CDC Gaming": "competitor",
    "Global Gaming Insider": "competitor",
    "iGaming Today": "competitor",
    "SBC News": "competitor",
    "iGaming Future": "competitor",
    # Affiliate competitors - category is COMPETITOR, is_affiliate=True handles filtering
    "Gambling Insider": "competitor",
    "Game Lounge": "competitor",
    "Gaming and Co": "competitor",
    "North Star Network": "competitor",
    "iGaming Afrika": "competitor",
    "iGaming Expert": "competitor",
    # Internal (Clarion brands)
    "iGaming Business": "internal",
    "iGB Affiliate": "internal",
    "GGB Magazine": "internal"
}

AFFILIATE_SOURCES = {
    "iGaming Afrika", "iGaming Expert", "Gambling Insider",
    "Game Lounge", "Gaming and Co", "North Star Network", "iGB Affiliate"
}


def cleanup_csv():
    """Fix categories in news_history.csv"""
    print("=" * 60)
    print("Cleaning up news_history.csv")
    print("=" * 60)

    df = pd.read_csv(NEWS_HISTORY_CSV)
    print(f"Loaded {len(df)} articles")

    print("\nBEFORE cleanup:")
    print(df['category'].value_counts())

    # Fix ALL categories based on source
    changes = 0
    for source, correct_category in SOURCE_CATEGORIES.items():
        mask = (df['source'] == source) & (df['category'] != correct_category)
        num_changed = mask.sum()
        if num_changed > 0:
            print(f"  Fixing {num_changed} articles: {source} → {correct_category}")
            df.loc[df['source'] == source, 'category'] = correct_category
            changes += num_changed

    # Handle any unknown sources - default to competitor
    unknown_mask = ~df['source'].isin(SOURCE_CATEGORIES.keys())
    if unknown_mask.any():
        unknown_sources = df.loc[unknown_mask, 'source'].unique()
        print(f"  Unknown sources (defaulting to competitor): {list(unknown_sources)}")
        df.loc[unknown_mask, 'category'] = 'competitor'
        changes += unknown_mask.sum()

    # Ensure is_affiliate column exists and is correct
    df['is_affiliate'] = df['source'].isin(AFFILIATE_SOURCES)

    # Save
    df.to_csv(NEWS_HISTORY_CSV, index=False)

    print(f"\nAFTER cleanup ({changes} articles fixed):")
    print(df['category'].value_counts())

    return df


def cleanup_json():
    """Fix categories in latest_competitor_news.json"""
    print("\n" + "=" * 60)
    print("Cleaning up latest_competitor_news.json")
    print("=" * 60)

    if not LATEST_NEWS_JSON.exists():
        print("File not found, skipping")
        return

    with open(LATEST_NEWS_JSON, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    print(f"Loaded {len(articles)} articles")

    changes = 0
    for article in articles:
        source = article.get('source', '')
        correct_category = SOURCE_CATEGORIES.get(source, 'competitor')

        if article.get('category') != correct_category:
            article['category'] = correct_category
            changes += 1

        article['is_affiliate'] = source in AFFILIATE_SOURCES

    with open(LATEST_NEWS_JSON, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"Fixed {changes} articles")


def verify():
    """Verify that competitor + internal = total"""
    print("\n" + "=" * 60)
    print("Verification")
    print("=" * 60)

    df = pd.read_csv(NEWS_HISTORY_CSV)

    total = len(df)
    competitor = len(df[df['category'] == 'competitor'])
    internal = len(df[df['category'] == 'internal'])

    print(f"Total: {total}")
    print(f"Competitor: {competitor}")
    print(f"Internal: {internal}")
    print(f"Sum: {competitor + internal}")

    if competitor + internal == total:
        print("\n✅ PASS: competitor + internal = total")
        return True
    else:
        print(f"\n❌ FAIL: {competitor} + {internal} ≠ {total}")
        return False


def main():
    print("🧹 Fixing category data for tests...\n")
    cleanup_csv()
    cleanup_json()
    success = verify()

    if success:
        print("\n✅ Data cleaned! Run `pytest tests/ -v` to verify tests pass.")
    else:
        print("\n❌ Cleanup incomplete. Check for unknown sources.")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
