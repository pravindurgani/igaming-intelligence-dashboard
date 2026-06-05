"""Fallback-path tests for ``src.gemini_ner_analysis``.

These tests prove that every dashboard insight degrades gracefully when no LLM
provider is configured (the common cold-start case on Streamlit Cloud) and when
the configured providers all fail. The dashboard must never crash or return
None for these helpers — it must surface a deterministic fallback string built
from the underlying data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src import gemini_ner_analysis as gna  # noqa: E402


@pytest.fixture(autouse=True)
def _force_llm_offline(monkeypatch):
    """Pretend no LLM provider is available and bypass disk cache.

    Without this, a real cache hit (or a real configured provider on the
    dev's machine) would mask the fallback path under test.
    """
    monkeypatch.setattr(gna.llm_client, 'is_available', lambda: False)
    monkeypatch.setattr(gna.llm_client, 'reinit', lambda: False)
    monkeypatch.setattr(gna.llm_client, 'generate', lambda *a, **kw: None)
    monkeypatch.setattr(gna, 'load_from_disk_cache', lambda *_a, **_kw: None)
    monkeypatch.setattr(gna, 'save_to_disk_cache', lambda *_a, **_kw: None)

    # The @st.cache_data decorator memoizes across tests in-process. Clearing
    # ensures one test's fallback string doesn't leak into the next.
    for name in (
        'get_geo_insight',
        'get_company_insight',
        'get_topic_insight',
        'get_regional_insight',
    ):
        fn = getattr(gna, name, None)
        if fn is not None and hasattr(fn, 'clear'):
            fn.clear()


# ---------------------------------------------------------------------------
# get_geo_insight
# ---------------------------------------------------------------------------

def test_geo_insight_fallback_names_top_gap_region():
    geo_data = json.dumps([
        {'entity': 'Brazil', 'competitor_pct': 30.0, 'internal_pct': 10.0},
        {'entity': 'Spain', 'competitor_pct': 25.0, 'internal_pct': 20.0},
    ])
    out = gna.get_geo_insight(geo_data, competitor_count=50, internal_count=15)
    assert isinstance(out, str)
    # Top gap is Brazil (20pp delta). Fallback should call it out by name.
    assert 'Brazil' in out
    assert '20' in out  # the delta percentage


def test_geo_insight_empty_data_returns_empty_string():
    out = gna.get_geo_insight('[]', competitor_count=0, internal_count=0)
    assert out == ''  # Documented fallback: empty string when no gaps.


def test_geo_insight_malformed_json_does_not_crash():
    out = gna.get_geo_insight('not json at all', 1, 1)
    assert isinstance(out, str)  # parse failure must still return a string.


# ---------------------------------------------------------------------------
# get_company_insight
# ---------------------------------------------------------------------------

def test_company_insight_fallback_lists_top_three():
    companies = json.dumps([
        {'name': 'Evolution', 'count': 50},
        {'name': 'DraftKings', 'count': 40},
        {'name': 'Flutter', 'count': 35},
        {'name': 'Bet365', 'count': 20},
    ])
    out = gna.get_company_insight(companies)
    assert 'Evolution' in out
    assert 'DraftKings' in out
    assert 'Flutter' in out
    # 4th name should NOT leak through — fallback caps at 3.
    assert 'Bet365' not in out


def test_company_insight_handles_tuple_shape():
    """Older callers passed [(name, count), ...] instead of dicts."""
    companies = json.dumps([['Evolution', 50], ['DraftKings', 40]])
    out = gna.get_company_insight(companies)
    assert 'Evolution' in out


# ---------------------------------------------------------------------------
# get_topic_insight
# ---------------------------------------------------------------------------

def test_topic_insight_fallback_names_top_gap_topic():
    topics = json.dumps([
        {'entity': 'Sports Betting', 'competitor_pct': 40, 'internal_pct': 10},
        {'entity': 'Casino', 'competitor_pct': 20, 'internal_pct': 50},
    ])
    out = gna.get_topic_insight(topics)
    assert 'Sports Betting' in out
    assert '40' in out  # external pct
    assert '10' in out  # internal pct


# ---------------------------------------------------------------------------
# get_regional_insight
# ---------------------------------------------------------------------------

def test_regional_insight_names_top_external_region():
    comp = json.dumps({'LATAM': 80, 'EMEA': 30, 'APAC': 20})
    intern = json.dumps({'EMEA': 50, 'NA': 40})
    out = gna.get_regional_insight(comp, intern)
    assert 'LATAM' in out
    assert '80' in out


def test_regional_insight_handles_empty_competitor():
    out = gna.get_regional_insight('{}', '{"EMEA": 5}')
    assert isinstance(out, str)
    assert out == ''  # no competitor regions => no insight to surface.


# ---------------------------------------------------------------------------
# generate_battleground_summary
# ---------------------------------------------------------------------------

def test_battleground_summary_returns_documented_fallback_string():
    out = gna.generate_battleground_summary(
        geo_json='[]',
        company_json='[]',
        competitor_count=10,
        internal_count=5,
    )
    # Exact contract used by the dashboard to decide whether to show the
    # block — if this string changes, callers must update too.
    assert out == 'LLM not available for summary generation.'
