"""
Tests for analysis window alignment.
Verifies that analysis metadata correctly captures window totals
and that analyzed count equals window total (no cap loss).
"""

import json
import sys
from pathlib import Path

import pytest

# Add project root
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from paths import DAILY_ANALYSIS_JSON


class TestAnalysisWindowAlignment:
    """Test suite for window alignment and metadata consistency."""

    @pytest.fixture
    def analysis_json(self):
        """Load the daily analysis JSON if it exists."""
        if not DAILY_ANALYSIS_JSON.exists():
            pytest.skip("No analysis JSON found - run analysis.py first")

        with open(DAILY_ANALYSIS_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)

    def test_metadata_has_window_totals(self, analysis_json):
        """Verify analysis metadata includes window totals before any caps."""
        metadata = analysis_json.get('metadata', {})

        # Check required fields exist
        assert 'total_window_articles' in metadata, "Metadata missing total_window_articles"
        assert 'total_window_competitor' in metadata, "Metadata missing total_window_competitor"
        assert 'total_window_internal' in metadata, "Metadata missing total_window_internal"

        # Verify they are integers > 0
        assert isinstance(metadata['total_window_articles'], int), "total_window_articles must be int"
        assert metadata['total_window_articles'] >= 0, "total_window_articles must be >= 0"

    def test_window_arithmetic_correct(self, analysis_json):
        """Verify competitor + internal = total for window counts."""
        metadata = analysis_json.get('metadata', {})

        total = metadata.get('total_window_articles', 0)
        competitor = metadata.get('total_window_competitor', 0)
        internal = metadata.get('total_window_internal', 0)

        assert competitor + internal == total, (
            f"Window arithmetic mismatch: {competitor} + {internal} != {total}"
        )

    def test_analyzed_equals_window_total(self, analysis_json):
        """
        With batching, analyzed count must equal window total (no cap loss).
        This is the KEY test - if batching works, we analyze ALL articles.
        """
        metadata = analysis_json.get('metadata', {})

        window_total = metadata.get('total_window_articles', 0)
        analyzed_total = metadata.get('articles_analyzed', 0)

        # With batching, these should be equal (no loss)
        assert analyzed_total == window_total, (
            f"Analyzed ({analyzed_total}) != Window ({window_total}). "
            f"Batching should ensure no article loss!"
        )

    def test_batched_flag_present(self, analysis_json):
        """Verify that batching metadata is present."""
        metadata = analysis_json.get('metadata', {})

        assert 'batched' in metadata, "Metadata missing 'batched' flag"
        assert metadata['batched'] is True, "Batching should be enabled"
        assert 'batch_size_articles' in metadata, "Metadata missing batch_size_articles"

    def test_soft_cap_disabled(self, analysis_json):
        """Verify soft cap is disabled when batching is used."""
        metadata = analysis_json.get('metadata', {})

        # If batched, soft_capped should be False
        if metadata.get('batched', False):
            assert metadata.get('soft_capped', True) is False, (
                "soft_capped should be False when batching is enabled"
            )

    def test_window_dates_present(self, analysis_json):
        """Verify window start and end dates are recorded."""
        metadata = analysis_json.get('metadata', {})

        assert 'window_start_utc' in metadata, "Missing window_start_utc"
        assert 'window_end_utc' in metadata, "Missing window_end_utc"
        assert 'analysis_period_days' in metadata, "Missing analysis_period_days"

        # Verify period is reasonable
        period_days = metadata['analysis_period_days']
        assert 1 <= period_days <= 365, f"Period days ({period_days}) out of reasonable range"

    def test_analysis_date_present(self, analysis_json):
        """Verify analysis_date is in metadata."""
        metadata = analysis_json.get('metadata', {})

        assert 'analysis_date' in metadata, "Missing analysis_date"
        assert len(metadata['analysis_date']) >= 10, "analysis_date should be YYYY-MM-DD format"


class TestAnalysisContent:
    """Tests for analysis content structure."""

    @pytest.fixture
    def analysis_json(self):
        """Load the daily analysis JSON if it exists."""
        if not DAILY_ANALYSIS_JSON.exists():
            pytest.skip("No analysis JSON found - run analysis.py first")

        with open(DAILY_ANALYSIS_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)

    def test_has_executive_summary(self, analysis_json):
        """Verify executive summary is present."""
        assert 'executive_summary' in analysis_json, "Missing executive_summary"
        assert len(analysis_json['executive_summary']) > 0, "Executive summary should not be empty"

    def test_has_market_pulse(self, analysis_json):
        """Verify market_pulse array is present."""
        assert 'market_pulse' in analysis_json, "Missing market_pulse"
        assert isinstance(analysis_json['market_pulse'], list), "market_pulse should be a list"

    def test_has_strategic_gaps(self, analysis_json):
        """Verify strategic_gaps array is present."""
        assert 'strategic_gaps' in analysis_json, "Missing strategic_gaps"
        assert isinstance(analysis_json['strategic_gaps'], list), "strategic_gaps should be a list"

    def test_has_commercial_radar(self, analysis_json):
        """Verify commercial_radar section is present."""
        assert 'commercial_radar' in analysis_json, "Missing commercial_radar"
        radar = analysis_json['commercial_radar']
        assert 'potential_sponsors' in radar, "Missing potential_sponsors in commercial_radar"
        assert 'potential_speakers' in radar, "Missing potential_speakers in commercial_radar"
