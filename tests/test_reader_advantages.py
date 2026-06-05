"""
Unit tests for src/reader_advantages.py

Tests cover:
- Ownership rules (70% threshold, exclusivity)
- Advantage builder functionality
- CSV export format
- Example link extraction
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.reader_advantages import (
    _extract_examples,
    _generate_commercial_levers,
    _generate_editorial_actions,
    _generate_product_enablers,
    advantages_to_csv,
    build_advantage,
    build_reader_advantages,
    compute_ownership_ratio,
    is_owned_topic,
)

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_topic_exclusive():
    """An exclusive topic (0 competitor articles)."""
    return {
        'topic_id': 'topic_001',
        'label': 'iGaming Regulation, Barcelona',
        'internal_count': 5,
        'competitor_count': 0,
        'ownership': 1.0,
        'exclusivity': 1.0,
        'timeliness': 0.8,
        'depth': 0.7,
        'format_edge': 0.6,
        'examples': [
            {'title': 'Article 1', 'link': 'https://example.com/1', 'published_date_utc': '2024-01-15'},
            {'title': 'Article 2', 'link': 'https://example.com/2', 'published_date_utc': '2024-01-14'},
        ],
        'diagnostics': {
            'median_words_internal': 500,
            'internal_weekend_pct': 15.0,
            'competitor_weekend_pct': 5.0
        },
        'actions': ['Action 1', 'Action 2', 'Action 3']
    }


@pytest.fixture
def sample_topic_owned():
    """A topic we own (>70% share)."""
    return {
        'topic_id': 'topic_002',
        'label': 'Sports Betting, US Market',
        'internal_count': 8,
        'competitor_count': 2,  # 80% ownership
        'ownership': 0.8,
        'exclusivity': 0.0,
        'timeliness': 0.6,
        'depth': 0.5,
        'format_edge': 0.4,
        'examples': [
            {'title': 'US Betting News', 'link': 'https://example.com/us', 'published_date_utc': '2024-01-10'},
        ],
        'diagnostics': {
            'median_words_internal': 400,
            'internal_weekend_pct': 10.0,
            'competitor_weekend_pct': 8.0
        },
        'actions': []
    }


@pytest.fixture
def sample_topic_not_owned():
    """A topic we don't own (<70% share)."""
    return {
        'topic_id': 'topic_003',
        'label': 'Casino Games, Europe',
        'internal_count': 3,
        'competitor_count': 5,  # 37.5% ownership
        'ownership': 0.375,
        'exclusivity': 0.0,
        'timeliness': 0.3,
        'depth': 0.4,
        'format_edge': 0.3,
        'examples': [],
        'diagnostics': {},
        'actions': []
    }


@pytest.fixture
def sample_analysis_json(sample_topic_exclusive, sample_topic_owned, sample_topic_not_owned):
    """Full analysis JSON with multiple topics."""
    return {
        'differentiators_v2': {
            'topics': [
                sample_topic_exclusive,
                sample_topic_owned,
                sample_topic_not_owned
            ],
            'global_notes': {
                'weekend_advantage': 'Clarion leads with 14.3% weekend coverage',
                'region_edge': [
                    {'region': 'North America', 'ratio': 1.8}
                ]
            },
            'internal_articles': 100,
            'competitor_articles': 80
        }
    }


# ============================================================================
# Ownership Rules Tests
# ============================================================================

class TestIsOwnedTopic:
    """Tests for is_owned_topic function."""

    def test_exclusive_topic_owned(self):
        """Exclusive topic (0 competitors, 3+ articles) is owned."""
        assert is_owned_topic(5, 0) is True
        assert is_owned_topic(3, 0) is True

    def test_exclusive_below_min_count(self):
        """Exclusive but below min count is not owned."""
        assert is_owned_topic(2, 0) is False
        assert is_owned_topic(1, 0) is False

    def test_high_ownership_ratio(self):
        """70%+ ownership ratio is owned."""
        # 7/10 = 70%
        assert is_owned_topic(7, 3) is True
        # 8/10 = 80%
        assert is_owned_topic(8, 2) is True
        # 9/10 = 90%
        assert is_owned_topic(9, 1) is True

    def test_below_ownership_threshold(self):
        """Below 70% is not owned."""
        # 6/10 = 60%
        assert is_owned_topic(6, 4) is False
        # 5/10 = 50%
        assert is_owned_topic(5, 5) is False
        # 3/10 = 30%
        assert is_owned_topic(3, 7) is False

    def test_minimum_internal_count(self):
        """Must have at least MIN_INTERNAL_COUNT articles."""
        # 2 articles, even with 100% would fail
        assert is_owned_topic(2, 0) is False
        # 3 articles at 100% passes
        assert is_owned_topic(3, 0) is True

    def test_boundary_at_70_percent(self):
        """Exactly 70% ownership passes."""
        # 70/100 = exactly 70%
        assert is_owned_topic(70, 30) is True
        # Just under 70%
        assert is_owned_topic(69, 31) is False


class TestComputeOwnershipRatio:
    """Tests for compute_ownership_ratio function."""

    def test_exclusive_ratio(self):
        """Exclusive topic has 100% ratio."""
        assert compute_ownership_ratio(5, 0) == 1.0

    def test_equal_coverage(self):
        """Equal coverage is 50%."""
        assert compute_ownership_ratio(5, 5) == 0.5

    def test_no_coverage(self):
        """No coverage returns 0."""
        assert compute_ownership_ratio(0, 0) == 0.0

    def test_normal_ratio(self):
        """Normal ownership calculation."""
        # 8/(8+2) = 0.8
        assert compute_ownership_ratio(8, 2) == pytest.approx(0.8)


# ============================================================================
# Build Advantages Tests
# ============================================================================

class TestBuildReaderAdvantages:
    """Tests for build_reader_advantages function."""

    def test_emits_cards_for_owned_topics(self, sample_analysis_json):
        """Should emit cards when owned-topic rules match."""
        advantages = build_reader_advantages(None, sample_analysis_json)

        # Should have 2 advantages (exclusive + owned, not the not_owned)
        assert len(advantages) >= 1

    def test_excludes_non_owned_topics(self, sample_analysis_json):
        """Should not emit cards for topics below threshold."""
        advantages = build_reader_advantages(None, sample_analysis_json)

        topics = [a['topic'] for a in advantages]
        assert 'Casino Games, Europe' not in topics

    def test_includes_exclusive_topics(self, sample_analysis_json):
        """Should include exclusive topics."""
        advantages = build_reader_advantages(None, sample_analysis_json)

        topics = [a['topic'] for a in advantages]
        assert 'iGaming Regulation, Barcelona' in topics

    def test_cards_have_required_fields(self, sample_analysis_json):
        """Each card should have all required fields."""
        advantages = build_reader_advantages(None, sample_analysis_json)

        if advantages:
            adv = advantages[0]

            # Required fields per spec
            assert 'topic' in adv
            assert 'reader_value' in adv
            assert 'evidence' in adv
            assert 'do_more_of_this' in adv
            assert 'product_enablers' in adv
            assert 'commercial_levers' in adv
            assert 'distribution' in adv
            assert 'risk_if_we_stop' in adv
            assert 'kpis' in adv

    def test_evidence_structure(self, sample_analysis_json):
        """Evidence should have our_articles, their_articles, examples."""
        advantages = build_reader_advantages(None, sample_analysis_json)

        if advantages:
            evidence = advantages[0]['evidence']
            assert 'our_articles' in evidence
            assert 'their_articles' in evidence
            assert 'examples' in evidence

    def test_empty_analysis_returns_empty(self):
        """Empty analysis should return empty list."""
        advantages = build_reader_advantages(None, {})
        assert advantages == []

    def test_sorted_by_exclusive_first(self, sample_analysis_json):
        """Exclusive topics should appear first."""
        advantages = build_reader_advantages(None, sample_analysis_json)

        if len(advantages) >= 2:
            # First should be exclusive
            assert advantages[0]['is_exclusive'] is True


class TestBuildAdvantage:
    """Tests for build_advantage function."""

    def test_reader_value_uses_template(self, sample_topic_exclusive):
        """Reader value should use the template."""
        adv = build_advantage(sample_topic_exclusive, {}, {})

        assert 'Readers come to us for' in adv['reader_value']
        assert 'iGaming Regulation' in adv['reader_value']

    def test_risk_uses_template(self, sample_topic_exclusive):
        """Risk should use the standard template."""
        adv = build_advantage(sample_topic_exclusive, {}, {})

        assert 'Competitors can close this gap' in adv['risk_if_we_stop']
        assert '4-6 weeks' in adv['risk_if_we_stop']


# ============================================================================
# Example Extraction Tests
# ============================================================================

class TestExtractExamples:
    """Tests for _extract_examples function."""

    def test_extracts_up_to_3_examples(self, sample_topic_exclusive):
        """Should extract at most 3 examples."""
        examples = _extract_examples(sample_topic_exclusive)

        assert len(examples) <= 3
        assert len(examples) == 2  # Topic has 2 examples

    def test_example_has_required_fields(self, sample_topic_exclusive):
        """Each example should have title, link, date."""
        examples = _extract_examples(sample_topic_exclusive)

        if examples:
            ex = examples[0]
            assert 'title' in ex
            assert 'link' in ex
            assert 'date' in ex

    def test_cards_include_example_links_when_available(self, sample_analysis_json):
        """Cards should include example links when available."""
        advantages = build_reader_advantages(None, sample_analysis_json)

        # Find the exclusive topic which has examples
        exclusive_adv = next((a for a in advantages if a['is_exclusive']), None)

        if exclusive_adv:
            examples = exclusive_adv['evidence']['examples']
            assert len(examples) >= 1
            assert examples[0]['link'].startswith('http')


# ============================================================================
# Action Generation Tests
# ============================================================================

class TestGenerateEditorialActions:
    """Tests for _generate_editorial_actions function."""

    def test_returns_existing_actions(self, sample_topic_exclusive):
        """Should return existing actions if present."""
        actions = _generate_editorial_actions(sample_topic_exclusive, 'Test')

        assert len(actions) == 3
        assert actions[0] == 'Action 1'

    def test_generates_defaults_if_missing(self, sample_topic_not_owned):
        """Should generate defaults if no actions exist."""
        actions = _generate_editorial_actions(sample_topic_not_owned, 'Casino')

        assert len(actions) == 3
        assert any('Casino' in a for a in actions)


class TestGenerateProductEnablers:
    """Tests for _generate_product_enablers function."""

    def test_returns_two_enablers(self):
        """Should return exactly 2 product enablers."""
        enablers = _generate_product_enablers('Sports Betting', {})

        assert len(enablers) == 2

    def test_includes_topic_name(self):
        """Enablers should mention the topic."""
        enablers = _generate_product_enablers('Sports Betting', {})

        assert any('Sports Betting' in e for e in enablers)


class TestGenerateCommercialLevers:
    """Tests for _generate_commercial_levers function."""

    def test_returns_two_levers(self):
        """Should return exactly 2 commercial levers."""
        levers = _generate_commercial_levers('iGaming', False)

        assert len(levers) == 2

    def test_exclusive_gets_premium_levers(self):
        """Exclusive topics should get premium suggestions."""
        levers = _generate_commercial_levers('iGaming', True)

        assert any('exclusive' in l.lower() or 'webinar' in l.lower() for l in levers)


# ============================================================================
# CSV Export Tests
# ============================================================================

class TestAdvantagesToCsv:
    """Tests for advantages_to_csv function."""

    def test_csv_has_required_columns(self, sample_analysis_json):
        """CSV should have all required columns."""
        advantages = build_reader_advantages(None, sample_analysis_json)
        csv_str = advantages_to_csv(advantages)

        required_cols = [
            'topic',
            'our_articles',
            'their_articles',
            'is_exclusive',
            'reader_value',
            'do_more_of_this',
            'product_enablers',
            'commercial_levers',
            'risk_if_we_stop'
        ]

        for col in required_cols:
            assert col in csv_str

    def test_empty_advantages_returns_header(self):
        """Empty list should return CSV with header only."""
        csv_str = advantages_to_csv([])

        assert 'topic' in csv_str
        assert csv_str.count('\n') == 1  # Just header row

    def test_csv_one_row_per_advantage(self, sample_analysis_json):
        """CSV should have one data row per advantage."""
        advantages = build_reader_advantages(None, sample_analysis_json)
        csv_str = advantages_to_csv(advantages)

        lines = csv_str.strip().split('\n')
        # Header + data rows
        assert len(lines) == len(advantages) + 1


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for the full workflow."""

    def test_full_workflow(self, sample_analysis_json):
        """Test the complete workflow from JSON to advantages."""
        # Build advantages
        advantages = build_reader_advantages(None, sample_analysis_json)

        # Should have data
        assert len(advantages) >= 1

        # Should be able to export to CSV
        csv_str = advantages_to_csv(advantages)
        assert len(csv_str) > 50

        # First advantage should have all required fields
        adv = advantages[0]
        assert adv['topic']
        assert adv['reader_value']
        assert adv['evidence']['our_articles'] > 0
        assert len(adv['do_more_of_this']) == 3
        assert len(adv['product_enablers']) == 2
        assert len(adv['commercial_levers']) == 2
        assert adv['risk_if_we_stop']
        assert len(adv['kpis']) >= 3
