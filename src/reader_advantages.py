"""
Reader Advantages: Decision-oriented module for "Reader Advantage Briefs".

Produces action cards for content, product, and commercial teams.
No statistical jargon - plain English value statements and actionable guidance.

All functions are pure and unit testable.
"""

import json

import pandas as pd

# ============================================================================
# Constants
# ============================================================================

MIN_INTERNAL_COUNT = 3
OWNERSHIP_THRESHOLD = 0.7  # 70% share = owned topic

# Copy deck templates (verbatim per spec)
VALUE_STATEMENT_TEMPLATE = (
    "Readers come to us for {topic} because our coverage is more frequent, "
    "timelier, and more actionable than competitors in the last 30 days."
)

RISK_TEMPLATE = (
    "Competitors can close this gap within 4-6 weeks if we slow down; "
    "defend with weekly explainers, deeper analysis, and an editorial series."
)


# ============================================================================
# Ownership Rules
# ============================================================================

def is_owned_topic(internal_count: int, competitor_count: int) -> bool:
    """
    Determine if a topic is "owned" using simple business rules.

    Owned if:
    - internal_count >= 3 AND competitor_count == 0 (exclusive), OR
    - internal_count / max(1, internal_count + competitor_count) >= 0.7

    Args:
        internal_count: Number of our articles on this topic
        competitor_count: Number of competitor articles on this topic

    Returns:
        True if we own this topic
    """
    if internal_count < MIN_INTERNAL_COUNT:
        return False

    # Exclusive topic
    if competitor_count == 0:
        return True

    # Ownership ratio check
    total = internal_count + competitor_count
    ownership_ratio = internal_count / max(1, total)

    return ownership_ratio >= OWNERSHIP_THRESHOLD


def compute_ownership_ratio(internal_count: int, competitor_count: int) -> float:
    """Compute ownership ratio for display purposes."""
    total = internal_count + competitor_count
    if total == 0:
        return 0.0
    return internal_count / total


# ============================================================================
# Advantage Builder
# ============================================================================

def _extract_examples(topic: dict) -> list[dict]:
    """Extract 1-3 example articles from topic data."""
    examples = topic.get('examples', [])
    result = []

    for ex in examples[:3]:
        result.append({
            'title': ex.get('title', 'Untitled'),
            'link': ex.get('link', '#'),
            'date': (ex.get('published_date_utc', '')[:10]
                    if ex.get('published_date_utc') else '')
        })

    return result


def _generate_editorial_actions(topic: dict, topic_name: str) -> list[str]:
    """Generate 3 editorial action bullets."""
    existing = topic.get('actions', [])

    if len(existing) >= 3:
        return existing[:3]

    defaults = [
        f"Publish a weekly explainer series on {topic_name}.",
        "Add deeper analysis with expert commentary.",
        "Create a roundup of key developments for the newsletter."
    ]

    actions = list(existing)
    for default in defaults:
        if len(actions) >= 3:
            break
        if default not in actions:
            actions.append(default)

    return actions[:3]


def _generate_product_enablers(topic_name: str, diagnostics: dict) -> list[str]:
    """Generate 2 product enabler suggestions."""
    enablers = [
        f"Add '{topic_name}' to internal search keywords for better discoverability.",
        f"Create a topic hub page to aggregate all {topic_name} coverage."
    ]

    # Add recirculation suggestion if we have good depth
    depth = diagnostics.get('median_words_internal', 0)
    if depth > 400:
        enablers[1] = f"Enable recirculation module on {topic_name} articles to increase page views."

    return enablers[:2]


def _generate_commercial_levers(topic_name: str, is_exclusive: bool) -> list[str]:
    """Generate 2 commercial lever suggestions."""
    if is_exclusive:
        return [
            f"Pitch exclusive sponsorship series on {topic_name} to relevant vendors.",
            f"Propose branded webinar on {topic_name} trends for Q1."
        ]
    else:
        return [
            f"Offer sponsored content package around {topic_name} coverage.",
            f"Identify speaker targets in {topic_name} space for upcoming events."
        ]


def _generate_distribution_notes(
    diagnostics: dict,
    global_notes: dict,
    topic_name: str
) -> list[str]:
    """Generate distribution notes based on cadence and regional data."""
    notes = []

    # Weekend hint
    weekend_internal = diagnostics.get('internal_weekend_pct', 0)
    weekend_competitor = diagnostics.get('competitor_weekend_pct', 0)

    if weekend_internal > weekend_competitor:
        notes.append(f"Continue weekend publishing - we lead with {weekend_internal:.0f}% vs competitors' {weekend_competitor:.0f}%.")
    elif weekend_internal < weekend_competitor:
        notes.append(f"Consider weekend push - competitors publish {weekend_competitor:.0f}% on weekends vs our {weekend_internal:.0f}%.")

    # Region hint from global notes
    region_edges = global_notes.get('region_edge', [])
    if region_edges:
        top_region = region_edges[0]
        region_name = top_region.get('region', '')
        if region_name:
            notes.append(f"Focus distribution on {region_name} where we have {top_region.get('ratio', 1):.1f}x advantage.")

    # Newsletter slot
    notes.append("Reserve a newsletter slot for the next major development.")

    return notes[:3]


def _generate_kpis(topic_name: str) -> list[str]:
    """Generate KPIs to track for this advantage."""
    return [
        "Articles published next 14 days",
        "Average article depth (word count)",
        "Weekend publishing percentage",
        "Reader engagement (time on page)"
    ]


def build_advantage(
    topic: dict,
    global_notes: dict,
    analysis_json: dict
) -> dict:
    """
    Build a single Advantage dict for a topic.

    Args:
        topic: Topic dict from differentiators_v2
        global_notes: Global notes from differentiators_v2
        analysis_json: Full analysis JSON for additional context

    Returns:
        Advantage dict with all fields
    """
    label = topic.get('label', 'Unknown Topic')
    topic_name = label.split(',')[0].strip() if ',' in label else label

    internal_count = topic.get('internal_count', 0)
    competitor_count = topic.get('competitor_count', 0)
    is_exclusive = competitor_count == 0

    diagnostics = topic.get('diagnostics', {})

    # Build the advantage
    advantage = {
        'topic': label,
        'topic_name': topic_name,
        'reader_value': VALUE_STATEMENT_TEMPLATE.format(topic=topic_name),
        'evidence': {
            'our_articles': internal_count,
            'their_articles': competitor_count,
            'examples': _extract_examples(topic)
        },
        'do_more_of_this': _generate_editorial_actions(topic, topic_name),
        'product_enablers': _generate_product_enablers(topic_name, diagnostics),
        'commercial_levers': _generate_commercial_levers(topic_name, is_exclusive),
        'distribution': _generate_distribution_notes(diagnostics, global_notes, topic_name),
        'risk_if_we_stop': RISK_TEMPLATE,
        'kpis': _generate_kpis(topic_name),
        # Metadata for CSV export
        'is_exclusive': is_exclusive,
        'ownership_ratio': compute_ownership_ratio(internal_count, competitor_count),
        'topic_id': topic.get('topic_id', ''),
    }

    return advantage


def build_reader_advantages(
    df_all: pd.DataFrame | None,
    analysis_json: dict
) -> list[dict]:
    """
    Build list of Reader Advantages from analysis data.

    Args:
        df_all: Full news history DataFrame (optional, not used for now)
        analysis_json: Analysis JSON dict containing differentiators_v2

    Returns:
        List of Advantage dicts, one per owned topic
    """
    diff_v2 = analysis_json.get('differentiators_v2', {})
    topics = diff_v2.get('topics', [])
    global_notes = diff_v2.get('global_notes', {})

    advantages = []

    for topic in topics:
        internal_count = topic.get('internal_count', 0)
        competitor_count = topic.get('competitor_count', 0)

        # Check if owned
        if not is_owned_topic(internal_count, competitor_count):
            continue

        advantage = build_advantage(topic, global_notes, analysis_json)
        advantages.append(advantage)

    # Sort by our_articles descending (most coverage first)
    advantages.sort(
        key=lambda x: (x['is_exclusive'], x['evidence']['our_articles']),
        reverse=True
    )

    return advantages


# ============================================================================
# CSV Export
# ============================================================================

def advantages_to_csv(advantages: list[dict]) -> str:
    """
    Convert advantages list to CSV string for download.

    Args:
        advantages: List of Advantage dicts

    Returns:
        CSV string with one row per advantage
    """
    if not advantages:
        return "topic,our_articles,their_articles,is_exclusive,reader_value,do_more_of_this,product_enablers,commercial_levers,risk_if_we_stop\n"

    rows = []
    for adv in advantages:
        rows.append({
            'topic': adv['topic'],
            'our_articles': adv['evidence']['our_articles'],
            'their_articles': adv['evidence']['their_articles'],
            'is_exclusive': 'Yes' if adv['is_exclusive'] else 'No',
            'reader_value': adv['reader_value'],
            'do_more_of_this': ' | '.join(adv['do_more_of_this']),
            'product_enablers': ' | '.join(adv['product_enablers']),
            'commercial_levers': ' | '.join(adv['commercial_levers']),
            'distribution': ' | '.join(adv['distribution']),
            'risk_if_we_stop': adv['risk_if_we_stop'],
            'kpis': ' | '.join(adv['kpis'])
        })

    df = pd.DataFrame(rows)
    return df.to_csv(index=False)


# ============================================================================
# Data Loading Helpers
# ============================================================================

def load_analysis_json(path: str) -> dict:
    """Load analysis JSON from path."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def render_reader_advantages(analysis_json_path: str) -> dict:
    """
    Main entry point for rendering Reader Advantages.

    Args:
        analysis_json_path: Path to analysis JSON file

    Returns:
        Dict with advantages list and metadata
    """
    analysis_json = load_analysis_json(analysis_json_path)
    advantages = build_reader_advantages(None, analysis_json)

    return {
        'advantages': advantages,
        'has_data': len(advantages) > 0,
        'count': len(advantages),
        'exclusive_count': sum(1 for a in advantages if a['is_exclusive'])
    }
