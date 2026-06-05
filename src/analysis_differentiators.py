"""
Analysis Differentiators: Decision-oriented module for "Why Readers Choose Us".

Outputs 3 views:
1. Editorial Wins - Topics we own with immediate actions
2. Audience Edge - Format/cadence advantages
3. Commercial Levers - Sponsorable topics and speaker targets

All functions are pure and unit testable.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# ============================================================================
# Constants
# ============================================================================

MIN_INTERNAL_COUNT = 3
MIN_TOTAL_COUNT = 5
TOI_THRESHOLD = 0.7
FORMAT_MIN_COUNT = 5
REGION_MIN_MENTIONS = 3
REGION_ADVANTAGE_THRESHOLD = 1.25
WEEKEND_BONUS_FACTOR = 0.20

# Output paths
OUTPUTS_DIR = Path(__file__).resolve().parent.parent / 'data' / 'outputs'


# ============================================================================
# Data Loading
# ============================================================================

def load_run(path: str) -> dict:
    """
    Load the analysis JSON from path.

    Args:
        path: Path to the JSON file

    Returns:
        Parsed JSON dict
    """
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_briefing(path: str) -> str:
    """
    Load the briefing markdown.

    Args:
        path: Path to the markdown file

    Returns:
        Markdown content string
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ""


# ============================================================================
# Editorial Wins
# ============================================================================

def compute_toi(internal_count: int, competitor_count: int) -> float:
    """
    Compute Topic Ownership Index.

    TOI = internal_count / max(1, internal_count + competitor_count)

    Returns:
        Float in [0, 1]
    """
    total = internal_count + competitor_count
    if total == 0:
        return 0.0
    return internal_count / total


def is_exclusive(competitor_count: int) -> bool:
    """Check if topic is exclusive (no competitor coverage)."""
    return competitor_count == 0


def generate_why_it_matters(topic: dict, briefing_md: str = "") -> str:
    """
    Generate a one-liner explaining why the topic matters.

    Args:
        topic: Topic dict from differentiators_v2
        briefing_md: Optional briefing markdown for context

    Returns:
        One-sentence explanation
    """
    label = topic.get('label', 'this topic')
    internal = topic.get('internal_count', 0)
    competitor = topic.get('competitor_count', 0)
    toi = compute_toi(internal, competitor)

    if is_exclusive(competitor):
        return f"We exclusively own '{label}' with {internal} articles - competitors have zero coverage."
    elif toi >= 0.8:
        return f"We dominate '{label}' with {toi*100:.0f}% ownership ({internal} vs {competitor} competitor articles)."
    elif toi >= 0.7:
        return f"We lead on '{label}' with {toi*100:.0f}% share - a strong differentiator for readers."
    else:
        return f"We have meaningful presence in '{label}' ({internal} articles, {toi*100:.0f}% share)."


def synthesize_actions(topic: dict) -> list[str]:
    """
    Synthesize 3 actions for a topic if not present.

    Args:
        topic: Topic dict

    Returns:
        List of 3 action strings
    """
    existing = topic.get('actions', [])
    if len(existing) >= 3:
        return existing[:3]

    label = topic.get('label', 'this topic')
    terms = [t.strip() for t in label.split(',')][:2]
    topic_name = terms[0] if terms else 'this topic'

    defaults = [
        f"Publish an explainer piece on {topic_name} this week.",
        "Launch an editorial series to defend exclusive position.",
        "Add local expert interview for depth and credibility."
    ]

    actions = list(existing)
    for default in defaults:
        if len(actions) >= 3:
            break
        if default not in actions:
            actions.append(default)

    return actions[:3]


def build_editorial_wins(run: dict, briefing_md: str = "") -> pd.DataFrame:
    """
    Build Editorial Wins DataFrame.

    Surfaces topics where:
    - Exclusive OR TOI >= 0.7
    - internal_count >= 3

    Args:
        run: Analysis JSON dict
        briefing_md: Optional briefing markdown

    Returns:
        DataFrame with editorial wins
    """
    diff_v2 = run.get('differentiators_v2', {})
    topics = diff_v2.get('topics', [])

    wins = []
    for topic in topics:
        internal = topic.get('internal_count', 0)
        competitor = topic.get('competitor_count', 0)

        # Minimum support
        if internal < MIN_INTERNAL_COUNT:
            continue
        if internal + competitor < MIN_TOTAL_COUNT:
            continue

        toi = compute_toi(internal, competitor)
        exclusive = is_exclusive(competitor)

        # Threshold check
        if not exclusive and toi < TOI_THRESHOLD:
            continue

        # Extract example links
        examples = topic.get('examples', [])
        example_links = [ex.get('link', '') for ex in examples[:3] if ex.get('link')]

        # Generate actions
        actions = synthesize_actions(topic)

        wins.append({
            'topic_id': topic.get('topic_id', ''),
            'label': topic.get('label', ''),
            'internal_count': internal,
            'competitor_count': competitor,
            'TOI': round(toi, 3),
            'exclusive': exclusive,
            'timeliness': topic.get('timeliness', 0.0),
            'depth': topic.get('depth', 0.0),
            'format_edge': topic.get('format_edge', 0.0),
            'ownership': topic.get('ownership', toi),
            'exclusivity': topic.get('exclusivity', 1.0 if exclusive else 0.0),
            'example_links': '|'.join(example_links),
            'actions_json': json.dumps(actions),
            'why_it_matters': generate_why_it_matters(topic, briefing_md),
            'examples': examples[:3],
            'actions': actions,
            'diagnostics': topic.get('diagnostics', {})
        })

    # Sort by TOI descending, then by exclusivity
    df = pd.DataFrame(wins)
    if len(df) > 0:
        df = df.sort_values(['exclusive', 'TOI'], ascending=[False, False]).reset_index(drop=True)

    return df


# ============================================================================
# Audience Edge
# ============================================================================

def build_audience_edge(run: dict) -> dict:
    """
    Build Audience Edge metrics.

    Computes:
    - Weekend Edge: internal_weekend_pct vs competitor_weekend_pct
    - Format Edge: formats where internal_share > competitor_share
    - Region Edge: regions where advantage_ratio > 1.25

    Args:
        run: Analysis JSON dict

    Returns:
        Dict with edge metrics
    """
    result = {
        'weekend_edge': {
            'our_pct': 0.0,
            'comp_pct': 0.0,
            'delta': 0.0,
            'positive': False
        },
        'format_edges': [],
        'region_edges': []
    }

    # Try differentiators_v2 first, then fall back to differentiators
    diff_v2 = run.get('differentiators_v2', {})
    diff_v1 = run.get('differentiators', {})

    # Weekend Edge from cadence metrics
    cadence = diff_v1.get('cadence_metrics', {})
    global_notes = diff_v2.get('global_notes', {})

    # Get weekend percentages
    our_weekend = cadence.get('internal_weekend_pct', 0.0)
    comp_weekend = cadence.get('competitor_weekend_pct', 0.0)

    # Also check global_notes weekend_advantage string
    weekend_str = global_notes.get('weekend_advantage', '')
    if not our_weekend and 'Clarion leads with' in weekend_str:
        # Parse from string like "Clarion leads with 14.3% weekend coverage vs competitors' 3.8%"
        match = re.search(r'(\d+\.?\d*)%.*vs.*?(\d+\.?\d*)%', weekend_str)
        if match:
            our_weekend = float(match.group(1))
            comp_weekend = float(match.group(2))

    result['weekend_edge'] = {
        'our_pct': round(our_weekend, 1),
        'comp_pct': round(comp_weekend, 1),
        'delta': round(our_weekend - comp_weekend, 1),
        'positive': our_weekend > comp_weekend
    }

    # Format Edge
    format_diffs = diff_v1.get('format_differentiators', [])
    format_summary = global_notes.get('format_summary', [])

    # Combine both sources
    formats_seen = set()
    format_edges = []

    for f in format_diffs:
        fmt_name = f.get('format', '')
        if fmt_name in formats_seen:
            continue
        formats_seen.add(fmt_name)

        internal_count = f.get('internal_count', 0)
        internal_pct = f.get('internal_pct', 0)
        comp_pct = f.get('competitor_pct', 0)

        if internal_count >= FORMAT_MIN_COUNT and internal_pct > comp_pct:
            format_edges.append({
                'format': fmt_name,
                'our_share': round(internal_pct, 1),
                'comp_share': round(comp_pct, 1),
                'advantage': 'more' if internal_pct > comp_pct else 'less'
            })

    for f in format_summary:
        fmt_name = f.get('format', '')
        if fmt_name in formats_seen:
            continue
        formats_seen.add(fmt_name)

        ratio = f.get('ratio_vs_comp', 1.0)
        if ratio >= 1.2:
            format_edges.append({
                'format': fmt_name,
                'our_share': f.get('internal_share', 0),
                'comp_share': f.get('competitor_share', 0),
                'advantage': 'more'
            })

    # Sort by our_share descending
    format_edges.sort(key=lambda x: x['our_share'], reverse=True)
    result['format_edges'] = format_edges[:5]

    # Region Edge
    region_diffs = diff_v1.get('region_differentiators', [])
    region_edges_v2 = global_notes.get('region_edge', [])

    regions_seen = set()
    region_edges = []

    for r in region_diffs:
        region = r.get('region', '')
        if region in regions_seen:
            continue
        regions_seen.add(region)

        ratio = r.get('advantage_ratio', 1.0)
        internal = r.get('internal_mentions', 0)

        if ratio >= REGION_ADVANTAGE_THRESHOLD and internal >= REGION_MIN_MENTIONS:
            region_edges.append({
                'region': region,
                'advantage_ratio': round(ratio, 2),
                'our_mentions': internal,
                'comp_mentions': r.get('competitor_mentions', 0)
            })

    for r in region_edges_v2:
        region = r.get('region', '')
        if region in regions_seen:
            continue
        regions_seen.add(region)

        ratio = r.get('ratio', 1.0)
        internal = r.get('internal_mentions', 0)

        if ratio >= REGION_ADVANTAGE_THRESHOLD and internal >= REGION_MIN_MENTIONS:
            region_edges.append({
                'region': region,
                'advantage_ratio': round(ratio, 2),
                'our_mentions': internal,
                'comp_mentions': r.get('competitor_mentions', 0)
            })

    # Sort by advantage_ratio descending
    region_edges.sort(key=lambda x: x['advantage_ratio'], reverse=True)
    result['region_edges'] = region_edges[:5]

    return result


# ============================================================================
# Commercial Levers
# ============================================================================

def extract_speakers_from_briefing(briefing_md: str) -> list[dict]:
    """
    Extract potential speakers from briefing markdown.

    Args:
        briefing_md: Briefing markdown content

    Returns:
        List of speaker dicts
    """
    speakers = []

    # Look for speaker section
    if 'Potential Speakers' in briefing_md or 'potential_speakers' in briefing_md:
        # Try to parse from briefing
        lines = briefing_md.split('\n')
        in_speaker_section = False

        for line in lines:
            if 'Speaker' in line and ('###' in line or '**' in line):
                in_speaker_section = True
                continue
            elif in_speaker_section and line.startswith('###'):
                break
            elif in_speaker_section and line.strip().startswith('-'):
                # Parse speaker line
                content = line.strip('- *').strip()
                if content:
                    speakers.append({
                        'name': content.split(':')[0].strip() if ':' in content else content,
                        'expertise': content.split(':')[1].strip() if ':' in content else 'Industry Expert'
                    })

    return speakers[:5]


def generate_package_suggestion(topic: dict, briefing_md: str = "") -> str:
    """
    Generate a suggested sponsorship package for a topic.

    Args:
        topic: Topic dict
        briefing_md: Optional briefing markdown

    Returns:
        Package suggestion string
    """
    label = topic.get('label', '')
    terms = [t.strip() for t in label.split(',')][:2]
    topic_name = terms[0] if terms else 'topic'

    exclusive = topic.get('exclusive', False)
    toi = topic.get('TOI', 0.5)

    if exclusive:
        return f"Exclusive editorial series on {topic_name} + sponsored newsletter spotlight + branded webinar"
    elif toi >= 0.8:
        return f"Premium content hub on {topic_name} + email campaign + podcast episode"
    elif toi >= 0.7:
        return f"Editorial feature series on {topic_name} + newsletter inclusion + social amplification"
    else:
        return f"Thought leadership article on {topic_name} + newsletter mention"


def build_commercial_levers(wins_df: pd.DataFrame, briefing_md: str = "", run: dict = None) -> pd.DataFrame:
    """
    Build Commercial Levers DataFrame.

    Creates:
    - Sponsorable Topics table ranked by audience potential
    - Speaker Targets from briefing

    Args:
        wins_df: Editorial Wins DataFrame
        briefing_md: Optional briefing markdown
        run: Optional run dict for additional data

    Returns:
        DataFrame with commercial levers
    """
    if len(wins_df) == 0:
        return pd.DataFrame(columns=[
            'type', 'name', 'audience_potential', 'package_suggestion', 'notes'
        ])

    levers = []

    # Get weekend edge for bonus calculation
    weekend_positive = False
    if run:
        edge = build_audience_edge(run)
        weekend_positive = edge['weekend_edge']['positive']

    # Sponsorable Topics
    for _, row in wins_df.iterrows():
        internal = row['internal_count']
        audience_potential = internal

        if weekend_positive:
            audience_potential = int(internal * (1 + WEEKEND_BONUS_FACTOR))

        package = generate_package_suggestion(row.to_dict(), briefing_md)

        levers.append({
            'type': 'sponsorable_topic',
            'name': row['label'],
            'audience_potential': audience_potential,
            'package_suggestion': package,
            'notes': f"TOI: {row['TOI']*100:.0f}%, {'Exclusive' if row['exclusive'] else 'Leading'}"
        })

    # Speaker Targets from briefing
    speakers = extract_speakers_from_briefing(briefing_md)

    # Also try to get from run JSON
    if run:
        commercial_radar = run.get('commercial_radar', {})
        potential_speakers = commercial_radar.get('potential_speakers', [])

        for s in potential_speakers[:3]:
            name = s.get('name_or_company', s.get('name', ''))
            expertise = s.get('expertise_area', s.get('expertise', ''))

            if name and name not in [sp['name'] for sp in speakers]:
                speakers.append({
                    'name': name,
                    'expertise': expertise
                })

    for speaker in speakers[:5]:
        levers.append({
            'type': 'speaker_target',
            'name': speaker.get('name', ''),
            'audience_potential': 0,
            'package_suggestion': f"Panel or keynote on {speaker.get('expertise', 'industry trends')}",
            'notes': speaker.get('expertise', '')
        })

    df = pd.DataFrame(levers)

    # Sort: sponsorable topics by audience_potential desc, then speakers
    if len(df) > 0:
        df['sort_key'] = df.apply(
            lambda r: (0 if r['type'] == 'sponsorable_topic' else 1, -r['audience_potential']),
            axis=1
        )
        df = df.sort_values('sort_key').drop(columns=['sort_key']).reset_index(drop=True)

    return df


# ============================================================================
# CSV Export
# ============================================================================

def save_csvs(wins_df: pd.DataFrame, edge: dict, levers_df: pd.DataFrame) -> dict:
    """
    Save CSVs to outputs directory with datestamped names and stable symlinks.

    Args:
        wins_df: Editorial Wins DataFrame
        edge: Audience Edge dict
        levers_df: Commercial Levers DataFrame

    Returns:
        Dict with paths to saved files
    """
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    paths = {}

    # Editorial Wins
    if len(wins_df) > 0:
        # Select export columns
        export_cols = [
            'topic_id', 'label', 'internal_count', 'competitor_count',
            'TOI', 'exclusive', 'timeliness', 'depth', 'format_edge',
            'example_links', 'actions_json'
        ]
        export_df = wins_df[[c for c in export_cols if c in wins_df.columns]]

        dated_path = OUTPUTS_DIR / f'editorial_wins_{timestamp}.csv'
        latest_path = OUTPUTS_DIR / 'editorial_wins_latest.csv'

        export_df.to_csv(dated_path, index=False)
        export_df.to_csv(latest_path, index=False)
        paths['editorial_wins'] = str(latest_path)

    # Audience Edge
    edge_rows = []

    # Weekend
    we = edge.get('weekend_edge', {})
    edge_rows.append({
        'metric': 'Weekend Coverage',
        'our_value': we.get('our_pct', 0),
        'comp_value': we.get('comp_pct', 0),
        'delta': we.get('delta', 0),
        'support_notes': 'Positive' if we.get('positive') else 'Negative'
    })

    # Formats
    for f in edge.get('format_edges', []):
        edge_rows.append({
            'metric': f"Format: {f['format']}",
            'our_value': f['our_share'],
            'comp_value': f['comp_share'],
            'delta': round(f['our_share'] - f['comp_share'], 1),
            'support_notes': f"We publish more {f['format']}"
        })

    # Regions
    for r in edge.get('region_edges', []):
        edge_rows.append({
            'metric': f"Region: {r['region']}",
            'our_value': r['our_mentions'],
            'comp_value': r['comp_mentions'],
            'delta': r['advantage_ratio'],
            'support_notes': f"{r['advantage_ratio']}x advantage"
        })

    edge_df = pd.DataFrame(edge_rows)
    dated_path = OUTPUTS_DIR / f'audience_edge_{timestamp}.csv'
    latest_path = OUTPUTS_DIR / 'audience_edge_latest.csv'

    edge_df.to_csv(dated_path, index=False)
    edge_df.to_csv(latest_path, index=False)
    paths['audience_edge'] = str(latest_path)

    # Commercial Levers
    if len(levers_df) > 0:
        dated_path = OUTPUTS_DIR / f'commercial_levers_{timestamp}.csv'
        latest_path = OUTPUTS_DIR / 'commercial_levers_latest.csv'

        levers_df.to_csv(dated_path, index=False)
        levers_df.to_csv(latest_path, index=False)
        paths['commercial_levers'] = str(latest_path)

    return paths


# ============================================================================
# Main Entry Point
# ============================================================================

def render_differentiators(run_json_path: str, briefing_md_path: str = "") -> dict:
    """
    Main entry point for rendering differentiators.

    Args:
        run_json_path: Path to analysis JSON
        briefing_md_path: Path to briefing markdown (optional)

    Returns:
        Dict with all computed data for UI rendering
    """
    run = load_run(run_json_path)
    briefing_md = load_briefing(briefing_md_path) if briefing_md_path else ""

    # Build data
    wins_df = build_editorial_wins(run, briefing_md)
    edge = build_audience_edge(run)
    levers_df = build_commercial_levers(wins_df, briefing_md, run)

    # Save CSVs
    csv_paths = save_csvs(wins_df, edge, levers_df)

    # Compute summary metrics
    summary = {
        'owned_topics': len(wins_df),
        'exclusive_topics': len(wins_df[wins_df['exclusive']]) if len(wins_df) > 0 else 0,
        'median_toi': float(wins_df['TOI'].median()) if len(wins_df) > 0 else 0.0,
        'weekend_positive': edge['weekend_edge']['positive'],
        'format_edges_count': len(edge['format_edges']),
        'region_edges_count': len(edge['region_edges'])
    }

    return {
        'wins_df': wins_df,
        'edge': edge,
        'levers_df': levers_df,
        'csv_paths': csv_paths,
        'summary': summary,
        'has_data': len(wins_df) > 0
    }


def get_csv_for_download(df_or_dict: Any, csv_type: str) -> str:
    """
    Get CSV string for download button.

    Args:
        df_or_dict: DataFrame or dict to convert
        csv_type: Type of CSV ('wins', 'edge', 'levers')

    Returns:
        CSV string
    """
    if isinstance(df_or_dict, pd.DataFrame):
        return df_or_dict.to_csv(index=False)
    elif isinstance(df_or_dict, dict) and csv_type == 'edge':
        # Convert edge dict to CSV
        rows = []
        we = df_or_dict.get('weekend_edge', {})
        rows.append({
            'metric': 'Weekend Coverage',
            'our_value': we.get('our_pct', 0),
            'comp_value': we.get('comp_pct', 0),
            'delta': we.get('delta', 0),
            'support_notes': 'Positive' if we.get('positive') else 'Negative'
        })

        for f in df_or_dict.get('format_edges', []):
            rows.append({
                'metric': f"Format: {f['format']}",
                'our_value': f['our_share'],
                'comp_value': f['comp_share'],
                'delta': round(f['our_share'] - f['comp_share'], 1),
                'support_notes': f"We publish more {f['format']}"
            })

        for r in df_or_dict.get('region_edges', []):
            rows.append({
                'metric': f"Region: {r['region']}",
                'our_value': r['our_mentions'],
                'comp_value': r['comp_mentions'],
                'delta': r['advantage_ratio'],
                'support_notes': f"{r['advantage_ratio']}x advantage"
            })

        return pd.DataFrame(rows).to_csv(index=False)

    return ""
