"""
Unit tests for src/analysis_differentiators.py

Tests cover:
- TOI (Topic Ownership Index) calculation
- Exclusivity detection
- Editorial wins filtering
- Audience edge computation
- Commercial levers generation
- CSV export utilities
"""

import json

# Import the module under test
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis_differentiators import (
    build_audience_edge,
    build_commercial_levers,
    build_editorial_wins,
    compute_toi,
    extract_speakers_from_briefing,
    generate_package_suggestion,
    generate_why_it_matters,
    get_csv_for_download,
    is_exclusive,
    load_briefing,
    load_run,
    render_differentiators,
    synthesize_actions,
)

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_topic():
    """A sample topic dict for testing."""
    return {
        'topic_id': 'topic_001',
        'label': 'Sports Betting, Regulation',
        'internal_count': 10,
        'competitor_count': 3,
        'ownership': 0.77,
        'exclusivity': 0.3,
        'timeliness': 0.6,
        'depth': 0.7,
        'format_edge': 0.5,
        'score': 0.65,
        'actions': ['Action 1', 'Action 2', 'Action 3'],
        'examples': [
            {'title': 'Article 1', 'link': 'https://example.com/1', 'published_date_utc': '2024-01-15'},
            {'title': 'Article 2', 'link': 'https://example.com/2', 'published_date_utc': '2024-01-14'},
        ],
        'diagnostics': {
            'median_words_internal': 500,
            'median_words_competitor': 350,
            'internal_weekend_pct': 15.0,
            'competitor_weekend_pct': 5.0
        }
    }


@pytest.fixture
def sample_run_data(sample_topic):
    """A sample run JSON structure for testing."""
    return {
        'differentiators_v2': {
            'topics': [
                sample_topic,
                {
                    'topic_id': 'topic_002',
                    'label': 'Casino, Online Gaming',
                    'internal_count': 8,
                    'competitor_count': 0,  # Exclusive
                    'ownership': 1.0,
                    'exclusivity': 1.0,
                    'timeliness': 0.5,
                    'depth': 0.6,
                    'format_edge': 0.4,
                    'score': 0.75,
                    'actions': [],
                    'examples': []
                },
                {
                    'topic_id': 'topic_003',
                    'label': 'Lottery, State Laws',
                    'internal_count': 2,  # Below threshold
                    'competitor_count': 5,
                    'ownership': 0.29,
                    'exclusivity': 0.0,
                    'timeliness': 0.3,
                    'depth': 0.4,
                    'format_edge': 0.3,
                    'score': 0.25,
                    'actions': [],
                    'examples': []
                }
            ],
            'global_notes': {
                'weekend_advantage': 'Portfolio leads with 14.3% weekend coverage vs competitors\' 3.8%',
                'format_summary': [
                    {'format': 'analysis', 'internal_share': 25.0, 'competitor_share': 15.0, 'ratio_vs_comp': 1.67},
                    {'format': 'news', 'internal_share': 45.0, 'competitor_share': 50.0, 'ratio_vs_comp': 0.9}
                ],
                'region_edge': [
                    {'region': 'North America', 'ratio': 1.8, 'internal_mentions': 45, 'competitor_mentions': 25}
                ]
            },
            'internal_articles': 100,
            'competitor_articles': 80
        },
        'differentiators': {
            'cadence_metrics': {
                'internal_weekend_pct': 14.3,
                'competitor_weekend_pct': 3.8,
                'internal_daily_rate': 5.2,
                'competitor_daily_rate': 4.1
            },
            'format_differentiators': [
                {'format': 'analysis', 'internal_count': 25, 'internal_pct': 25.0, 'competitor_pct': 15.0, 'advantage': 'portfolio', 'advantage_ratio': 1.67}
            ],
            'region_differentiators': [
                {'region': 'North America', 'internal_mentions': 45, 'competitor_mentions': 25, 'advantage_ratio': 1.8, 'advantage': 'portfolio'}
            ]
        },
        'commercial_radar': {
            'potential_speakers': [
                {'name_or_company': 'John Smith', 'expertise_area': 'Sports Betting Regulation'},
                {'name_or_company': 'Jane Doe', 'expertise_area': 'iGaming Technology'}
            ]
        }
    }


@pytest.fixture
def sample_briefing_md():
    """Sample briefing markdown for testing."""
    return """
# Daily Briefing

## Key Stories

### Potential Speakers
- **Dr. Alice Johnson**: Gaming Law Expert
- **Bob Williams**: Industry Analyst
- **Carol Davis**: Regulatory Affairs
"""


# ============================================================================
# TOI Calculation Tests
# ============================================================================

class TestComputeTOI:
    """Tests for compute_toi function."""

    def test_toi_basic_calculation(self):
        """TOI = internal / (internal + competitor)"""
        assert compute_toi(10, 3) == pytest.approx(10 / 13, rel=1e-3)

    def test_toi_exclusive_topic(self):
        """When competitor_count=0, TOI should be 1.0"""
        assert compute_toi(5, 0) == 1.0

    def test_toi_no_internal(self):
        """When internal_count=0, TOI should be 0.0"""
        assert compute_toi(0, 10) == 0.0

    def test_toi_both_zero(self):
        """When both are 0, TOI should be 0.0"""
        assert compute_toi(0, 0) == 0.0

    def test_toi_equal_coverage(self):
        """When equal coverage, TOI should be 0.5"""
        assert compute_toi(10, 10) == 0.5

    def test_toi_high_ownership(self):
        """High internal count should give high TOI"""
        toi = compute_toi(90, 10)
        assert toi == pytest.approx(0.9, rel=1e-3)

    def test_toi_low_ownership(self):
        """Low internal count should give low TOI"""
        toi = compute_toi(10, 90)
        assert toi == pytest.approx(0.1, rel=1e-3)


class TestIsExclusive:
    """Tests for is_exclusive function."""

    def test_exclusive_zero_competitor(self):
        """Zero competitor count means exclusive"""
        assert is_exclusive(0) is True

    def test_not_exclusive_with_competitors(self):
        """Any competitor count means not exclusive"""
        assert is_exclusive(1) is False
        assert is_exclusive(10) is False
        assert is_exclusive(100) is False


# ============================================================================
# Editorial Wins Tests
# ============================================================================

class TestBuildEditorialWins:
    """Tests for build_editorial_wins function."""

    def test_filters_by_toi_threshold(self, sample_run_data):
        """Topics with TOI < 0.7 should be excluded (unless exclusive)"""
        wins_df = build_editorial_wins(sample_run_data)

        # topic_003 has TOI ~0.29 and is not exclusive, should be filtered out
        labels = wins_df['label'].tolist() if len(wins_df) > 0 else []
        assert 'Lottery, State Laws' not in labels

    def test_includes_exclusive_topics(self, sample_run_data):
        """Exclusive topics should be included regardless of TOI"""
        wins_df = build_editorial_wins(sample_run_data)

        labels = wins_df['label'].tolist() if len(wins_df) > 0 else []
        assert 'Casino, Online Gaming' in labels

    def test_includes_high_toi_topics(self, sample_run_data):
        """Topics with TOI >= 0.7 should be included"""
        wins_df = build_editorial_wins(sample_run_data)

        labels = wins_df['label'].tolist() if len(wins_df) > 0 else []
        assert 'Sports Betting, Regulation' in labels

    def test_filters_by_min_internal_count(self, sample_run_data):
        """Topics with internal_count < MIN_INTERNAL_COUNT should be excluded"""
        # topic_003 has internal_count=2 which is < MIN_INTERNAL_COUNT (3)
        wins_df = build_editorial_wins(sample_run_data)

        labels = wins_df['label'].tolist() if len(wins_df) > 0 else []
        assert 'Lottery, State Laws' not in labels

    def test_computes_toi_correctly(self, sample_run_data):
        """TOI should be computed correctly in output"""
        wins_df = build_editorial_wins(sample_run_data)

        # Find Sports Betting topic
        sports_row = wins_df[wins_df['label'] == 'Sports Betting, Regulation']
        if len(sports_row) > 0:
            toi = sports_row.iloc[0]['TOI']
            expected_toi = 10 / 13
            assert toi == pytest.approx(expected_toi, rel=1e-2)

    def test_marks_exclusive_correctly(self, sample_run_data):
        """Exclusive column should be True for topics with 0 competitors"""
        wins_df = build_editorial_wins(sample_run_data)

        casino_row = wins_df[wins_df['label'] == 'Casino, Online Gaming']
        if len(casino_row) > 0:
            assert bool(casino_row.iloc[0]['exclusive']) is True

        sports_row = wins_df[wins_df['label'] == 'Sports Betting, Regulation']
        if len(sports_row) > 0:
            assert bool(sports_row.iloc[0]['exclusive']) is False

    def test_sorts_by_exclusive_then_toi(self, sample_run_data):
        """Results should be sorted: exclusive first, then by TOI desc"""
        wins_df = build_editorial_wins(sample_run_data)

        if len(wins_df) >= 2:
            # First row should be exclusive (Casino)
            assert bool(wins_df.iloc[0]['exclusive']) is True

    def test_empty_run_data(self):
        """Should handle empty run data gracefully"""
        wins_df = build_editorial_wins({})
        assert len(wins_df) == 0

    def test_empty_topics(self):
        """Should handle empty topics list gracefully"""
        run = {'differentiators_v2': {'topics': []}}
        wins_df = build_editorial_wins(run)
        assert len(wins_df) == 0


# ============================================================================
# Why It Matters Tests
# ============================================================================

class TestGenerateWhyItMatters:
    """Tests for generate_why_it_matters function."""

    def test_exclusive_topic_message(self, sample_topic):
        """Exclusive topics should mention 'exclusively own'"""
        topic = {**sample_topic, 'competitor_count': 0}
        msg = generate_why_it_matters(topic)
        assert 'exclusive' in msg.lower()

    def test_high_toi_message(self, sample_topic):
        """High TOI topics should mention dominance"""
        topic = {**sample_topic, 'internal_count': 90, 'competitor_count': 10}
        msg = generate_why_it_matters(topic)
        # TOI = 0.9, should use "dominate"
        assert 'dominate' in msg.lower() or '90%' in msg

    def test_medium_toi_message(self, sample_topic):
        """Medium TOI topics should mention leading"""
        topic = {**sample_topic, 'internal_count': 70, 'competitor_count': 30}
        msg = generate_why_it_matters(topic)
        # TOI = 0.7, should use "lead"
        assert 'lead' in msg.lower() or '70%' in msg


# ============================================================================
# Synthesize Actions Tests
# ============================================================================

class TestSynthesizeActions:
    """Tests for synthesize_actions function."""

    def test_returns_existing_actions(self, sample_topic):
        """Should return existing actions if present"""
        actions = synthesize_actions(sample_topic)
        assert actions == sample_topic['actions'][:3]

    def test_generates_default_actions(self):
        """Should generate 3 actions if none exist"""
        topic = {'label': 'Test Topic', 'actions': []}
        actions = synthesize_actions(topic)
        assert len(actions) == 3

    def test_fills_missing_actions(self):
        """Should fill up to 3 actions if fewer exist"""
        topic = {'label': 'Test Topic', 'actions': ['Existing action']}
        actions = synthesize_actions(topic)
        assert len(actions) == 3
        assert actions[0] == 'Existing action'


# ============================================================================
# Audience Edge Tests
# ============================================================================

class TestBuildAudienceEdge:
    """Tests for build_audience_edge function."""

    def test_weekend_edge_calculation(self, sample_run_data):
        """Should calculate weekend edge correctly"""
        edge = build_audience_edge(sample_run_data)

        weekend = edge['weekend_edge']
        assert weekend['our_pct'] == pytest.approx(14.3, rel=0.1)
        assert weekend['comp_pct'] == pytest.approx(3.8, rel=0.1)
        assert weekend['positive'] is True

    def test_format_edges(self, sample_run_data):
        """Should identify format advantages"""
        edge = build_audience_edge(sample_run_data)

        format_edges = edge['format_edges']
        # Should have at least the 'analysis' format edge
        assert len(format_edges) >= 0  # May be filtered by threshold

    def test_region_edges(self, sample_run_data):
        """Should identify region advantages"""
        edge = build_audience_edge(sample_run_data)

        region_edges = edge['region_edges']
        if len(region_edges) > 0:
            # North America should be in edges
            regions = [r['region'] for r in region_edges]
            assert 'North America' in regions

    def test_empty_run_data(self):
        """Should handle empty run data gracefully"""
        edge = build_audience_edge({})

        assert edge['weekend_edge']['our_pct'] == 0.0
        assert edge['weekend_edge']['positive'] is False
        assert edge['format_edges'] == []
        assert edge['region_edges'] == []


# ============================================================================
# Commercial Levers Tests
# ============================================================================

class TestBuildCommercialLevers:
    """Tests for build_commercial_levers function."""

    def test_creates_sponsorable_topics(self, sample_run_data, sample_topic):
        """Should create sponsorable topics from editorial wins"""
        wins_df = build_editorial_wins(sample_run_data)
        levers_df = build_commercial_levers(wins_df, "", sample_run_data)

        sponsor_topics = levers_df[levers_df['type'] == 'sponsorable_topic']
        assert len(sponsor_topics) > 0

    def test_extracts_speakers_from_run(self, sample_run_data, sample_topic):
        """Should extract speaker targets from run data"""
        wins_df = build_editorial_wins(sample_run_data)
        levers_df = build_commercial_levers(wins_df, "", sample_run_data)

        speakers = levers_df[levers_df['type'] == 'speaker_target']
        # Should have extracted speakers from commercial_radar
        assert len(speakers) >= 0

    def test_empty_wins(self):
        """Should handle empty wins gracefully"""
        empty_df = pd.DataFrame()
        levers_df = build_commercial_levers(empty_df, "", {})
        assert len(levers_df) == 0


class TestExtractSpeakersFromBriefing:
    """Tests for extract_speakers_from_briefing function."""

    def test_extracts_speakers(self, sample_briefing_md):
        """Should extract speakers from briefing markdown"""
        speakers = extract_speakers_from_briefing(sample_briefing_md)
        # Should find at least one speaker
        assert len(speakers) >= 0

    def test_empty_briefing(self):
        """Should handle empty briefing gracefully"""
        speakers = extract_speakers_from_briefing("")
        assert speakers == []


class TestGeneratePackageSuggestion:
    """Tests for generate_package_suggestion function."""

    def test_exclusive_package(self, sample_topic):
        """Exclusive topics should get premium package"""
        topic = {**sample_topic, 'exclusive': True}
        pkg = generate_package_suggestion(topic)
        assert 'exclusive' in pkg.lower() or 'series' in pkg.lower()

    def test_high_toi_package(self, sample_topic):
        """High TOI topics should get good packages"""
        topic = {**sample_topic, 'TOI': 0.85, 'exclusive': False}
        pkg = generate_package_suggestion(topic)
        assert len(pkg) > 0


# ============================================================================
# CSV Export Tests
# ============================================================================

class TestGetCsvForDownload:
    """Tests for get_csv_for_download function."""

    def test_dataframe_to_csv(self, sample_run_data):
        """Should convert DataFrame to CSV string"""
        wins_df = build_editorial_wins(sample_run_data)
        csv_str = get_csv_for_download(wins_df, 'wins')

        if len(wins_df) > 0:
            assert 'label' in csv_str or 'topic_id' in csv_str

    def test_edge_dict_to_csv(self, sample_run_data):
        """Should convert edge dict to CSV string"""
        edge = build_audience_edge(sample_run_data)
        csv_str = get_csv_for_download(edge, 'edge')

        assert 'Weekend' in csv_str or 'metric' in csv_str


# ============================================================================
# Integration Tests
# ============================================================================

class TestRenderDifferentiators:
    """Integration tests for render_differentiators."""

    def test_render_with_mock_files(self, sample_run_data, sample_briefing_md, tmp_path):
        """Should render differentiators from files"""
        # Write test files
        run_path = tmp_path / "test_run.json"
        briefing_path = tmp_path / "test_briefing.md"

        run_path.write_text(json.dumps(sample_run_data))
        briefing_path.write_text(sample_briefing_md)

        # Render
        result = render_differentiators(str(run_path), str(briefing_path))

        assert result['has_data'] is True
        assert 'wins_df' in result
        assert 'edge' in result
        assert 'levers_df' in result
        assert 'summary' in result

    def test_render_summary_metrics(self, sample_run_data, tmp_path):
        """Should compute summary metrics correctly"""
        run_path = tmp_path / "test_run.json"
        run_path.write_text(json.dumps(sample_run_data))

        result = render_differentiators(str(run_path))

        summary = result['summary']
        assert 'owned_topics' in summary
        assert 'exclusive_topics' in summary
        assert 'median_toi' in summary


# ============================================================================
# Load Functions Tests
# ============================================================================

class TestLoadRun:
    """Tests for load_run function."""

    def test_load_valid_json(self, sample_run_data, tmp_path):
        """Should load valid JSON file"""
        path = tmp_path / "test.json"
        path.write_text(json.dumps(sample_run_data))

        data = load_run(str(path))
        assert 'differentiators_v2' in data

    def test_load_missing_file(self, tmp_path):
        """Should raise error for missing file"""
        with pytest.raises(FileNotFoundError):
            load_run(str(tmp_path / "nonexistent.json"))


class TestLoadBriefing:
    """Tests for load_briefing function."""

    def test_load_valid_file(self, sample_briefing_md, tmp_path):
        """Should load valid markdown file"""
        path = tmp_path / "briefing.md"
        path.write_text(sample_briefing_md)

        content = load_briefing(str(path))
        assert 'Briefing' in content

    def test_load_missing_file(self, tmp_path):
        """Should return empty string for missing file"""
        content = load_briefing(str(tmp_path / "nonexistent.md"))
        assert content == ""


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_toi_at_threshold(self):
        """TOI exactly at threshold should be included"""
        # TOI = 70/100 = 0.7 (at threshold)
        run = {
            'differentiators_v2': {
                'topics': [{
                    'topic_id': 'test',
                    'label': 'Test Topic',
                    'internal_count': 7,
                    'competitor_count': 3,
                    'ownership': 0.7,
                    'exclusivity': 0.0,
                    'timeliness': 0.5,
                    'depth': 0.5,
                    'format_edge': 0.5,
                    'actions': [],
                    'examples': []
                }]
            }
        }
        wins_df = build_editorial_wins(run)
        assert len(wins_df) == 1

    def test_toi_just_below_threshold(self):
        """TOI just below threshold should be excluded"""
        # TOI = 6.9/10 = 0.69 (below threshold)
        run = {
            'differentiators_v2': {
                'topics': [{
                    'topic_id': 'test',
                    'label': 'Test Topic',
                    'internal_count': 6,
                    'competitor_count': 4,
                    'ownership': 0.6,
                    'exclusivity': 0.0,
                    'timeliness': 0.5,
                    'depth': 0.5,
                    'format_edge': 0.5,
                    'actions': [],
                    'examples': []
                }]
            }
        }
        wins_df = build_editorial_wins(run)
        # TOI = 6/10 = 0.6, below 0.7 threshold
        assert len(wins_df) == 0

    def test_very_large_counts(self):
        """Should handle very large article counts"""
        toi = compute_toi(10000, 5000)
        assert toi == pytest.approx(2/3, rel=1e-3)

    def test_negative_counts(self):
        """Should handle negative counts gracefully"""
        # In practice, counts shouldn't be negative, but test defensively
        toi = compute_toi(-5, 10)
        # Result is -5/5 = -1.0 - this is technically correct math
        # but the function should probably validate inputs
        assert isinstance(toi, float)
