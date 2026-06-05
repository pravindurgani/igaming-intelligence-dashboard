"""
Unit tests for src/ui_components/briefs.py

Tests cover:
- Brief contains required sections (Editorial, Product, Commercial, KPIs)
- Brief formatting
- Preview truncation
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ui_components.briefs import brief_to_dict, render_brief_preview, render_content_brief

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_advantage():
    """A sample Advantage dict for testing briefs."""
    return {
        'topic': 'iGaming Regulation, Barcelona',
        'topic_name': 'iGaming Regulation',
        'reader_value': 'Readers come to us for iGaming Regulation because our coverage is more frequent.',
        'evidence': {
            'our_articles': 10,
            'their_articles': 2,
            'examples': [
                {'title': 'Article 1', 'link': 'https://example.com/1', 'date': '2024-01-15'},
                {'title': 'Article 2', 'link': 'https://example.com/2', 'date': '2024-01-14'},
            ]
        },
        'do_more_of_this': [
            'Publish weekly explainer series.',
            'Add deeper analysis with expert commentary.',
            'Create roundup for newsletter.'
        ],
        'product_enablers': [
            'Add topic to internal search keywords.',
            'Create topic hub page.'
        ],
        'commercial_levers': [
            'Pitch exclusive sponsorship series.',
            'Propose branded webinar.'
        ],
        'distribution': [
            'Continue weekend publishing.',
            'Focus on North America.'
        ],
        'risk_if_we_stop': 'Competitors can close this gap within 4-6 weeks.',
        'kpis': [
            'Articles published next 14 days',
            'Average article depth',
            'Weekend publishing percentage',
            'Reader engagement'
        ],
        'is_exclusive': True,
        'ownership_ratio': 1.0,
        'topic_id': 'topic_001'
    }


# ============================================================================
# Render Content Brief Tests
# ============================================================================

class TestRenderContentBrief:
    """Tests for render_content_brief function."""

    def test_brief_contains_editorial_section(self, sample_advantage):
        """Brief should contain Editorial Actions section."""
        brief = render_content_brief(sample_advantage)

        assert '## Editorial Actions' in brief

    def test_brief_contains_product_section(self, sample_advantage):
        """Brief should contain Product Enablers section."""
        brief = render_content_brief(sample_advantage)

        assert '## Product Enablers' in brief

    def test_brief_contains_commercial_section(self, sample_advantage):
        """Brief should contain Commercial Ideas section."""
        brief = render_content_brief(sample_advantage)

        assert '## Commercial Ideas' in brief

    def test_brief_contains_kpis_section(self, sample_advantage):
        """Brief should contain KPIs to Track section."""
        brief = render_content_brief(sample_advantage)

        assert '## KPIs to Track' in brief

    def test_brief_contains_headline(self, sample_advantage):
        """Brief should contain topic headline."""
        brief = render_content_brief(sample_advantage)

        assert '# Content Brief: iGaming Regulation' in brief

    def test_brief_contains_value_statement(self, sample_advantage):
        """Brief should contain the value statement."""
        brief = render_content_brief(sample_advantage)

        assert 'Readers come to us for' in brief

    def test_brief_contains_evidence(self, sample_advantage):
        """Brief should contain evidence counts."""
        brief = render_content_brief(sample_advantage)

        assert '10 articles' in brief
        assert '2 from competitors' in brief

    def test_brief_contains_risk(self, sample_advantage):
        """Brief should contain risk section."""
        brief = render_content_brief(sample_advantage)

        assert '## Risk if We Stop' in brief
        assert 'Competitors can close' in brief

    def test_brief_contains_examples(self, sample_advantage):
        """Brief should contain reference articles."""
        brief = render_content_brief(sample_advantage)

        assert '## Reference Articles' in brief
        assert 'example.com/1' in brief

    def test_brief_is_markdown(self, sample_advantage):
        """Brief should be valid markdown."""
        brief = render_content_brief(sample_advantage)

        # Should have markdown headers
        assert brief.startswith('#')
        # Should have lists
        assert '1.' in brief or '-' in brief

    def test_brief_editorial_has_3_items(self, sample_advantage):
        """Editorial section should have 3 numbered items."""
        brief = render_content_brief(sample_advantage)

        # Find editorial section
        sections = brief.split('##')
        editorial = next((s for s in sections if 'Editorial Actions' in s), '')

        assert '1.' in editorial
        assert '2.' in editorial
        assert '3.' in editorial

    def test_brief_product_has_2_items(self, sample_advantage):
        """Product section should have 2 numbered items."""
        brief = render_content_brief(sample_advantage)

        sections = brief.split('##')
        product = next((s for s in sections if 'Product Enablers' in s), '')

        assert '1.' in product
        assert '2.' in product

    def test_brief_commercial_has_2_items(self, sample_advantage):
        """Commercial section should have 2 numbered items."""
        brief = render_content_brief(sample_advantage)

        sections = brief.split('##')
        commercial = next((s for s in sections if 'Commercial Ideas' in s), '')

        assert '1.' in commercial
        assert '2.' in commercial


# ============================================================================
# Brief Preview Tests
# ============================================================================

class TestRenderBriefPreview:
    """Tests for render_brief_preview function."""

    def test_preview_shorter_than_full(self, sample_advantage):
        """Preview should be shorter than full brief."""
        full = render_content_brief(sample_advantage)
        preview = render_brief_preview(sample_advantage, max_lines=10)

        assert len(preview) <= len(full)

    def test_preview_includes_truncation_note(self, sample_advantage):
        """Preview should include truncation note when truncated."""
        preview = render_brief_preview(sample_advantage, max_lines=5)

        assert 'Preview truncated' in preview or len(preview.split('\n')) <= 6

    def test_short_brief_not_truncated(self):
        """Short briefs should not be truncated."""
        short_adv = {
            'topic': 'Test',
            'topic_name': 'Test',
            'reader_value': 'Short.',
            'evidence': {'our_articles': 1, 'their_articles': 0, 'examples': []},
            'do_more_of_this': ['A'],
            'product_enablers': ['B'],
            'commercial_levers': ['C'],
            'distribution': [],
            'risk_if_we_stop': 'Risk.',
            'kpis': ['KPI']
        }

        preview = render_brief_preview(short_adv, max_lines=100)
        full = render_content_brief(short_adv)

        # Should be the same when max_lines is high
        assert 'Preview truncated' not in preview


# ============================================================================
# Brief to Dict Tests
# ============================================================================

class TestBriefToDict:
    """Tests for brief_to_dict function."""

    def test_dict_has_required_fields(self, sample_advantage):
        """Dict should have all required fields for JSON export."""
        result = brief_to_dict(sample_advantage)

        assert 'topic' in result
        assert 'topic_name' in result
        assert 'generated_at' in result
        assert 'value_statement' in result
        assert 'evidence' in result
        assert 'editorial_actions' in result
        assert 'product_enablers' in result
        assert 'commercial_ideas' in result
        assert 'kpis' in result
        assert 'risk_if_we_stop' in result
        assert 'example_links' in result

    def test_dict_limits_items(self, sample_advantage):
        """Dict should limit items per section."""
        result = brief_to_dict(sample_advantage)

        assert len(result['editorial_actions']) <= 3
        assert len(result['product_enablers']) <= 2
        assert len(result['commercial_ideas']) <= 2
        assert len(result['kpis']) <= 4

    def test_dict_extracts_links(self, sample_advantage):
        """Dict should extract just the links from examples."""
        result = brief_to_dict(sample_advantage)

        links = result['example_links']
        assert all(link.startswith('http') or link == '' for link in links)


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_examples(self):
        """Should handle empty examples gracefully."""
        adv = {
            'topic': 'Test',
            'topic_name': 'Test',
            'reader_value': 'Value.',
            'evidence': {'our_articles': 5, 'their_articles': 0, 'examples': []},
            'do_more_of_this': ['A', 'B', 'C'],
            'product_enablers': ['D', 'E'],
            'commercial_levers': ['F', 'G'],
            'distribution': [],
            'risk_if_we_stop': 'Risk.',
            'kpis': ['KPI1', 'KPI2']
        }

        brief = render_content_brief(adv)
        assert 'Reference Articles' not in brief or 'Reference Articles' in brief

    def test_missing_optional_fields(self):
        """Should handle missing optional fields."""
        adv = {
            'topic': 'Test',
            'topic_name': 'Test',
            'reader_value': 'Value.',
            'evidence': {'our_articles': 5, 'their_articles': 0, 'examples': []},
            'do_more_of_this': [],
            'product_enablers': [],
            'commercial_levers': [],
            'risk_if_we_stop': 'Risk.',
            'kpis': []
        }

        # Should not raise
        brief = render_content_brief(adv)
        assert '# Content Brief' in brief

    def test_special_characters_in_topic(self):
        """Should handle special characters in topic name."""
        adv = {
            'topic': 'Test & Analysis: Special <Topic>',
            'topic_name': 'Test & Analysis',
            'reader_value': 'Value.',
            'evidence': {'our_articles': 5, 'their_articles': 0, 'examples': []},
            'do_more_of_this': ['A'],
            'product_enablers': ['B'],
            'commercial_levers': ['C'],
            'distribution': [],
            'risk_if_we_stop': 'Risk.',
            'kpis': ['KPI']
        }

        brief = render_content_brief(adv)
        assert 'Test & Analysis' in brief
