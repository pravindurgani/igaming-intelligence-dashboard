#!/usr/bin/env python3
"""
Pure functions for competitive intelligence metrics calculations.
Extracted from dashboard for testability and reusability.
"""



def get_clarion_strengths(
    competitor_pct: dict[str, float],
    clarion_pct: dict[str, float],
    top_n: int = 10
) -> list[dict[str, float]]:
    """
    Identify topics where Clarion's coverage exceeds competitor coverage.
    Returns top N entities sorted by percentage point lead.

    Args:
        competitor_pct: Dict mapping entity to competitor percentage
        clarion_pct: Dict mapping entity to Clarion percentage
        top_n: Number of top strengths to return

    Returns:
        List of dicts with entity, clarion_pct, competitor_pct, and gap_pct.
        Sorted by gap_pct descending (largest lead first).

    Example:
        >>> competitor_pct = {'Sports Betting': 15.3, 'Mobile Gaming': 8.75}
        >>> clarion_pct = {'Sports Betting': 14.1, 'Mobile Gaming': 14.5}
        >>> strengths = get_clarion_strengths(competitor_pct, clarion_pct, top_n=2)
        >>> strengths[0]['entity']
        'Mobile Gaming'
        >>> strengths[0]['gap_pct']
        5.75
    """
    rows = []

    # Get all unique entities from both dictionaries
    all_entities = set(list(competitor_pct.keys()) + list(clarion_pct.keys()))

    for entity in all_entities:
        comp = competitor_pct.get(entity, 0.0)
        clar = clarion_pct.get(entity, 0.0)
        gap = clar - comp

        # Only include if Clarion has coverage AND leads competitors
        if clar > 0 and gap > 0:
            rows.append({
                "entity": entity,
                "clarion_pct": clar,
                "competitor_pct": comp,
                "gap_pct": gap,
            })

    # Sort by gap (largest lead first)
    rows.sort(key=lambda r: r["gap_pct"], reverse=True)
    return rows[:top_n]
