"""
Reader Advantages V2: Pattern-based advantage detection for "Why Readers Choose Us".

This module detects READER ADVANTAGES (not topics) based on observable coverage patterns:
- Explainers and analysis depth
- Franchises and recurring editorial formats
- Geography depth
- Follow-through coverage
- Event-first/on-the-ground reporting

Key principles:
1. Advantages describe coverage BEHAVIOR patterns, not topic labels
2. Evidence threshold: internal_count >= 2 to qualify
3. Never show single-word topics as advantages
4. If signals are weak, show "emerging patterns" fallback
5. 30-day and 90-day windows must both work correctly
"""

import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd

# ============================================================================
# Constants and Configuration
# ============================================================================

# Minimum internal articles to qualify as a card
MIN_INTERNAL_COUNT = 2

# Target number of cards
TARGET_CARDS = 3
MAX_CARDS = 5

# Pattern detection keywords
EXPLAINER_SIGNALS = {
    'explainer', 'what it means', 'analysis', 'deep dive', 'guide',
    'breakdown', 'explained', 'how to', 'understanding', 'insight',
    'in-depth', 'comprehensive', 'detailed', 'examination', 'why',
    'implications', 'impact', 'future of', 'state of'
}

FRANCHISE_PATTERNS = [
    r'most influential',
    r'top \d+',
    r'power \d+',
    r'rising stars?',
    r'women in',
    r'men in',
    r'awards?',
    r'ranking',
    r'list',
    r'winners?',
    r'annual',
    r'quarterly',
    r'monthly',
    r'weekly roundup',
    r'week in review',
]

EVENT_SIGNALS = {
    'ice', 'igb', 'barcelona', 'summit', 'conference', 'show floor',
    'panel', 'keynote', 'networking', 'expo', 'london', 'amsterdam',
    'las vegas', 'g2e', 'sigma', 'sbc', 'affiliate', 'event',
    'speaker', 'session', 'booth', 'exhibition'
}

GEOGRAPHY_TOKENS = {
    # Emerging markets
    'india', 'brazil', 'latam', 'latin america', 'nigeria', 'africa',
    'philippines', 'asia', 'japan', 'south korea', 'mexico', 'colombia',
    'argentina', 'peru', 'chile',
    # Established markets
    'uk', 'united kingdom', 'britain', 'us', 'usa', 'united states',
    'germany', 'spain', 'italy', 'france', 'netherlands', 'sweden',
    'denmark', 'malta', 'gibraltar', 'canada', 'australia',
    # Regions
    'europe', 'european', 'north america', 'apac', 'mena', 'emea'
}

# Brand tokens to exclude from analysis
BRAND_TOKENS = {
    'igbaffiliate', 'igamingbusiness', 'igba', 'igb',
    'igbaffiliate.com', 'igamingbusiness.com',
    'barcelona.igbaffiliate.com', 'ggb magazine', 'ggbmagazine',
}


# ============================================================================
# Data Preparation
# ============================================================================

def normalize_datetime(dt) -> datetime | None:
    """Normalize datetime to UTC timezone-aware."""
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = pd.to_datetime(dt, utc=True)
        except Exception:
            return None
    if isinstance(dt, pd.Timestamp):
        if dt.tzinfo is None:
            dt = dt.tz_localize('UTC')
        else:
            dt = dt.tz_convert('UTC')
        return dt.to_pydatetime()
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    return None


def prepare_dataframe(df: pd.DataFrame, window_days: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Prepare and filter DataFrame by window.

    Returns:
        (internal_df, competitor_df, debug_info)
    """
    debug_info = {
        'total_rows_before': len(df) if df is not None else 0,
        'date_col_found': None,
        'min_date': None,
        'max_date': None,
        'rows_after_filter': 0,
        'internal_after_filter': 0,
        'competitor_after_filter': 0,
    }

    if df is None or len(df) == 0:
        return pd.DataFrame(), pd.DataFrame(), debug_info

    df = df.copy()

    # Find date column
    date_col = None
    for col in ['published_date_utc', 'published_date', 'published_dt', 'date', 'timestamp', 'scrape_timestamp']:
        if col in df.columns:
            date_col = col
            break

    if date_col is None:
        debug_info['error'] = 'No date column found'
        return pd.DataFrame(), pd.DataFrame(), debug_info

    debug_info['date_col_found'] = date_col

    # Normalize timestamps to UTC
    df['_date_normalized'] = pd.to_datetime(df[date_col], errors='coerce', utc=True)

    # Get date range before filtering
    valid_dates = df['_date_normalized'].dropna()
    if len(valid_dates) > 0:
        debug_info['min_date'] = str(valid_dates.min())
        debug_info['max_date'] = str(valid_dates.max())

    # Calculate cutoff
    cutoff = datetime.now(UTC) - timedelta(days=window_days)

    # Filter by window
    df_filtered = df[df['_date_normalized'] >= cutoff].copy()
    debug_info['rows_after_filter'] = len(df_filtered)

    if len(df_filtered) == 0:
        debug_info['warning'] = f'No rows after {window_days}-day filter. Cutoff: {cutoff}'
        return pd.DataFrame(), pd.DataFrame(), debug_info

    # Partition by category
    source_col = None
    if 'source_type' in df_filtered.columns:
        source_col = 'source_type'
    elif 'category' in df_filtered.columns:
        source_col = 'category'

    if source_col:
        internal_mask = df_filtered[source_col].str.lower().isin(['internal', 'us', 'ours', 'own'])
        competitor_mask = df_filtered[source_col].str.lower().isin(['competitor', 'them', 'external', 'comp'])

        internal_df = df_filtered[internal_mask].copy()
        competitor_df = df_filtered[competitor_mask].copy()
    else:
        # No category column - treat all as internal
        internal_df = df_filtered.copy()
        competitor_df = pd.DataFrame()

    debug_info['internal_after_filter'] = len(internal_df)
    debug_info['competitor_after_filter'] = len(competitor_df)

    return internal_df, competitor_df, debug_info


# ============================================================================
# Pattern Detectors
# ============================================================================

def detect_explainer_advantage(internal_df: pd.DataFrame, competitor_df: pd.DataFrame) -> dict | None:
    """
    Detect explainer/analysis depth advantage.

    Signals: "explainer", "what it means", "analysis", "deep dive", etc.
    """
    def count_explainer_articles(df: pd.DataFrame) -> tuple[int, list[dict]]:
        if df is None or len(df) == 0:
            return 0, []

        matches = []
        for _, row in df.iterrows():
            title = str(row.get('title', '')).lower()
            summary = str(row.get('summary', '')).lower() if row.get('summary') else ''
            text = f"{title} {summary}"

            for signal in EXPLAINER_SIGNALS:
                if signal in text:
                    matches.append({
                        'title': row.get('title', '')[:80],
                        'link': row.get('link', ''),
                        'date': str(row.get('published_date_utc', row.get('published_date', '')))[:10]
                    })
                    break  # Count each article once

        return len(matches), matches

    internal_count, internal_examples = count_explainer_articles(internal_df)
    competitor_count, _ = count_explainer_articles(competitor_df)

    if internal_count < MIN_INTERNAL_COUNT:
        return None

    # Calculate advantage score
    total = internal_count + competitor_count
    internal_share = internal_count / max(total, 1)

    score = internal_count  # base
    if internal_share > 0.5:
        score += 2  # boost for majority share
    if internal_count >= 4:
        score += 1  # boost for volume

    return {
        'advantage_key': 'explainer_depth',
        'internal_count': internal_count,
        'competitor_count': competitor_count,
        'internal_examples': internal_examples[:3],
        'score': score,
        'machine_rationale': f'{internal_count} explainer/analysis articles vs {competitor_count} competitor. Share: {internal_share:.0%}',
        'headline_template': 'We explain, not just report',
        'reader_value_template': 'Readers get context and analysis beyond the headline, helping them understand implications.',
        'why_matters_template': 'Decision-makers need insight, not just news. Depth builds trust and authority.',
    }


def detect_franchise_advantage(internal_df: pd.DataFrame, competitor_df: pd.DataFrame) -> dict | None:
    """
    Detect recurring editorial franchises (awards, rankings, recurring formats).

    Requires >= 2 articles matching franchise patterns.
    """
    def count_franchise_articles(df: pd.DataFrame) -> tuple[int, list[dict], set[str]]:
        if df is None or len(df) == 0:
            return 0, [], set()

        matches = []
        franchise_types = set()

        for _, row in df.iterrows():
            title = str(row.get('title', '')).lower()

            for pattern in FRANCHISE_PATTERNS:
                if re.search(pattern, title):
                    matches.append({
                        'title': row.get('title', '')[:80],
                        'link': row.get('link', ''),
                        'date': str(row.get('published_date_utc', row.get('published_date', '')))[:10]
                    })
                    franchise_types.add(pattern)
                    break

        return len(matches), matches, franchise_types

    internal_count, internal_examples, internal_types = count_franchise_articles(internal_df)
    competitor_count, _, _ = count_franchise_articles(competitor_df)

    if internal_count < MIN_INTERNAL_COUNT:
        return None

    score = internal_count
    if len(internal_types) >= 2:
        score += 2  # Multiple franchise types
    if internal_count > competitor_count:
        score += 1

    return {
        'advantage_key': 'editorial_franchises',
        'internal_count': internal_count,
        'competitor_count': competitor_count,
        'internal_examples': internal_examples[:3],
        'score': score,
        'machine_rationale': f'{internal_count} franchise articles (awards, rankings, recurring formats). Types: {len(internal_types)}',
        'headline_template': 'We create industry moments competitors react to',
        'reader_value_template': 'Readers access exclusive rankings, awards, and recognitions that define industry benchmarks.',
        'why_matters_template': 'Franchises build anticipation and establish our voice as the industry authority.',
    }


def detect_geography_advantage(internal_df: pd.DataFrame, competitor_df: pd.DataFrame) -> dict | None:
    """
    Detect geography depth advantage (repeated coverage of specific regions).

    IMPORTANT: Counts unique article_ids, not keyword hits.
    """
    def count_geography_articles(df: pd.DataFrame) -> tuple[dict[str, set[str]], dict[str, int], dict[str, list[dict]]]:
        """Returns (geo_article_ids, geo_counts, geo_examples)"""
        if df is None or len(df) == 0:
            return {}, {}, {}

        geo_article_ids = defaultdict(set)  # geo -> set of article_ids
        geo_examples = defaultdict(list)

        for _, row in df.iterrows():
            article_id = str(row.get('article_id', ''))
            title = str(row.get('title', '')).lower()
            summary = str(row.get('summary', '')).lower() if row.get('summary') else ''
            text = f"{title} {summary}"

            for geo in GEOGRAPHY_TOKENS:
                if geo in text:
                    geo_article_ids[geo].add(article_id)
                    if len(geo_examples[geo]) < 3:
                        geo_examples[geo].append({
                            'title': row.get('title', '')[:80],
                            'link': row.get('link', ''),
                            'date': str(row.get('published_date_utc', row.get('published_date', '')))[:10]
                        })

        geo_counts = {geo: len(ids) for geo, ids in geo_article_ids.items()}
        return dict(geo_article_ids), geo_counts, dict(geo_examples)

    internal_geo_ids, internal_geo, internal_examples = count_geography_articles(internal_df)
    competitor_geo_ids, competitor_geo, _ = count_geography_articles(competitor_df)

    # Find geographies where we have sustained advantage
    advantaged_geos = []
    for geo, count in internal_geo.items():
        if count >= MIN_INTERNAL_COUNT:
            comp_count = competitor_geo.get(geo, 0)
            if count > comp_count or comp_count == 0:
                advantaged_geos.append((geo, count, comp_count))

    if not advantaged_geos:
        return None

    # Pick the strongest geography
    advantaged_geos.sort(key=lambda x: x[1], reverse=True)
    top_geo, internal_count, competitor_count = advantaged_geos[0]

    # Aggregate counts using UNIQUE article_ids across all advantaged geographies
    # This prevents double-counting when an article mentions multiple geographies
    internal_unique_ids = set()
    competitor_unique_ids = set()
    for geo, _, _ in advantaged_geos:
        internal_unique_ids.update(internal_geo_ids.get(geo, set()))
        competitor_unique_ids.update(competitor_geo_ids.get(geo, set()))

    total_internal = len(internal_unique_ids)
    total_competitor = len(competitor_unique_ids)

    # Get examples from top geography
    examples = internal_examples.get(top_geo, [])[:3]

    score = total_internal
    if len(advantaged_geos) >= 2:
        score += 2  # Multiple regions
    if total_internal > total_competitor * 2:
        score += 2  # Strong lead

    geo_names = [g[0].title() for g in advantaged_geos[:3]]

    return {
        'advantage_key': 'geography_depth',
        'internal_count': total_internal,
        'competitor_count': total_competitor,
        'internal_examples': examples,
        'score': score,
        'machine_rationale': f'Strong coverage of {", ".join(geo_names)}. {total_internal} unique articles vs {total_competitor} competitor.',
        'headline_template': 'We go deeper on emerging markets',
        'reader_value_template': f'Readers get sustained coverage of key markets like {", ".join(geo_names[:2])}, not just one-off headlines.',
        'why_matters_template': 'Market-specific depth helps readers make regional investment and expansion decisions.',
    }


def detect_event_advantage(internal_df: pd.DataFrame, competitor_df: pd.DataFrame) -> dict | None:
    """
    Detect on-the-ground/event-first reporting advantage.

    Never display location token as advantage name - convert to reader value.
    """
    def count_event_articles(df: pd.DataFrame) -> tuple[int, list[dict]]:
        if df is None or len(df) == 0:
            return 0, []

        matches = []
        for _, row in df.iterrows():
            title = str(row.get('title', '')).lower()
            summary = str(row.get('summary', '')).lower() if row.get('summary') else ''
            link = str(row.get('link', '')).lower()
            text = f"{title} {summary} {link}"

            for signal in EVENT_SIGNALS:
                if signal in text:
                    matches.append({
                        'title': row.get('title', '')[:80],
                        'link': row.get('link', ''),
                        'date': str(row.get('published_date_utc', row.get('published_date', '')))[:10]
                    })
                    break

        return len(matches), matches

    internal_count, internal_examples = count_event_articles(internal_df)
    competitor_count, _ = count_event_articles(competitor_df)

    if internal_count < MIN_INTERNAL_COUNT:
        return None

    internal_share = internal_count / max(internal_count + competitor_count, 1)

    score = internal_count
    if internal_share > 0.6:
        score += 2
    if internal_count >= 5:
        score += 1

    return {
        'advantage_key': 'event_coverage',
        'internal_count': internal_count,
        'competitor_count': competitor_count,
        'internal_examples': internal_examples[:3],
        'score': score,
        'machine_rationale': f'{internal_count} event/conference articles vs {competitor_count} competitor. Share: {internal_share:.0%}',
        'headline_template': 'We cover events with insider context',
        'reader_value_template': 'Readers get show floor insights, keynote coverage, and networking highlights that competitors miss.',
        'why_matters_template': 'Event coverage extends our reach beyond attendees and builds anticipation for future events.',
    }


def detect_followthrough_advantage(internal_df: pd.DataFrame, competitor_df: pd.DataFrame) -> dict | None:
    """
    Detect follow-through coverage advantage.

    Identifies topic clusters where internal has multi-article follow-ups.
    Uses simple keyword overlap for clustering.

    IMPORTANT: Counts UNIQUE article_ids, not cluster membership count.
    An article appearing in multiple clusters is only counted once.
    """
    def extract_keywords(title: str) -> set[str]:
        """Extract meaningful keywords from title."""
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'has', 'have', 'will'}
        words = re.findall(r'\b[a-z]{4,}\b', title.lower())
        return {w for w in words if w not in stopwords and w not in BRAND_TOKENS}

    def find_clusters(df: pd.DataFrame) -> tuple[dict[tuple, list[dict]], set[str]]:
        """Find clusters of related articles. Returns (clusters, unique_article_ids)."""
        if df is None or len(df) == 0:
            return {}, set()

        articles = []
        for _, row in df.iterrows():
            article_id = str(row.get('article_id', ''))
            title = str(row.get('title', ''))
            keywords = extract_keywords(title)
            if len(keywords) >= 2:
                articles.append({
                    'article_id': article_id,
                    'title': title[:80],
                    'link': row.get('link', ''),
                    'date': str(row.get('published_date_utc', row.get('published_date', '')))[:10],
                    'keywords': keywords
                })

        # Find clusters with overlapping keywords
        clusters = defaultdict(list)
        for i, art1 in enumerate(articles):
            for art2 in articles[i+1:]:
                overlap = art1['keywords'] & art2['keywords']
                if len(overlap) >= 2:
                    cluster_key = tuple(sorted(overlap)[:3])
                    if art1 not in clusters[cluster_key]:
                        clusters[cluster_key].append(art1)
                    if art2 not in clusters[cluster_key]:
                        clusters[cluster_key].append(art2)

        valid_clusters = {k: v for k, v in clusters.items() if len(v) >= 2}

        # Collect UNIQUE article_ids across all clusters (prevents double-counting)
        unique_ids = set()
        for cluster_articles in valid_clusters.values():
            for art in cluster_articles:
                unique_ids.add(art['article_id'])

        return valid_clusters, unique_ids

    internal_clusters, internal_unique_ids = find_clusters(internal_df)
    competitor_clusters, competitor_unique_ids = find_clusters(competitor_df)

    if not internal_clusters:
        return None

    # Count UNIQUE articles involved in follow-through (not cluster memberships)
    internal_followthrough = len(internal_unique_ids)
    competitor_followthrough = len(competitor_unique_ids)

    if internal_followthrough < MIN_INTERNAL_COUNT:
        return None

    # Get examples from largest cluster
    largest_cluster = max(internal_clusters.values(), key=len)
    examples = largest_cluster[:3]

    score = internal_followthrough
    if len(internal_clusters) >= 3:
        score += 2  # Multiple story threads
    if internal_followthrough > competitor_followthrough:
        score += 1

    return {
        'advantage_key': 'followthrough_coverage',
        'internal_count': internal_followthrough,
        'competitor_count': competitor_followthrough,
        'internal_examples': examples,
        'score': score,
        'machine_rationale': f'{len(internal_clusters)} story clusters with {internal_followthrough} unique articles',
        'headline_template': 'We follow stories beyond the first headline',
        'reader_value_template': 'Readers get continued updates on developing stories, not just initial announcements.',
        'why_matters_template': 'Follow-through coverage builds deeper understanding and keeps readers coming back.',
    }


# ============================================================================
# Main Detection Pipeline
# ============================================================================

def detect_all_advantages(
    df: pd.DataFrame,
    window_days: int = 30
) -> dict[str, Any]:
    """
    Run all pattern detectors and return structured advantage data.

    Returns:
        {
            'window_days': int,
            'generated_at': str,
            'cards': [...],  # Top 3-5 advantages
            'emerging_patterns': [...],  # Fallback if <3 strong advantages
            'diagnostics': {...},
            'debug': {...}
        }
    """
    # Prepare data
    internal_df, competitor_df, debug_info = prepare_dataframe(df, window_days)

    result = {
        'window_days': window_days,
        'generated_at': datetime.now(UTC).isoformat(),
        'cards': [],
        'emerging_patterns': [],
        'diagnostics': {
            'internal_articles': debug_info.get('internal_after_filter', 0),
            'competitor_articles': debug_info.get('competitor_after_filter', 0),
            'max_internal_in_window': len(internal_df),
            'max_competitor_in_window': len(competitor_df),
        },
        'debug': debug_info,
    }

    # Handle empty data
    if len(internal_df) == 0:
        result['empty_message'] = f"No internal articles found in the last {window_days} days for the selected sources."
        return result

    # Run all detectors
    detectors = [
        detect_explainer_advantage,
        detect_franchise_advantage,
        detect_geography_advantage,
        detect_event_advantage,
        detect_followthrough_advantage,
    ]

    candidates = []
    for detector in detectors:
        try:
            advantage = detector(internal_df, competitor_df)
            if advantage:
                candidates.append(advantage)
        except Exception as e:
            result['debug'][f'{detector.__name__}_error'] = str(e)

    # =========================================================================
    # SANITY CHECKS: Ensure counts don't exceed window denominators
    # =========================================================================
    max_internal = len(internal_df)
    max_competitor = len(competitor_df)

    sanity_warnings = []
    for candidate in candidates:
        advantage_key = candidate.get('advantage_key', 'unknown')

        # Check internal count
        if candidate['internal_count'] > max_internal:
            sanity_warnings.append(
                f"{advantage_key}: internal_count {candidate['internal_count']} > max {max_internal}"
            )
            candidate['internal_count'] = max_internal  # Auto-correct

        # Check competitor count
        if candidate['competitor_count'] > max_competitor:
            sanity_warnings.append(
                f"{advantage_key}: competitor_count {candidate['competitor_count']} > max {max_competitor}"
            )
            candidate['competitor_count'] = max_competitor  # Auto-correct

    if sanity_warnings:
        result['debug']['sanity_warnings'] = sanity_warnings
        print(f"[reader_advantages_v2] SANITY WARNINGS: {sanity_warnings}")

    # =========================================================================
    # CALCULATE CONCENTRATION-BASED ADVANTAGE
    # Raw counts are misleading (1 publisher vs 10+ competitors).
    # Concentration = % of content focused on each area.
    # =========================================================================
    for candidate in candidates:
        internal_count = candidate['internal_count']
        competitor_count = candidate['competitor_count']

        # Calculate concentration (% of total content)
        our_concentration = (internal_count / max_internal * 100) if max_internal > 0 else 0
        their_concentration = (competitor_count / max_competitor * 100) if max_competitor > 0 else 0

        # Calculate concentration ratio (how much more we focus on this)
        if their_concentration > 0:
            concentration_ratio = our_concentration / their_concentration
        else:
            concentration_ratio = float('inf') if our_concentration > 0 else 0

        # Store in candidate
        candidate['our_concentration'] = round(our_concentration, 1)
        candidate['their_concentration'] = round(their_concentration, 1)
        candidate['concentration_ratio'] = round(concentration_ratio, 2) if concentration_ratio != float('inf') else 99.0

        # IS THIS A REAL ADVANTAGE? (we focus more than them)
        candidate['is_real_advantage'] = our_concentration > their_concentration

    # =========================================================================
    # FILTER: Only keep cards where we have genuine advantage
    # This removes cards like "follow-through" where competitors focus more
    # =========================================================================
    candidates_before_filter = len(candidates)
    candidates = [c for c in candidates if c.get('is_real_advantage', False)]
    result['debug']['candidates_filtered_out'] = candidates_before_filter - len(candidates)

    # =========================================================================
    # Sort by concentration_ratio descending (higher = stronger advantage)
    candidates.sort(key=lambda x: x.get('concentration_ratio', 0), reverse=True)

    # Split into cards and emerging patterns
    qualifying = [c for c in candidates if c['internal_count'] >= MIN_INTERNAL_COUNT]
    emerging = [c for c in candidates if c['internal_count'] < MIN_INTERNAL_COUNT and c['internal_count'] >= 1]

    result['cards'] = qualifying[:MAX_CARDS]

    # If fewer than 3 cards, add emerging patterns
    if len(result['cards']) < TARGET_CARDS:
        # Add any remaining qualifying candidates
        result['emerging_patterns'] = emerging[:3]

    result['diagnostics']['candidates_found'] = len(candidates)
    result['diagnostics']['cards_generated'] = len(result['cards'])
    result['diagnostics']['max_internal_in_window'] = max_internal
    result['diagnostics']['max_competitor_in_window'] = max_competitor

    return result


# ============================================================================
# Gemini Integration (Stage B)
# ============================================================================

def build_gemini_prompt(cards: list[dict]) -> str:
    """
    Build prompt for Gemini to rewrite cards into clean reader-centric wording.

    Gemini MUST NOT invent new claims - only rewrite what's provided.
    """
    if not cards:
        return ""

    cards_json = []
    for card in cards:
        cards_json.append({
            'advantage_key': card['advantage_key'],
            'internal_count': card['internal_count'],
            'competitor_count': card['competitor_count'],
            'machine_rationale': card['machine_rationale'],
            'headline_template': card['headline_template'],
            'reader_value_template': card['reader_value_template'],
            'why_matters_template': card['why_matters_template'],
        })

    prompt = f"""You are a copy editor for a B2B iGaming media company. Rewrite these reader advantage cards into clean, professional wording.

RULES:
1. Keep each headline to 5-10 words
2. Keep "what_readers_get" to one sentence
3. Keep "why_it_matters" to one sentence
4. Do NOT add claims not in the data
5. Do NOT use superlatives like "best", "leading", "dominant"
6. Do NOT bash competitors
7. Use the templates as starting points, improve phrasing naturally

INPUT CARDS:
{cards_json}

OUTPUT FORMAT (strict JSON):
{{
  "why_readers_choose_us": [
    {{
      "advantage_key": "...",
      "headline": "...",
      "what_readers_get": "...",
      "why_it_matters": "..."
    }}
  ]
}}

Return ONLY the JSON, no explanation."""

    return prompt


def parse_gemini_response(response_text: str, original_cards: list[dict]) -> list[dict]:
    """
    Parse Gemini response and merge with original card data.
    Falls back to templates if parsing fails.
    """
    import json

    try:
        # Clean response
        text = response_text.strip()
        if text.startswith('```'):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)

        data = json.loads(text)
        gemini_cards = data.get('why_readers_choose_us', [])

        # Merge with original data
        result = []
        for orig in original_cards:
            # Find matching Gemini card
            gemini_card = None
            for gc in gemini_cards:
                if gc.get('advantage_key') == orig['advantage_key']:
                    gemini_card = gc
                    break

            merged = {
                **orig,
                'headline': gemini_card.get('headline', orig['headline_template']) if gemini_card else orig['headline_template'],
                'what_readers_get': gemini_card.get('what_readers_get', orig['reader_value_template']) if gemini_card else orig['reader_value_template'],
                'why_it_matters': gemini_card.get('why_it_matters', orig['why_matters_template']) if gemini_card else orig['why_matters_template'],
            }
            result.append(merged)

        return result

    except (json.JSONDecodeError, KeyError, TypeError):
        # Fallback to templates
        return [{
            **card,
            'headline': card['headline_template'],
            'what_readers_get': card['reader_value_template'],
            'why_it_matters': card['why_matters_template'],
        } for card in original_cards]


# ============================================================================
# CSV Export
# ============================================================================

def advantages_to_csv(result: dict[str, Any]) -> str:
    """Export advantages to CSV format with concentration metrics."""
    cards = result.get('cards', [])

    if not cards:
        return "window_days,advantage_key,headline,internal_count,competitor_count,our_concentration,their_concentration,concentration_ratio,internal_example_links,score,rationale\n"

    rows = []
    for card in cards:
        example_links = ';'.join([ex.get('link', '') for ex in card.get('internal_examples', [])])
        rows.append({
            'window_days': result.get('window_days', 30),
            'advantage_key': card.get('advantage_key', ''),
            'headline': card.get('headline', card.get('headline_template', '')),
            'internal_count': card.get('internal_count', 0),
            'competitor_count': card.get('competitor_count', 0),
            'our_concentration': card.get('our_concentration', 0),
            'their_concentration': card.get('their_concentration', 0),
            'concentration_ratio': card.get('concentration_ratio', 0),
            'internal_example_links': example_links,
            'score': card.get('score', 0),
            'rationale': card.get('machine_rationale', ''),
        })

    df = pd.DataFrame(rows)
    return df.to_csv(index=False)


# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == '__main__':
    import argparse
    import json

    parser = argparse.ArgumentParser(description='Detect reader advantages from articles')
    parser.add_argument('--window', type=int, default=30, help='Window in days')
    parser.add_argument('--input', type=str, help='Input CSV file')
    parser.add_argument('--output', type=str, help='Output JSON file')
    parser.add_argument('--debug', action='store_true', help='Show debug info')

    args = parser.parse_args()

    if args.input:
        df = pd.read_csv(args.input)
        result = detect_all_advantages(df, window_days=args.window)

        if args.debug:
            print("DEBUG INFO:")
            print(json.dumps(result['debug'], indent=2))
            print()

        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
        else:
            print(json.dumps(result, indent=2))
    else:
        print("Usage: python reader_advantages_v2.py --input articles.csv --output analysis.json --window 30")
