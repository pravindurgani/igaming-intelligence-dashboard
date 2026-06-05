"""
Differentiators extraction module.

Identifies what the tracked portfolio covers that competitors don't:
- Language differentiators via log-odds analysis
- Entity/company coverage differentiators
- Region/geography advantages
- Format differentiators (guides, interviews, etc.)
- Cadence/timeliness metrics

Uses log-odds with smoothed prior for robust corpus comparison.
"""

import math
import re
from collections import Counter
from datetime import UTC, datetime

import pandas as pd

# Try sklearn for n-gram extraction, fall back to simple tokenization
try:
    from sklearn.feature_extraction.text import CountVectorizer
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from src.textnorm import normalize_text

# ============================================================================
# Text Preprocessing
# ============================================================================

def preprocess_for_ngrams(text: str) -> str:
    """
    Preprocess text for n-gram extraction.

    Transformations:
    1. Strip HTML tags
    2. Normalize unicode (via textnorm)
    3. Split camelCase (via textnorm)
    4. Lowercase
    5. Collapse whitespace

    Args:
        text: Raw text input

    Returns:
        Cleaned text suitable for n-gram extraction
    """
    if not text or not isinstance(text, str):
        return ""

    # Strip HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)

    # Use existing normalizer (handles accents, camelCase, etc.)
    text = normalize_text(text)

    return text


def build_corpus(df: pd.DataFrame, text_fields: tuple[str, ...] = ('title', 'summary', 'content')) -> str:
    """
    Build a single corpus string from a DataFrame of articles.

    Args:
        df: DataFrame with articles
        text_fields: Fields to concatenate

    Returns:
        Single preprocessed corpus string
    """
    parts = []
    for _, row in df.iterrows():
        for field in text_fields:
            val = row.get(field)
            if val and isinstance(val, str) and val.strip():
                parts.append(preprocess_for_ngrams(val))

    return ' '.join(parts)


# ============================================================================
# N-gram Extraction
# ============================================================================

def extract_ngrams_sklearn(corpus: str, ngram_range: tuple[int, int] = (1, 3),
                           min_df: int = 1, max_features: int = 10000) -> Counter:
    """
    Extract n-grams using sklearn CountVectorizer.

    Args:
        corpus: Preprocessed text corpus
        ngram_range: (min_n, max_n) for n-gram sizes
        min_df: Minimum document frequency
        max_features: Maximum vocabulary size

    Returns:
        Counter of {ngram: count}
    """
    if not corpus.strip():
        return Counter()

    vectorizer = CountVectorizer(
        ngram_range=ngram_range,
        min_df=min_df,
        max_features=max_features,
        token_pattern=r'\b[a-z][a-z0-9]+\b'  # Words starting with letter, 2+ chars
    )

    try:
        # Fit on single document (the corpus)
        X = vectorizer.fit_transform([corpus])
        feature_names = vectorizer.get_feature_names_out()
        counts = X.toarray()[0]

        return Counter(dict(zip(feature_names, counts)))
    except ValueError:
        # Empty vocabulary
        return Counter()


def extract_ngrams_simple(corpus: str, ngram_range: tuple[int, int] = (1, 3)) -> Counter:
    """
    Simple fallback n-gram extraction without sklearn.

    Args:
        corpus: Preprocessed text corpus
        ngram_range: (min_n, max_n) for n-gram sizes

    Returns:
        Counter of {ngram: count}
    """
    if not corpus.strip():
        return Counter()

    # Tokenize
    tokens = re.findall(r'\b[a-z][a-z0-9]+\b', corpus.lower())

    ngram_counts = Counter()
    min_n, max_n = ngram_range

    for n in range(min_n, max_n + 1):
        for i in range(len(tokens) - n + 1):
            ngram = ' '.join(tokens[i:i+n])
            ngram_counts[ngram] += 1

    return ngram_counts


def extract_ngrams(corpus: str, ngram_range: tuple[int, int] = (1, 3),
                   min_df: int = 1, max_features: int = 10000) -> Counter:
    """
    Extract n-grams from corpus, using sklearn if available.
    """
    if HAS_SKLEARN:
        return extract_ngrams_sklearn(corpus, ngram_range, min_df, max_features)
    else:
        return extract_ngrams_simple(corpus, ngram_range)


# ============================================================================
# Log-Odds Calculation
# ============================================================================

def log_odds_ratio(count_a: int, total_a: int, count_b: int, total_b: int,
                   prior_weight: float = 1.0) -> float:
    """
    Calculate log-odds ratio with smoothed prior (informative Dirichlet prior).

    Uses Monroe et al. (2008) approach for fighting words:
    - Adds prior_weight to both counts to prevent divide-by-zero
    - Normalizes by corpus size

    Positive values = more associated with corpus A (internal/portfolio)
    Negative values = more associated with corpus B (competitors)

    Args:
        count_a: Count of term in corpus A (internal)
        total_a: Total term count in corpus A
        count_b: Count of term in corpus B (competitor)
        total_b: Total term count in corpus B
        prior_weight: Smoothing parameter (default 1.0 for Laplace)

    Returns:
        Log-odds ratio (positive = portfolio advantage)
    """
    # Add smoothing
    smoothed_a = count_a + prior_weight
    smoothed_b = count_b + prior_weight

    # Normalize by corpus size (add prior to totals too)
    total_a_smooth = total_a + prior_weight * 2  # Account for smoothing in numerator
    total_b_smooth = total_b + prior_weight * 2

    # Calculate proportions
    prop_a = smoothed_a / total_a_smooth
    prop_b = smoothed_b / total_b_smooth

    # Log-odds ratio
    return math.log(prop_a / prop_b)


def calculate_log_odds_scores(internal_counts: Counter, competitor_counts: Counter,
                              min_count: int = 3, prior_weight: float = 1.0) -> dict[str, float]:
    """
    Calculate log-odds scores for all terms in both corpora.

    Args:
        internal_counts: Counter of n-grams in internal corpus
        competitor_counts: Counter of n-grams in competitor corpus
        min_count: Minimum total count across both corpora to include term
        prior_weight: Smoothing parameter

    Returns:
        Dict of {term: log_odds_score}
    """
    # Get all terms
    all_terms = set(internal_counts.keys()) | set(competitor_counts.keys())

    # Get totals
    total_internal = sum(internal_counts.values())
    total_competitor = sum(competitor_counts.values())

    if total_internal == 0 or total_competitor == 0:
        return {}

    scores = {}
    for term in all_terms:
        count_i = internal_counts.get(term, 0)
        count_c = competitor_counts.get(term, 0)

        # Skip rare terms
        if count_i + count_c < min_count:
            continue

        score = log_odds_ratio(count_i, total_internal, count_c, total_competitor, prior_weight)
        scores[term] = score

    return scores


# ============================================================================
# Differentiator Extraction
# ============================================================================

# Stopwords to filter out from differentiators
STOPWORDS = {
    'the', 'and', 'for', 'that', 'with', 'this', 'from', 'will', 'are', 'was',
    'have', 'has', 'been', 'their', 'more', 'new', 'its', 'also', 'but', 'not',
    'than', 'into', 'can', 'which', 'about', 'other', 'out', 'one', 'all', 'who',
    'said', 'they', 'were', 'what', 'when', 'there', 'your', 'how', 'had', 'would',
    'could', 'just', 'some', 'over', 'such', 'only', 'after', 'most', 'any', 'through',
    # Industry generic terms
    'gaming', 'igaming', 'betting', 'gambling', 'casino', 'online', 'industry',
    'market', 'company', 'companies', 'business', 'operator', 'operators', 'player',
    'players', 'game', 'games', 'sports', 'sportsbook', 'esports'
}


def is_meaningful_term(term: str) -> bool:
    """Check if a term is meaningful (not a stopword or too generic)."""
    # Split into words
    words = term.split()

    # Single word checks
    if len(words) == 1:
        return words[0] not in STOPWORDS and len(words[0]) > 2

    # Multi-word: at least one non-stopword
    return any(w not in STOPWORDS and len(w) > 2 for w in words)


def extract_term_differentiators(internal_counts: Counter, competitor_counts: Counter,
                                  top_n: int = 20, min_count: int = 3) -> list[dict]:
    """
    Extract top language/term differentiators using log-odds.

    Args:
        internal_counts: N-gram counts for internal corpus
        competitor_counts: N-gram counts for competitor corpus
        top_n: Number of top differentiators to return
        min_count: Minimum count threshold

    Returns:
        List of {term, log_odds, internal_count, competitor_count, advantage}
    """
    scores = calculate_log_odds_scores(internal_counts, competitor_counts, min_count)

    # Filter meaningful terms and sort by absolute score
    meaningful_scores = {k: v for k, v in scores.items() if is_meaningful_term(k)}

    # Get top portfolio advantages (positive log-odds)
    portfolio_terms = sorted(
        [(term, score) for term, score in meaningful_scores.items() if score > 0],
        key=lambda x: x[1],
        reverse=True
    )[:top_n]

    results = []
    for term, score in portfolio_terms:
        results.append({
            'term': term,
            'log_odds': round(score, 3),
            'internal_count': internal_counts.get(term, 0),
            'competitor_count': competitor_counts.get(term, 0),
            'advantage': 'portfolio'
        })

    return results


# ============================================================================
# Company/Entity Differentiators
# ============================================================================

# Known iGaming companies for entity detection
KNOWN_COMPANIES = {
    'draftkings', 'fanduel', 'betmgm', 'caesars', 'pointsbet', 'barstool',
    'bet365', 'william hill', 'ladbrokes', 'coral', 'paddy power', 'betfair',
    'flutter', 'entain', 'kindred', 'betsson', '888', 'unibet', 'bwin',
    'evolution', 'netent', 'playtech', 'igt', 'scientific games', 'aristocrat',
    'sportradar', 'genius sports', 'img arena', 'betgenius', 'kambi',
    'softswiss', 'betconstruct', 'digitain', 'altenar', 'sbtech',
    'microgaming', 'pragmatic play', 'yggdrasil', 'big time gaming', 'red tiger',
    'igb', 'ice', 'sigma', 'sbc', 'egr', 'gambling insider'
}


def extract_company_mentions(corpus: str) -> Counter:
    """
    Extract company/brand mentions from corpus.

    Args:
        corpus: Preprocessed text corpus

    Returns:
        Counter of {company: count}
    """
    corpus_lower = corpus.lower()
    mentions = Counter()

    for company in KNOWN_COMPANIES:
        # Count occurrences
        count = corpus_lower.count(company)
        if count > 0:
            mentions[company] = count

    return mentions


def extract_company_differentiators(internal_df: pd.DataFrame, competitor_df: pd.DataFrame,
                                     top_n: int = 10) -> list[dict]:
    """
    Find companies mentioned more by the tracked portfolio than competitors.

    Args:
        internal_df: Internal articles DataFrame
        competitor_df: Competitor articles DataFrame
        top_n: Number of top differentiators

    Returns:
        List of {company, internal_mentions, competitor_mentions, ratio}
    """
    internal_corpus = build_corpus(internal_df)
    competitor_corpus = build_corpus(competitor_df)

    internal_mentions = extract_company_mentions(internal_corpus)
    competitor_mentions = extract_company_mentions(competitor_corpus)

    # Normalize by corpus size (articles)
    internal_size = max(len(internal_df), 1)
    competitor_size = max(len(competitor_df), 1)

    results = []
    all_companies = set(internal_mentions.keys()) | set(competitor_mentions.keys())

    for company in all_companies:
        int_count = internal_mentions.get(company, 0)
        comp_count = competitor_mentions.get(company, 0)

        # Skip our own brands
        if company in {'igb', 'ice'}:
            continue

        # Normalize per-article rate
        int_rate = int_count / internal_size
        comp_rate = comp_count / competitor_size

        # Calculate advantage ratio (with smoothing)
        ratio = (int_rate + 0.01) / (comp_rate + 0.01)

        if ratio > 1.2:  # At least 20% more coverage
            results.append({
                'company': company.title(),
                'internal_mentions': int_count,
                'competitor_mentions': comp_count,
                'internal_rate': round(int_rate, 3),
                'competitor_rate': round(comp_rate, 3),
                'advantage_ratio': round(ratio, 2)
            })

    # Sort by advantage ratio
    results.sort(key=lambda x: x['advantage_ratio'], reverse=True)
    return results[:top_n]


# ============================================================================
# Region/Geography Differentiators
# ============================================================================

REGIONS = {
    'latam': ['brazil', 'mexico', 'argentina', 'colombia', 'peru', 'chile', 'latin america', 'latam'],
    'africa': ['africa', 'nigeria', 'kenya', 'south africa', 'ghana', 'african'],
    'asia': ['asia', 'japan', 'philippines', 'macau', 'singapore', 'asian', 'apac'],
    'europe': ['europe', 'uk', 'germany', 'spain', 'italy', 'france', 'european', 'emea'],
    'north_america': ['usa', 'us ', 'united states', 'canada', 'american', 'north america'],
    'emerging': ['emerging markets', 'frontier markets', 'developing']
}


def extract_region_mentions(corpus: str) -> dict[str, int]:
    """Extract region mentions from corpus."""
    corpus_lower = corpus.lower()
    region_counts = {}

    for region, keywords in REGIONS.items():
        count = sum(corpus_lower.count(kw) for kw in keywords)
        if count > 0:
            region_counts[region] = count

    return region_counts


def extract_region_differentiators(internal_df: pd.DataFrame, competitor_df: pd.DataFrame) -> list[dict]:
    """
    Find regions covered more by the tracked portfolio than competitors.

    Returns:
        List of {region, internal_mentions, competitor_mentions, advantage_ratio}
    """
    internal_corpus = build_corpus(internal_df)
    competitor_corpus = build_corpus(competitor_df)

    internal_regions = extract_region_mentions(internal_corpus)
    competitor_regions = extract_region_mentions(competitor_corpus)

    # Normalize
    internal_size = max(len(internal_df), 1)
    competitor_size = max(len(competitor_df), 1)

    results = []
    for region in REGIONS.keys():
        int_count = internal_regions.get(region, 0)
        comp_count = competitor_regions.get(region, 0)

        int_rate = int_count / internal_size
        comp_rate = comp_count / competitor_size

        ratio = (int_rate + 0.01) / (comp_rate + 0.01)

        results.append({
            'region': region.replace('_', ' ').title(),
            'internal_mentions': int_count,
            'competitor_mentions': comp_count,
            'advantage_ratio': round(ratio, 2),
            'advantage': 'portfolio' if ratio > 1.0 else 'competitor'
        })

    # Sort by portfolio advantage
    results.sort(key=lambda x: x['advantage_ratio'], reverse=True)
    return results


# ============================================================================
# Format Differentiators
# ============================================================================

FORMAT_KEYWORDS = {
    'interview': ['interview', 'spoke to', 'talked to', 'q&a', 'conversation with'],
    'guide': ['guide', 'how to', 'tutorial', 'step by step', 'beginner'],
    'analysis': ['analysis', 'deep dive', 'breakdown', 'explained', 'in-depth'],
    'opinion': ['opinion', 'commentary', 'editorial', 'perspective', 'viewpoint'],
    'news': ['announces', 'launches', 'releases', 'unveils', 'reports'],
    'report': ['report', 'study', 'research', 'survey', 'findings'],
    'preview': ['preview', 'upcoming', 'what to expect', 'look ahead'],
    'review': ['review', 'recap', 'roundup', 'summary', 'highlights']
}


def classify_article_format(row: pd.Series) -> str:
    """Classify an article's format based on content."""
    text = f"{row.get('title', '')} {row.get('summary', '')}".lower()

    format_scores = {}
    for fmt, keywords in FORMAT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            format_scores[fmt] = score

    if format_scores:
        return max(format_scores, key=format_scores.get)
    return 'news'  # Default


def extract_format_differentiators(internal_df: pd.DataFrame, competitor_df: pd.DataFrame) -> list[dict]:
    """
    Compare content format distribution between corpora.

    Returns:
        List of {format, internal_pct, competitor_pct, advantage_ratio}
    """
    internal_formats = Counter(classify_article_format(row) for _, row in internal_df.iterrows())
    competitor_formats = Counter(classify_article_format(row) for _, row in competitor_df.iterrows())

    internal_total = max(sum(internal_formats.values()), 1)
    competitor_total = max(sum(competitor_formats.values()), 1)

    results = []
    for fmt in FORMAT_KEYWORDS.keys():
        int_count = internal_formats.get(fmt, 0)
        comp_count = competitor_formats.get(fmt, 0)

        int_pct = int_count / internal_total * 100
        comp_pct = comp_count / competitor_total * 100

        ratio = (int_pct + 0.1) / (comp_pct + 0.1)

        results.append({
            'format': fmt.title(),
            'internal_count': int_count,
            'competitor_count': comp_count,
            'internal_pct': round(int_pct, 1),
            'competitor_pct': round(comp_pct, 1),
            'advantage_ratio': round(ratio, 2),
            'advantage': 'portfolio' if ratio > 1.0 else 'competitor'
        })

    results.sort(key=lambda x: x['advantage_ratio'], reverse=True)
    return results


# ============================================================================
# Cadence/Timeliness Metrics
# ============================================================================

def calculate_cadence_metrics(internal_df: pd.DataFrame, competitor_df: pd.DataFrame,
                              days: int = 7) -> dict:
    """
    Calculate publishing cadence and timeliness metrics.

    Args:
        internal_df: Internal articles with published_date
        competitor_df: Competitor articles with published_date
        days: Analysis window

    Returns:
        Dict with cadence metrics
    """
    internal_count = len(internal_df)
    competitor_count = len(competitor_df)

    # Articles per day
    internal_rate = internal_count / max(days, 1)
    competitor_rate = competitor_count / max(days, 1)

    # Day of week distribution
    def get_dow_distribution(df: pd.DataFrame) -> dict[str, int]:
        if len(df) == 0:
            return {}

        if 'published_date_utc' in df.columns:
            dates = pd.to_datetime(df['published_date_utc'], errors='coerce')
        elif 'published_date' in df.columns:
            dates = pd.to_datetime(df['published_date'], errors='coerce')
        else:
            return {}

        if dates is None or len(dates) == 0:
            return {}

        dow = dates.dt.day_name().value_counts().to_dict()
        return dow

    internal_dow = get_dow_distribution(internal_df)
    competitor_dow = get_dow_distribution(competitor_df)

    # Weekend coverage ratio
    weekend_days = {'Saturday', 'Sunday'}
    int_weekend = sum(internal_dow.get(d, 0) for d in weekend_days)
    comp_weekend = sum(competitor_dow.get(d, 0) for d in weekend_days)

    int_weekend_pct = int_weekend / max(internal_count, 1) * 100
    comp_weekend_pct = comp_weekend / max(competitor_count, 1) * 100

    return {
        'analysis_days': days,
        'internal_articles': internal_count,
        'competitor_articles': competitor_count,
        'internal_daily_rate': round(internal_rate, 2),
        'competitor_daily_rate': round(competitor_rate, 2),
        'rate_ratio': round((internal_rate + 0.1) / (competitor_rate + 0.1), 2),
        'internal_weekend_pct': round(int_weekend_pct, 1),
        'competitor_weekend_pct': round(comp_weekend_pct, 1),
        'weekend_advantage': 'portfolio' if int_weekend_pct > comp_weekend_pct else 'competitor'
    }


# ============================================================================
# JSON Serialization Helper
# ============================================================================

def _make_json_serializable(obj):
    """
    Recursively convert numpy/pandas types to native Python types for JSON serialization.
    """
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
# Main Extraction Function
# ============================================================================

def extract_all_differentiators(internal_df: pd.DataFrame, competitor_df: pd.DataFrame,
                                 analysis_days: int = 7) -> dict:
    """
    Extract all differentiators between internal and competitor coverage.

    Args:
        internal_df: Internal (portfolio) articles DataFrame
        competitor_df: Competitor articles DataFrame
        analysis_days: Number of days in analysis window

    Returns:
        Complete differentiators dict for JSON storage
    """
    # Build corpora
    internal_corpus = build_corpus(internal_df)
    competitor_corpus = build_corpus(competitor_df)

    # Extract n-grams
    internal_ngrams = extract_ngrams(internal_corpus, ngram_range=(1, 3), min_df=1)
    competitor_ngrams = extract_ngrams(competitor_corpus, ngram_range=(1, 3), min_df=1)

    # Calculate all differentiators
    term_diffs = extract_term_differentiators(internal_ngrams, competitor_ngrams, top_n=20)
    company_diffs = extract_company_differentiators(internal_df, competitor_df, top_n=10)
    region_diffs = extract_region_differentiators(internal_df, competitor_df)
    format_diffs = extract_format_differentiators(internal_df, competitor_df)
    cadence = calculate_cadence_metrics(internal_df, competitor_df, days=analysis_days)

    # Find example articles for top term differentiators
    for diff in term_diffs[:5]:
        term = diff['term']
        examples = []
        for _, row in internal_df.iterrows():
            text = f"{row.get('title', '')} {row.get('summary', '')}".lower()
            if term in text:
                examples.append({
                    'title': row.get('title', ''),
                    'source': row.get('source', ''),
                    'link': row.get('link', '')
                })
                if len(examples) >= 2:
                    break
        diff['examples'] = examples

    result = {
        'generated_at': datetime.now(UTC).isoformat(),
        'analysis_window_days': analysis_days,
        'corpus_stats': {
            'internal_articles': len(internal_df),
            'competitor_articles': len(competitor_df),
            'internal_ngrams': len(internal_ngrams),
            'competitor_ngrams': len(competitor_ngrams)
        },
        'language_differentiators': term_diffs,
        'company_differentiators': company_diffs,
        'region_differentiators': region_diffs,
        'format_differentiators': format_diffs,
        'cadence_metrics': cadence,
        'summary': {
            'top_portfolio_terms': [d['term'] for d in term_diffs[:5]],
            'top_portfolio_companies': [d['company'] for d in company_diffs[:3]],
            'strongest_region': next(
                (r['region'] for r in region_diffs if r['advantage'] == 'portfolio'),
                None
            ),
            'strongest_format': next(
                (f['format'] for f in format_diffs if f['advantage'] == 'portfolio'),
                None
            )
        }
    }

    # Ensure all values are JSON serializable (convert numpy types to native Python)
    return _make_json_serializable(result)
