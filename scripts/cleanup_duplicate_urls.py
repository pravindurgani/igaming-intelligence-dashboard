#!/usr/bin/env python3
"""
Cleanup Script: Remove Duplicate URLs from news_history.csv

This script removes duplicate URLs that were created before P0-1 fix was applied.
Keeps the earliest occurrence of each URL (by scrape_timestamp).

Usage:
    python scripts/cleanup_duplicate_urls.py
    python scripts/cleanup_duplicate_urls.py --dry-run  # Preview without making changes
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from paths import NEWS_HISTORY_CSV


def main(dry_run=False):
    print("=" * 80)
    print("CLEANUP: Remove Duplicate URLs from news_history.csv")
    print("=" * 80)

    if not NEWS_HISTORY_CSV.exists():
        print(f"✗ CSV file not found: {NEWS_HISTORY_CSV}")
        sys.exit(1)

    # Load CSV
    df = pd.read_csv(NEWS_HISTORY_CSV)
    before_count = len(df)

    print("\n📊 Current state:")
    print(f"   Total rows: {before_count}")

    # Normalize URLs for comparison
    df['_link_norm'] = df['link'].str.lower().str.strip()

    # Find duplicates
    duplicates = df[df.duplicated('_link_norm', keep=False)]
    dup_url_count = duplicates['_link_norm'].nunique()

    if dup_url_count == 0:
        print("\n✅ No duplicate URLs found!")
        return

    print(f"\n⚠️  Found {dup_url_count} URLs with duplicates")
    print(f"   Total duplicate rows: {len(duplicates)}")

    # Show sample
    print("\n📋 Sample duplicates:")
    url_groups = duplicates.groupby('_link_norm').agg({
        'article_id': lambda x: list(x),
        'scrape_timestamp': lambda x: list(x),
        'title': 'first'
    })

    for idx, (url, row) in enumerate(url_groups.head(5).iterrows(), 1):
        print(f"\n   {idx}. {url[:70]}...")
        print(f"      Title: {row['title'][:60]}...")
        print(f"      article_ids: {row['article_id']}")
        print(f"      Timestamps: {row['scrape_timestamp']}")

    if dry_run:
        print("\n🔍 DRY RUN MODE - No changes will be made")
        print(f"\n   Would remove {len(duplicates)} rows")
        print(f"   Would keep {before_count - len(duplicates)} rows")
        print("\n   To apply changes, run without --dry-run flag")
        return

    # Confirm before proceeding
    print("\n" + "=" * 80)
    print("CLEANUP PLAN:")
    print(f"  • Remove {len(duplicates)} duplicate rows")
    print("  • Keep earliest occurrence of each URL (by scrape_timestamp)")
    print(f"  • Create backup: {NEWS_HISTORY_CSV}.backup")
    print("=" * 80)

    response = input("\nProceed with cleanup? (yes/no): ")

    if response.lower() != 'yes':
        print("✗ Cleanup cancelled")
        return

    # Create backup
    backup_path = NEWS_HISTORY_CSV.with_suffix('.csv.backup')
    df.drop(columns=['_link_norm']).to_csv(backup_path, index=False)
    print(f"\n✓ Created backup: {backup_path}")

    # Remove duplicates (keep first occurrence by scrape_timestamp)
    df_sorted = df.sort_values('scrape_timestamp')
    df_clean = df_sorted.drop_duplicates('_link_norm', keep='first')

    # Drop temporary column
    df_clean = df_clean.drop(columns=['_link_norm'])

    after_count = len(df_clean)
    removed_count = before_count - after_count

    # Save cleaned CSV (using atomic write pattern)
    temp_csv = NEWS_HISTORY_CSV.with_suffix('.tmp')
    df_clean.to_csv(temp_csv, index=False)
    import os
    os.replace(temp_csv, NEWS_HISTORY_CSV)

    print("\n" + "=" * 80)
    print("✅ CLEANUP COMPLETE")
    print("=" * 80)
    print(f"   Before:  {before_count} rows")
    print(f"   After:   {after_count} rows")
    print(f"   Removed: {removed_count} duplicate rows")
    print(f"\n   Backup saved to: {backup_path}")
    print(f"   Cleaned CSV: {NEWS_HISTORY_CSV}")
    print("=" * 80)

    # Verify no duplicates remain
    df_verify = pd.read_csv(NEWS_HISTORY_CSV)
    df_verify['_link_norm'] = df_verify['link'].str.lower().str.strip()
    remaining_dups = df_verify[df_verify.duplicated('_link_norm', keep=False)]

    if len(remaining_dups) == 0:
        print("\n✅ Verification: No duplicate URLs remain!")
    else:
        print(f"\n⚠️  Warning: {len(remaining_dups)} duplicate URLs still present")
        print("   This may indicate an issue with the cleanup logic")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Remove duplicate URLs from news_history.csv"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the CSV"
    )

    args = parser.parse_args()
    main(dry_run=args.dry_run)
