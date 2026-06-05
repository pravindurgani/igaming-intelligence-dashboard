"""
All-time full-text search for the iGaming Intelligence Dashboard.

Features:
- Searches title, summary, AND content fields by default
- Works across ALL TIME (independent of 30/90-day window)
- Supports phrase queries with "quoted strings"
- Supports AND (default between tokens) and OR operators
- Token index for efficient keyword lookups
- Cache fingerprinting based on CSV modified time and row count
- Unified text normalization for iGaming, eCricket, eSports terms
- Index caching to avoid rebuilding on every query
"""

import re
from pathlib import Path

import pandas as pd

# Import unified text normalization from textnorm module
from src.textnorm import build_search_field, normalize_text
from src.textnorm import has_content as textnorm_has_content

# Module-level index cache to avoid rebuilding on every query
_INDEX_CACHE: dict[str, 'SearchIndex'] = {}


def tokenize(text: str) -> list[str]:
    """
    Tokenize normalized text into words.

    Args:
        text: Normalized text

    Returns:
        List of tokens
    """
    normalized = normalize_text(text)
    return normalized.split()


def get_csv_fingerprint(csv_path: Path) -> str:
    """
    Generate cache fingerprint based on CSV file properties.
    Includes modification time and file size for cache invalidation.

    Args:
        csv_path: Path to CSV file

    Returns:
        Fingerprint string
    """
    if not csv_path.exists():
        return "missing"

    stat = csv_path.stat()
    mtime = stat.st_mtime
    size = stat.st_size

    # Read row count without loading full file
    try:
        with open(csv_path, 'r') as f:
            row_count = sum(1 for _ in f) - 1  # Subtract header
    except Exception:
        row_count = 0

    return f"mtime:{mtime:.0f}_size:{size}_rows:{row_count}"


def _get_dataframe_fingerprint(df: pd.DataFrame) -> str:
    """Generate a fingerprint for cache invalidation based on DataFrame contents."""
    if df.empty:
        return "empty"
    # Use row count and hash of article IDs + first title for accurate invalidation
    row_count = len(df)
    if 'article_id' in df.columns:
        # Hash all article IDs for uniqueness
        ids_str = ','.join(df['article_id'].astype(str).tolist())
    else:
        ids_str = "unknown"
    # Include first title to differentiate DataFrames with same IDs but different content
    first_title = ""
    if 'title' in df.columns and len(df) > 0:
        first_title = str(df['title'].iloc[0])[:50]
    return f"rows:{row_count}_ids:{hash(ids_str)}_t:{hash(first_title)}"


def get_or_build_index(
    df: pd.DataFrame,
    fields: tuple[str, ...] = ('title', 'summary', 'content')
) -> 'SearchIndex':
    """
    Get cached search index or build a new one if cache is stale.

    This avoids rebuilding the index on every query, which is expensive
    for large DataFrames.

    Args:
        df: DataFrame with articles
        fields: Fields to index

    Returns:
        SearchIndex instance (cached if possible)
    """
    global _INDEX_CACHE

    # Generate cache key from fields and DataFrame fingerprint
    fingerprint = _get_dataframe_fingerprint(df)
    cache_key = f"{fields}_{fingerprint}"

    # Check if cached index is still valid
    if cache_key in _INDEX_CACHE:
        return _INDEX_CACHE[cache_key]

    # Build new index and cache it
    index = SearchIndex()
    index.build(df, fields=fields)
    index.fingerprint = fingerprint

    # Clear old cache entries (keep only most recent)
    if len(_INDEX_CACHE) > 5:
        _INDEX_CACHE.clear()

    _INDEX_CACHE[cache_key] = index
    return index


class SearchIndex:
    """
    Inverted index for efficient full-text search.
    Maps tokens to sets of article IDs.
    """

    def __init__(self):
        self.token_to_articles: dict[str, set[str]] = {}
        self.article_texts: dict[str, str] = {}  # For phrase matching
        self.article_has_content: dict[str, bool] = {}
        self.fingerprint: str = ""

    def build(self, df: pd.DataFrame, fields: tuple[str, ...] = ('title', 'summary', 'content')) -> 'SearchIndex':
        """
        Build inverted index from DataFrame.

        Uses unified text normalization from textnorm module for consistent
        matching of iGaming, eCricket, eSports terms across News Feed and Context Explorer.

        Args:
            df: DataFrame with articles
            fields: Fields to index (default includes content for full-text search)

        Returns:
            self for chaining
        """
        self.token_to_articles.clear()
        self.article_texts.clear()
        self.article_has_content.clear()

        for _, row in df.iterrows():
            article_id = str(row.get('article_id', ''))
            if not article_id:
                continue

            # Use unified build_search_field for consistent normalization
            # This handles iGaming -> igaming gaming, eCricket -> ecricket cricket, etc.
            normalized = build_search_field(row)

            # Store for phrase matching
            self.article_texts[article_id] = normalized

            # Track if article has content using textnorm helper
            self.article_has_content[article_id] = textnorm_has_content(row)

            # Index tokens
            tokens = normalized.split()
            for token in set(tokens):  # Deduplicate
                if token not in self.token_to_articles:
                    self.token_to_articles[token] = set()
                self.token_to_articles[token].add(article_id)

        return self

    def search_token(self, token: str, use_word_boundary: bool = None) -> set[str]:
        """
        Get article IDs containing a token.

        Matching strategy:
        - Short tokens (< 4 chars): word-boundary regex to reduce noise (e.g., 'AI' won't match 'again')
        - Long tokens (>= 4 chars): substring match on normalized text for flexibility
        - Multi-word normalized tokens: require ALL words to be present (AND logic)

        Also handles edge cases where camelCase splitting produces unexpected results:
        - "bRazil" normalizes to "b razil" - also try plain lowercase "brazil"
        - "DraftKings" normalizes to "draft kings" - search for both words

        Args:
            token: Search token
            use_word_boundary: Override automatic boundary detection. If None, uses length heuristic.

        Returns:
            Set of matching article IDs
        """
        normalized_token = normalize_text(token)
        if not normalized_token:
            return set()

        # Handle multi-word normalization (e.g., "DraftKings" -> "draft kings")
        # If normalization produced multiple words, require ALL to match
        words = normalized_token.split()
        if len(words) > 1:
            # Multi-word: find articles containing ALL words
            matches = None
            for word in words:
                word_matches = self._search_single_token(word, use_word_boundary)
                if matches is None:
                    matches = word_matches
                else:
                    matches = matches.intersection(word_matches)

            result = matches if matches else set()

            # If no results, also try plain lowercase as fallback
            # This handles cases like "bRazil" -> "b razil" where the user
            # probably meant "brazil"
            if not result:
                plain_lower = token.lower()
                if plain_lower and plain_lower != normalized_token:
                    fallback = self._search_single_token(plain_lower, use_word_boundary)
                    result = result.union(fallback)

            return result
        else:
            # Single word: use standard matching
            result = self._search_single_token(normalized_token, use_word_boundary)

            # If no results and the original token was mixed case like "bRazil",
            # also try plain lowercase as a fallback
            if not result and token.lower() != normalized_token:
                plain_lower = token.lower()
                if plain_lower:
                    fallback = self._search_single_token(plain_lower, use_word_boundary)
                    result = result.union(fallback)

            return result

    def _search_single_token(self, token: str, use_word_boundary: bool = None) -> set[str]:
        """
        Search for a single normalized token.

        Args:
            token: Already-normalized single token
            use_word_boundary: Override automatic boundary detection

        Returns:
            Set of matching article IDs
        """
        if not token:
            return set()

        # Decide matching strategy based on token length
        if use_word_boundary is None:
            use_word_boundary = len(token) < 4

        if use_word_boundary:
            # Word-boundary regex for short tokens to reduce noise
            pattern = r'\b' + re.escape(token) + r'\b'
            matches = set()
            for article_id, text in self.article_texts.items():
                if re.search(pattern, text):
                    matches.add(article_id)
            return matches
        else:
            # Substring match for longer tokens - check both index and full text
            # First try exact token match (faster)
            if token in self.token_to_articles:
                return self.token_to_articles[token].copy()

            # Fall back to substring search in normalized text
            matches = set()
            for article_id, text in self.article_texts.items():
                if token in text:
                    matches.add(article_id)
            return matches

    def search_phrase(self, phrase: str) -> set[str]:
        """
        Search for exact phrase in article texts.

        Always uses substring match since phrases are quoted and explicit.

        Args:
            phrase: Phrase to search (will be normalized)

        Returns:
            Set of matching article IDs
        """
        normalized_phrase = normalize_text(phrase)
        if not normalized_phrase:
            return set()

        matches = set()
        for article_id, text in self.article_texts.items():
            if normalized_phrase in text:
                matches.add(article_id)

        return matches


def parse_query(query: str) -> list[tuple[str, str]]:
    """
    Parse query into tokens with operators.

    Supports:
    - "quoted phrases" for exact matching
    - OR between terms for union
    - AND (implicit, default between tokens)

    Args:
        query: User query string

    Returns:
        List of (term, operator) tuples
        operator is 'AND', 'OR', or 'PHRASE'
    """
    tokens = []
    query = query.strip()

    # Extract quoted phrases first
    phrase_pattern = r'"([^"]+)"'
    phrases = re.findall(phrase_pattern, query)
    for phrase in phrases:
        tokens.append((phrase, 'PHRASE'))

    # Remove quoted phrases from query
    remaining = re.sub(phrase_pattern, ' ', query)

    # Split remaining by whitespace
    words = remaining.split()

    i = 0
    pending_or = False
    while i < len(words):
        word = words[i]
        word_lower = word.lower()

        if word_lower == 'or':
            pending_or = True
            i += 1
            continue
        elif word_lower == 'and':
            # Explicit AND - skip (it's the default)
            i += 1
            continue
        else:
            # Regular term - keep original case for proper camelCase splitting
            if pending_or:
                tokens.append((words[i], 'OR'))
                pending_or = False
            else:
                tokens.append((words[i], 'AND'))
            i += 1

    return tokens


def execute_query(index: SearchIndex, query: str) -> set[str]:
    """
    Execute parsed query against index.

    Args:
        index: SearchIndex instance
        query: User query string

    Returns:
        Set of matching article IDs
    """
    if not query or not query.strip():
        return set()

    parsed = parse_query(query)
    if not parsed:
        return set()

    result = None
    or_accumulator = set()

    for term, operator in parsed:
        if operator == 'PHRASE':
            matches = index.search_phrase(term)
        else:
            matches = index.search_token(term)

        if operator == 'OR':
            or_accumulator.update(matches)
        else:  # AND or PHRASE
            if result is None:
                result = matches
            else:
                # Flush OR accumulator first
                if or_accumulator:
                    result = result.union(or_accumulator)
                    or_accumulator.clear()
                result = result.intersection(matches)

    # Final OR flush
    if or_accumulator:
        if result is None:
            result = or_accumulator
        else:
            result = result.union(or_accumulator)

    return result if result is not None else set()


def search_articles(
    df: pd.DataFrame,
    query: str,
    search_fields: list[str] = None,
    filters: dict = None
) -> pd.DataFrame:
    """
    Search articles using full-text search across ALL TIME.

    IMPORTANT: This searches the ENTIRE DataFrame, not limited by date window.
    The Context Explorer uses this to find articles regardless of when they were published.

    Args:
        df: DataFrame with articles (ALL articles, not filtered by date)
        query: Search query (supports phrases, AND, OR)
        search_fields: List of column names to search. Defaults to ['title', 'summary', 'content']
        filters: Optional dict with filter criteria:
            - sources: List of allowed sources
            - categories: List of allowed categories
            - regions: List of allowed regions (if column exists)

    Returns:
        DataFrame with matching articles containing:
        article_id, source, title, link, category, published_date, has_content
    """
    if df.empty or not query or not query.strip():
        return pd.DataFrame(columns=[
            'article_id', 'source', 'title', 'link', 'category', 'published_date', 'has_content'
        ])

    if search_fields is None:
        search_fields = ['title', 'summary', 'content']

    # Get cached index (or build new one if stale)
    index = get_or_build_index(df, fields=tuple(search_fields))

    # Execute query
    matching_ids = execute_query(index, query)

    if not matching_ids:
        return pd.DataFrame(columns=[
            'article_id', 'source', 'title', 'link', 'category', 'published_date', 'has_content'
        ])

    # Filter DataFrame to matches
    mask = df['article_id'].astype(str).isin(matching_ids)
    result_df = df[mask].copy()

    # Apply optional filters
    if filters:
        if 'sources' in filters and filters['sources']:
            result_df = result_df[result_df['source'].isin(filters['sources'])]
        if 'categories' in filters and filters['categories']:
            result_df = result_df[result_df['category'].isin(filters['categories'])]
        if 'regions' in filters and filters['regions'] and 'region' in result_df.columns:
            result_df = result_df[result_df['region'].isin(filters['regions'])]

    # Add has_content flag
    result_df['has_content'] = result_df['article_id'].astype(str).map(
        lambda aid: index.article_has_content.get(aid, False)
    )

    # Select output columns
    output_cols = ['article_id', 'source', 'title', 'link', 'category', 'published_date']
    available_cols = [c for c in output_cols if c in result_df.columns]
    available_cols.append('has_content')

    return result_df[available_cols].reset_index(drop=True)


def build_keyword_index(
    df: pd.DataFrame,
    keywords: list[str],
    search_fields: list[str] = None
) -> dict[str, set[str]]:
    """
    Precompute a keyword -> article_ids index for efficient filtering.

    Args:
        df: DataFrame with articles
        keywords: List of keywords to index
        search_fields: List of column names to search. Defaults to ['title', 'summary', 'content']

    Returns:
        Dictionary mapping keyword -> set of article_ids that match
    """
    if search_fields is None:
        search_fields = ['title', 'summary', 'content']

    # Get cached index (or build new one if stale)
    index = get_or_build_index(df, fields=tuple(search_fields))

    # Query each keyword
    result = {}
    for keyword in keywords:
        matching_ids = execute_query(index, keyword)
        result[keyword] = matching_ids

    return result


def filter_keywords_with_results(
    df: pd.DataFrame,
    keywords: list[str],
    search_fields: list[str] = None
) -> list[tuple[str, int]]:
    """
    Filter keywords to only those that return results, with counts.

    Args:
        df: DataFrame with articles
        keywords: List of candidate keywords
        search_fields: List of column names to search. Defaults to ['title', 'summary', 'content']

    Returns:
        List of (keyword, count) tuples, sorted by count desc then alphabetically.
        Only includes keywords with count > 0.
    """
    if search_fields is None:
        search_fields = ['title', 'summary', 'content']

    keyword_index = build_keyword_index(df, keywords, search_fields)

    # Build list of (keyword, count) tuples
    keyword_counts = [
        (keyword, len(article_ids))
        for keyword, article_ids in keyword_index.items()
        if len(article_ids) > 0
    ]

    # Sort by count descending, then alphabetically
    keyword_counts.sort(key=lambda x: (-x[1], x[0]))

    return keyword_counts


def format_keyword_option(keyword: str, count: int) -> str:
    """
    Format a keyword option with its count for display in dropdown.

    Args:
        keyword: The keyword
        count: Number of matching articles

    Returns:
        Formatted string like "keyword (12 articles)"
    """
    article_word = "article" if count == 1 else "articles"
    return f"{keyword} ({count} {article_word})"


def parse_keyword_from_option(option: str) -> str:
    """
    Extract the keyword from a formatted option string.

    Args:
        option: Formatted option like "keyword (12 articles)"

    Returns:
        The keyword without the count suffix
    """
    match = re.match(r'^(.+?)\s*\(\d+\s+articles?\)$', option)
    if match:
        return match.group(1).strip()
    return option.strip()


# Unified search function - same matcher used by News Feed and Context Explorer
def search_all_time(
    df: pd.DataFrame,
    query: str,
    search_fields: list[str] = None
) -> pd.DataFrame:
    """
    Unified search across articles with full-text capabilities.

    This is the SINGLE search engine used by BOTH:
    - News Feed (filtered by date window)
    - Context Explorer (ALL TIME, independent of date window)

    Uses unified text normalization from textnorm module:
    - 'iGaming' -> matches 'igaming' and 'gaming'
    - 'eCricket' -> matches 'ecricket' and 'cricket'
    - 'eSports' -> matches 'esports'

    Matching strategy:
    - Short tokens (< 4 chars like 'AI'): word-boundary regex to reduce noise
    - Long tokens (>= 4 chars like 'gaming'): substring match for flexibility
    - Quoted phrases: exact substring match

    Args:
        df: DataFrame with articles (can be date-filtered or full history)
        query: Search query string (supports phrases, AND, OR)
        search_fields: Fields to search (default: title, summary, content)

    Returns:
        DataFrame with matching articles including has_content flag
    """
    return search_articles(df, query, search_fields)
