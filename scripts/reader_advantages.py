"""
Reader Advantages: Topic-based competitive analysis for "Why Readers Choose Us".

Scoring Rules:
- Counts articles first, THEN applies brand token filtering
- Uses explicit source_type field (internal vs competitor) for partitioning
- Selection: min_total >= 3, our_count >= 2
- Does NOT require their_count >= 2 (this was causing empty results)
- Score = 2*ownership + 1.5*edge + 1*momentum + share_diff

Key fixes over previous implementation:
- Brand tokens filtered AFTER counting (not before)
- Competitor counts from explicit source_type field
- Graceful near-advantages fallback (never empty)
- Timezone normalization to UTC before window comparisons
"""

import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# YAML is optional - use defaults if not available
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    yaml = None

# Try sklearn for TF-IDF, fall back to simple extraction
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# Try spaCy for noun chunks
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    spacy = None


# ============================================================================
# Configuration Loading
# ============================================================================

def load_config(config_path: Path) -> dict:
    """Load YAML configuration file."""
    if not YAML_AVAILABLE:
        return {}
    if config_path.exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}


def get_brand_tokens(config_dir: Path = None) -> set[str]:
    """Load brand tokens from config or return defaults."""
    if config_dir is None:
        config_dir = Path(__file__).parent.parent / 'configs'

    config = load_config(config_dir / 'brand_tokens.yml')

    tokens = set()

    # Collect all token lists
    for key in ['our_brands', 'our_domains', 'boilerplate', 'web_artifacts']:
        tokens.update(t.lower() for t in config.get(key, []))

    # Add defaults if empty
    if not tokens:
        tokens = {
            # Brand tokens - core
            'igbaffiliate', 'igamingbusiness', 'igba', 'igb',
            'clarion', 'clarionigaming', 'clarion gaming',
            'igbaffiliate.com', 'igamingbusiness.com',
            'barcelona.igbaffiliate.com', 'ggb magazine', 'ggbmagazine',
            # Web artifacts
            'read more', 'click here', 'subscribe', 'newsletter',
            'www', 'http', 'https', 'html', 'aspx',
            # Generic noise - NOT including 'com' which is too broad
            'article', 'press release', 'sponsored', 'advertisement',
            'privacy policy', 'terms of service', 'contact us', 'editorial',
        }

    return tokens


def get_thresholds(config_dir: Path = None) -> dict:
    """Load thresholds from config or return defaults."""
    if config_dir is None:
        config_dir = Path(__file__).parent.parent / 'configs'

    config = load_config(config_dir / 'reader_advantages.yml')

    return {
        'min_total': config.get('thresholds', {}).get('min_total', 3),
        'min_our': config.get('thresholds', {}).get('min_our', 2),
        'share_edge': config.get('share', {}).get('edge_threshold', 0.6),
        'top_n': config.get('limits', {}).get('top_n', 10),
        'near_advantages_n': config.get('limits', {}).get('near_advantages_n', 5),
        'examples_per_topic': config.get('limits', {}).get('examples_per_topic', 3),
        'ownership_weight': config.get('scoring', {}).get('ownership_weight', 2.0),
        'edge_weight': config.get('scoring', {}).get('edge_weight', 1.5),
        'momentum_weight': config.get('scoring', {}).get('momentum_weight', 1.0),
        'share_diff_weight': config.get('scoring', {}).get('share_diff_weight', 1.0),
        'momentum_days': config.get('momentum', {}).get('window_days', 7),
    }


# ============================================================================
# Text Processing
# ============================================================================

_nlp_model = None

def get_nlp():
    """Get or load spaCy model."""
    global _nlp_model
    if _nlp_model is None and SPACY_AVAILABLE:
        try:
            _nlp_model = spacy.load("en_core_web_sm")
        except OSError:
            _nlp_model = None
    return _nlp_model


def clean_text(text: str) -> str:
    """Clean and normalize text."""
    if not text or not isinstance(text, str):
        return ""
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove email addresses
    text = re.sub(r'\S+@\S+', '', text)
    # Remove social handles
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'#\w+', '', text)
    # Remove special characters but keep spaces
    text = re.sub(r'[^\w\s\'-]', ' ', text)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text.lower().strip()


def extract_ngrams(text: str, n_range: tuple[int, int] = (1, 2)) -> list[str]:
    """Extract n-grams from text."""
    cleaned = clean_text(text)
    words = cleaned.split()

    # Stopwords to filter - common non-meaningful words
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
        'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'that',
        'this', 'it', 'its', 'he', 'she', 'they', 'we', 'you', 'i', 'what',
        'which', 'who', 'whom', 'how', 'when', 'where', 'why', 'all', 'each',
        'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no',
        'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just',
        'new', 'now', 'also', 'any', 'our', 'your', 'their', 'us', 'them',
        'about', 'after', 'into', 'over', 'under', 'between', 'out', 'up',
    }

    ngrams = []
    for n in range(n_range[0], n_range[1] + 1):
        for i in range(len(words) - n + 1):
            ngram_words = words[i:i+n]
            ngram = ' '.join(ngram_words)

            # Filter by length (3-30 chars)
            if not (3 <= len(ngram) <= 30):
                continue

            # Must be alphabetic (allow spaces and hyphens)
            if not all(c.isalpha() or c in ' -' for c in ngram):
                continue

            # Skip if starts/ends with stopword or dash
            first_word = ngram_words[0].strip('-')
            last_word = ngram_words[-1].strip('-')
            if first_word in stopwords or last_word in stopwords:
                continue

            # Skip if contains only stopwords
            if all(w in stopwords for w in ngram_words):
                continue

            # Skip if starts with dash (like "- barcelona")
            if ngram.startswith('-') or ngram.endswith('-'):
                continue

            ngrams.append(ngram)

    return ngrams


def extract_noun_chunks(text: str) -> list[str]:
    """Extract noun chunks using spaCy."""
    nlp = get_nlp()
    if nlp is None:
        return []

    cleaned = clean_text(text)
    doc = nlp(cleaned[:5000])  # Limit for performance

    chunks = []
    for chunk in doc.noun_chunks:
        # Remove leading determiners
        phrase = re.sub(r'^(the|a|an)\s+', '', chunk.text.lower().strip())
        if 3 <= len(phrase) <= 30:
            chunks.append(phrase)

    return chunks


def extract_topics_from_article(title: str, summary: str, body: str = '') -> list[str]:
    """
    Extract top topics from a single article using TF-IDF-like scoring.

    Returns up to 3 top n-grams per article.
    """
    # Combine text fields
    text = f"{title or ''} {summary or ''} {body[:1000] if body else ''}"

    # Extract n-grams
    ngrams = extract_ngrams(text, (1, 2))

    # Also try noun chunks
    noun_chunks = extract_noun_chunks(text)

    # Combine and dedupe
    all_candidates = list(set(ngrams + noun_chunks))

    # Simple TF scoring (count in this article)
    tf_scores = Counter(all_candidates)

    # Return top 3
    return [t for t, _ in tf_scores.most_common(3)]


# ============================================================================
# Core Counting Logic
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


def partition_by_source(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Partition articles by source_type field.

    Uses explicit source_type or category field, NOT token inference.
    """
    if df is None or len(df) == 0:
        return pd.DataFrame(), pd.DataFrame()

    # Try source_type first, then category
    source_col = None
    if 'source_type' in df.columns:
        source_col = 'source_type'
    elif 'category' in df.columns:
        source_col = 'category'
    else:
        # No source info - treat all as internal
        return df.copy(), pd.DataFrame()

    # Partition
    internal_mask = df[source_col].str.lower().isin(['internal', 'us', 'ours', 'own'])
    competitor_mask = df[source_col].str.lower().isin(['competitor', 'them', 'external', 'comp'])

    return df[internal_mask].copy(), df[competitor_mask].copy()


def filter_by_window(df: pd.DataFrame, window_days: int) -> pd.DataFrame:
    """
    Filter DataFrame by window using normalized UTC timestamps.
    """
    if df is None or len(df) == 0:
        return pd.DataFrame()

    # Get date column
    date_col = None
    for col in ['published_date_utc', 'published_date', 'date', 'timestamp']:
        if col in df.columns:
            date_col = col
            break

    if date_col is None:
        return df  # No date column, return all

    df = df.copy()

    # Normalize timestamps to UTC
    df['_normalized_date'] = pd.to_datetime(df[date_col], errors='coerce', utc=True)

    # Calculate cutoff
    cutoff = datetime.now(UTC) - timedelta(days=window_days)

    # Filter
    result = df[df['_normalized_date'] >= cutoff].drop(columns=['_normalized_date'])

    return result


def count_topics_by_source(
    df_internal: pd.DataFrame,
    df_competitor: pd.DataFrame,
    brand_tokens: set[str],
    window_days: int = 30
) -> dict[str, dict[str, Any]]:
    """
    Count topic occurrences by source.

    CRITICAL: Count articles FIRST, then filter brand tokens.
    This ensures competitor counts are accurate.
    """
    # Apply window filter
    df_internal = filter_by_window(df_internal, window_days)
    df_competitor = filter_by_window(df_competitor, window_days)

    # Also compute 7-day momentum window
    df_internal_7d = filter_by_window(df_internal, 7)
    df_competitor_7d = filter_by_window(df_competitor, 7)

    # Extract topics from all articles (BEFORE brand filtering)
    topic_articles_us: dict[str, list[dict]] = defaultdict(list)
    topic_articles_them: dict[str, list[dict]] = defaultdict(list)

    # Process internal articles
    for _, row in df_internal.iterrows():
        title = str(row.get('title', '')) if row.get('title') else ''
        summary = str(row.get('summary', row.get('description', ''))) if row.get('summary', row.get('description')) else ''
        body = str(row.get('body', row.get('content', ''))) if row.get('body', row.get('content')) else ''

        topics = extract_topics_from_article(title, summary, body)

        article_info = {
            'article_id': row.get('article_id', row.get('link', '')),
            'title': title[:100],
            'link': row.get('link', ''),
            'date': str(row.get('published_date_utc', ''))[:10]
        }

        for topic in topics:
            topic_articles_us[topic].append(article_info)

    # Process competitor articles
    for _, row in df_competitor.iterrows():
        title = str(row.get('title', '')) if row.get('title') else ''
        summary = str(row.get('summary', row.get('description', ''))) if row.get('summary', row.get('description')) else ''
        body = str(row.get('body', row.get('content', ''))) if row.get('body', row.get('content')) else ''

        topics = extract_topics_from_article(title, summary, body)

        article_info = {
            'article_id': row.get('article_id', row.get('link', '')),
            'title': title[:100],
            'link': row.get('link', ''),
            'date': str(row.get('published_date_utc', ''))[:10]
        }

        for topic in topics:
            topic_articles_them[topic].append(article_info)

    # Compute 7-day counts for momentum
    topics_us_7d = Counter()
    for _, row in df_internal_7d.iterrows():
        title = str(row.get('title', '')) if row.get('title') else ''
        summary = str(row.get('summary', row.get('description', ''))) if row.get('summary', row.get('description')) else ''
        for topic in extract_topics_from_article(title, summary, ''):
            topics_us_7d[topic] += 1

    topics_them_7d = Counter()
    for _, row in df_competitor_7d.iterrows():
        title = str(row.get('title', '')) if row.get('title') else ''
        summary = str(row.get('summary', row.get('description', ''))) if row.get('summary', row.get('description')) else ''
        for topic in extract_topics_from_article(title, summary, ''):
            topics_them_7d[topic] += 1

    # Merge all topics
    all_topics = set(topic_articles_us.keys()) | set(topic_articles_them.keys())

    # Build result dict with counts
    result = {}

    for topic in all_topics:
        # Get counts BEFORE filtering
        our_articles = topic_articles_us.get(topic, [])
        their_articles = topic_articles_them.get(topic, [])
        our_count = len(our_articles)
        their_count = len(their_articles)

        # NOW check if topic is a brand token (filter AFTER counting)
        topic_lower = topic.lower()
        is_brand = (
            topic_lower in brand_tokens or
            any(bt in topic_lower for bt in brand_tokens if len(bt) > 3)
        )

        if is_brand:
            continue  # Skip brand topics, but counts were already computed

        total = our_count + their_count
        our_share = our_count / max(total, 1)
        their_share = their_count / max(total, 1)
        share_diff = our_share - their_share

        # Dedupe examples by article_id, newest first
        def dedupe_examples(articles: list[dict], max_n: int = 3) -> list[dict]:
            seen_ids = set()
            deduped = []
            # Sort by date desc
            sorted_articles = sorted(articles, key=lambda x: x.get('date', ''), reverse=True)
            for art in sorted_articles:
                art_id = art.get('article_id', art.get('link', ''))
                if art_id and art_id not in seen_ids:
                    seen_ids.add(art_id)
                    deduped.append(art)
                    if len(deduped) >= max_n:
                        break
            return deduped

        result[topic] = {
            'topic': topic,
            'our_count': our_count,
            'their_count': their_count,
            'total': total,
            'our_share': round(our_share, 2),
            'their_share': round(their_share, 2),
            'share_diff': round(share_diff, 2),
            'our_count_7d': topics_us_7d.get(topic, 0),
            'their_count_7d': topics_them_7d.get(topic, 0),
            'examples_us': dedupe_examples(our_articles),
            'examples_them': dedupe_examples(their_articles),
        }

    return result


# ============================================================================
# Scoring and Selection
# ============================================================================

def compute_topic_scores(
    topic_counts: dict[str, dict[str, Any]],
    thresholds: dict
) -> list[dict[str, Any]]:
    """
    Compute scores for each topic and select top candidates.

    Score = ownership_weight*ownership + edge_weight*edge + momentum_weight*momentum + share_diff

    Gates:
    - min_total >= 3
    - our_count >= 2
    - Does NOT require their_count >= 2
    """
    min_total = thresholds.get('min_total', 3)
    min_our = thresholds.get('min_our', 2)
    share_edge = thresholds.get('share_edge', 0.6)
    ownership_weight = thresholds.get('ownership_weight', 2.0)
    edge_weight = thresholds.get('edge_weight', 1.5)
    momentum_weight = thresholds.get('momentum_weight', 1.0)
    share_diff_weight = thresholds.get('share_diff_weight', 1.0)

    scored_topics = []
    near_advantages = []

    for topic, data in topic_counts.items():
        our_count = data['our_count']
        their_count = data['their_count']
        total = data['total']
        our_share = data['our_share']
        share_diff = data['share_diff']
        our_count_7d = data['our_count_7d']
        their_count_7d = data['their_count_7d']

        # Compute flags
        ownership = (their_count == 0 and our_count >= 2)
        edge = (our_share >= share_edge and total >= 4)
        momentum = (our_count_7d >= 2 and their_count_7d == 0)

        # Compute score
        score = (
            ownership_weight * (1 if ownership else 0) +
            edge_weight * (1 if edge else 0) +
            momentum_weight * (1 if momentum else 0) +
            share_diff_weight * share_diff
        )

        topic_entry = {
            **data,
            'ownership': ownership,
            'edge': edge,
            'momentum_7d': momentum,
            'score': round(score, 3)
        }

        # Apply gates
        if total >= min_total and our_count >= min_our:
            scored_topics.append(topic_entry)
        elif our_count >= 1 and share_diff > 0:
            # Near-advantage: fails gates but positive share_diff
            near_advantages.append(topic_entry)

    # Sort by score descending
    scored_topics.sort(key=lambda x: -x['score'])
    near_advantages.sort(key=lambda x: -x['share_diff'])

    return scored_topics, near_advantages


# ============================================================================
# Main Builder Function
# ============================================================================

def build_reader_advantages(
    df: pd.DataFrame,
    window_days: int = 30,
    config_dir: Path = None
) -> dict[str, Any]:
    """
    Build reader advantages analysis.

    Args:
        df: Full articles DataFrame with source_type/category column
        window_days: Analysis window (30 or 90)
        config_dir: Path to configs directory

    Returns:
        Dict with reader_advantages structure for JSON output
    """
    if config_dir is None:
        config_dir = Path(__file__).parent.parent / 'configs'

    brand_tokens = get_brand_tokens(config_dir)
    thresholds = get_thresholds(config_dir)

    # Partition by source
    df_internal, df_competitor = partition_by_source(df)

    # Count topics by source
    topic_counts = count_topics_by_source(
        df_internal,
        df_competitor,
        brand_tokens,
        window_days
    )

    # Score and select
    top_n = thresholds.get('top_n', 10)
    near_n = thresholds.get('near_advantages_n', 5)

    scored_topics, near_advantages = compute_topic_scores(topic_counts, thresholds)

    # Build result
    result = {
        'window_days': window_days,
        'generated_at': datetime.now(UTC).isoformat(),
        'topics': scored_topics[:top_n],
        'near_advantages': near_advantages[:near_n],
        'metadata': {
            'brand_tokens_used': list(brand_tokens)[:20],  # Sample for auditability
            'thresholds': thresholds,
        },
        'diagnostics': {
            'total_internal_articles': len(filter_by_window(df_internal, window_days)),
            'total_competitor_articles': len(filter_by_window(df_competitor, window_days)),
            'total_topics_extracted': len(topic_counts),
            'topics_passing_gates': len(scored_topics),
            'near_advantages_count': len(near_advantages),
        }
    }

    return result


# ============================================================================
# Action Generation
# ============================================================================

def generate_why_matters(topic_data: dict) -> str:
    """Generate one-line 'why it matters' explanation."""
    if topic_data.get('ownership'):
        return "Only we covered this meaningfully in the window"
    elif topic_data.get('edge'):
        return "We dominate coverage share in this topic"
    elif topic_data.get('momentum_7d'):
        return "We surged in the last 7 days while competitors were quiet"
    elif topic_data['our_share'] > 0.5:
        return f"We lead with {int(topic_data['our_share'] * 100)}% share of coverage"
    else:
        return "Emerging opportunity to establish leadership"


def generate_actions(topic_data: dict) -> dict[str, str]:
    """Generate 3 action bullets."""
    topic = topic_data['topic']

    return {
        'content': f"Publish 1 explainer + 1 interview on '{topic}' next week",
        'product': f"Create topic hub/SEO tag for '{topic}'",
        'commercial': f"Pitch sponsor package on '{topic}' series for Q1"
    }


# ============================================================================
# CSV Export
# ============================================================================

def advantages_to_csv(advantages: dict[str, Any]) -> str:
    """Convert reader advantages to CSV string."""
    topics = advantages.get('topics', [])

    if not topics:
        return "topic,our_count,their_count,our_share,examples_us,examples_them\n"

    rows = []
    for t in topics:
        examples_us = ' | '.join([f"{e.get('title', '')} ({e.get('link', '')})" for e in t.get('examples_us', [])[:3]])
        examples_them = ' | '.join([f"{e.get('title', '')} ({e.get('link', '')})" for e in t.get('examples_them', [])[:3]])

        rows.append({
            'topic': t['topic'],
            'our_count': t['our_count'],
            'their_count': t['their_count'],
            'our_share': t['our_share'],
            'examples_us': examples_us,
            'examples_them': examples_them
        })

    df = pd.DataFrame(rows)
    return df.to_csv(index=False)


# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == '__main__':
    import argparse
    import json

    parser = argparse.ArgumentParser(description='Generate reader advantages analysis')
    parser.add_argument('--window', type=int, default=30, help='Window in days (30 or 90)')
    parser.add_argument('--input', type=str, help='Input CSV file')
    parser.add_argument('--output', type=str, help='Output JSON file')

    args = parser.parse_args()

    if args.input:
        df = pd.read_csv(args.input)
        result = build_reader_advantages(df, window_days=args.window)

        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
        else:
            print(json.dumps(result, indent=2))
    else:
        print("Usage: python reader_advantages.py --input articles.csv --output analysis.json --window 30")
