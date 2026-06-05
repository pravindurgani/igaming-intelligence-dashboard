#!/usr/bin/env python3
"""
Test suite for Clarion strengths calculation.
Uses pytest assertions to validate get_clarion_strengths function.
"""

import sys
from pathlib import Path

import pytest

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.metrics import get_clarion_strengths


def test_strengths_returns_correct_length():
    """Test that get_clarion_strengths returns at most top_n items."""
    competitor_pct = {
        'Sports Betting': 15.3,
        'Mobile Gaming': 8.75,
        'Regulation': 18.5,
        'Technology': 12.0,
        'Esports': 5.5,
    }

    clarion_pct = {
        'Sports Betting': 14.1,  # Gap (competitor leads)
        'Mobile Gaming': 14.5,   # Strength (Clarion leads by 5.75)
        'Regulation': 12.3,      # Gap (competitor leads)
        'Technology': 16.25,     # Strength (Clarion leads by 4.25)
        'Esports': 9.75,         # Strength (Clarion leads by 4.25)
    }

    # Request top 3, should get 3 (there are 3 strengths)
    strengths = get_clarion_strengths(competitor_pct, clarion_pct, top_n=3)
    assert len(strengths) == 3, f"Expected 3 strengths, got {len(strengths)}"

    # Request top 10, should get only 3 (max available)
    strengths = get_clarion_strengths(competitor_pct, clarion_pct, top_n=10)
    assert len(strengths) == 3, f"Expected 3 strengths (max available), got {len(strengths)}"

    # Request top 1, should get 1
    strengths = get_clarion_strengths(competitor_pct, clarion_pct, top_n=1)
    assert len(strengths) == 1, f"Expected 1 strength, got {len(strengths)}"


def test_strengths_all_have_positive_gap():
    """Test that all returned strengths have gap_pct > 0."""
    competitor_pct = {
        'Mobile Gaming': 8.75,
        'Technology': 12.0,
        'Esports': 5.5,
        'Regulation': 18.5,
    }

    clarion_pct = {
        'Mobile Gaming': 14.5,   # Strength (gap = 5.75)
        'Technology': 16.25,     # Strength (gap = 4.25)
        'Esports': 9.75,         # Strength (gap = 4.25)
        'Regulation': 12.3,      # Gap (negative, should be excluded)
    }

    strengths = get_clarion_strengths(competitor_pct, clarion_pct, top_n=10)

    for strength in strengths:
        gap_pct = strength['gap_pct']
        assert gap_pct > 0, \
            f"Strength '{strength['entity']}' has non-positive gap: {gap_pct}"


def test_strengths_clarion_exceeds_competitor():
    """Test that for all strengths, clarion_pct > competitor_pct."""
    competitor_pct = {
        'Mobile Gaming': 8.75,
        'Technology': 12.0,
        'Responsible Gaming': 6.5,
        'Sports Betting': 15.3,
    }

    clarion_pct = {
        'Mobile Gaming': 14.5,         # Clarion leads
        'Technology': 16.25,           # Clarion leads
        'Responsible Gaming': 11.0,    # Clarion leads
        'Sports Betting': 14.1,        # Competitor leads (should be excluded)
    }

    strengths = get_clarion_strengths(competitor_pct, clarion_pct, top_n=10)

    for strength in strengths:
        entity = strength['entity']
        clarion = strength['clarion_pct']
        competitor = strength['competitor_pct']

        assert clarion > competitor, \
            f"Strength '{entity}' has clarion ({clarion}) <= competitor ({competitor})"


def test_strengths_sorted_by_gap_descending():
    """Test that strengths are sorted by gap_pct in descending order."""
    competitor_pct = {
        'Mobile Gaming': 8.75,
        'Technology': 12.0,
        'Esports': 5.5,
        'Virtual Reality': 4.25,
    }

    clarion_pct = {
        'Mobile Gaming': 14.5,      # Gap = 5.75 (largest)
        'Technology': 16.25,        # Gap = 4.25
        'Esports': 9.75,            # Gap = 4.25
        'Virtual Reality': 7.5,     # Gap = 3.25 (smallest)
    }

    strengths = get_clarion_strengths(competitor_pct, clarion_pct, top_n=10)

    # Verify sorted descending
    for i in range(len(strengths) - 1):
        current_gap = strengths[i]['gap_pct']
        next_gap = strengths[i + 1]['gap_pct']

        assert current_gap >= next_gap, \
            f"Strengths not sorted: {strengths[i]['entity']} ({current_gap}) < {strengths[i + 1]['entity']} ({next_gap})"


def test_strengths_handles_clarion_only_entities():
    """Test that entities only in Clarion (not in competitors) are included as strengths."""
    competitor_pct = {
        'Sports Betting': 15.3,
    }

    clarion_pct = {
        'Sports Betting': 14.1,      # Gap (excluded)
        'Payment Systems': 10.5,     # Clarion only (should be included as strength)
    }

    strengths = get_clarion_strengths(competitor_pct, clarion_pct, top_n=10)

    assert len(strengths) == 1, f"Expected 1 strength (Payment Systems), got {len(strengths)}"
    assert strengths[0]['entity'] == 'Payment Systems'
    assert strengths[0]['clarion_pct'] == 10.5
    assert strengths[0]['competitor_pct'] == 0.0
    assert strengths[0]['gap_pct'] == 10.5


def test_strengths_excludes_competitor_only_entities():
    """Test that entities only in competitors (not in Clarion) are excluded."""
    competitor_pct = {
        'Sports Betting': 15.3,
        'Cryptocurrency': 7.8,     # Competitor only
    }

    clarion_pct = {
        'Sports Betting': 14.1,
    }

    strengths = get_clarion_strengths(competitor_pct, clarion_pct, top_n=10)

    # Cryptocurrency should not appear (Clarion has 0%, gap would be negative)
    entity_names = [s['entity'] for s in strengths]
    assert 'Cryptocurrency' not in entity_names, \
        "Competitor-only entities should not appear in strengths"


def test_strengths_realistic_scenario():
    """Test with realistic iGaming topic data."""
    competitor_pct = {
        'Regulation & Compliance': 18.5,
        'Tax Policy': 14.2,
        'M&A Activity': 11.7,
        'Sports Betting': 15.3,
        'Mobile Gaming': 8.75,
        'Responsible Gaming': 6.5,
        'Technology & Innovation': 12.0,
        'Esports': 5.5,
    }

    clarion_pct = {
        'Regulation & Compliance': 12.3,
        'Tax Policy': 9.8,
        'M&A Activity': 8.5,
        'Sports Betting': 14.1,
        'Mobile Gaming': 14.5,             # Strength
        'Responsible Gaming': 11.0,        # Strength
        'Technology & Innovation': 16.25,  # Strength
        'Esports': 9.75,                   # Strength
    }

    strengths = get_clarion_strengths(competitor_pct, clarion_pct, top_n=5)

    # Should have 4 strengths (Mobile, Responsible, Technology, Esports)
    assert len(strengths) == 4, f"Expected 4 strengths, got {len(strengths)}"

    # Top strength should be Mobile Gaming (5.75pp gap)
    assert strengths[0]['entity'] == 'Mobile Gaming'
    assert abs(strengths[0]['gap_pct'] - 5.75) < 0.01

    # All should have positive gaps
    for strength in strengths:
        assert strength['gap_pct'] > 0
        assert strength['clarion_pct'] > strength['competitor_pct']


if __name__ == "__main__":
    # Run tests with pytest when executed directly
    pytest.main([__file__, "-v"])
