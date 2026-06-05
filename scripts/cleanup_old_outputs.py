#!/usr/bin/env python3
"""
Cleanup script to remove timestamped output files.

Keeps only *_latest.csv files in data/outputs/.
Run periodically to prevent accumulation of old output files.

Usage:
    python scripts/cleanup_old_outputs.py
"""

import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cleanup_outputs():
    """Remove timestamped output files, keeping only *_latest.csv files."""
    outputs_dir = Path('data/outputs')

    if not outputs_dir.exists():
        print(f"Directory {outputs_dir} does not exist.")
        return 0

    # Match files with timestamp pattern: *_YYYYMMDD_HHMMSS.csv
    timestamped_pattern = re.compile(r'.*_\d{8}_\d{6}\.csv$')

    removed_count = 0
    kept_count = 0

    for f in outputs_dir.glob('*.csv'):
        if timestamped_pattern.match(f.name) and '_latest' not in f.name:
            print(f"Removing: {f.name}")
            f.unlink()
            removed_count += 1
        else:
            kept_count += 1

    print("\nCleanup complete:")
    print(f"  Removed: {removed_count} timestamped files")
    print(f"  Kept: {kept_count} files (including *_latest.csv)")

    return removed_count


if __name__ == "__main__":
    cleanup_outputs()
