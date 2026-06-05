"""
Differentiators v2: Topic-level scorecard for content strategy.

Surfaces where Clarion truly leads vs competitors using explainable indices:
- Ownership Index (O): Share of topic coverage that is ours
- Exclusivity Index (E): Share of our coverage that competitors don't have
- Timeliness Index (T): Speed/timing advantage
- Depth Index (D): Content depth advantage
- Format Edge (F): Advantage in high-value formats

Uses sklearn for topic clustering (TF-IDF + SVD + KMeans).
"""

import re
from collections import Counter
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD

# sklearn imports
from sklearn.feature_extraction.text import TfidfVectorizer

from src.textnorm import normalize_text

# ============================================================================
# Constants
# ============================================================================

MIN_TOPIC_SIZE = 5
MIN_INTERNAL_COUNT = 3
MIN_OWNERSHIP_THRESHOLD = 0.6
MIN_EXCLUSIVITY_THRESHOLD = 0.4
MAX_TOPICS = 25
MIN_TOPICS = 8
TOP_N_TOPICS = 6
MAX_EXAMPLES_PER_TOPIC = 3

# Scoring weights
WEIGHT_OWNERSHIP = 0.35
WEIGHT_EXCLUSIVITY = 0.25
WEIGHT_TIMELINESS = 0.15
WEIGHT_DEPTH = 0.15
WEIGHT_FORMAT = 0.10

# High-value formats (over-indexed = internal_share >= 1.5x competitor)
HIGH_VALUE_FORMATS = {
    'explainer', 'guide', 'interview', 'analysis', 'opinion', 'data story',
    'deep dive', 'tutorial', 'how to', 'report'
}

# Format detection keywords
FORMAT_KEYWORDS = {
    'explainer': ['explainer', 'explained', 'what is', 'understanding', 'breakdown'],
    'guide': ['guide', 'how to', 'tutorial', 'step by step', 'beginner', 'complete guide'],
    'interview': ['interview', 'spoke to', 'talked to', 'q&a', 'conversation with', 'exclusive with'],
    'analysis': ['analysis', 'deep dive', 'in-depth', 'examining', 'insights'],
    'opinion': ['opinion', 'commentary', 'editorial', 'perspective', 'viewpoint', 'why i think'],
    'data story': ['data', 'statistics', 'numbers', 'report', 'study', 'research', 'survey'],
    'news': ['announces', 'launches', 'releases', 'unveils', 'reports', 'confirms'],
    'preview': ['preview', 'upcoming', 'what to expect', 'look ahead'],
    'review': ['review', 'recap', 'roundup', 'summary', 'highlights']
}

# Regions for action heuristics
REGIONS = ['latam', 'brazil', 'africa', 'asia', 'europe', 'us', 'uk', 'emerging markets']


# ============================================================================
# Text Processing
# ============================================================================

def preprocess_text(text: str) -> str:
    """Preprocess text for vectorization."""
    if not text or not isinstance(text, str):
        return ""
    # Use existing normalizer
    return normalize_text(text)


def combine_article_text(row: pd.Series) -> str:
    """Combine title, summary, content into single text."""
    parts = []
    for field in ['title', 'summary', 'content']:
        val = row.get(field)
        if val and isinstance(val, str) and val.strip():
            parts.append(val)
    return ' '.join(parts)


def count_words(text: str) -> int:
    """Count words in text."""
    if not text:
        return 0
    return len(text.split())


def detect_format(row: pd.Series) -> str:
    """Detect article format from title and summary."""
    text = f"{row.get('title', '')} {row.get('summary', '')}".lower()

    format_scores = {}
    for fmt, keywords in FORMAT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            format_scores[fmt] = score

    if format_scores:
        return max(format_scores, key=format_scores.get)
    return 'news'


def extract_regions_mentioned(text: str) -> list[str]:
    """Extract regions mentioned in text."""
    text_lower = text.lower() if text else ""
    found = []
    for region in REGIONS:
        if region in text_lower:
            found.append(region)
    return found


def extract_companies_mentioned(text: str) -> list[str]:
    """Extract company names from text (simple heuristic)."""
    # Look for capitalized words that might be company names
    if not text:
        return []
    # Simple pattern: capitalized words not at sentence start
    words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
    # Filter common non-company words
    stopwords = {'The', 'This', 'That', 'These', 'Their', 'Monday', 'Tuesday',
                 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
                 'January', 'February', 'March', 'April', 'May', 'June',
                 'July', 'August', 'September', 'October', 'November', 'December'}
    return [w for w in words if w not in stopwords][:5]


# ============================================================================
# Window Building
# ============================================================================

def build_window_df(df_history: pd.DataFrame, window_days: int = 30) -> pd.DataFrame:
    """
    Build windowed DataFrame with UTC timestamps and category split.

    Args:
        df_history: Full history DataFrame
        window_days: Number of days to look back

    Returns:
        DataFrame filtered to window with normalized dates
    """
    df = df_history.copy()

    # Normalize dates to UTC
    if 'published_date_utc' not in df.columns:
        df['published_date_utc'] = pd.to_datetime(df['published_date'], errors='coerce', utc=True)
    else:
        df['published_date_utc'] = pd.to_datetime(df['published_date_utc'], errors='coerce', utc=True)

    # Filter to window
    utc_now = datetime.now(UTC)
    window_start = utc_now - timedelta(days=window_days)

    mask = (df['published_date_utc'] >= window_start) & (df['published_date_utc'] <= utc_now)
    df_window = df[mask].copy()

    # Add derived fields
    df_window['combined_text'] = df_window.apply(combine_article_text, axis=1)
    df_window['preprocessed_text'] = df_window['combined_text'].apply(preprocess_text)
    df_window['word_count'] = df_window['combined_text'].apply(count_words)
    df_window['article_format'] = df_window.apply(detect_format, axis=1)
    df_window['is_internal'] = df_window['category'] == 'internal'

    # Extract hour and day of week for timeliness
    df_window['publish_hour'] = df_window['published_date_utc'].dt.hour
    df_window['publish_dow'] = df_window['published_date_utc'].dt.dayofweek  # 0=Mon, 6=Sun
    df_window['is_weekend'] = df_window['publish_dow'] >= 5

    return df_window


# ============================================================================
# Topic Clustering
# ============================================================================

def find_optimal_k(X_svd: np.ndarray, min_k: int = MIN_TOPICS, max_k: int = MAX_TOPICS) -> int:
    """
    Find optimal number of clusters using knee/elbow heuristic.

    Args:
        X_svd: SVD-reduced feature matrix
        min_k: Minimum clusters to try
        max_k: Maximum clusters to try

    Returns:
        Optimal k value
    """
    n_samples = X_svd.shape[0]
    max_k = min(max_k, n_samples // MIN_TOPIC_SIZE)

    if max_k < min_k:
        return max(min_k, 2)

    inertias = []
    k_range = range(min_k, max_k + 1)

    for k in k_range:
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=300)
        kmeans.fit(X_svd)
        inertias.append(kmeans.inertia_)

    if len(inertias) < 3:
        return min_k

    # Find knee using simple second derivative
    inertias = np.array(inertias)

    # Normalize inertias for better knee detection
    if inertias[0] > 0:
        inertias_norm = inertias / inertias[0]
    else:
        return min_k

    # Second derivative (discrete)
    first_diff = np.diff(inertias_norm)
    second_diff = np.diff(first_diff)

    # Knee is where second derivative is maximum (most positive)
    if len(second_diff) > 0:
        knee_idx = np.argmax(second_diff) + 1  # +1 because of diff offset
        optimal_k = list(k_range)[knee_idx]
    else:
        optimal_k = min_k

    return optimal_k


def build_topics(df_window: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    """
    Build topic clusters from windowed articles.

    Args:
        df_window: Windowed DataFrame with preprocessed_text

    Returns:
        Tuple of (df with cluster assignments, cluster labels, top terms per cluster)
    """
    df = df_window.copy()

    # Filter out empty texts
    df = df[df['preprocessed_text'].str.len() > 10].copy()

    if len(df) < MIN_TOPIC_SIZE * 2:
        # Not enough data for clustering
        df['cluster'] = 0
        return df, np.array([0] * len(df)), ['general']

    # Vectorize with TF-IDF
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=2,
        max_features=20000,
        stop_words='english'
    )

    try:
        X_tfidf = vectorizer.fit_transform(df['preprocessed_text'])
    except ValueError:
        # Vocabulary is empty
        df['cluster'] = 0
        return df, np.array([0] * len(df)), ['general']

    feature_names = vectorizer.get_feature_names_out()

    # Reduce dimensions with SVD
    n_components = min(100, X_tfidf.shape[1] - 1, X_tfidf.shape[0] - 1)
    if n_components < 2:
        df['cluster'] = 0
        return df, np.array([0] * len(df)), ['general']

    svd = TruncatedSVD(n_components=n_components, random_state=42)
    X_svd = svd.fit_transform(X_tfidf)

    # Find optimal k
    optimal_k = find_optimal_k(X_svd)

    # Cluster with KMeans
    kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=10, max_iter=300)
    cluster_labels = kmeans.fit_predict(X_svd)

    df['cluster'] = cluster_labels

    # Generate topic labels from top TF-IDF terms per cluster
    topic_labels = []
    for cluster_id in range(optimal_k):
        cluster_mask = cluster_labels == cluster_id
        if cluster_mask.sum() == 0:
            topic_labels.append(f"topic_{cluster_id}")
            continue

        # Get mean TF-IDF for this cluster
        cluster_tfidf = X_tfidf[cluster_mask].mean(axis=0).A1
        top_indices = cluster_tfidf.argsort()[-3:][::-1]
        top_terms = [feature_names[i] for i in top_indices]
        topic_labels.append(', '.join(top_terms))

    return df, cluster_labels, topic_labels


# ============================================================================
# Metric Computation
# ============================================================================

def compute_ownership_index(internal_count: int, competitor_count: int) -> float:
    """O = internal_count / max(1, internal + competitor)"""
    total = internal_count + competitor_count
    if total == 0:
        return 0.0
    return internal_count / total


def compute_exclusivity_index(df_topic: pd.DataFrame) -> float:
    """
    E = internal_only_count / max(1, internal_count)

    An article is "internal only" if competitors don't have similar coverage
    (approximated by checking if topic has low competitor presence).
    """
    internal_df = df_topic[df_topic['is_internal']]
    competitor_df = df_topic[~df_topic['is_internal']]

    internal_count = len(internal_df)
    if internal_count == 0:
        return 0.0

    # If competitors have very few articles in this topic, our articles are "exclusive"
    competitor_count = len(competitor_df)
    if competitor_count == 0:
        return 1.0

    # Ratio-based exclusivity
    ratio = internal_count / (internal_count + competitor_count)
    # Scale so high ownership = high exclusivity
    return min(1.0, ratio * 1.5)


def compute_timeliness_index(df_topic: pd.DataFrame) -> float:
    """
    T = timeliness advantage based on weekend coverage and publish timing.
    """
    internal_df = df_topic[df_topic['is_internal']]
    competitor_df = df_topic[~df_topic['is_internal']]

    if len(internal_df) == 0:
        return 0.0

    # Weekend coverage advantage
    internal_weekend_pct = internal_df['is_weekend'].mean() if len(internal_df) > 0 else 0
    competitor_weekend_pct = competitor_df['is_weekend'].mean() if len(competitor_df) > 0 else 0

    weekend_advantage = 0.0
    if internal_weekend_pct > competitor_weekend_pct:
        weekend_advantage = min(1.0, (internal_weekend_pct - competitor_weekend_pct) * 3)

    # Publish hour advantage (earlier in day = more timely for breaking news)
    if len(competitor_df) > 0 and len(internal_df) > 0:
        internal_median_hour = internal_df['publish_hour'].median()
        competitor_median_hour = competitor_df['publish_hour'].median()

        # Earlier publish = better (scaled)
        hour_advantage = 0.0
        if internal_median_hour < competitor_median_hour:
            hour_diff = competitor_median_hour - internal_median_hour
            hour_advantage = min(1.0, hour_diff / 6)  # 6 hours earlier = max advantage
    else:
        hour_advantage = 0.5  # Neutral if no comparison

    # Combine
    return 0.6 * weekend_advantage + 0.4 * hour_advantage


def compute_depth_index(df_topic: pd.DataFrame) -> float:
    """
    D = clipped z-score of internal word_count vs competitor, mapped to [0,1].
    """
    internal_df = df_topic[df_topic['is_internal']]
    competitor_df = df_topic[~df_topic['is_internal']]

    if len(internal_df) == 0:
        return 0.0

    internal_median_words = internal_df['word_count'].median()

    if len(competitor_df) == 0:
        # No competitor baseline, assume neutral advantage
        return 0.5

    competitor_median_words = competitor_df['word_count'].median()
    competitor_std = competitor_df['word_count'].std()

    if competitor_std == 0 or pd.isna(competitor_std):
        competitor_std = 100  # Default std

    # Z-score
    z = (internal_median_words - competitor_median_words) / competitor_std

    # Clip to [-2, 2] and map to [0, 1]
    z_clipped = max(-2, min(2, z))
    return (z_clipped + 2) / 4


def compute_format_edge(df_topic: pd.DataFrame) -> float:
    """
    F = share of internal articles in over-indexed high-value formats.
    """
    internal_df = df_topic[df_topic['is_internal']]
    competitor_df = df_topic[~df_topic['is_internal']]

    if len(internal_df) == 0:
        return 0.0

    # Count formats
    internal_formats = Counter(internal_df['article_format'])
    competitor_formats = Counter(competitor_df['article_format'])

    internal_total = len(internal_df)
    competitor_total = max(1, len(competitor_df))

    # Find over-indexed high-value formats
    over_indexed_count = 0
    for fmt in HIGH_VALUE_FORMATS:
        internal_share = internal_formats.get(fmt, 0) / internal_total
        competitor_share = competitor_formats.get(fmt, 0) / competitor_total

        # Check if internal is 1.5x or more than competitor
        if competitor_share > 0:
            ratio = internal_share / competitor_share
            if ratio >= 1.5:
                over_indexed_count += internal_formats.get(fmt, 0)
        elif internal_share > 0:
            # We have it, they don't
            over_indexed_count += internal_formats.get(fmt, 0)

    return min(1.0, over_indexed_count / internal_total)


def compute_differentiator_score(O: float, E: float, T: float, D: float, F: float) -> float:
    """
    S = weighted combination of indices.
    """
    return (
        WEIGHT_OWNERSHIP * O +
        WEIGHT_EXCLUSIVITY * E +
        WEIGHT_TIMELINESS * T +
        WEIGHT_DEPTH * D +
        WEIGHT_FORMAT * F
    )


# ============================================================================
# Action Generation
# ============================================================================

def generate_actions(topic_data: dict, df_topic: pd.DataFrame) -> list[str]:
    """
    Generate 3 actionable bullets based on topic metrics.
    """
    actions = []
    O = topic_data['ownership']
    E = topic_data['exclusivity']
    T = topic_data['timeliness']
    D = topic_data['depth']
    F = topic_data['format_edge']

    internal_df = df_topic[df_topic['is_internal']]

    # Extract context for personalized actions
    all_text = ' '.join(internal_df['combined_text'].tolist())
    regions = extract_regions_mentioned(all_text)
    companies = extract_companies_mentioned(all_text)

    # Format-based actions
    if F >= 0.5:
        dominant_formats = Counter(internal_df['article_format']).most_common(2)
        fmt_names = [f[0] for f in dominant_formats]
        actions.append(f"Double down on {' and '.join(fmt_names)} formats - these are winning for this topic.")
    elif F < 0.3:
        actions.append("Add explainer or data story content to increase depth and differentiation.")

    # Timeliness-based actions
    if T >= 0.5 and O < 0.7:
        actions.append("Leverage your speed advantage - publish breaking news faster to capture more ownership.")
    elif T < 0.3:
        actions.append("Improve publish cadence - consider weekend coverage to reach audiences competitors miss.")

    # Exclusivity-based actions
    if E >= 0.5:
        actions.append("Launch an editorial series to defend your exclusive position in this topic.")
    elif E < 0.3 and O >= 0.5:
        actions.append("Differentiate with unique angles - competitors cover this too, find untold stories.")

    # Depth-based actions
    if D < 0.4:
        actions.append("Increase article depth with expert quotes, data, and analysis.")
    elif D >= 0.6:
        actions.append("Your depth advantage is strong - promote these pieces as definitive resources.")

    # Region/company specific
    if regions and len(actions) < 3:
        top_region = regions[0]
        actions.append(f"Expand {top_region} coverage with local expert interviews and market analysis.")

    if companies and len(actions) < 3:
        top_company = companies[0]
        actions.append(f"Pursue exclusive interview with {top_company} leadership on this topic.")

    # Ensure exactly 3 actions
    default_actions = [
        "Publish 2 pieces per week on this topic to maintain leadership.",
        "Create a topic hub page to aggregate all coverage.",
        "Develop a newsletter segment dedicated to this topic."
    ]

    while len(actions) < 3:
        for da in default_actions:
            if da not in actions:
                actions.append(da)
                break
        if len(actions) >= 3:
            break

    return actions[:3]


def generate_risk(topic_data: dict) -> str:
    """
    Generate risk statement based on topic metrics.
    """
    E = topic_data['exclusivity']
    O = topic_data['ownership']
    competitor_count = topic_data['competitor_count']

    if E >= 0.7:
        return "High exclusivity protects you, but competitors can close the gap in 4-6 weeks if they prioritize this topic."
    elif E >= 0.4:
        return "Competitors can close the gap in 2-3 weeks based on their current cadence."
    elif competitor_count > 0:
        return "Competitors are already active here - stopping coverage would cede ground within 1-2 weeks."
    else:
        return "Low immediate risk, but first-mover advantage will erode without continued investment."


# ============================================================================
# Main Assembly
# ============================================================================

def compute_topic_metrics(df_window: pd.DataFrame, cluster_labels: np.ndarray,
                          topic_labels: list[str]) -> list[dict]:
    """
    Compute all metrics for each topic cluster.
    """
    topics = []
    unique_clusters = sorted(set(cluster_labels))

    for cluster_id in unique_clusters:
        df_topic = df_window[df_window['cluster'] == cluster_id].copy()

        # Skip small topics
        if len(df_topic) < MIN_TOPIC_SIZE:
            continue

        internal_df = df_topic[df_topic['is_internal']]
        competitor_df = df_topic[~df_topic['is_internal']]

        internal_count = len(internal_df)
        competitor_count = len(competitor_df)

        # Skip topics with too few internal articles
        if internal_count < MIN_INTERNAL_COUNT:
            continue

        # Compute indices
        O = compute_ownership_index(internal_count, competitor_count)
        E = compute_exclusivity_index(df_topic)
        T = compute_timeliness_index(df_topic)
        D = compute_depth_index(df_topic)
        F = compute_format_edge(df_topic)

        # Check thresholds
        if O < MIN_OWNERSHIP_THRESHOLD and E < MIN_EXCLUSIVITY_THRESHOLD:
            continue

        # Compute score
        S = compute_differentiator_score(O, E, T, D, F)

        # Get example articles (latest internal)
        examples = []
        if len(internal_df) > 0:
            internal_sorted = internal_df.sort_values('published_date_utc', ascending=False)
            for _, row in internal_sorted.head(MAX_EXAMPLES_PER_TOPIC).iterrows():
                examples.append({
                    'title': row.get('title', ''),
                    'link': row.get('link', ''),
                    'published_date_utc': row['published_date_utc'].isoformat() if pd.notna(row['published_date_utc']) else ''
                })

        # Diagnostics
        diagnostics = {
            'median_words_internal': int(internal_df['word_count'].median()) if len(internal_df) > 0 else 0,
            'median_words_competitor': int(competitor_df['word_count'].median()) if len(competitor_df) > 0 else 0,
            'internal_weekend_pct': round(internal_df['is_weekend'].mean() * 100, 1) if len(internal_df) > 0 else 0,
            'competitor_weekend_pct': round(competitor_df['is_weekend'].mean() * 100, 1) if len(competitor_df) > 0 else 0
        }

        topic_data = {
            'topic_id': f"t_{cluster_id:03d}",
            'label': topic_labels[cluster_id] if cluster_id < len(topic_labels) else f"topic_{cluster_id}",
            'score': round(S, 3),
            'ownership': round(O, 3),
            'exclusivity': round(E, 3),
            'timeliness': round(T, 3),
            'depth': round(D, 3),
            'format_edge': round(F, 3),
            'internal_count': internal_count,
            'competitor_count': competitor_count,
            'examples': examples,
            'diagnostics': diagnostics
        }

        # Generate actions and risk
        topic_data['actions'] = generate_actions(topic_data, df_topic)
        topic_data['risk'] = generate_risk(topic_data)

        topics.append(topic_data)

    # Sort by score descending
    topics.sort(key=lambda x: x['score'], reverse=True)

    return topics[:TOP_N_TOPICS * 2]  # Return more than needed for UI flexibility


def compute_global_notes(df_window: pd.DataFrame) -> dict:
    """
    Compute global insights across all topics.
    """
    internal_df = df_window[df_window['is_internal']]
    competitor_df = df_window[~df_window['is_internal']]

    # Weekend advantage
    int_weekend = internal_df['is_weekend'].mean() * 100 if len(internal_df) > 0 else 0
    comp_weekend = competitor_df['is_weekend'].mean() * 100 if len(competitor_df) > 0 else 0

    if int_weekend > comp_weekend:
        weekend_advantage = f"Clarion leads with {int_weekend:.1f}% weekend coverage vs competitors' {comp_weekend:.1f}%"
    else:
        weekend_advantage = f"Competitors lead with {comp_weekend:.1f}% weekend coverage vs our {int_weekend:.1f}%"

    # Region edge
    region_edges = []
    for region in REGIONS:
        int_mentions = internal_df['combined_text'].str.lower().str.contains(region).sum()
        comp_mentions = competitor_df['combined_text'].str.lower().str.contains(region).sum()

        int_rate = int_mentions / max(1, len(internal_df))
        comp_rate = comp_mentions / max(1, len(competitor_df))

        if comp_rate > 0:
            ratio = int_rate / comp_rate
            if ratio >= 1.3:
                region_edges.append({
                    'region': region.title(),
                    'ratio': round(ratio, 2),
                    'internal_mentions': int(int_mentions),
                    'competitor_mentions': int(comp_mentions)
                })

    region_edges.sort(key=lambda x: x['ratio'], reverse=True)

    # Format summary
    format_summary = []
    internal_formats = Counter(internal_df['article_format'])
    competitor_formats = Counter(competitor_df['article_format'])

    int_total = max(1, len(internal_df))
    comp_total = max(1, len(competitor_df))

    for fmt in FORMAT_KEYWORDS.keys():
        int_share = internal_formats.get(fmt, 0) / int_total
        comp_share = competitor_formats.get(fmt, 0) / comp_total

        ratio = int_share / comp_share if comp_share > 0 else (2.0 if int_share > 0 else 1.0)

        format_summary.append({
            'format': fmt.title(),
            'internal_share': round(int_share * 100, 1),
            'competitor_share': round(comp_share * 100, 1),
            'ratio_vs_comp': round(ratio, 2)
        })

    format_summary.sort(key=lambda x: x['ratio_vs_comp'], reverse=True)

    return {
        'weekend_advantage': weekend_advantage,
        'region_edge': region_edges[:5],
        'format_summary': format_summary
    }


def build_differentiators_v2(df_history: pd.DataFrame, window_days: int = 30) -> dict:
    """
    Main entry point: build complete differentiators v2 analysis.

    Args:
        df_history: Full article history DataFrame
        window_days: Analysis window in days

    Returns:
        Complete differentiators_v2 dict for JSON storage
    """
    # Build window
    df_window = build_window_df(df_history, window_days)

    if len(df_window) < MIN_TOPIC_SIZE * 2:
        return {
            'generated_at_utc': datetime.now(UTC).isoformat(),
            'window_days': window_days,
            'topics': [],
            'global_notes': {
                'weekend_advantage': 'Insufficient data',
                'region_edge': [],
                'format_summary': []
            },
            'error': 'Insufficient articles in window for topic clustering'
        }

    # Build topics
    df_clustered, cluster_labels, topic_labels = build_topics(df_window)

    # Compute metrics
    topics = compute_topic_metrics(df_clustered, cluster_labels, topic_labels)

    # Global notes
    global_notes = compute_global_notes(df_window)

    # Assemble result
    result = {
        'generated_at_utc': datetime.now(UTC).isoformat(),
        'window_days': window_days,
        'total_articles_in_window': len(df_window),
        'internal_articles': int(df_window['is_internal'].sum()),
        'competitor_articles': int((~df_window['is_internal']).sum()),
        'topics_surfaced': len(topics),
        'topics': topics,
        'global_notes': global_notes
    }

    # Ensure JSON serializable
    return _make_json_serializable(result)


def _make_json_serializable(obj):
    """Recursively convert numpy/pandas types to native Python types."""
    import numpy as np

    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_json_serializable(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif pd.isna(obj):
        return None
    else:
        return obj


# ============================================================================
# Content Brief Generation
# ============================================================================

def generate_content_brief(topic: dict, window_days: int = 30) -> str:
    """
    Generate a markdown content brief for a topic.

    Args:
        topic: Topic dict from differentiators_v2
        window_days: Analysis window

    Returns:
        Markdown string for the brief
    """
    label = topic['label']
    score = topic['score']
    O = topic['ownership']
    E = topic['exclusivity']
    actions = topic.get('actions', [])
    examples = topic.get('examples', [])
    diagnostics = topic.get('diagnostics', {})

    # Generate headline options
    terms = [t.strip() for t in label.split(',')]
    headlines = [
        f"The Definitive Guide to {terms[0].title() if terms else 'This Topic'} in iGaming",
        f"Why {terms[0].title() if terms else 'This'} Matters: An Expert Analysis",
        f"{terms[0].title() if terms else 'Topic'} Trends: What Every Operator Needs to Know"
    ]

    # Determine format suggestion
    if topic['format_edge'] >= 0.5:
        format_suggestion = "Deep analysis or explainer - your strength in this area"
    elif topic['depth'] < 0.4:
        format_suggestion = "Data story with original research to increase depth"
    else:
        format_suggestion = "Interview with industry expert for unique perspective"

    # Target persona
    if 'regulation' in label.lower() or 'compliance' in label.lower():
        persona = "Compliance officers and legal teams at operators"
    elif 'product' in label.lower() or 'launch' in label.lower():
        persona = "Product managers and innovation leads"
    elif 'market' in label.lower() or 'expansion' in label.lower():
        persona = "Business development and market entry teams"
    else:
        persona = "Senior executives and industry decision-makers"

    # Build outline
    outline = f"""## H2 Sections

1. **Introduction: Why {terms[0].title() if terms else 'This Topic'} Matters Now**
   - Hook with latest development
   - Context on industry significance

2. **The Current Landscape**
   - Key players and their positions
   - Recent developments (last {window_days} days)

3. **Expert Perspectives**
   - Quotes from industry leaders
   - Analysis of different viewpoints

4. **What This Means for Operators**
   - Practical implications
   - Action items for readers

5. **Looking Ahead**
   - Predictions for next 6-12 months
   - Key indicators to watch
"""

    # Sources to quote
    sources = []
    for ex in examples[:3]:
        sources.append(f"- {ex.get('title', 'Article')} ([link]({ex.get('link', '#')}))")

    brief = f"""# Content Brief: {label.title()}

**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}
**Topic Score:** {score:.2f}
**Ownership:** {O*100:.0f}% | **Exclusivity:** {E*100:.0f}%

---

## Proposed Headlines (pick one)

1. {headlines[0]}
2. {headlines[1]}
3. {headlines[2]}

---

## Editorial Direction

**Angle:** We own this topic with {topic['internal_count']} articles in the last {window_days} days vs {topic['competitor_count']} from competitors. Reinforce leadership with authoritative content.

**Format Suggestion:** {format_suggestion}

**Target Persona:** {persona}

**Word Count Target:** {max(800, diagnostics.get('median_words_internal', 600) + 200)} words (above current median)

---

{outline}

---

## Sources to Quote/Reference

{chr(10).join(sources) if sources else '- Research additional sources'}

---

## Key Actions

{chr(10).join(f'{i+1}. {a}' for i, a in enumerate(actions))}

---

## Risk Note

{topic.get('risk', 'Monitor competitor activity in this space.')}

---

*Brief generated by Clarion Competitive Intelligence System*
"""

    return brief
