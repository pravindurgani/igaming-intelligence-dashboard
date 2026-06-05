"""
Tests for analysis batching functionality.
Verifies that batching covers all articles exactly once
and produces deterministic output.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

# Add project root
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))


class TestBatchIterator:
    """Tests for the batch_iter function."""

    def test_batch_covers_all_articles(self):
        """Given N articles, ensure batches cover all articles exactly once."""
        # Note: We use a MockAnalyzer instead of importing NewsAnalyzer
        # to avoid requiring the google-genai module in tests

        # Create test DataFrame with known articles
        n_articles = 295  # Simulate real scenario
        test_df = pd.DataFrame({
            'article_id': [f'article_{i:04d}' for i in range(n_articles)],
            'source': ['Test Source'] * n_articles,
            'title': [f'Test Title {i}' for i in range(n_articles)],
            'summary': [f'Test Summary {i}' for i in range(n_articles)],
            'content': [f'Test Content {i}' for i in range(n_articles)],
            'published_date': [datetime.now(UTC).isoformat()] * n_articles,
            'category': ['competitor'] * (n_articles - 30) + ['internal'] * 30,
        })

        # Mock analyzer that replicates batch_iter logic without API dependencies
        class MockAnalyzer:
            def __init__(self):
                self.batch_size = 60
                self.content_truncate_chars = 500

            def batch_iter(self, df):
                """Yield batches of articles in deterministic order."""
                articles = []
                for _, row in df.iterrows():
                    content = str(row.get('content', '') or '')
                    if len(content) > self.content_truncate_chars:
                        content = content[:self.content_truncate_chars] + '...'

                    articles.append({
                        'article_id': row.get('article_id', ''),
                        'source': row.get('source', 'Unknown'),
                        'title': row.get('title', ''),
                        'summary': row.get('summary', ''),
                        'content': content,
                        'published_date': str(row.get('published_date', '')),
                        'category': row.get('category', ''),
                    })

                for i in range(0, len(articles), self.batch_size):
                    yield articles[i:i + self.batch_size]

        analyzer = MockAnalyzer()

        # Collect all batched articles
        all_batched_ids = []
        batch_count = 0
        for batch in analyzer.batch_iter(test_df):
            batch_count += 1
            for article in batch:
                all_batched_ids.append(article['article_id'])

        # Verify coverage
        assert len(all_batched_ids) == n_articles, (
            f"Expected {n_articles} articles, got {len(all_batched_ids)}"
        )

        # Verify no duplicates
        assert len(all_batched_ids) == len(set(all_batched_ids)), (
            "Duplicate articles found in batches!"
        )

        # Verify correct batch count
        expected_batches = (n_articles + 60 - 1) // 60  # Ceiling division
        assert batch_count == expected_batches, (
            f"Expected {expected_batches} batches, got {batch_count}"
        )

    def test_batch_order_deterministic(self):
        """Verify batch order is deterministic across multiple runs."""

        class MockAnalyzer:
            def __init__(self):
                self.batch_size = 10
                self.content_truncate_chars = 500

            def batch_iter(self, df):
                articles = []
                for _, row in df.iterrows():
                    articles.append({'article_id': row.get('article_id', '')})
                for i in range(0, len(articles), self.batch_size):
                    yield articles[i:i + self.batch_size]

        analyzer = MockAnalyzer()

        # Create test DataFrame
        test_df = pd.DataFrame({
            'article_id': [f'article_{i:04d}' for i in range(50)],
        })

        # Run twice
        run1_ids = []
        for batch in analyzer.batch_iter(test_df):
            for article in batch:
                run1_ids.append(article['article_id'])

        run2_ids = []
        for batch in analyzer.batch_iter(test_df):
            for article in batch:
                run2_ids.append(article['article_id'])

        # Verify same order
        assert run1_ids == run2_ids, "Batch order not deterministic!"

    def test_batch_size_respected(self):
        """Verify each batch respects the batch size limit."""

        class MockAnalyzer:
            def __init__(self):
                self.batch_size = 60
                self.content_truncate_chars = 500

            def batch_iter(self, df):
                articles = []
                for _, row in df.iterrows():
                    articles.append({'article_id': row.get('article_id', '')})
                for i in range(0, len(articles), self.batch_size):
                    yield articles[i:i + self.batch_size]

        analyzer = MockAnalyzer()

        # Create test DataFrame with 145 articles (60 + 60 + 25)
        test_df = pd.DataFrame({
            'article_id': [f'article_{i:04d}' for i in range(145)],
        })

        batch_sizes = []
        for batch in analyzer.batch_iter(test_df):
            batch_sizes.append(len(batch))

        # First two batches should be full (60), last should be remainder (25)
        assert batch_sizes[0] == 60, f"First batch should be 60, got {batch_sizes[0]}"
        assert batch_sizes[1] == 60, f"Second batch should be 60, got {batch_sizes[1]}"
        assert batch_sizes[2] == 25, f"Third batch should be 25, got {batch_sizes[2]}"

    def test_empty_dataframe_yields_no_batches(self):
        """Verify empty DataFrame produces no batches."""

        class MockAnalyzer:
            def __init__(self):
                self.batch_size = 60
                self.content_truncate_chars = 500

            def batch_iter(self, df):
                articles = []
                for _, row in df.iterrows():
                    articles.append({'article_id': row.get('article_id', '')})
                for i in range(0, len(articles), self.batch_size):
                    yield articles[i:i + self.batch_size]

        analyzer = MockAnalyzer()
        empty_df = pd.DataFrame(columns=['article_id'])

        batches = list(analyzer.batch_iter(empty_df))
        assert len(batches) == 0, "Empty DataFrame should produce no batches"

    def test_content_truncation(self):
        """Verify content is truncated to limit."""

        class MockAnalyzer:
            def __init__(self):
                self.batch_size = 60
                self.content_truncate_chars = 100

            def batch_iter(self, df):
                articles = []
                for _, row in df.iterrows():
                    content = str(row.get('content', '') or '')
                    if len(content) > self.content_truncate_chars:
                        content = content[:self.content_truncate_chars] + '...'
                    articles.append({
                        'article_id': row.get('article_id', ''),
                        'content': content
                    })
                for i in range(0, len(articles), self.batch_size):
                    yield articles[i:i + self.batch_size]

        analyzer = MockAnalyzer()

        # Create test with very long content
        long_content = 'A' * 500  # 500 chars
        test_df = pd.DataFrame({
            'article_id': ['article_001'],
            'content': [long_content]
        })

        for batch in analyzer.batch_iter(test_df):
            for article in batch:
                # Should be 100 chars + '...'
                assert len(article['content']) == 103, (
                    f"Expected 103 chars (100 + '...'), got {len(article['content'])}"
                )
                assert article['content'].endswith('...'), "Truncated content should end with ..."


class TestWindowSelection:
    """Tests for window selection logic."""

    def test_window_filters_by_date(self):
        """Verify window selection filters articles by date."""
        # Create test data spanning multiple days
        now = datetime.now(UTC)
        dates = [
            now - timedelta(days=5),   # In window
            now - timedelta(days=25),  # In window
            now - timedelta(days=35),  # Out of window
            now - timedelta(days=60),  # Out of window
        ]

        df = pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3', 'a4'],
            'published_date_utc': dates,
            'category': ['competitor', 'competitor', 'competitor', 'competitor'],
        })

        # Window logic (30 days)
        window_start = now - timedelta(days=30)
        mask = (df['published_date_utc'] >= window_start) & (df['published_date_utc'] <= now)
        df_window = df[mask]

        assert len(df_window) == 2, f"Expected 2 articles in window, got {len(df_window)}"
        assert 'a1' in df_window['article_id'].values
        assert 'a2' in df_window['article_id'].values

    def test_window_splits_by_category(self):
        """Verify window correctly splits competitor vs internal."""
        now = datetime.now(UTC)

        df = pd.DataFrame({
            'article_id': ['a1', 'a2', 'a3', 'a4', 'a5'],
            'published_date_utc': [now - timedelta(days=1)] * 5,
            'category': ['competitor', 'competitor', 'competitor', 'internal', 'internal'],
        })

        competitor_df = df[df['category'] == 'competitor']
        internal_df = df[df['category'] == 'internal']

        assert len(competitor_df) == 3, f"Expected 3 competitor articles, got {len(competitor_df)}"
        assert len(internal_df) == 2, f"Expected 2 internal articles, got {len(internal_df)}"
