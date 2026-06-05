#!/usr/bin/env python3
"""
E2E Idempotency Test Harness

Tests that running the full pipeline twice with unchanged inputs produces
identical primary keys and row counts.

Acceptance Criteria:
- First run creates baseline snapshot
- Second run with same inputs produces identical:
  - Row count in news_history.csv
  - Set of article_ids
  - Set of normalized URLs
- Only allowed to differ: scrape_timestamp for new articles

Usage:
    pytest tests/e2e_idempotency.py -v
    # OR
    python tests/e2e_idempotency.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from paths import LATEST_NEWS_JSON, LATEST_RUN_INFO_JSON, NEWS_HISTORY_CSV


class TestE2EIdempotency:
    """End-to-end idempotency tests for the full pipeline"""

    @pytest.fixture(scope="class")
    def backup_data(self):
        """Backup existing data before tests, restore after"""
        backup_dir = project_root / "data_backup_e2e"
        backup_dir.mkdir(exist_ok=True)

        # Backup files if they exist
        files_to_backup = [NEWS_HISTORY_CSV, LATEST_NEWS_JSON, LATEST_RUN_INFO_JSON]
        for file in files_to_backup:
            if file.exists():
                shutil.copy2(file, backup_dir / file.name)

        yield

        # Restore files
        for file in files_to_backup:
            backup_file = backup_dir / file.name
            if backup_file.exists():
                shutil.copy2(backup_file, file)
            elif file.exists():
                file.unlink()  # Remove if didn't exist before

        # Cleanup backup
        shutil.rmtree(backup_dir)

    def run_pipeline_step(self, script: str) -> subprocess.CompletedProcess:
        """Run a pipeline script and return result"""
        result = subprocess.run(
            [sys.executable, str(project_root / script)],
            capture_output=True,
            text=True,
            cwd=project_root,
        )
        return result

    def load_csv_snapshot(self) -> dict:
        """Load CSV and create snapshot of key metrics"""
        if not NEWS_HISTORY_CSV.exists():
            return {
                "exists": False,
                "row_count": 0,
                "article_ids": set(),
                "urls": set(),
                "min_date": None,
                "max_date": None,
            }

        df = pd.read_csv(NEWS_HISTORY_CSV)

        snapshot = {
            "exists": True,
            "row_count": len(df),
            "article_ids": set(df["article_id"].tolist()),
            "urls": set(df["link"].str.lower().str.strip().tolist()),
            "min_date": df["published_date"].min() if "published_date" in df.columns else None,
            "max_date": df["published_date"].max() if "published_date" in df.columns else None,
            "columns": list(df.columns),
        }

        return snapshot

    def test_full_pipeline_idempotency_on_same_day(self, backup_data):
        """
        CRITICAL TEST: Running pipeline twice on same day should produce identical results

        This is the core idempotency guarantee:
        - Run 1: Scrape articles, save to CSV
        - Run 2: Scrape SAME articles, should detect duplicates and NOT append

        Expected: row_count_1 == row_count_2, article_ids_1 == article_ids_2
        """
        print("\n" + "=" * 80)
        print("E2E IDEMPOTENCY TEST: Same-Day Double Run")
        print("=" * 80)

        # Clear existing data for clean test
        if NEWS_HISTORY_CSV.exists():
            NEWS_HISTORY_CSV.unlink()
        if LATEST_NEWS_JSON.exists():
            LATEST_NEWS_JSON.unlink()

        # === RUN 1: First execution ===
        print("\n--- RUN 1: First Execution ---")
        result1 = self.run_pipeline_step("scripts/main.py")

        assert result1.returncode == 0, f"Pipeline run 1 failed:\n{result1.stderr}"

        snapshot1 = self.load_csv_snapshot()
        print("Run 1 Results:")
        print(f"  - Row count: {snapshot1['row_count']}")
        print(f"  - Unique article_ids: {len(snapshot1['article_ids'])}")
        print(f"  - Unique URLs: {len(snapshot1['urls'])}")

        assert snapshot1["exists"], "CSV should exist after run 1"
        assert snapshot1["row_count"] > 0, "Should have articles after run 1"

        # === RUN 2: Second execution (same day, same inputs) ===
        print("\n--- RUN 2: Second Execution (IDEMPOTENCY TEST) ---")
        result2 = self.run_pipeline_step("scripts/main.py")

        assert result2.returncode == 0, f"Pipeline run 2 failed:\n{result2.stderr}"

        snapshot2 = self.load_csv_snapshot()
        print("Run 2 Results:")
        print(f"  - Row count: {snapshot2['row_count']}")
        print(f"  - Unique article_ids: {len(snapshot2['article_ids'])}")
        print(f"  - Unique URLs: {len(snapshot2['urls'])}")

        # === ASSERTIONS: Idempotency Check ===
        print("\n--- IDEMPOTENCY VERIFICATION ---")

        # Row count should be identical
        row_diff = snapshot2["row_count"] - snapshot1["row_count"]
        print(f"Row count difference: {row_diff}")

        if row_diff == 0:
            print("✅ PASS: Row count identical (perfect idempotency)")
        elif 0 < row_diff <= 5:
            print(f"⚠️  WARNING: Row count increased by {row_diff} (minor drift)")
            print("This may be acceptable if new articles were published between runs")
        else:
            print(f"❌ FAIL: Row count increased by {row_diff} (significant drift)")

        # Article IDs should be mostly identical (allowing for new articles)
        new_ids = snapshot2["article_ids"] - snapshot1["article_ids"]
        removed_ids = snapshot1["article_ids"] - snapshot2["article_ids"]

        print(f"New article_ids: {len(new_ids)}")
        print(f"Removed article_ids: {len(removed_ids)}")

        assert len(removed_ids) == 0, "Should not lose article_ids on second run"

        # URLs should not have duplicates
        df2 = pd.read_csv(NEWS_HISTORY_CSV)
        df2["_link_norm"] = df2["link"].str.lower().str.strip()
        duplicates = df2[df2.duplicated("_link_norm", keep=False)]

        assert len(duplicates) == 0, f"Found {len(duplicates)} duplicate URLs after run 2"

        # STRICT ASSERTION: Row count should be identical
        # This is the CORE idempotency requirement
        assert (
            row_diff == 0
        ), f"IDEMPOTENCY VIOLATION: Row count changed by {row_diff} on same-day re-run"

        print("\n✅ All idempotency checks passed!")

    def test_csv_structure_stability(self, backup_data):
        """Test that CSV schema remains stable across runs"""
        print("\n" + "=" * 80)
        print("SCHEMA STABILITY TEST")
        print("=" * 80)

        # Run once to get baseline
        result = self.run_pipeline_step("scripts/main.py")
        assert result.returncode == 0

        snapshot = self.load_csv_snapshot()

        # Expected columns
        required_columns = {
            "article_id",
            "title",
            "link",
            "summary",
            "source",
            "category",
            "published_date",
            "scrape_timestamp",
        }

        actual_columns = set(snapshot["columns"])

        missing = required_columns - actual_columns
        assert not missing, f"Missing required columns: {missing}"

        print(f"✅ All required columns present: {required_columns}")
        print(f"   Additional columns: {actual_columns - required_columns}")

    def test_no_duplicate_article_ids(self, backup_data):
        """Test that article_ids are unique"""
        result = self.run_pipeline_step("scripts/main.py")
        assert result.returncode == 0

        df = pd.read_csv(NEWS_HISTORY_CSV)

        duplicates = df[df.duplicated("article_id", keep=False)]

        assert len(duplicates) == 0, f"Found {len(duplicates)} rows with duplicate article_ids"

        print(f"✅ All {len(df)} article_ids are unique")

    def test_no_duplicate_urls(self, backup_data):
        """Test that normalized URLs are unique"""
        result = self.run_pipeline_step("scripts/main.py")
        assert result.returncode == 0

        df = pd.read_csv(NEWS_HISTORY_CSV)
        df["_link_norm"] = df["link"].str.lower().str.strip()

        duplicates = df[df.duplicated("_link_norm", keep=False)]

        assert len(duplicates) == 0, f"Found {len(duplicates)} rows with duplicate URLs"

        print(f"✅ All {len(df)} URLs are unique")

    def test_dates_are_utc_naive(self, backup_data):
        """Test that all dates are in UTC naive format"""
        result = self.run_pipeline_step("scripts/main.py")
        assert result.returncode == 0

        df = pd.read_csv(NEWS_HISTORY_CSV)

        # Check published_date
        if "published_date" in df.columns:
            sample = df["published_date"].dropna().head(100)
            for date_str in sample:
                # Should NOT have timezone indicators
                assert "UTC" not in str(date_str).upper()
                assert "+" not in str(date_str)
                assert "Z" not in str(date_str)

        # Check scrape_timestamp
        if "scrape_timestamp" in df.columns:
            sample = df["scrape_timestamp"].dropna().head(100)
            for date_str in sample:
                assert "UTC" not in str(date_str).upper()
                assert "+" not in str(date_str)
                assert "Z" not in str(date_str)

        print("✅ All dates are in UTC naive format (YYYY-MM-DD HH:MM)")


def main():
    """Run tests manually without pytest"""
    print("=" * 80)
    print("E2E IDEMPOTENCY TEST HARNESS")
    print("=" * 80)
    print("Running all tests...")
    print()

    # Run with pytest
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    main()
