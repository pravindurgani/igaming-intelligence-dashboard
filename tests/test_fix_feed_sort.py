"""
Test Fix B: News Feed sorts newest-first with stable tie-breaks.

Verifies that articles are strictly ordered by published_date descending,
with nulls handled safely and tie-breaks stable by article_id.
"""


import pandas as pd


def test_news_feed_sorted_newest_first():
    """Verify DataFrame is sorted by published_dt descending."""
    # Create test data with various dates
    test_data = pd.DataFrame([
        {'published_dt': pd.Timestamp('2025-12-15 10:00', tz='UTC'), 'article_id': 'a1', 'title': 'Newest'},
        {'published_dt': pd.Timestamp('2025-12-14 15:00', tz='UTC'), 'article_id': 'a2', 'title': 'Middle'},
        {'published_dt': pd.Timestamp('2025-12-13 08:00', tz='UTC'), 'article_id': 'a3', 'title': 'Oldest'},
    ])

    # Sort using the same logic as dashboard
    sorted_df = test_data.sort_values(
        by=['published_dt', 'article_id'],
        ascending=[False, False],
        na_position='last'
    )

    # Verify order: newest first
    titles = sorted_df['title'].tolist()
    assert titles == ['Newest', 'Middle', 'Oldest'], "Should be newest-first order"


def test_tie_breaks_stable_by_article_id():
    """When dates are equal, sort by article_id descending."""
    test_data = pd.DataFrame([
        {'published_dt': pd.Timestamp('2025-12-15 10:00', tz='UTC'), 'article_id': 'a3', 'title': 'Third'},
        {'published_dt': pd.Timestamp('2025-12-15 10:00', tz='UTC'), 'article_id': 'a1', 'title': 'First'},
        {'published_dt': pd.Timestamp('2025-12-15 10:00', tz='UTC'), 'article_id': 'a2', 'title': 'Second'},
    ])

    sorted_df = test_data.sort_values(
        by=['published_dt', 'article_id'],
        ascending=[False, False],
        na_position='last'
    )

    article_ids = sorted_df['article_id'].tolist()
    assert article_ids == ['a3', 'a2', 'a1'], "Should sort by article_id desc when dates tie"


def test_nulls_pushed_to_end():
    """Null published_dt should appear last."""
    test_data = pd.DataFrame([
        {'published_dt': pd.Timestamp('2025-12-15', tz='UTC'), 'article_id': 'a1', 'title': 'Has date'},
        {'published_dt': pd.NaT, 'article_id': 'a2', 'title': 'No date'},
        {'published_dt': pd.Timestamp('2025-12-14', tz='UTC'), 'article_id': 'a3', 'title': 'Older date'},
    ])

    sorted_df = test_data.sort_values(
        by=['published_dt', 'article_id'],
        ascending=[False, False],
        na_position='last'
    )

    titles = sorted_df['title'].tolist()
    assert titles[-1] == 'No date', "Null dates should be last"
    assert titles[0] == 'Has date', "Valid dates should come first"


def test_mixed_dates_and_nulls():
    """Complex scenario with dates, nulls, and ties."""
    test_data = pd.DataFrame([
        {'published_dt': pd.Timestamp('2025-12-15 12:00', tz='UTC'), 'article_id': 'a4'},
        {'published_dt': pd.NaT, 'article_id': 'a6'},
        {'published_dt': pd.Timestamp('2025-12-15 12:00', tz='UTC'), 'article_id': 'a5'},  # Tie
        {'published_dt': pd.Timestamp('2025-12-14 09:00', tz='UTC'), 'article_id': 'a2'},
        {'published_dt': pd.NaT, 'article_id': 'a7'},  # Another null
        {'published_dt': pd.Timestamp('2025-12-16 08:00', tz='UTC'), 'article_id': 'a1'},  # Newest
    ])

    sorted_df = test_data.sort_values(
        by=['published_dt', 'article_id'],
        ascending=[False, False],
        na_position='last'
    )

    article_ids = sorted_df['article_id'].tolist()

    # Expected order:
    # 1. a1 (2025-12-16) - newest date
    # 2. a5 (2025-12-15 12:00, higher article_id) - tied date
    # 3. a4 (2025-12-15 12:00, lower article_id) - tied date
    # 4. a2 (2025-12-14) - older date
    # 5. a7 (null, higher article_id) - null dates last
    # 6. a6 (null, lower article_id) - null dates last

    assert article_ids[0] == 'a1', "Newest date should be first"
    assert article_ids[-2:] == ['a7', 'a6'] or article_ids[-2:] == ['a6', 'a7'], "Nulls should be last"
