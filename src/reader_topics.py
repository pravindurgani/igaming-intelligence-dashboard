"""
Reader Topics: Brand-neutral topic discovery for "Why Readers Choose Us".

Scoring Rules:
- Filters out brand/domain tokens (igbaffiliate, igamingbusiness, etc.)
- Extracts topics from title+summary using spaCy noun chunks and named entities
- Selection: Us >= 3 AND (Us >= 2*Them OR Them <= 1)
- Near-wins fallback: Us >= 2 AND Advantage >= 1
- Returns top 3-7 topics sorted by advantage

Actions generated per topic:
- Editorial: "Publish a [explainer|interview|data piece] on '{topic}' within 7 days to defend advantage."
- Product: "Add a topic hub tag '{topic}' for internal search and cross-linking."
- Commercial: "Pitch a sponsor package aligned to '{topic}' for Q1 webinar/newsletter."

Caching: Results cached by (window_days, data_hash) for session performance.
"""

import re
from collections import Counter
from datetime import UTC, datetime, timedelta

import pandas as pd

# spaCy is optional - degrade gracefully
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    spacy = None


# ============================================================================
# Brand/Domain Stopwords - REQUIRED for filtering
# ============================================================================

STOPWORDS_EXACT = {
    # Tracked portfolio brands and domains
    "igbaffiliate", "igamingbusiness", "igba", "igb",
    "igbaffiliate.com", "igamingbusiness.com", "barcelona.igbaffiliate.com",
    # Generic domain artifacts
    "com", "www", "http", "https", "html", "magazine",
    # Common non-topic words
    "news", "article", "read", "more", "click", "here",
}

# Regex pattern for brand detection
BRAND_PATTERN = re.compile(
    r"^(igb|igamingbusiness|igbaffiliate)(\.com)?$",
    re.IGNORECASE
)

# Additional stopwords for general filtering
GENERAL_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
    "be", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can", "need",
    "this", "that", "these", "those", "it", "its", "they", "their",
    "he", "she", "we", "you", "i", "my", "your", "our", "his", "her",
}

# Known good bigrams to preserve
KNOWN_BIGRAMS = {
    "sports betting", "responsible gambling", "online gaming",
    "prediction markets", "match fixing", "salary trends",
    "uk tax", "us market", "latin america", "north america",
    "mobile gaming", "live casino", "slot games", "table games",
    "affiliate marketing", "player protection", "age verification",
    "money laundering", "gambling commission", "gaming license",
}


# ============================================================================
# spaCy Model Loading
# ============================================================================

_nlp_model = None

def get_nlp():
    """Get or load spaCy model."""
    global _nlp_model
    if _nlp_model is None and SPACY_AVAILABLE:
        try:
            _nlp_model = spacy.load("en_core_web_sm")
        except OSError:
            # Model not installed
            _nlp_model = None
    return _nlp_model


# ============================================================================
# Text Processing Helpers
# ============================================================================

def clean_text(text: str) -> str:
    """Clean and normalize text."""
    if not text or not isinstance(text, str):
        return ""
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove email addresses
    text = re.sub(r'\S+@\S+', '', text)
    # Remove special characters but keep spaces and basic punctuation
    text = re.sub(r'[^\w\s\'-]', ' ', text)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text.lower().strip()


def is_brand_token(token: str) -> bool:
    """Check if token is a brand/domain stopword."""
    token_lower = token.lower().strip()

    # Exact match
    if token_lower in STOPWORDS_EXACT:
        return True

    # Regex match
    if BRAND_PATTERN.match(token_lower):
        return True

    # Contains our domain
    if any(brand in token_lower for brand in ["igbaffiliate", "igamingbusiness"]):
        return True

    return False


def is_valid_topic(phrase: str) -> bool:
    """Check if phrase is a valid topic (not a brand, not too short/long)."""
    if not phrase or len(phrase) < 3:
        return False

    # Check brand filtering
    if is_brand_token(phrase):
        return False

    # Check each word in the phrase
    words = phrase.split()
    for word in words:
        if is_brand_token(word):
            return False

    # Filter out single general stopwords
    if len(words) == 1 and phrase in GENERAL_STOPWORDS:
        return False

    # Must have at least one word with 3+ chars
    if not any(len(w) >= 3 for w in words):
        return False

    return True


def tokenize_phrases(text: str) -> list[str]:
    """
    Extract noun phrases and entities from text using spaCy.

    Falls back to simple word extraction if spaCy unavailable.

    Args:
        text: Input text

    Returns:
        List of candidate phrases (lowercase, cleaned)
    """
    cleaned = clean_text(text)
    if not cleaned:
        return []

    nlp = get_nlp()

    if nlp is None:
        # Fallback: simple word/bigram extraction
        words = cleaned.split()
        phrases = []

        # Unigrams
        for w in words:
            if len(w) >= 3 and w not in GENERAL_STOPWORDS:
                phrases.append(w)

        # Bigrams
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            if bigram in KNOWN_BIGRAMS or (
                words[i] not in GENERAL_STOPWORDS and
                words[i+1] not in GENERAL_STOPWORDS
            ):
                phrases.append(bigram)

        return phrases

    # Use spaCy for better extraction
    doc = nlp(cleaned[:10000])  # Limit length for performance
    phrases = []

    # Named entities
    for ent in doc.ents:
        phrase = ent.text.lower().strip()
        if is_valid_topic(phrase):
            phrases.append(phrase)

    # Noun chunks
    for chunk in doc.noun_chunks:
        phrase = chunk.text.lower().strip()
        # Remove leading determiners
        phrase = re.sub(r'^(the|a|an)\s+', '', phrase)
        if is_valid_topic(phrase):
            phrases.append(phrase)

    # Also extract known bigrams
    text_lower = cleaned.lower()
    for bigram in KNOWN_BIGRAMS:
        if bigram in text_lower:
            phrases.append(bigram)

    return phrases


def get_article_text(row: pd.Series) -> str:
    """Combine title + summary + body for an article."""
    parts = []

    title = row.get('title', '')
    if title and isinstance(title, str):
        parts.append(title)

    summary = row.get('summary', row.get('description', ''))
    if summary and isinstance(summary, str):
        parts.append(summary)

    body = row.get('body', row.get('content', ''))
    if body and isinstance(body, str):
        parts.append(body[:2000])  # Limit body length

    return ' '.join(parts)


# ============================================================================
# Topic Counting
# ============================================================================

def count_matches(df: pd.DataFrame, phrases: list[str]) -> dict[str, int]:
    """
    Count how many articles contain each phrase.

    Uses whole-word matching with word boundaries, case insensitive.

    Args:
        df: DataFrame with articles
        phrases: List of phrases to count

    Returns:
        Dict mapping phrase -> article count
    """
    counts = Counter()

    if df is None or len(df) == 0:
        return dict(counts)

    # Build regex patterns for whole-word matching
    patterns = {}
    for phrase in phrases:
        # Escape special regex chars
        escaped = re.escape(phrase)
        # Use word boundaries
        patterns[phrase] = re.compile(r'\b' + escaped + r'\b', re.IGNORECASE)

    # Count matches across articles
    for _, row in df.iterrows():
        text = get_article_text(row)
        if not text:
            continue

        text_lower = text.lower()

        for phrase, pattern in patterns.items():
            if pattern.search(text_lower):
                counts[phrase] += 1

    return dict(counts)


def extract_candidate_topics(df: pd.DataFrame, max_articles: int = 500) -> list[str]:
    """
    Extract candidate topic phrases from a corpus.

    Args:
        df: DataFrame with articles
        max_articles: Maximum articles to process for extraction

    Returns:
        List of unique candidate phrases
    """
    all_phrases = Counter()

    # Sample if too many articles
    sample_df = df.head(max_articles) if len(df) > max_articles else df

    for _, row in sample_df.iterrows():
        text = get_article_text(row)
        phrases = tokenize_phrases(text)

        for phrase in phrases:
            if is_valid_topic(phrase):
                all_phrases[phrase] += 1

    # Filter to phrases appearing at least twice
    return [p for p, c in all_phrases.most_common(200) if c >= 2]


# ============================================================================
# Text Generation Helpers
# ============================================================================

def summarize_why(topic: str, us: int, them: int) -> str:
    """
    Generate a one-sentence why_matters statement.

    Args:
        topic: Topic name
        us: Our article count
        them: Competitor article count

    Returns:
        12-18 word sentence explaining reader value
    """
    lead = us - them

    if them == 0:
        return f"We exclusively cover {topic} in depth, giving readers unique insights they can't find elsewhere."
    elif lead >= 5:
        return f"Our {topic} coverage leads the market with {lead} more articles, keeping readers ahead of developments."
    elif lead >= 2:
        return f"Readers trust us for {topic} updates because we publish more frequently than competitors."
    else:
        return f"We provide comprehensive {topic} coverage that readers rely on for industry intelligence."


def suggest_action(topic: str, us: int, them: int) -> str:
    """
    Generate a next action suggestion.

    Args:
        topic: Topic name
        us: Our article count
        them: Competitor article count

    Returns:
        One imperative sentence guiding editorial/distribution
    """
    lead = us - them

    if them == 0:
        return f"Defend exclusive position with a weekly {topic} explainer series."
    elif lead >= 5:
        return f"Publish an in-depth {topic} analysis with expert quotes this week."
    elif lead >= 2:
        return f"Schedule a weekend {topic} follow-up and add a market overview."
    else:
        return f"Strengthen {topic} coverage with a roundup article and newsletter feature."


def get_evidence_links(df: pd.DataFrame, topic: str, max_links: int = 3) -> list[dict]:
    """
    Get evidence article links for a topic.

    Args:
        df: Internal articles DataFrame
        topic: Topic to find evidence for
        max_links: Maximum links to return

    Returns:
        List of dicts with title, link, date
    """
    if df is None or len(df) == 0:
        return []

    pattern = re.compile(r'\b' + re.escape(topic) + r'\b', re.IGNORECASE)
    evidence = []

    # Sort by date descending
    df_sorted = df.sort_values('published_date_utc', ascending=False) if 'published_date_utc' in df.columns else df

    for _, row in df_sorted.iterrows():
        text = get_article_text(row)
        if pattern.search(text):
            evidence.append({
                'title': row.get('title', 'Untitled')[:60],
                'link': row.get('link', '#'),
                'date': str(row.get('published_date_utc', ''))[:10]
            })
            if len(evidence) >= max_links:
                break

    return evidence


# ============================================================================
# Main Builder Function
# ============================================================================

def build_reader_topics(
    df_internal: pd.DataFrame,
    df_competitors: pd.DataFrame,
    window_days: int = 30
) -> pd.DataFrame:
    """
    Build reader topics table with brand filtering.

    Args:
        df_internal: Internal articles DataFrame
        df_competitors: Competitor articles DataFrame
        window_days: Analysis window (for display purposes)

    Returns:
        DataFrame with columns:
        ["topic", "us", "them", "lead", "why_matters", "next_action", "evidence_links"]
    """
    # Handle empty inputs
    if df_internal is None or len(df_internal) == 0:
        return pd.DataFrame(columns=[
            "topic", "us", "them", "lead", "why_matters", "next_action", "evidence_links"
        ])

    if df_competitors is None:
        df_competitors = pd.DataFrame()

    # Extract candidate topics from BOTH corpora
    internal_candidates = extract_candidate_topics(df_internal)
    competitor_candidates = extract_candidate_topics(df_competitors) if len(df_competitors) > 0 else []

    # Merge and deduplicate candidates
    all_candidates = list(set(internal_candidates + competitor_candidates))

    # Filter out brand tokens again (safety check)
    all_candidates = [c for c in all_candidates if is_valid_topic(c)]

    if not all_candidates:
        return pd.DataFrame(columns=[
            "topic", "us", "them", "lead", "why_matters", "next_action", "evidence_links"
        ])

    # Count matches using SAME tokenizer and fields for both corpora
    us_counts = count_matches(df_internal, all_candidates)
    them_counts = count_matches(df_competitors, all_candidates) if len(df_competitors) > 0 else {}

    # Build topic list with scoring
    topics_data = []

    for topic in all_candidates:
        us = us_counts.get(topic, 0)
        them = them_counts.get(topic, 0)
        lead = us - them

        # Selection criteria:
        # (us >= 3 and lead >= 2) OR (us >= 5 and us / max(them,1) >= 1.5)
        ratio = us / max(them, 1)

        if (us >= 3 and lead >= 2) or (us >= 5 and ratio >= 1.5):
            # Final brand check
            if not is_valid_topic(topic):
                continue

            evidence = get_evidence_links(df_internal, topic)

            topics_data.append({
                'topic': topic,
                'us': us,
                'them': them,
                'lead': lead,
                'why_matters': summarize_why(topic, us, them),
                'next_action': suggest_action(topic, us, them),
                'evidence_links': evidence
            })

    if not topics_data:
        return pd.DataFrame(columns=[
            "topic", "us", "them", "lead", "why_matters", "next_action", "evidence_links"
        ])

    # Sort by lead desc, tie-break by us desc
    topics_data.sort(key=lambda x: (-x['lead'], -x['us']))

    # Keep top 5
    topics_data = topics_data[:5]

    return pd.DataFrame(topics_data)


def topics_to_csv(df: pd.DataFrame) -> str:
    """
    Convert topics DataFrame to CSV string.

    Args:
        df: Topics DataFrame

    Returns:
        CSV string for download
    """
    if df is None or len(df) == 0:
        return "topic,us,them,lead,why_matters,next_action,evidence\n"

    export_df = df.copy()

    # Convert evidence_links to string
    if 'evidence_links' in export_df.columns:
        export_df['evidence'] = export_df['evidence_links'].apply(
            lambda links: ' | '.join([f"{l['title']} ({l['link']})" for l in links]) if links else ''
        )
        export_df = export_df.drop(columns=['evidence_links'])

    return export_df.to_csv(index=False)


def format_evidence_html(links: list[dict]) -> str:
    """
    Format evidence links as middot-separated hyperlinks.

    Args:
        links: List of link dicts

    Returns:
        HTML string with hyperlinked titles
    """
    if not links:
        return ""

    parts = []
    for link in links[:3]:
        title = link.get('title', 'Article')[:30]
        url = link.get('link', '#')
        parts.append(f"[{title}]({url})")

    return " · ".join(parts)


# ============================================================================
# Caching
# ============================================================================

import hashlib

_reader_wins_cache: dict[str, pd.DataFrame] = {}


def _compute_data_hash(df: pd.DataFrame) -> str:
    """Compute a hash of DataFrame for caching."""
    if df is None or len(df) == 0:
        return "empty"
    # Use shape and first/last row for quick hash
    sample = f"{len(df)}_{df.iloc[0].to_dict() if len(df) > 0 else ''}_{df.iloc[-1].to_dict() if len(df) > 0 else ''}"
    return hashlib.md5(sample.encode()).hexdigest()[:16]


# ============================================================================
# Action Generation (per spec)
# ============================================================================

def _generate_editorial_action(topic: str, us: int, them: int) -> str:
    """Generate editorial action per spec format."""
    # Vary the content type based on topic characteristics
    if them == 0:
        content_type = "explainer"
    elif us >= 2 * them:
        content_type = "data piece"
    else:
        content_type = "interview"

    return f"Publish a {content_type} on '{topic}' within 7 days to defend advantage."


def _generate_product_action(topic: str) -> str:
    """Generate product action per spec format."""
    return f"Add a topic hub tag '{topic}' for internal search and cross-linking."


def _generate_commercial_action(topic: str) -> str:
    """Generate commercial action per spec format."""
    return f"Pitch a sponsor package aligned to '{topic}' for Q1 webinar/newsletter."


# ============================================================================
# Main compute_reader_wins Function (per spec)
# ============================================================================

def compute_reader_wins(
    df_internal: pd.DataFrame,
    df_comp: pd.DataFrame,
    window_days: int,
    stoplist: set
) -> pd.DataFrame:
    """
    Compute reader wins with brand filtering and action generation.

    Selection criteria:
    - Us >= 3 AND (Us >= 2*Them OR Them <= 1)
    - Near-wins fallback: Us >= 2 AND Advantage >= 1

    Args:
        df_internal: Internal articles DataFrame
        df_comp: Competitor articles DataFrame
        window_days: Analysis window (30 or 90)
        stoplist: Set of brand/domain tokens to exclude

    Returns:
        DataFrame with columns:
        [topic, us, them, advantage, examples, editorial_action, product_action,
         commercial_action, near_win]
    """
    global _reader_wins_cache

    # Check cache
    cache_key = f"{window_days}_{_compute_data_hash(df_internal)}_{_compute_data_hash(df_comp)}"
    if cache_key in _reader_wins_cache:
        return _reader_wins_cache[cache_key]

    # Handle empty inputs
    empty_result = pd.DataFrame(columns=[
        "topic", "us", "them", "advantage", "examples",
        "editorial_action", "product_action", "commercial_action", "near_win"
    ])

    if df_internal is None or len(df_internal) == 0:
        return empty_result

    if df_comp is None:
        df_comp = pd.DataFrame()

    # Merge default stoplist with provided stoplist
    full_stoplist = STOPWORDS_EXACT | stoplist

    # Filter DataFrames by window (UTC timestamps)
    cutoff = datetime.now(UTC) - timedelta(days=window_days)

    def filter_by_window(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or len(df) == 0:
            return pd.DataFrame()
        if 'published_date_utc' not in df.columns:
            return df
        df = df.copy()
        df['published_date_utc'] = pd.to_datetime(df['published_date_utc'], errors='coerce', utc=True)
        return df[df['published_date_utc'] >= cutoff]

    df_internal_windowed = filter_by_window(df_internal)
    df_comp_windowed = filter_by_window(df_comp)

    if len(df_internal_windowed) == 0:
        return empty_result

    # Extract candidates from title+summary only (for performance)
    def extract_topics_fast(df: pd.DataFrame) -> list[str]:
        """Extract topics from title+summary only."""
        all_phrases = Counter()

        for _, row in df.iterrows():
            # Only use title + summary for speed
            title = str(row.get('title', '')) if row.get('title') else ''
            summary = str(row.get('summary', row.get('description', ''))) if row.get('summary', row.get('description')) else ''
            text = f"{title} {summary}"

            phrases = tokenize_phrases(text)
            for phrase in phrases:
                phrase_lower = phrase.lower().strip()
                # Skip if in stoplist
                if phrase_lower in full_stoplist:
                    continue
                # Skip if any word is in stoplist
                if any(w in full_stoplist for w in phrase_lower.split()):
                    continue
                if is_valid_topic(phrase_lower):
                    all_phrases[phrase_lower] += 1

        return [p for p, c in all_phrases.most_common(100) if c >= 2]

    # Extract candidates from both corpora
    internal_candidates = extract_topics_fast(df_internal_windowed)
    comp_candidates = extract_topics_fast(df_comp_windowed) if len(df_comp_windowed) > 0 else []

    all_candidates = list(set(internal_candidates + comp_candidates))

    # Final filter against stoplist
    all_candidates = [c for c in all_candidates if c not in full_stoplist and is_valid_topic(c)]

    if not all_candidates:
        return empty_result

    # Count matches (title+summary only for consistency)
    def count_matches_fast(df: pd.DataFrame, phrases: list[str]) -> dict[str, int]:
        """Count matches using title+summary only."""
        counts = Counter()
        if df is None or len(df) == 0:
            return dict(counts)

        patterns = {}
        for phrase in phrases:
            escaped = re.escape(phrase)
            patterns[phrase] = re.compile(r'\b' + escaped + r'\b', re.IGNORECASE)

        for _, row in df.iterrows():
            title = str(row.get('title', '')) if row.get('title') else ''
            summary = str(row.get('summary', row.get('description', ''))) if row.get('summary', row.get('description')) else ''
            text = f"{title} {summary}".lower()

            for phrase, pattern in patterns.items():
                if pattern.search(text):
                    counts[phrase] += 1

        return dict(counts)

    us_counts = count_matches_fast(df_internal_windowed, all_candidates)
    them_counts = count_matches_fast(df_comp_windowed, all_candidates) if len(df_comp_windowed) > 0 else {}

    # Build topic list with scoring
    wins_data = []
    near_wins_data = []

    for topic in all_candidates:
        us = us_counts.get(topic, 0)
        them = them_counts.get(topic, 0)
        advantage = us - them

        # Get example links (top 3, latest first)
        examples = get_evidence_links(df_internal_windowed, topic, max_links=3)

        topic_row = {
            'topic': topic,
            'us': us,
            'them': them,
            'advantage': advantage,
            'examples': examples,
            'editorial_action': _generate_editorial_action(topic, us, them),
            'product_action': _generate_product_action(topic),
            'commercial_action': _generate_commercial_action(topic),
            'near_win': False
        }

        # Selection: Us >= 3 AND (Us >= 2*Them OR Them <= 1)
        if us >= 3 and (us >= 2 * them or them <= 1):
            wins_data.append(topic_row)
        # Near-wins fallback: Us >= 2 AND Advantage >= 1
        elif us >= 2 and advantage >= 1:
            topic_row['near_win'] = True
            near_wins_data.append(topic_row)

    # Use wins if available, otherwise near-wins
    if wins_data:
        result_data = wins_data
    elif near_wins_data:
        result_data = near_wins_data
    else:
        return empty_result

    # Sort by advantage descending, tie-break by us descending
    result_data.sort(key=lambda x: (-x['advantage'], -x['us']))

    # Keep top 7 (spec says 3-7 items)
    result_data = result_data[:7]

    result_df = pd.DataFrame(result_data)

    # Cache result
    _reader_wins_cache[cache_key] = result_df

    return result_df


def reader_wins_to_csv(df: pd.DataFrame) -> str:
    """
    Convert reader wins DataFrame to CSV string.

    Args:
        df: Reader wins DataFrame

    Returns:
        CSV string for download
    """
    if df is None or len(df) == 0:
        return "topic,us,them,advantage,editorial_action,product_action,commercial_action,near_win,examples\n"

    export_df = df.copy()

    # Convert examples to string
    if 'examples' in export_df.columns:
        export_df['examples'] = export_df['examples'].apply(
            lambda links: ' | '.join([f"{l.get('title', '')} ({l.get('link', '')})" for l in links]) if links else ''
        )

    return export_df.to_csv(index=False)


def clear_reader_wins_cache():
    """Clear the reader wins cache."""
    global _reader_wins_cache
    _reader_wins_cache = {}
