#!/usr/bin/env python3
"""
Clarion Competitive Intelligence Dashboard
Interactive Streamlit dashboard using spaCy NER for entity extraction.
"""

__version__ = "1.0.0"

import sys
from pathlib import Path

# Add project root to sys.path
# (This allows importing from 'paths.py' and 'src/' even when running from app/)
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

import hashlib
import json
import os
import warnings
from collections import Counter
from datetime import datetime

from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
# On Streamlit Cloud, secrets are injected as environment variables
load_dotenv()

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from packaging import version

# Suppress coroutine warnings from Streamlit cache operations
warnings.filterwarnings("ignore", message="coroutine.*was never awaited")

# Streamlit version compatibility: width parameter changed in 1.33.0
# - Old versions (< 1.33): use_container_width=True
# - New versions (>= 1.33): width='stretch'
_ST_VERSION = version.parse(st.__version__)
_USE_NEW_WIDTH_PARAM = _ST_VERSION >= version.parse("1.33.0")

def _get_width_kwargs():
    """Return the correct width kwargs for the current Streamlit version."""
    if _USE_NEW_WIDTH_PARAM:
        return {"width": "stretch"}
    else:
        return {"use_container_width": True}

# Debug mode flag - set DEBUG_MODE=1 to show debug tools
DEBUG_MODE = os.getenv('DEBUG_MODE', '').lower() in ('1', 'true', 'yes')

# spaCy is optional - NER features will be disabled if not installed
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    spacy = None

# Centralized file paths
from paths import COMPANY_METADATA_JSON, DAILY_ANALYSIS_JSON, DAILY_BRIEFING_MD, GEMINI_CACHE_JSON, NEWS_HISTORY_CSV
from src.config import SEARCH_FIELDS_DEFAULT
from src.gemini_cache import get_cache_stats, load_disk_cache
from src.reader_advantages_v2 import (
    advantages_to_csv as advantages_to_csv_v2,
)
from src.reader_advantages_v2 import (
    detect_all_advantages,
)
from src.search import (
    filter_keywords_with_results,
    format_keyword_option,
    get_csv_fingerprint,
    parse_keyword_from_option,
    search_all_time,
)
from src.taxonomy import (
    classify_topic,
    is_platform_domain,
    normalize_company,
    normalize_region,
    should_ignore,
)

# Version info for cache invalidation (may not exist on first run)
try:
    from src._version import DATA_VERSION, PIPELINE_TIMESTAMP
except ImportError:
    DATA_VERSION = None
    PIPELINE_TIMESTAMP = None

def _validate_and_refresh_caches():
    """
    Check if data files have been updated and invalidate caches if needed.

    This runs on each page load to ensure we're using fresh data.
    Called at the start of main() to handle pipeline updates.
    """
    from src.gemini_cache import get_cache_stats, load_disk_cache

    # Force a cache check (will reload if file changed)
    load_disk_cache()

    # Log cache status for debugging
    stats = get_cache_stats()
    if stats['valid_entries'] > 0:
        print(f"Gemini cache: {stats['valid_entries']} valid entries loaded")

    return stats


def _render_data_freshness():
    """Show data freshness info in sidebar."""
    from paths import GEMINI_CACHE_JSON, NEWS_HISTORY_CSV
    from src.gemini_cache import get_cache_stats

    with st.sidebar:
        st.divider()
        st.caption("Data Freshness")

        # CSV last modified
        if NEWS_HISTORY_CSV.exists():
            csv_mtime = datetime.fromtimestamp(NEWS_HISTORY_CSV.stat().st_mtime)
            st.caption(f"Data updated: {csv_mtime.strftime('%Y-%m-%d %H:%M')}")

        # Cache status
        if GEMINI_CACHE_JSON.exists():
            stats = get_cache_stats()
            if stats['valid_entries'] > 0:
                cache_status = f"{stats['valid_entries']} cached"
            else:
                cache_status = "Empty"
            st.caption(f"AI Cache: {cache_status}")
        else:
            st.caption("AI Cache: Not found")

        # Version info
        try:
            from src._version import DATA_VERSION, PIPELINE_TIMESTAMP
            st.caption(f"Pipeline v{DATA_VERSION}")
        except ImportError:
            pass


# Gemini search enhancement (optional - works without API key)
try:
    from src.search_gemini import expand_query, init_gemini
    GEMINI_SEARCH_AVAILABLE = init_gemini()
except ImportError:
    GEMINI_SEARCH_AVAILABLE = False
    expand_query = None

# Gemini NER analysis enhancement (optional - works without API key)
try:
    from src.gemini_ner_analysis import (
        CACHE_TTL_SECONDS,
        analyze_company_landscape,
        # Legacy functions for backward compatibility
        analyze_geographic_gaps,
        analyze_topic_trends,
        enhance_reader_advantages_with_gemini,
        generate_battleground_summary,
        get_company_insight,
        get_geo_insight,
        get_regional_insight,
        get_topic_insight,
        is_gemini_available,
        reinit_gemini,
    )
    from src.gemini_ner_analysis import init_gemini as init_gemini_ner
    GEMINI_NER_AVAILABLE = init_gemini_ner()
except ImportError:
    GEMINI_NER_AVAILABLE = False
    CACHE_TTL_SECONDS = 86400  # Fallback: 24 hours
    reinit_gemini = None
    is_gemini_available = None
    get_geo_insight = None
    get_company_insight = None
    get_topic_insight = None
    get_regional_insight = None
    analyze_geographic_gaps = None
    analyze_company_landscape = None
    analyze_topic_trends = None
    generate_battleground_summary = None
    enhance_reader_advantages_with_gemini = None


def compute_search_parity(
    query: str,
    filtered_df: pd.DataFrame,
    df_history: pd.DataFrame,
    search_fields: list
) -> dict:
    """
    Compute search parity between News Feed (windowed) and Context Explorer (all-time).

    Both use search_all_time but on different DataFrames:
    - News Feed: searches filtered_df (date-windowed)
    - Context Explorer: searches df_history (all time), then we filter to window for comparison

    Returns dict with parity metrics and differing article details.
    """

    # News Feed pipeline: search on filtered_df (already windowed)
    news_feed_results = search_all_time(filtered_df, query, search_fields=search_fields)
    news_feed_ids = set(news_feed_results['article_id'].astype(str)) if not news_feed_results.empty else set()

    # Context Explorer pipeline: search on df_history (all time)
    context_explorer_results = search_all_time(df_history, query, search_fields=search_fields)

    # For fair comparison, filter CE results to the same window as filtered_df
    if not context_explorer_results.empty and 'published_date' in context_explorer_results.columns:
        # Get the date range from filtered_df
        if not filtered_df.empty and 'published_date' in filtered_df.columns:
            min_date = filtered_df['published_date'].min()
            max_date = filtered_df['published_date'].max()

            # Parse dates in CE results
            ce_dates = pd.to_datetime(context_explorer_results['published_date'], utc=True, errors='coerce')
            mask = (ce_dates >= min_date) & (ce_dates <= max_date)
            ce_windowed = context_explorer_results[mask]
            context_explorer_ids = set(ce_windowed['article_id'].astype(str)) if not ce_windowed.empty else set()
        else:
            context_explorer_ids = set(context_explorer_results['article_id'].astype(str))
    else:
        context_explorer_ids = set()

    # Compute symmetric difference
    only_in_news_feed = news_feed_ids - context_explorer_ids
    only_in_context_explorer = context_explorer_ids - news_feed_ids
    is_parity = len(only_in_news_feed) == 0 and len(only_in_context_explorer) == 0

    # Get details for differing articles (limit to 25)
    def get_details(article_ids, df):
        if not article_ids:
            return []
        subset = df[df['article_id'].astype(str).isin(article_ids)].head(25)
        return [
            {'id': str(row.get('article_id', '')), 'title': str(row.get('title', ''))[:60]}
            for _, row in subset.iterrows()
        ]

    return {
        'news_feed_count': len(news_feed_ids),
        'context_explorer_count': len(context_explorer_ids),
        'only_in_news_feed': only_in_news_feed,
        'only_in_context_explorer': only_in_context_explorer,
        'news_feed_only_details': get_details(only_in_news_feed, filtered_df),
        'context_explorer_only_details': get_details(only_in_context_explorer, df_history),
        'is_parity': is_parity,
        'diff_count': len(only_in_news_feed) + len(only_in_context_explorer),
    }


# Page configuration
st.set_page_config(
    page_title="Clarion Competitive Intelligence",
    page_icon="🎰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CRITICAL FIX (P1-1): Initialize session state to prevent KeyError on first load
if 'gap_quick_select' not in st.session_state:
    st.session_state.gap_quick_select = "None"
if 'drill_down_input' not in st.session_state:
    st.session_state.drill_down_input = ""

# Initialize global session state (AI caches are now filter-keyed dynamically)
# Only initialize keys that need global state
global_session_keys = [
    'last_filter_key',  # Track current filter for debugging
    'ai_seo_retry_requested',  # Global retry flag
]
for key in global_session_keys:
    if key not in st.session_state:
        st.session_state[key] = None


# ============================================================================
# JSON-Safe DataFrame Conversion Helper
# ============================================================================

def dataframe_to_json_safe(df: pd.DataFrame, max_records: int = 50) -> str:
    """
    Convert DataFrame to JSON-safe string, handling Timestamps and other non-serializable types.

    Args:
        df: DataFrame to convert
        max_records: Maximum number of records to include

    Returns:
        JSON string safe for Gemini API calls
    """
    # Take only required columns and limit records
    cols_needed = ['title', 'summary', 'source', 'category', 'published_date']
    available_cols = [c for c in cols_needed if c in df.columns]

    # Create a copy to avoid modifying original
    subset = df[available_cols].head(max_records).copy()

    # Convert any datetime/Timestamp columns to ISO format strings
    for col in subset.columns:
        if pd.api.types.is_datetime64_any_dtype(subset[col]):
            subset[col] = subset[col].dt.strftime('%Y-%m-%d').fillna('')
        elif subset[col].dtype == 'object':
            # Handle any remaining Timestamp objects in object columns
            subset[col] = subset[col].apply(
                lambda x: x.isoformat() if isinstance(x, (pd.Timestamp, datetime)) else x
            )

    # Convert to records and serialize
    records = subset.to_dict('records')
    return json.dumps(records, default=str)  # default=str as final fallback


# ============================================================================
# Company Metadata Loading (Auto-generated from LLM)
# ============================================================================

@st.cache_resource
def load_company_metadata():
    """
    Load auto-generated company metadata from JSON file.
    Returns empty dict if file doesn't exist.
    Cached to avoid repeated disk I/O.
    """
    if not COMPANY_METADATA_JSON.exists():
        return {}

    try:
        with COMPANY_METADATA_JSON.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def get_company_metadata(name: str) -> dict:
    """
    Get metadata for a company by name.

    Tries exact match first, then case-insensitive match.
    Returns default structure if not found.

    Args:
        name: Company name to lookup

    Returns:
        Dict with company metadata (type, segment, etc.)
    """
    meta_all = load_company_metadata()

    # Try exact match first
    metadata = None
    if name in meta_all:
        metadata = meta_all[name]
    else:
        # Fallback: case-insensitive match
        lower_map = {k.lower(): v for k, v in meta_all.items()}
        if name.lower() in lower_map:
            metadata = lower_map[name.lower()]

    # Map new schema to old schema for backwards compatibility
    if metadata:
        # Try new schema first (type, primary_segment), then fall back to old schema (company_type, business_segment)
        company_type = metadata.get("type") or metadata.get("company_type", "unknown")
        business_segment = metadata.get("primary_segment") or metadata.get("business_segment", "unknown")

        return {
            "canonical_name": name,
            "type": company_type,
            "primary_segment": business_segment,
            "is_regulator": company_type == "regulator",
            "is_media": company_type == "media",
            "confidence": metadata.get("confidence", 0.0),
            "mention_count": 0,
            "enriched": metadata.get("enriched", False)
        }

    # Default fallback if not found
    return {
        "canonical_name": name,
        "type": "unknown",
        "primary_segment": "unknown",
        "is_regulator": False,
        "is_media": False,
        "confidence": 0.0,
        "mention_count": 0
    }


# Publisher domains to filter OUT from entity extraction (domain-based matching)
# Maps canonical publisher name to their domain for precise filtering
PUBLISHER_DOMAINS = {
    # Competitor publishers
    'SBC News': 'sbcnews.co.uk',
    'iGaming Future': 'igamingfuture.com',
    'Next.io': 'next.io',
    'SiGMA World': 'sigma.world',
    'EGR Global': 'egrmagazine.com',
    'CDC Gaming': 'cdcgamingreports.com',
    'Global Gaming Insider': 'globalgaminginsider.com',
    'iGaming Today': 'igamingtoday.com',

    # Internal brands
    'iGaming Business': 'igamingbusiness.com',
    'iGB Affiliate': 'igbaffiliate.com',
    'GGB Magazine': 'ggbmagazine.com',
    'ICE Gaming': 'icegaming.com',
    'Clarion Events': 'clarionevents.com'
}

# Extract domain values for matching
EXCLUDED_DOMAINS = set(PUBLISHER_DOMAINS.values())


# Internal brand domains for robust category detection
# Note: ice365.com and ice365.news redirect to icegaming.com and are excluded
INTERNAL_DOMAINS = {
    'igamingbusiness.com',
    'igbaffiliate.com',
    'ggbmagazine.com',
    'ggbdirectory.com',
    'clarionevents.com'
}

# Non-gambling organizations to exclude from sponsor candidate lists
# These are generic tech/platform companies, entertainment media, political entities,
# and acronyms/terms that are not companies
STOP_ORGS = {
    # Tech giants
    'google', 'alphabet', 'meta', 'facebook', 'microsoft', 'apple', 'amazon',
    # Social platforms
    'youtube', 'tiktok', 'x', 'twitter', 'linkedin', 'instagram', 'whatsapp',
    # Media/entertainment
    'netflix', 'warner bros', 'warner bros.', 'paramount', 'nyse', 'nasdaq',
    'wbd', 'warner bros discovery', "warner bros discovery's",
    # Political parties/organizations (not companies)
    'labour', 'labour party', 'conservative', 'conservative party', 'tory', 'tories',
    'democrat', 'democrats', 'republican', 'republicans', 'congress', 'parliament',
    'government', 'eu', 'european union', 'un', 'united nations',
    # Acronyms/terms that are not companies (false positives from NER)
    'pat', 'tacp', 'nsw', 'flo', 'atg', 'ksa',  # Common acronyms misidentified as orgs
    'the international tennis integrity agency', 'itia',  # Sports integrity body
    'tennis anti-corruption program',  # Program, not company
    # Job titles / corporate terms (not companies)
    'non-executive', 'non executive', 'executive', 'ceo', 'cfo', 'cto', 'coo',
    # Partial product/game names extracted from article titles (not companies)
    "play'n", "play'n go content",  # From "Betway Launches Play'n GO Content"
    # Headline fragments - NER incorrectly extracting parts of article titles as ORGs
    # These contain action words that indicate they're headlines, not company names
    'launches', 'partners', 'hustle', 'global partners', 'content',
    'announces', 'expands', 'acquires', 'signs', 'joins', 'enters',
    'debuts', 'unveils', 'reveals', 'introduces', 'secures', 'wins',
    # Specific headline fragments seen in false positives
    "betway launches play'n go content", "betby launches play'n go content",
    'hustle in igaming she', 'hustle in igaming',
    'global partners 1spin4win', 'partners 1spin4win',
    # Generic headline patterns
    'in igaming', 'igaming she', 'she leadership',
}

# Action words commonly found in headlines - used to detect headline fragments
HEADLINE_ACTION_WORDS = {
    'launches', 'partners', 'announces', 'expands', 'acquires', 'signs',
    'joins', 'enters', 'debuts', 'unveils', 'reveals', 'introduces',
    'secures', 'wins', 'extends', 'renews', 'targets', 'appoints',
    'names', 'hires', 'promotes', 'strengthens', 'boosts', 'enhances',
}


def is_headline_fragment(text: str) -> bool:
    """
    Check if text looks like a headline fragment (not a company name).

    Headline fragments typically:
    1. Contain action words like 'Launches', 'Partners', 'Announces'
    2. Have 3+ words (real company names are usually 1-3 words)
    3. Contain lowercase connecting words in unusual positions

    Args:
        text: The candidate company name text

    Returns:
        True if text looks like a headline fragment, False otherwise
    """
    if not text or not isinstance(text, str):
        return False

    text_lower = text.lower().strip()
    words = text_lower.split()

    # Check if any word is an action word
    for word in words:
        if word in HEADLINE_ACTION_WORDS:
            return True

    # Long phrases with 4+ words are likely headlines
    if len(words) >= 4:
        return True

    # Check for patterns like "X in Y" which are headline fragments
    if ' in ' in text_lower and len(words) >= 3:
        return True

    return False


def get_domain_from_url(url: str) -> str:
    """
    Extract domain from URL for publisher filtering.
    Returns empty string if URL is invalid.

    Example:
        >>> get_domain_from_url("https://www.sbcnews.co.uk/article/...")
        'sbcnews.co.uk'
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(str(url))
        domain = parsed.netloc.lower()
        # Remove www. prefix for consistency
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def is_internal(source: str, link: str) -> bool:
    """
    Check if article is from an internal Clarion brand.

    Uses both domain matching and source name matching for robustness.

    Args:
        source: Article source name
        link: Article URL

    Returns:
        True if article is from internal brand, False otherwise

    Example:
        >>> is_internal("iGaming Business", "https://igamingbusiness.com/article")
        True
        >>> is_internal("SBC News", "https://sbcnews.co.uk/article")
        False
    """
    # Check domain
    host = get_domain_from_url(link)
    if any(host == domain or host.endswith('.' + domain) for domain in INTERNAL_DOMAINS):
        return True

    # Check source name (normalized)
    source_normalized = (source or '').strip().lower()
    internal_source_names = {
        'igaming business',
        'igb affiliate',
        'ggb magazine',
        'ggb directory',
        'ice365',
        'clarion events'
    }

    return source_normalized in internal_source_names


@st.cache_resource
def load_spacy_model():
    """Load spaCy model (cached to avoid reloading on every interaction).

    Returns None if spaCy is not available or model not installed.
    NER features will be disabled but dashboard will still work.
    """
    if not SPACY_AVAILABLE:
        return None
    try:
        nlp = spacy.load("en_core_web_sm")
        return nlp
    except OSError:
        st.warning("⚠️ spaCy model 'en_core_web_sm' not found. NER entity extraction disabled. To enable, run:\n```bash\npip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl\n```")
        return None


def _get_csv_cache_key():
    """Generate cache key based on CSV file properties for cache invalidation."""
    if not NEWS_HISTORY_CSV.exists():
        return "missing"
    return get_csv_fingerprint(NEWS_HISTORY_CSV)


@st.cache_data(show_spinner="Loading article history...")
def load_history_data(cache_key: str = "default"):
    """
    Load full historical news articles from CSV file.
    Returns a pandas DataFrame and a stats dict.

    IMPORTANT: cache_key parameter IS used for cache invalidation.
    When the CSV fingerprint changes (new data), the cache is invalidated.
    """
    if not NEWS_HISTORY_CSV.exists():
        st.warning("⚠️ No history file found. Run main.py to start building history.")
        return pd.DataFrame(), {}

    # Get fingerprint for cache invalidation
    fingerprint = get_csv_fingerprint(NEWS_HISTORY_CSV)

    df_history = pd.read_csv(NEWS_HISTORY_CSV)

    # Drop any obviously empty rows if present
    df_history = df_history.dropna(subset=["title", "link"], how="all")

    # Parse publication date - normalize to UTC
    df_history["published_dt"] = pd.to_datetime(
        df_history["published_date"], errors="coerce", utc=True
    )
    df_history = df_history.dropna(subset=["published_dt"])
    df_history["published_dt"] = df_history["published_dt"].dt.tz_localize(None)

    # Deduplicate articles by title+source (Google News URLs have varying query params)
    # Keep first occurrence (oldest) to preserve original article_id
    rows_before = len(df_history)
    df_history = df_history.drop_duplicates(subset=["title", "source"], keep="first")
    rows_after = len(df_history)
    if rows_before != rows_after:
        print(f"Deduplicated {rows_before - rows_after} duplicate articles")

    stats = {
        "total_rows": len(df_history),
        "min_date": df_history["published_dt"].min(),
        "max_date": df_history["published_dt"].max(),
        "csv_fingerprint": fingerprint
    }
    return df_history, stats


def load_briefing():
    """Load the AI-generated briefing."""
    try:
        if not DAILY_BRIEFING_MD.exists():
            return None

        with open(DAILY_BRIEFING_MD, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return None


def _generate_nlp_cache_key(df):
    """
    Generate stable cache key using ALL article identifiers.
    Ensures cache invalidates when data changes anywhere in dataframe.

    IMPORTANT: Now includes CSV fingerprint for proper cache invalidation.
    """
    if df.empty:
        return "empty_df"

    # Use article_id column if available (most reliable)
    if 'article_id' in df.columns:
        article_ids = sorted(df['article_id'].dropna().astype(str).tolist())
    elif 'link' in df.columns:
        article_ids = sorted(df['link'].dropna().astype(str).tolist())
    else:
        # Fallback: use all titles
        article_ids = sorted(df['title'].dropna().astype(str).tolist())

    # Hash ALL article IDs (not just first 5!) to prevent collisions
    ids_hash = hashlib.sha256('|'.join(article_ids).encode()).hexdigest()

    # Include row count, date range, and CSV fingerprint
    max_date = df['published_date'].max() if 'published_date' in df.columns else ""
    csv_fp = get_csv_fingerprint(NEWS_HISTORY_CSV) if NEWS_HISTORY_CSV.exists() else ""
    fingerprint = f"count:{len(df)}_date:{max_date}_ids:{ids_hash}_csv:{csv_fp}"

    return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]


# ============================================================================
# CACHED READER ADVANTAGES (Performance Optimization)
# ============================================================================

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Analyzing coverage patterns...")
def cached_reader_advantages(csv_fingerprint: str, window_days: int = 90) -> dict:
    """
    Cache expensive reader advantages computation.

    Uses CSV fingerprint as cache key - invalidates when data changes.
    """
    df = load_history_data(cache_key=csv_fingerprint)[0]
    if df is None or df.empty:
        return {
            'cards': [],
            'diagnostics': {'internal_articles': 0, 'competitor_articles': 0},
            'empty_message': 'No article data available'
        }

    # detect_all_advantages is already imported at module level
    return detect_all_advantages(df, window_days=window_days)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def cached_gemini_reader_enhancement(
    csv_fingerprint: str,
    pattern_json: str,
    internal_json: str,
    competitor_json: str,
    window_days: int = 90
) -> dict:
    """
    Cache Gemini AI enhancement for reader advantages.

    Separate cache allows pattern detection to work even if AI fails.
    """
    try:
        from src.gemini_ner_analysis import enhance_reader_advantages_with_gemini
        return enhance_reader_advantages_with_gemini(
            pattern_json, internal_json, competitor_json, window_days
        )
    except ImportError:
        return {"fallback_used": True, "error": "Gemini module not available"}
    except Exception as e:
        return {"fallback_used": True, "error": str(e)[:100]}


@st.cache_data(show_spinner=False)
def process_articles_with_nlp(df, _nlp):
    """
    Process all articles with spaCy NER using taxonomy normalization.
    Uses rule-based classify_topic for topic detection (no ML models).
    Returns three lists: locations (GPE), companies (ORG), and key topics.
    Also enriches df with article-level metadata for topic-aware search.

    Cached to avoid recomputation on each interaction.
    If _nlp is None (spaCy not available), returns empty entity lists but still processes topics.
    """
    # Short-circuit for empty dataframe or no NLP
    if df.empty or _nlp is None:
        return {
            'competitor_locations': [],
            'internal_locations': [],
            'competitor_companies': [],
            'internal_companies': [],
            'competitor_topics': [],
            'internal_topics': [],
            'competitor_locations_per_article': [],
            'internal_locations_per_article': [],
            'competitor_companies_per_article': [],
            'internal_companies_per_article': [],
            'competitor_topics_per_article': [],
            'internal_topics_per_article': []
        }

    # Fix category assignment using robust domain/source detection
    # Some articles may have incorrect category from ingestion
    for idx, row in df.iterrows():
        source = row.get('source', '')
        link = row.get('link', '')
        if is_internal(source, link):
            df.at[idx, 'category'] = 'internal'
        else:
            df.at[idx, 'category'] = 'competitor'

    # Separate by category
    competitor_articles = df[df['category'] == 'competitor']
    internal_articles = df[df['category'] == 'internal']

    # Storage for entities
    competitor_locations = []
    internal_locations = []

    competitor_companies = []
    internal_companies = []

    competitor_topics = []
    internal_topics = []

    # Use rule-based classification from taxonomy.py (no ML models)
    # Use .copy() and .loc to avoid SettingWithCopyWarning
    df = df.copy()
    df.loc[:, 'ml_topic'] = df.apply(
        lambda row: classify_topic(str(row.get('title', '')) + ' ' + str(row.get('summary', '')))[0]
        if classify_topic(str(row.get('title', '')) + ' ' + str(row.get('summary', '')))
        else None,
        axis=1
    )

    # Initialize columns for article-level metadata
    df.loc[:, 'topics_list'] = None
    df.loc[:, 'companies_list'] = None
    df.loc[:, 'regions_list'] = None

    # Re-slice after adding ml_topic column
    competitor_articles = df[df['category'] == 'competitor']
    internal_articles = df[df['category'] == 'internal']

    # Process competitor articles
    for idx, article in competitor_articles.iterrows():
        text = str(article.get('title', '')) + ' ' + str(article.get('summary', ''))
        doc = _nlp(text)

        # Get article domain for publisher filtering
        article_link = article.get('link', '')
        article_domain = get_domain_from_url(article_link)

        # Article-level lists
        article_topics = []
        article_companies_list = []
        article_regions_list = []

        # Get ML topic (already computed)
        ml_topic = article.get('ml_topic')
        if ml_topic:
            competitor_topics.append(ml_topic)
            article_topics.append(ml_topic)

        # Also get all rule-based topics for better coverage
        rule_topics = classify_topic(text)
        for topic in rule_topics:
            if topic not in article_topics:
                article_topics.append(topic)

        # Extract locations (GPE and LOC entities)
        for ent in doc.ents:
            if ent.label_ in {"GPE", "LOC"}:
                # Skip if should be ignored
                if should_ignore(ent.text):
                    continue
                # Normalize to regional grouping
                normalized_region = normalize_region(ent.text)
                # Only add if recognized as a valid location
                if normalized_region:
                    competitor_locations.append(normalized_region)
                    if normalized_region not in article_regions_list:
                        article_regions_list.append(normalized_region)
            elif ent.label_ == "ORG":
                # Skip if should be ignored
                if should_ignore(ent.text):
                    continue
                # Skip if entity matches publisher domain (avoid false positives)
                if article_domain and article_domain in EXCLUDED_DOMAINS:
                    # Check if entity text could be the publisher name
                    entity_lower = ent.text.lower()
                    # Simple check: if entity contains key terms from domain, skip it
                    domain_parts = article_domain.replace('.com', '').replace('.co.uk', '').split('.')
                    if any(part in entity_lower for part in domain_parts if len(part) > 3):
                        continue
                # Normalize company name
                normalized_company = normalize_company(ent.text)
                # Skip if in STOP_ORGS (generic tech companies)
                if normalized_company.lower() in STOP_ORGS:
                    continue
                # Skip headline fragments (NER incorrectly extracting article title phrases)
                if is_headline_fragment(ent.text):
                    continue
                # Skip if article link is from a platform domain
                if article_link and is_platform_domain(get_domain_from_url(article_link)):
                    continue
                competitor_companies.append(normalized_company)
                if normalized_company not in article_companies_list:
                    article_companies_list.append(normalized_company)

        # Comprehensive phrase fallbacks for regions (catches mentions NER might miss)
        text_lower = text.lower()

        # North America - expanded with US gaming terms, states, casinos, and operators
        na_phrases = [
            'las vegas', 'nevada', 'new jersey', 'atlantic city', 'california',
            'new york', 'pennsylvania', 'michigan', 'ohio', 'illinois', 'arizona',
            'colorado', 'massachusetts', 'connecticut', 'indiana', 'iowa', 'louisiana',
            'maryland', 'virginia', 'west virginia', 'tennessee', 'kansas', 'missouri',
            'florida', 'texas', 'washington state', 'tribal gaming', 'tribal casino',
            'tribal law', 'indian gaming', 'native american', 'united states', 'u.s.',
            ' usa ', 'american gaming', 'foxwoods', 'mohegan sun', 'seneca gaming',
            'san manuel', 'pechanga', 'station casinos', 'venetian', 'wynn resorts',
            'mgm', 'caesars', 'hard rock', 'draftkings', 'fanduel', 'betmgm'
        ]
        has_tribal = ' tribal ' in text_lower or text_lower.startswith('tribal ') or text_lower.endswith(' tribal')
        if any(phrase in text_lower for phrase in na_phrases) or has_tribal:
            if 'North America' not in article_regions_list:
                article_regions_list.append('North America')
                competitor_locations.append('North America')

        # LatAm - expanded
        if any(phrase in text_lower for phrase in ['latam', 'latin america', 'latin-america', 'brazil', 'brasil', 'argentina', 'mexico', 'colombia', 'chile', 'peru', 'uruguay']):
            if 'LatAm' not in article_regions_list:
                article_regions_list.append('LatAm')
                competitor_locations.append('LatAm')

        # Middle East & Africa - expanded
        if any(phrase in text_lower for phrase in ['mena', 'gcc', 'middle east', 'mea', 'africa', 'uae', 'dubai', 'saudi', 'south africa', 'nigeria', 'kenya', 'egypt']):
            if 'Middle East & Africa' not in article_regions_list:
                article_regions_list.append('Middle East & Africa')
                competitor_locations.append('Middle East & Africa')

        # Europe - new fallback
        if any(phrase in text_lower for phrase in ['uk ', ' uk', 'united kingdom', 'britain', 'british', 'germany', 'spain', 'italy', 'france', 'netherlands', 'sweden', 'denmark', 'malta', 'gibraltar', 'isle of man', 'alderney', 'european', ' eu ']):
            if 'Europe' not in article_regions_list:
                article_regions_list.append('Europe')
                competitor_locations.append('Europe')

        # Asia-Pacific - new fallback
        if any(phrase in text_lower for phrase in ['asia', 'asian', 'japan', 'philippines', 'macau', 'singapore', 'australia', 'new zealand', 'india', 'south korea', 'thailand', 'vietnam']):
            if 'Asia Pacific' not in article_regions_list:
                article_regions_list.append('Asia Pacific')
                competitor_locations.append('Asia Pacific')

        # Store article-level metadata in dataframe
        df.at[idx, 'topics_list'] = article_topics
        df.at[idx, 'companies_list'] = article_companies_list
        df.at[idx, 'regions_list'] = article_regions_list

    # Process internal articles
    for idx, article in internal_articles.iterrows():
        text = str(article.get('title', '')) + ' ' + str(article.get('summary', ''))
        doc = _nlp(text)

        # Get article domain for publisher filtering
        article_link = article.get('link', '')
        article_domain = get_domain_from_url(article_link)

        # Article-level lists
        article_topics = []
        article_companies_list = []
        article_regions_list = []

        # Get ML topic (already computed)
        ml_topic = article.get('ml_topic')
        if ml_topic:
            internal_topics.append(ml_topic)
            article_topics.append(ml_topic)

        # Also get all rule-based topics for better coverage
        rule_topics = classify_topic(text)
        for topic in rule_topics:
            if topic not in article_topics:
                article_topics.append(topic)

        # Extract locations (GPE and LOC entities)
        for ent in doc.ents:
            if ent.label_ in {"GPE", "LOC"}:
                # Skip if should be ignored
                if should_ignore(ent.text):
                    continue
                # Normalize to regional grouping
                normalized_region = normalize_region(ent.text)
                # Only add if recognized as a valid location
                if normalized_region:
                    internal_locations.append(normalized_region)
                    if normalized_region not in article_regions_list:
                        article_regions_list.append(normalized_region)
            elif ent.label_ == "ORG":
                # Skip if should be ignored
                if should_ignore(ent.text):
                    continue
                # Skip if entity matches publisher domain (avoid false positives)
                if article_domain and article_domain in EXCLUDED_DOMAINS:
                    # Check if entity text could be the publisher name
                    entity_lower = ent.text.lower()
                    # Simple check: if entity contains key terms from domain, skip it
                    domain_parts = article_domain.replace('.com', '').replace('.co.uk', '').split('.')
                    if any(part in entity_lower for part in domain_parts if len(part) > 3):
                        continue
                # Normalize company name
                normalized_company = normalize_company(ent.text)
                # Skip if in STOP_ORGS (generic tech companies)
                if normalized_company.lower() in STOP_ORGS:
                    continue
                # Skip headline fragments (NER incorrectly extracting article title phrases)
                if is_headline_fragment(ent.text):
                    continue
                # Skip if article link is from a platform domain
                if article_link and is_platform_domain(get_domain_from_url(article_link)):
                    continue
                internal_companies.append(normalized_company)
                if normalized_company not in article_companies_list:
                    article_companies_list.append(normalized_company)

        # Comprehensive phrase fallbacks for regions (catches mentions NER might miss)
        text_lower = text.lower()

        # North America - expanded with US gaming terms, states, casinos, and operators
        na_phrases = [
            'las vegas', 'nevada', 'new jersey', 'atlantic city', 'california',
            'new york', 'pennsylvania', 'michigan', 'ohio', 'illinois', 'arizona',
            'colorado', 'massachusetts', 'connecticut', 'indiana', 'iowa', 'louisiana',
            'maryland', 'virginia', 'west virginia', 'tennessee', 'kansas', 'missouri',
            'florida', 'texas', 'washington state', 'tribal gaming', 'tribal casino',
            'tribal law', 'indian gaming', 'native american', 'united states', 'u.s.',
            ' usa ', 'american gaming', 'foxwoods', 'mohegan sun', 'seneca gaming',
            'san manuel', 'pechanga', 'station casinos', 'venetian', 'wynn resorts',
            'mgm', 'caesars', 'hard rock', 'draftkings', 'fanduel', 'betmgm'
        ]
        has_tribal = ' tribal ' in text_lower or text_lower.startswith('tribal ') or text_lower.endswith(' tribal')
        if any(phrase in text_lower for phrase in na_phrases) or has_tribal:
            if 'North America' not in article_regions_list:
                article_regions_list.append('North America')
                internal_locations.append('North America')

        # LatAm - expanded
        if any(phrase in text_lower for phrase in ['latam', 'latin america', 'latin-america', 'brazil', 'brasil', 'argentina', 'mexico', 'colombia', 'chile', 'peru', 'uruguay']):
            if 'LatAm' not in article_regions_list:
                article_regions_list.append('LatAm')
                internal_locations.append('LatAm')

        # Middle East & Africa - expanded
        if any(phrase in text_lower for phrase in ['mena', 'gcc', 'middle east', 'mea', 'africa', 'uae', 'dubai', 'saudi', 'south africa', 'nigeria', 'kenya', 'egypt']):
            if 'Middle East & Africa' not in article_regions_list:
                article_regions_list.append('Middle East & Africa')
                internal_locations.append('Middle East & Africa')

        # Europe - new fallback
        if any(phrase in text_lower for phrase in ['uk ', ' uk', 'united kingdom', 'britain', 'british', 'germany', 'spain', 'italy', 'france', 'netherlands', 'sweden', 'denmark', 'malta', 'gibraltar', 'isle of man', 'alderney', 'european', ' eu ']):
            if 'Europe' not in article_regions_list:
                article_regions_list.append('Europe')
                internal_locations.append('Europe')

        # Asia-Pacific - new fallback
        if any(phrase in text_lower for phrase in ['asia', 'asian', 'japan', 'philippines', 'macau', 'singapore', 'australia', 'new zealand', 'india', 'south korea', 'thailand', 'vietnam']):
            if 'Asia Pacific' not in article_regions_list:
                article_regions_list.append('Asia Pacific')
                internal_locations.append('Asia Pacific')

        # Store article-level metadata in dataframe
        df.at[idx, 'topics_list'] = article_topics
        df.at[idx, 'companies_list'] = article_companies_list
        df.at[idx, 'regions_list'] = article_regions_list

    # Build per-article entity lists for coverage calculation
    competitor_locations_per_article = []
    internal_locations_per_article = []
    competitor_companies_per_article = []
    internal_companies_per_article = []
    competitor_topics_per_article = []
    internal_topics_per_article = []

    # Collect from stored article metadata
    # Include affiliate articles with competitor (external sources)
    for idx, article in df[df['category'].isin(['competitor', 'affiliate'])].iterrows():
        competitor_locations_per_article.append(article.get('regions_list') or [])
        competitor_companies_per_article.append(article.get('companies_list') or [])
        competitor_topics_per_article.append(article.get('topics_list') or [])

    for idx, article in df[df['category'] == 'internal'].iterrows():
        internal_locations_per_article.append(article.get('regions_list') or [])
        internal_companies_per_article.append(article.get('companies_list') or [])
        internal_topics_per_article.append(article.get('topics_list') or [])

    return {
        'competitor_locations': competitor_locations,
        'internal_locations': internal_locations,
        'competitor_companies': competitor_companies,
        'internal_companies': internal_companies,
        'competitor_topics': competitor_topics,
        'internal_topics': internal_topics,
        # Per-article lists for true coverage calculation
        'competitor_locations_per_article': competitor_locations_per_article,
        'internal_locations_per_article': internal_locations_per_article,
        'competitor_companies_per_article': competitor_companies_per_article,
        'internal_companies_per_article': internal_companies_per_article,
        'competitor_topics_per_article': competitor_topics_per_article,
        'internal_topics_per_article': internal_topics_per_article
    }


def calculate_entity_article_coverage(per_article_entities: list) -> list:
    """
    Calculate percentage of articles that mention each entity.

    Args:
        per_article_entities: List of lists, one list of entities per article.
                             Each inner list contains entities mentioned in that article.

    Returns:
        List of dicts with keys: entity, percentage, count
        where count = number of articles mentioning the entity (not total mentions)
        and percentage = (count / total_articles) * 100

    Example:
        If entity X appears 5 times in article 1 and 1 time in article 2,
        the count will be 2 (two articles), not 6 (total mentions).
    """
    if not per_article_entities:
        return []

    n_articles = len(per_article_entities)

    # Count in how many distinct articles each entity appears
    entity_article_count = Counter()

    for article_entities in per_article_entities:
        # Deduplicate entities within this article
        unique_entities_in_article = set(article_entities)
        # Increment counter once per article
        for entity in unique_entities_in_article:
            entity_article_count[entity] += 1

    # Calculate percentages
    entity_percentages = []
    for entity, article_count in entity_article_count.most_common(20):
        percentage = (article_count / n_articles) * 100
        entity_percentages.append({
            'entity': entity,
            'percentage': round(percentage, 2),
            'count': article_count  # Now represents number of articles, not mentions
        })

    return entity_percentages


def get_top_entities_comparison(competitor_per_article, internal_per_article, top_n=15):
    """
    Compare entity coverage between competitor and internal articles.
    Uses true article coverage (not mention frequency).

    Args:
        competitor_per_article: List of lists, each inner list contains entities from one competitor article
        internal_per_article: List of lists, each inner list contains entities from one internal article
        top_n: Number of top entities to return

    Returns:
        List of dicts with entity, competitor_pct, internal_pct
        where percentages represent % of articles mentioning the entity
    """
    # Get percentage coverage for both using correct article-based calculation
    competitor_percentages = calculate_entity_article_coverage(competitor_per_article)
    internal_percentages = calculate_entity_article_coverage(internal_per_article)

    # Create lookup dictionaries
    competitor_dict = {item['entity']: item['percentage'] for item in competitor_percentages}
    internal_dict = {item['entity']: item['percentage'] for item in internal_percentages}

    # Get all unique entities from competitors (top sources)
    all_entities = [item['entity'] for item in competitor_percentages[:top_n]]

    # Build comparison data
    comparison_data = []
    for entity in all_entities:
        comparison_data.append({
            'entity': entity,
            'competitor_pct': competitor_dict.get(entity, 0),
            'internal_pct': internal_dict.get(entity, 0)
        })

    return comparison_data


def find_articles_by_topic(df, topic_label):
    """
    Find all articles that belong to a specific topic cluster.
    Falls back to keyword search if topics_list column doesn't exist.
    Returns filtered dataframe with source, title, category, and article_id.
    """
    matching_articles = []

    # Check if topics_list column exists
    if 'topics_list' in df.columns:
        for _, article in df.iterrows():
            topics_list = article.get('topics_list')
            if topics_list and topic_label in topics_list:
                matching_articles.append({
                    'article_id': article.get('article_id', ''),
                    'source': article.get('source', 'Unknown'),
                    'title': article.get('title', 'No title'),
                    'link': article.get('link', ''),
                    'category': article.get('category', 'unknown'),
                    'date': article.get('published_date', 'No date')
                })
    else:
        # Fallback: use keyword search
        return find_articles_by_keyword(df, topic_label)

    return pd.DataFrame(matching_articles) if matching_articles else None


def find_articles_by_company(df, company_name):
    """
    Find all articles that mention a specific company via NER.
    Falls back to keyword search if companies_list column doesn't exist.
    Returns filtered dataframe with source, title, category, and article_id.
    """
    matching_articles = []

    # Check if companies_list column exists
    if 'companies_list' in df.columns:
        for _, article in df.iterrows():
            companies_list = article.get('companies_list')
            if companies_list and company_name in companies_list:
                matching_articles.append({
                    'article_id': article.get('article_id', ''),
                    'source': article.get('source', 'Unknown'),
                    'title': article.get('title', 'No title'),
                    'link': article.get('link', ''),
                    'category': article.get('category', 'unknown'),
                    'date': article.get('published_date', 'No date')
                })
    else:
        # Fallback: use keyword search
        return find_articles_by_keyword(df, company_name)

    return pd.DataFrame(matching_articles) if matching_articles else None


def find_articles_by_region(df, region_name):
    """
    Find all articles that mention a specific region via NER.
    Falls back to keyword search if regions_list column doesn't exist.
    Returns filtered dataframe with source, title, category, and article_id.
    """
    matching_articles = []

    # Check if regions_list column exists
    if 'regions_list' in df.columns:
        for _, article in df.iterrows():
            regions_list = article.get('regions_list')
            if regions_list and region_name in regions_list:
                matching_articles.append({
                    'article_id': article.get('article_id', ''),
                    'source': article.get('source', 'Unknown'),
                    'title': article.get('title', 'No title'),
                    'link': article.get('link', ''),
                    'category': article.get('category', 'unknown'),
                    'date': article.get('published_date', 'No date')
                })
    else:
        # Fallback: use keyword search
        return find_articles_by_keyword(df, region_name)

    return pd.DataFrame(matching_articles) if matching_articles else None


def find_articles_by_keyword(df, keyword):
    """
    Find all articles that mention a specific keyword via substring search.
    Fallback method for free-text searches.
    Returns filtered dataframe with source, title, category, and article_id.
    """
    keyword_lower = keyword.lower()

    matching_articles = []
    for _, article in df.iterrows():
        text = str(article.get('title', '')) + ' ' + str(article.get('summary', ''))
        if keyword_lower in text.lower():
            matching_articles.append({
                'article_id': article.get('article_id', ''),
                'source': article.get('source', 'Unknown'),
                'title': article.get('title', 'No title'),
                'link': article.get('link', ''),
                'category': article.get('category', 'unknown'),
                'date': article.get('published_date', 'No date')
            })

    return pd.DataFrame(matching_articles) if matching_articles else None


def find_articles_smart(df, search_term, known_topics, known_companies, known_regions):
    """
    Intelligently find articles based on search term type.

    Args:
        df: DataFrame with articles
        search_term: User's search query
        known_topics: List of known topic labels from Chart C
        known_companies: List of known company names from Chart B
        known_regions: List of known region names from Chart A/D

    Returns:
        Tuple of (matching_df, search_type)
        where search_type is 'topic', 'company', 'region', or 'keyword'
    """
    # Check if it's a known topic
    if search_term in known_topics:
        result = find_articles_by_topic(df, search_term)
        return result, 'topic'

    # Check if it's a known company
    if search_term in known_companies:
        result = find_articles_by_company(df, search_term)
        return result, 'company'

    # Check if it's a known region
    if search_term in known_regions:
        result = find_articles_by_region(df, search_term)
        return result, 'region'

    # Fall back to substring search
    result = find_articles_by_keyword(df, search_term)
    return result, 'keyword'


def _display_static_exhibitor_categories(categories):
    """Display static exhibitor categories as fallback when AI is unavailable."""
    if categories:
        for idx, category in enumerate(categories, 1):
            with st.container():
                st.markdown(f"**{idx}. {category.get('category', 'Unknown')}**")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("📊 **Evidence:**")
                    st.caption(category.get('evidence', 'N/A'))
                with col2:
                    st.markdown("💡 **Opportunity:**")
                    st.caption(category.get('opportunity', 'N/A'))
                st.markdown("---")
    else:
        st.info("No exhibitor categories identified in the current analysis.")


def generate_seo_insights(strategic_gaps, clarion_wins, market_pulse, df):
    """
    Generate SEO insights from analysis data with intelligent keyword extraction.

    Args:
        strategic_gaps: List of strategic gap dicts
        clarion_wins: List of Clarion win dicts
        market_pulse: List of market theme dicts
        df: Filtered DataFrame with articles

    Returns:
        Dict with SEO insights including smart trending keywords
    """
    import re
    from collections import Counter

    insights = {
        'content_gaps': [],
        'strengths_to_amplify': [],
        'trending_keywords': [],
        'recommendations': [],
        'keyword_analysis': {}  # Detailed keyword data
    }

    # ========== SMART KEYWORD EXTRACTION FROM ARTICLES ==========
    # Stop words to filter out
    STOP_WORDS = {
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'will', 'have',
        'has', 'been', 'were', 'are', 'was', 'its', 'their', 'our', 'your',
        'can', 'could', 'would', 'should', 'may', 'might', 'must', 'into',
        'over', 'under', 'after', 'before', 'between', 'through', 'during',
        'about', 'than', 'more', 'most', 'some', 'any', 'all', 'each',
        'new', 'first', 'last', 'year', 'years', 'also', 'just', 'only',
        'now', 'says', 'said', 'like', 'make', 'made', 'get', 'got'
    }

    # Industry-specific valuable terms to boost
    BOOST_TERMS = {
        'regulation', 'regulatory', 'license', 'licensing', 'compliance',
        'sports', 'betting', 'casino', 'poker', 'slots', 'igaming',
        'responsible', 'gambling', 'artificial', 'intelligence',
        'mobile', 'digital', 'online', 'platform', 'technology',
        'market', 'expansion', 'launch', 'partnership', 'acquisition',
        'revenue', 'growth', 'investment', 'funding', 'ipo',
        'brazil', 'latam', 'europe', 'asia', 'africa', 'americas',
        'esports', 'crypto', 'blockchain', 'nft', 'metaverse'
    }

    # Extract keywords from competitor vs internal articles
    competitor_keywords = Counter()
    internal_keywords = Counter()
    all_keywords = Counter()

    for _, row in df.iterrows():
        # Combine title and summary
        text = f"{row.get('title', '')} {row.get('summary', '')}".lower()

        # Extract words (alphanumeric, 3+ chars)
        words = re.findall(r'\b[a-z]{3,}\b', text)

        # Filter and count
        filtered_words = [w for w in words if w not in STOP_WORDS]

        category = row.get('category', 'competitor')
        if category == 'internal':
            internal_keywords.update(filtered_words)
        else:
            competitor_keywords.update(filtered_words)
        all_keywords.update(filtered_words)

    # Calculate trending keywords with NORMALIZED competitive intelligence
    trending = []

    # Get total article counts for normalization
    total_competitor_articles = len(df[df['category'] != 'internal'])
    total_internal_articles = len(df[df['category'] == 'internal'])

    if total_competitor_articles == 0 or total_internal_articles == 0:
        # Can't compare without both categories
        insights['trending_keywords'] = []
        insights['keyword_analysis'] = {
            'error': 'Need both competitor and internal articles',
            'competitor_articles': total_competitor_articles,
            'internal_articles': total_internal_articles
        }
    else:
        for keyword, total_count in all_keywords.most_common(100):
            comp_count = competitor_keywords.get(keyword, 0)
            int_count = internal_keywords.get(keyword, 0)

            # NORMALIZE by article count - calculate % of articles mentioning this keyword
            # This fixes the article imbalance problem
            comp_rate = (comp_count / total_competitor_articles) * 100
            int_rate = (int_count / total_internal_articles) * 100

            # Calculate normalized gap (percentage points difference)
            rate_gap = comp_rate - int_rate

            # Determine trend based on RATE difference, not raw counts
            # Using 2 percentage points as threshold
            if rate_gap > 2:
                trend = 'competitor_focus'
                trend_icon = '🔴'
                action = 'Content opportunity'
            elif rate_gap < -2:
                trend = 'our_strength'
                trend_icon = '🟢'
                action = 'Amplify leadership'
            else:
                trend = 'balanced'
                trend_icon = '🟡'
                action = 'Maintain coverage'

            # Only include keywords with meaningful presence
            min_rate = max(comp_rate, int_rate)
            is_boosted = keyword in BOOST_TERMS

            if min_rate >= 1.0:  # At least 1% of articles mention this
                trending.append({
                    'keyword': keyword,
                    'total_mentions': total_count,
                    'competitor_mentions': comp_count,
                    'internal_mentions': int_count,
                    'competitor_rate': round(comp_rate, 1),
                    'internal_rate': round(int_rate, 1),
                    'rate_gap': round(rate_gap, 1),
                    'trend': trend,
                    'trend_icon': trend_icon,
                    'action': action,
                    'is_industry_term': is_boosted,
                    'priority': 'High' if (is_boosted and rate_gap > 3) else
                               ('Medium' if abs(rate_gap) > 2 else 'Low')
                })

        # Sort by absolute rate gap (most significant differences first)
        trending.sort(key=lambda x: (not x['is_industry_term'], -abs(x['rate_gap'])))

        # Take top 15 most significant
        insights['trending_keywords'] = trending[:15]

        # Calculate balanced metrics
        comp_focus = len([k for k in trending[:15] if k['trend'] == 'competitor_focus'])
        our_strength = len([k for k in trending[:15] if k['trend'] == 'our_strength'])
        balanced = len([k for k in trending[:15] if k['trend'] == 'balanced'])

        insights['keyword_analysis'] = {
            'total_keywords_analyzed': len(all_keywords),
            'competitor_articles': total_competitor_articles,
            'internal_articles': total_internal_articles,
            'competitor_opportunities': comp_focus,
            'our_strengths': our_strength,
            'balanced_coverage': balanced,
            'top_opportunities': [k['keyword'] for k in trending if k['trend'] == 'competitor_focus'][:5],
            'top_strengths': [k['keyword'] for k in trending if k['trend'] == 'our_strength'][:5]
        }

    # ========== CONTENT GAPS (from strategic_gaps) ==========
    for gap in strategic_gaps[:5]:
        gap_title = gap.get('gap_title', '')
        priority = gap.get('priority', 'Medium')

        # Extract keywords more intelligently
        words = re.findall(r'\b[a-z]{4,}\b', gap_title.lower())
        keywords = [w for w in words if w not in STOP_WORDS][:5]

        insights['content_gaps'].append({
            'topic': gap_title,
            'priority': priority,
            'keywords': keywords,
            'opportunity': gap.get('opportunity', ''),
            'competitor_coverage': gap.get('competitor_coverage', 'Unknown')
        })

    # ========== STRENGTHS TO AMPLIFY (from clarion_wins) ==========
    for win in clarion_wins[:5]:
        topic = win.get('topic', '')
        narrative = win.get('our_narrative', '')

        insights['strengths_to_amplify'].append({
            'topic': topic,
            'angle': narrative[:100] + '...' if len(narrative) > 100 else narrative,
            'amplification': win.get('amplification_opportunity', '')
        })

    # ========== ACTIONABLE RECOMMENDATIONS ==========
    # Based on keyword analysis (use .get() to handle error case)
    comp_opps = insights['keyword_analysis'].get('competitor_opportunities', 0)
    our_strengths_count = insights['keyword_analysis'].get('our_strengths', 0)

    if comp_opps > 3:
        competitor_terms = insights['keyword_analysis'].get('top_opportunities', [])
        insights['recommendations'].append({
            'title': 'Urgent: Address Competitor Content Gaps',
            'description': f"Competitors are dominating coverage on {len(competitor_terms)} key topics.",
            'action_items': [
                f"Create content targeting: {', '.join(competitor_terms[:3])}",
                "Analyze top competitor articles for these topics",
                "Develop a 2-week content sprint to close gaps"
            ],
            'priority': 'High'
        })

    if our_strengths_count > 2:
        our_terms = insights['keyword_analysis'].get('top_strengths', [])
        insights['recommendations'].append({
            'title': 'Amplify Your Content Strengths',
            'description': f"You lead on {len(our_terms)} key topics - maximize this advantage.",
            'action_items': [
                f"Create topic clusters around: {', '.join(our_terms[:3])}",
                "Add internal links from high-traffic pages to these topics",
                "Pitch these as expertise areas for speaking opportunities"
            ],
            'priority': 'Medium'
        })

    if insights['content_gaps']:
        top_gap = insights['content_gaps'][0]
        insights['recommendations'].append({
            'title': f"Priority Content: {top_gap['topic'][:40]}...",
            'description': "This is your biggest strategic content gap.",
            'action_items': [
                f"Write 2-3 articles targeting: {', '.join(top_gap['keywords'][:3])}",
                "Research competitor coverage for this topic",
                "Create cornerstone content piece"
            ],
            'priority': top_gap['priority']
        })

    return insights


def _validate_and_refresh_caches():
    """
    Check if data files have been updated and invalidate caches if needed.

    This runs on each page load to ensure we're using fresh data.
    Called at the start of main() to handle pipeline updates.
    """
    # Force a cache check (will reload if file changed)
    load_disk_cache()

    # Log cache status for debugging
    stats = get_cache_stats()
    if stats['valid_entries'] > 0:
        print(f"Gemini cache: {stats['valid_entries']} valid entries loaded")

    return stats


def _render_data_freshness():
    """Show data freshness info in sidebar."""
    st.divider()
    st.caption("Data Freshness")

    # CSV last modified
    if NEWS_HISTORY_CSV.exists():
        csv_mtime = datetime.fromtimestamp(NEWS_HISTORY_CSV.stat().st_mtime)
        st.caption(f"Data updated: {csv_mtime.strftime('%Y-%m-%d %H:%M')}")

    # Cache status
    if GEMINI_CACHE_JSON.exists():
        stats = get_cache_stats()
        if stats['valid_entries'] > 0:
            cache_status = f"AI Cache: {stats['valid_entries']} cached"
        else:
            cache_status = "AI Cache: Empty"
        st.caption(cache_status)
    else:
        st.caption("AI Cache: Not found")

    # Version info
    if DATA_VERSION is not None:
        st.caption(f"Pipeline v{DATA_VERSION}")


def main():
    """Main dashboard function."""

    # Check for cache updates from pipeline run
    _validate_and_refresh_caches()

    # Health check endpoint for monitoring
    if st.query_params.get("health") == "check":
        st.success("Dashboard healthy")
        st.json({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": __version__
        })
        st.stop()

    # Header
    st.title("🎰 Clarion Competitive Intelligence Dashboard")
    st.markdown("**iGaming Industry News Aggregation & Gap Analysis (spaCy NER)**")
    st.markdown("---")

    # Load spaCy model
    nlp = load_spacy_model()

    # Load full history once - this is ALL articles (for all-time search)
    # Cache key invalidates when CSV changes (new articles added)
    df_history, history_stats = load_history_data(cache_key=_get_csv_cache_key())
    if df_history.empty:
        st.warning("No data available. Please run main.py to collect news.")
        return

    # Compute min / max dates for the UI
    min_date = history_stats["min_date"].date()
    max_date = history_stats["max_date"].date()

    # Sidebar: date filter and data diagnostics
    from datetime import date, timedelta

    with st.sidebar:
        st.header("📅 Date Filter")

        window_option = st.selectbox(
            "Time window",
            ["Last 30 days", "Last 90 days", "Year to date", "All time", "Custom range"],
            index=0,  # Default to "Last 30 days" to match AI Briefing window
        )

        today = date.today()

        if window_option == "Last 30 days":
            start_date = today - timedelta(days=30)
            end_date = today
        elif window_option == "Last 90 days":
            start_date = today - timedelta(days=90)
            end_date = today
        elif window_option == "Year to date":
            start_date = date(today.year, 1, 1)
            end_date = today
        elif window_option == "All time":
            start_date, end_date = min_date, max_date
        else:
            default_start = max(min_date, max_date - timedelta(days=90))
            default_end = max_date
            date_input_result = st.date_input(
                "Custom range",
                value=(default_start, default_end),
                min_value=min_date,
                max_value=max_date,
            )
            if isinstance(date_input_result, tuple) and len(date_input_result) == 2:
                start_date, end_date = date_input_result
            else:
                start_date, end_date = default_start, default_end

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        # History data quality (no "Latest run" anymore)
        with st.expander("📊 History Data Quality", expanded=False):
            total_rows = history_stats.get("total_rows", len(df_history))
            mask_window = df_history["published_dt"].dt.date.between(start_date, end_date)
            window_count = int(mask_window.sum())
            outside_count = int(total_rows - window_count)

            st.metric("Articles in selected window", window_count)
            st.metric("Total rows in CSV", total_rows)
            st.caption(
                f"CSV date range: {min_date.isoformat()} to {max_date.isoformat()}"
            )
            if outside_count > 0 and window_option != "All time":
                st.caption(f"{outside_count} articles outside the selected window")

        st.markdown("---")

    # Apply date filter first
    mask_window = df_history["published_dt"].dt.date.between(start_date, end_date)
    df = df_history.loc[mask_window].copy()

    if df.empty:
        st.warning("No articles in the selected date range. Try another window.")
        return

    # Ensure article_id exists
    if "article_id" not in df.columns:
        import hashlib
        df["article_id"] = df.apply(
            lambda row: hashlib.sha256(
                f"{row.get('source', '')}|{row.get('title', '')}".encode('utf-8')
            ).hexdigest()[:16],
            axis=1,
        )

    # Load AI analysis JSON (used in Tab 1 and Tab 3)
    analysis_json = None
    try:
        if DAILY_ANALYSIS_JSON.exists():
            with open(DAILY_ANALYSIS_JSON, 'r', encoding='utf-8') as f:
                analysis_json = json.load(f)
    except Exception as e:
        st.warning(f"⚠️ Could not load AI analysis: {str(e)}")

    # Load run metadata
    from paths import LATEST_RUN_INFO_JSON
    run_meta = None
    try:
        if LATEST_RUN_INFO_JSON.exists():
            with open(LATEST_RUN_INFO_JSON, 'r', encoding='utf-8') as f:
                run_meta = json.load(f)
    except Exception:
        pass

    # Sidebar
    with st.sidebar:
        st.header("🔍 Filters")

        # ========== SPACE FILTER (Affiliate Toggle) ==========
        st.subheader("📌 Space")

        # Determine which sources are affiliate
        AFFILIATE_SOURCES = {
            "iGaming Afrika", "iGaming Expert", "Gambling Insider",
            "Game Lounge", "Gaming and Co", "North Star Network", "iGB Affiliate"
        }

        all_sources = sorted(df['source'].unique().tolist())

        # Callback to update source multiselect when space changes
        def on_space_change():
            space_val = st.session_state.get('space_filter', 'All Sources')
            if space_val == "Affiliate Only":
                new_sources = [s for s in all_sources if s in AFFILIATE_SOURCES]
            elif space_val == "Non-Affiliate Only":
                new_sources = [s for s in all_sources if s not in AFFILIATE_SOURCES]
            else:
                new_sources = all_sources
            # Update the multiselect widget's key directly
            st.session_state.source_multiselect = new_sources

        space_options = ["All Sources", "Affiliate Only", "Non-Affiliate Only"]
        space_filter = st.radio(
            "Filter by space:",
            space_options,
            index=0,
            horizontal=True,
            key="space_filter",
            on_change=on_space_change
        )

        # ========== SOURCE FILTER ==========
        st.subheader("📰 Sources")

        # Initialize source_multiselect in session state if not present
        # Note: Do NOT use 'default' parameter when also using session state key
        if 'source_multiselect' not in st.session_state:
            st.session_state.source_multiselect = all_sources
        else:
            # Ensure all values in session state exist in all_sources (handles data changes)
            valid_selection = [s for s in st.session_state.source_multiselect if s in all_sources]
            if not valid_selection:
                st.session_state.source_multiselect = all_sources
            elif len(valid_selection) != len(st.session_state.source_multiselect):
                st.session_state.source_multiselect = valid_selection

        selected_sources = st.multiselect(
            "Select Sources",
            options=all_sources,
            key="source_multiselect"
        )

        # ========== CATEGORY FILTER ==========
        st.subheader("🏷️ Categories")
        # Only show main categories (competitor/internal)
        main_categories = ['competitor', 'internal']
        all_categories_raw = sorted(df['category'].unique().tolist())
        all_categories = [c for c in all_categories_raw if c in main_categories]

        # Warn if there are unexpected categories
        unexpected = [c for c in all_categories_raw if c not in main_categories]
        if unexpected:
            st.warning(f"⚠️ Found unexpected categories in data: {unexpected}. Run cleanup script to fix.")

        selected_categories = st.multiselect(
            "Select Categories",
            options=all_categories,
            default=all_categories,
            key="category_filter"
        )

        st.markdown("---")
        st.caption(f"Dashboard powered by Streamlit + spaCy | v{__version__}")

        # Display run information and check for mismatches
        if run_meta:
            news_run_id = run_meta.get("run_id")
            news_generated_at = run_meta.get("generated_at")

            # Get analysis run info if available
            analysis_run_id = None
            if analysis_json:
                analysis_run_id = analysis_json.get("run_id")

            # Parse timestamp for display
            if news_generated_at:
                try:
                    dt = datetime.fromisoformat(news_generated_at)
                    display_time = dt.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    display_time = news_generated_at

                st.caption(f"🕒 Last run: {display_time}")
            else:
                st.caption(f"🕒 Last run: {news_run_id}")

            # Check for mismatch
            if analysis_json and analysis_run_id and news_run_id:
                if analysis_run_id != news_run_id:
                    st.warning(f"⚠️ AI analysis is from run `{analysis_run_id}`, but latest news is from run `{news_run_id}`. Run `python analysis.py` to sync.")
        else:
            st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        # Data freshness indicator (cache status, pipeline version)
        _render_data_freshness()

    # Apply filters
    filtered_df = df[
        (df['source'].isin(selected_sources)) &
        (df['category'].isin(selected_categories))
    ].copy()

    # Handle empty filtered DataFrame gracefully
    if filtered_df.empty:
        st.warning("No articles match your filters. Adjust the date range or filters.")
        return

    # CRITICAL: Sort by published_date descending (newest first) with stable tie-breaks
    # Handle nulls by filling from scrape_timestamp or pushing to end
    if 'published_dt' in filtered_df.columns:
        # Ensure we have a secondary sort key for stable ordering
        if 'article_id' not in filtered_df.columns:
            filtered_df['article_id'] = filtered_df.index.astype(str)

        # Sort by published_dt descending, then article_id descending for stability
        filtered_df = filtered_df.sort_values(
            by=['published_dt', 'article_id'],
            ascending=[False, False],
            na_position='last'  # Push nulls to end
        )

    # Main content tabs - using radio button for persistent navigation
    # (st.tabs has issues on Streamlit Cloud where session state changes cause unwanted tab resets)
    TAB_OPTIONS = ["🧠 AI Briefing", "📰 News Feed", "⚔️ Intelligence Battleground"]

    # Horizontal radio button navigation (looks like tabs)
    # Note: Do NOT pre-initialize session state for widget keys - it interferes with widget state management
    selected_tab = st.radio(
        "Navigation",
        TAB_OPTIONS,
        horizontal=True,
        key="selected_tab",
        label_visibility="collapsed"
    )

    # ================================================================
    # SHARED FILTER-KEYED CACHING SETUP (used by all tabs)
    # ================================================================
    # Create stable cache key from ALL filter dimensions for AI result caching
    # This ensures cached results are correctly retrieved when switching any filter
    import hashlib
    sources_str = ",".join(sorted(selected_sources))
    categories_str = ",".join(sorted(selected_categories))
    # Combine all filter dimensions into a single hash for compactness
    filter_hash_input = f"{window_option}|{sources_str}|{categories_str}"
    current_filter_key = hashlib.md5(filter_hash_input.encode()).hexdigest()[:16]

    def get_ai_cache_key(ai_type: str) -> str:
        """Generate a filter-specific cache key for AI results.

        This allows caching AI results per filter combination, so switching
        filters back and forth doesn't trigger redundant API calls.
        Key includes: time window, sources, and categories.
        """
        return f"{ai_type}_{current_filter_key}"

    # Tab 1: AI Briefing
    if selected_tab == TAB_OPTIONS[0]:
        st.header("🧠 AI-Powered Gap Analysis Briefing")

        # Show mismatch warning at top of AI tab if detected
        if run_meta and analysis_json:
            news_run_id = run_meta.get("run_id")
            analysis_run_id = analysis_json.get("run_id")
            if analysis_run_id and news_run_id and analysis_run_id != news_run_id:
                st.error(
                    f"⚠️ **Data Mismatch Detected**\n\n"
                    f"This AI analysis was generated from news run `{analysis_run_id}`, "
                    f"but the latest news collection is from run `{news_run_id}`.\n\n"
                    f"**Action required:** Run `python scripts/analysis.py` to generate analysis for the latest news data."
                )

        # Check if AI analysis is available
        if analysis_json:
            # Executive Summary
            st.subheader("📋 Executive Summary")
            st.info(analysis_json.get('executive_summary', 'No summary available'))

            # Metadata - prefer live counts from filtered_df to ensure consistency
            metadata = analysis_json.get('metadata', {})

            # Compute live counts from dashboard data (matches News Feed tab)
            if 'category' in filtered_df.columns:
                live_competitor_count = len(filtered_df[filtered_df['category'] == 'competitor'])
                live_internal_count = len(filtered_df[filtered_df['category'] == 'internal'])
            else:
                live_competitor_count = metadata.get('total_window_competitor', 'N/A')
                live_internal_count = metadata.get('total_window_internal', 'N/A')

            col1, col2, col3 = st.columns(3)
            with col1:
                # Use live count from dashboard data for consistency
                st.metric("Competitor Articles", live_competitor_count)
            with col2:
                st.metric("Internal Articles", live_internal_count)
            with col3:
                st.metric("Analysis Date", metadata.get('analysis_date', 'N/A'))

            # Show analyzed badge - use live deduplicated counts for consistency
            # The dashboard deduplicates articles, so use len(filtered_df) as the live total
            live_total = live_competitor_count + live_internal_count
            if live_total > 0:
                st.success(f"✅ **{live_total} articles** in selected window")

            st.markdown("---")

            # Market Pulse
            st.subheader("📈 Market Pulse: Industry Trends")
            market_pulse = analysis_json.get('market_pulse', [])

            if market_pulse:
                for idx, theme in enumerate(market_pulse, 1):
                    importance_color = {
                        'High': '🔴',
                        'Medium': '🟡',
                        'Low': '🟢'
                    }.get(theme.get('importance', 'Medium'), '⚪')

                    with st.expander(f"{importance_color} **{idx}. {theme.get('theme', 'Unknown Theme')}** - {theme.get('importance', 'N/A')} Importance", expanded=(idx == 1)):
                        st.markdown(f"**Competitors Covering:** {', '.join(theme.get('competitors_covering', []))}")
                        st.markdown("**Narrative:**")
                        st.write(theme.get('narrative', 'N/A'))
                        st.markdown("**ICE/iGB Relevance:**")
                        st.write(theme.get('recommended_action', 'N/A'))
            else:
                st.info("No market pulse themes identified.")

            st.markdown("---")

            # Strategic Gaps
            st.subheader("⚠️ Strategic Gaps: Missed Opportunities")
            strategic_gaps = analysis_json.get('strategic_gaps', [])

            if strategic_gaps:
                for idx, gap in enumerate(strategic_gaps, 1):
                    priority = gap.get('priority', 'Medium')
                    priority_color = {
                        'High': '🔴',
                        'Medium': '🟡',
                        'Low': '🟢'
                    }.get(priority, '⚪')

                    gap_title = gap.get('gap_title', 'Unknown Topic')

                    # Collapsible expander - first one expanded by default
                    with st.expander(
                        f"**Gap #{idx}: {gap_title}** - {priority_color} {priority.upper()}",
                        expanded=(idx == 1)
                    ):
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            st.markdown("**Description:**")
                            st.write(gap.get('description', 'N/A'))
                            st.markdown("**Our Coverage:**")
                            st.write(gap.get('our_coverage', 'N/A'))
                        with col2:
                            st.markdown("**Competitor Coverage:**")
                            st.write(gap.get('competitor_coverage', 'N/A'))
                            st.markdown("**Potential Impact:**")
                            st.write(gap.get('potential_impact', 'N/A'))

                        st.markdown(f"**💡 Opportunity:** {gap.get('opportunity', 'N/A')}")

                        # Show supporting articles (evidence)
                        supporting = gap.get("supporting_articles", [])
                        if supporting:
                            match_method = gap.get("match_method", "unknown")
                            method_label = "🎯 keyword match" if match_method == "keyword" else "📂 topic match"
                            st.markdown(f"**📰 Evidence articles** ({method_label}):")
                            for art in supporting:
                                category_badge = "🏠" if art.get('category') == 'internal' else "🌐"
                                st.markdown(
                                    f"{category_badge} [{art.get('title', 'Untitled')}]({art.get('link', '#')}) - "
                                    f"*{art.get('source', 'Unknown')}*"
                                )
                        else:
                            st.caption("No specific evidence articles found for this gap.")
            else:
                st.success("✅ No significant gaps identified - good coverage alignment!")

            st.markdown("---")

            # ================================================================
            # WHY READERS CHOOSE US - AI-Enhanced Pattern Detection
            # ================================================================
            st.subheader("🎯 Why Readers Choose Us")

            # Fixed 90-day window
            reader_days = 90

            # Get cache key
            csv_fp = get_csv_fingerprint(NEWS_HISTORY_CSV) if NEWS_HISTORY_CSV.exists() else ""

            # STEP 1: Get Python-detected patterns (CACHED)
            reader_adv_data = None
            try:
                reader_adv_data = cached_reader_advantages(csv_fp, window_days=reader_days)
            except Exception as e:
                st.warning(f"Error computing patterns: {e}")
                reader_adv_data = {'cards': [], 'diagnostics': {}}

            diagnostics = reader_adv_data.get('diagnostics', {})
            internal_count = diagnostics.get('internal_articles', 0)
            comp_count = diagnostics.get('competitor_articles', 0)
            python_cards = reader_adv_data.get('cards', [])

            # STEP 2: Enhance with Gemini AI (if available and patterns exist)
            gemini_result = None
            use_ai = False

            if GEMINI_NER_AVAILABLE and python_cards and internal_count > 0:
                try:
                    # Prepare article samples for AI
                    cutoff = datetime.now() - timedelta(days=reader_days)

                    internal_sample = df_history[
                        (df_history['category'] == 'internal') &
                        (pd.to_datetime(df_history['published_date']) >= cutoff)
                    ].head(20).to_dict('records')

                    competitor_sample = df_history[
                        (df_history['category'] != 'internal') &
                        (pd.to_datetime(df_history['published_date']) >= cutoff)
                    ].head(20).to_dict('records')

                    # Convert timestamps for JSON
                    def sanitize_for_json(records):
                        for r in records:
                            for k, v in list(r.items()):
                                if hasattr(v, 'isoformat'):
                                    r[k] = v.isoformat()
                                elif pd.isna(v):
                                    r[k] = None
                        return records

                    internal_sample = sanitize_for_json(internal_sample)
                    competitor_sample = sanitize_for_json(competitor_sample)

                    # Call cached Gemini enhancement
                    gemini_result = cached_gemini_reader_enhancement(
                        csv_fp,
                        json.dumps(reader_adv_data, default=str),
                        json.dumps(internal_sample, default=str),
                        json.dumps(competitor_sample, default=str),
                        reader_days
                    )

                    use_ai = (
                        gemini_result and
                        not gemini_result.get('fallback_used', True) and
                        gemini_result.get('enhanced_cards')
                    )

                except Exception as e:
                    st.caption(f"⚠️ AI enhancement error: {str(e)[:50]}")

            # STEP 3: Display results
            if use_ai:
                # === AI-ENHANCED DISPLAY ===
                st.caption(f"🤖 AI-enhanced analysis • {internal_count} internal vs {comp_count} competitor articles • Last {reader_days} days")

                # Strategic summary
                if gemini_result.get('strategic_summary'):
                    st.success(f"💡 **Editorial Position:** {gemini_result['strategic_summary']}")

                # Enhanced cards
                enhanced_cards = gemini_result.get('enhanced_cards', [])
                for idx, card in enumerate(enhanced_cards[:5], 1):
                    headline = card.get('headline', 'Coverage Advantage')
                    what_get = card.get('what_readers_get', '')
                    why_matters = card.get('why_it_matters', '')
                    evidence = card.get('evidence_summary', '')
                    confidence = card.get('confidence', 'medium')
                    ratio = card.get('concentration_ratio', 0)

                    # Confidence indicator
                    conf_emoji = {'high': '🟢', 'medium': '🟡', 'low': '🟠'}.get(confidence, '⚪')
                    ratio_text = f" • {ratio:.1f}x" if ratio else ""

                    with st.expander(f"{conf_emoji} **{headline}**{ratio_text}", expanded=(idx == 1)):
                        if what_get:
                            st.markdown(f"**What readers get:** {what_get}")
                        if evidence:
                            st.markdown(f"**Evidence:** {evidence}")
                        if why_matters:
                            st.markdown(f"*Why it matters: {why_matters}*")

                        # Show original articles if available in Python data
                        original_type = card.get('original_type', '')
                        matching_python = next(
                            (c for c in python_cards if c.get('advantage_key', '').startswith(original_type[:5])),
                            None
                        )
                        if matching_python and matching_python.get('internal_examples'):
                            st.markdown("**📰 Example articles:**")
                            for ex in matching_python['internal_examples'][:3]:
                                title = ex.get('title', 'Article')[:55]
                                link = ex.get('link', '#')
                                st.markdown(f"- [{title}...]({link})")

                # AI-discovered advantages
                ai_discovered = gemini_result.get('ai_discovered', [])
                if ai_discovered:
                    with st.expander("🔍 **AI-Discovered Patterns**", expanded=False):
                        st.caption("Additional advantages identified by AI analysis")
                        for disc in ai_discovered[:3]:
                            st.markdown(f"**{disc.get('headline', 'Pattern')}**")
                            st.markdown(f"{disc.get('what_readers_get', '')}")
                            if disc.get('evidence'):
                                st.caption(f"Evidence: {disc['evidence']}")
                            st.markdown("---")

                # Confidence footer
                overall_conf = gemini_result.get('overall_confidence', 0.7)
                st.caption(f"*Analysis confidence: {overall_conf:.0%} • Patterns strengthen as coverage accumulates*")

            elif python_cards:
                # === PYTHON-ONLY FALLBACK ===
                if GEMINI_NER_AVAILABLE:
                    st.caption(f"📊 Pattern-based analysis • {internal_count} internal vs {comp_count} competitor articles • Last {reader_days} days")
                else:
                    st.caption(f"📊 Pattern-based analysis (AI unavailable) • {internal_count} internal vs {comp_count} competitor articles")

                for idx, card in enumerate(python_cards[:5], 1):
                    headline = card.get('headline', card.get('headline_template', 'Coverage Advantage'))
                    what_get = card.get('what_readers_get', card.get('reader_value_template', ''))
                    why_matters = card.get('why_it_matters', card.get('why_matters_template', ''))
                    examples = card.get('internal_examples', [])

                    our_pct = card.get('our_concentration', 0)
                    their_pct = card.get('their_concentration', 0)
                    ratio = card.get('concentration_ratio', 0)

                    if ratio >= 2:
                        evidence = f"{our_pct:.0f}% of our content vs {their_pct:.0f}% ({ratio:.1f}x more focused)"
                    else:
                        evidence = f"{our_pct:.0f}% vs {their_pct:.0f}% of competitor content"

                    with st.expander(f"✅ **{headline}** • {ratio:.1f}x advantage", expanded=(idx == 1)):
                        st.markdown(f"**What readers get:** {what_get}")
                        st.markdown(f"**Evidence:** {evidence}")

                        if examples:
                            st.markdown("**📰 Example articles:**")
                            for ex in examples[:3]:
                                st.markdown(f"- [{ex.get('title', 'Article')[:55]}...]({ex.get('link', '#')})")

                        st.markdown(f"*Why it matters: {why_matters}*")

                st.caption("*Advantages reflect repeated patterns and strengthen as coverage accumulates.*")

            elif reader_adv_data.get('empty_message'):
                st.info(reader_adv_data['empty_message'])

            elif internal_count > 0:
                st.warning("**No strong advantages detected in this window.**")
                st.caption(f"Analyzed {internal_count} internal articles but patterns didn't meet the threshold.")

            else:
                st.info("No internal articles found in the selected time period.")

            # How this is calculated
            with st.expander("📊 How this is calculated", expanded=False):
                ai_status = "✅ Active" if use_ai else "❌ Inactive (using pattern detection only)"
                st.markdown(f"""
**Hybrid Analysis: Pattern Detection + AI Enhancement**

**Step 1: Pattern Detection**
Python analyzes {internal_count} internal and {comp_count} competitor articles to find coverage patterns:
- Explainer depth (analysis, guides, deep dives)
- Editorial franchises (awards, rankings, series)
- Geography focus (sustained market coverage)
- Event coverage (conference reporting)
- Follow-through (multi-article stories)

**Step 2: AI Enhancement** {ai_status}
When available, Gemini AI:
- Validates patterns represent real reader value
- Rewrites headlines to be reader-focused
- Identifies additional patterns Python might miss
- Ranks by actual reader value, not just counts

**Key Metric: Concentration**
We compare what % of OUR content covers each area vs competitors.
A 2.0x ratio means we're twice as focused on that topic.
""")

            # CSV Download
            csv_data = advantages_to_csv_v2(reader_adv_data)
            st.download_button(
                label="📥 Download Reader Advantages CSV",
                data=csv_data,
                file_name=f"reader_advantages_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                key="download_reader_advantages"
            )

            # ================================================================
            # BUSINESS INTELLIGENCE HUB (Consolidated Section)
            # ================================================================
            st.markdown("---")
            st.subheader("📊 Business Intelligence Hub")
            st.caption("Unified commercial, exhibition, and content strategy insights")

            # Generate SEO insights first (needed for all tabs)
            seo_insights = generate_seo_insights(
                analysis_json.get('strategic_gaps', []),
                analysis_json.get('clarion_wins', []),
                analysis_json.get('market_pulse', []),
                filtered_df
            )

            # Note: current_filter_key and get_ai_cache_key() are defined at the top level
            # (shared across all tabs) for filter-keyed AI result caching

            # ========== TABBED INTERFACE ==========
            biz_tab1, biz_tab2, biz_tab3 = st.tabs([
                "💼 Commercial Radar",
                "🎯 Exhibitor Prospecting",
                "🔍 SEO & Content Strategy"
            ])

            # ========== TAB 1: COMMERCIAL RADAR ==========
            with biz_tab1:
                sponsors = analysis_json.get('commercial_radar', {}).get('potential_sponsors', [])
                speakers = analysis_json.get('commercial_radar', {}).get('potential_speakers', [])

                # Quick stats row (compact - 2 columns)
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("🎯 Sponsor Leads", len(sponsors))
                with col2:
                    st.metric("🎤 Speaker Candidates", len(speakers))

                st.markdown("---")

                # ===== SPONSORS TABLE =====
                st.markdown("### 🎯 Potential Sponsors")

                if sponsors:
                    # Create DataFrame for display - show full text, let table handle wrapping
                    sponsor_data = []
                    for s in sponsors:
                        sponsor_data.append({
                            'Company': s.get('company_name', 'Unknown'),
                            'Why': s.get('rationale', 'N/A'),
                            'Pitch Angle': s.get('engagement_angle', 'N/A')
                        })

                    sponsor_df = pd.DataFrame(sponsor_data)
                    st.dataframe(
                        sponsor_df,
                        hide_index=True,
                        column_config={
                            'Company': st.column_config.TextColumn('Company', width='small'),
                            'Why': st.column_config.TextColumn('Why', width='medium'),
                            'Pitch Angle': st.column_config.TextColumn('Pitch Angle', width='large')
                        },
                        **_get_width_kwargs()
                    )
                else:
                    st.info("No sponsors identified in this period.")

                st.markdown("---")

                # ===== SPEAKERS TABLE (Compact) =====
                st.markdown("### 🎤 Potential Speakers")

                if speakers:
                    # Create compact DataFrame for display
                    speaker_data = []
                    for s in speakers:
                        speaker_data.append({
                            'Name': s.get('name_or_company', 'Unknown'),
                            'Expertise': s.get('expertise_area', 'N/A'),
                            'Session Fit': s.get('session_fit', 'N/A')
                        })

                    speaker_df = pd.DataFrame(speaker_data)
                    st.dataframe(
                        speaker_df,
                        hide_index=True,
                        column_config={
                            'Name': st.column_config.TextColumn('Name/Company', width='medium'),
                            'Expertise': st.column_config.TextColumn('Expertise Area', width='large'),
                            'Session Fit': st.column_config.TextColumn('Suggested Session', width='large')
                        },
                        **_get_width_kwargs()
                    )
                else:
                    st.info("No speakers identified in this period.")

            # ========== TAB 2: EXHIBITOR PROSPECTING ==========
            with biz_tab2:
                st.markdown("### 🎯 Exhibitor Prospecting")
                st.caption("AI-powered recommendations for ICE/iGB exhibition booth sales")

                # Get context data
                exhibitor_categories = analysis_json.get('commercial_radar', {}).get('emerging_exhibitor_categories', [])
                existing_sponsors = [s.get('company_name', '') for s in
                                    analysis_json.get('commercial_radar', {}).get('potential_sponsors', [])]

                # Filter-keyed session state for exhibitor prospects
                exhibitor_key = get_ai_cache_key('exhibitor_prospects')
                exhibitor_error_key = get_ai_cache_key('exhibitor_error')

                # Generate prospects (with proper error handling)
                if GEMINI_NER_AVAILABLE:
                    # Only call if not already cached for this filter
                    if st.session_state.get(exhibitor_key) is None and st.session_state.get(exhibitor_error_key) is None:
                        try:
                            from src.gemini_ner_analysis import get_exhibitor_prospects

                            # No spinner - function has disk cache for instant retrieval
                            exhibitor_prospects = get_exhibitor_prospects(
                                dataframe_to_json_safe(filtered_df, max_records=50),
                                exhibitor_categories,
                                existing_sponsors
                            )

                            if exhibitor_prospects and 'error' not in exhibitor_prospects:
                                st.session_state[exhibitor_key] = exhibitor_prospects
                            else:
                                st.session_state[exhibitor_error_key] = exhibitor_prospects.get('error', 'Unknown error') if exhibitor_prospects else 'No response'
                        except Exception as e:
                            st.session_state[exhibitor_error_key] = str(e)

                    # Display prospects if available
                    exhibitor_result = st.session_state.get(exhibitor_key)
                    if exhibitor_result:
                        prospects = exhibitor_result.get('exhibitor_prospects', [])

                        if prospects:
                            # Summary metrics
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                high_priority = len([p for p in prospects if p.get('contact_urgency') == 'High'])
                                st.metric("🔥 High Priority", high_priority)
                            with col2:
                                st.metric("📋 Total Prospects", len(prospects))
                            with col3:
                                large_booths = len([p for p in prospects if 'Large' in str(p.get('estimated_booth_size', ''))])
                                st.metric("🏢 Large Booth Potential", large_booths)

                            st.markdown("---")

                            # Prospect cards
                            for idx, prospect in enumerate(prospects, 1):
                                urgency = prospect.get('contact_urgency', 'Medium')
                                urgency_color = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}.get(urgency, '⚪')

                                with st.expander(
                                    f"{urgency_color} **{prospect.get('company', 'Unknown')}** - {prospect.get('category_fit', '')}",
                                    expanded=(idx <= 2)
                                ):
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        st.markdown("**📰 News Trigger:**")
                                        st.write(prospect.get('news_trigger', 'N/A'))
                                        st.markdown("**🎯 Booth Pitch:**")
                                        st.write(prospect.get('booth_pitch', 'N/A'))
                                    with col2:
                                        st.markdown(f"**📐 Estimated Booth:** {prospect.get('estimated_booth_size', 'N/A')}")
                                        st.markdown(f"**⏰ Contact Urgency:** {urgency}")

                            # Timing note
                            timing_note = exhibitor_result.get('timing_note')
                            if timing_note:
                                st.info(f"⏰ **Timing Recommendation:** {timing_note}")

                            # Category gaps
                            category_gaps = exhibitor_result.get('category_gaps', [])
                            if category_gaps:
                                with st.expander("📊 Exhibition Category Gaps", expanded=False):
                                    for gap in category_gaps:
                                        st.markdown(f"**{gap.get('category', '')}**")
                                        st.caption(f"Opportunity: {gap.get('opportunity', '')}")
                                        if gap.get('target_company_types'):
                                            st.caption(f"Target: {', '.join(gap['target_company_types'])}")
                                        st.markdown("---")

                            # Refresh button
                            if st.button("🔄 Refresh Prospects", key="refresh_exhibitor"):
                                st.session_state[exhibitor_key] = None
                                st.session_state[exhibitor_error_key] = None
                                st.rerun()
                        else:
                            st.info("No exhibitor prospects generated. Try adjusting date filters.")

                    # Show error if any
                    elif st.session_state.get(exhibitor_error_key):
                        col_err, col_retry = st.columns([3, 1])
                        with col_err:
                            st.warning(f"⚠️ AI Analysis unavailable: {st.session_state.get(exhibitor_error_key, '')[:60]}...")
                        with col_retry:
                            if st.button("🔄 Retry AI", key="retry_exhibitor"):
                                st.session_state[exhibitor_key] = None
                                st.session_state[exhibitor_error_key] = None
                                if reinit_gemini:
                                    reinit_gemini()
                                st.rerun()
                        st.markdown("---")
                        # Show fallback
                        st.markdown("### 📋 Emerging Exhibitor Categories")
                        st.caption("Static categories from analysis (AI enhancement unavailable)")
                        _display_static_exhibitor_categories(exhibitor_categories)
                else:
                    # Gemini not available - show static content
                    st.markdown("### 📋 Emerging Exhibitor Categories")
                    st.caption("Categories identified for ICE/iGB exhibition halls")
                    _display_static_exhibitor_categories(exhibitor_categories)

            # ========== TAB 3: SEO & CONTENT STRATEGY ==========
            with biz_tab3:
                st.markdown("### 📊 Content Strategy Dashboard")
                st.caption("Actionable insights for your marketing team")

                keyword_analysis = seo_insights.get('keyword_analysis', {})
                trending = seo_insights.get('trending_keywords', [])

                # Filter-keyed session state for AI SEO recommendations
                # This preserves results when users switch between filter combinations
                ai_seo_key = get_ai_cache_key('ai_seo')
                ai_seo_error_key = get_ai_cache_key('ai_seo_error')
                ai_seo_retry_key = get_ai_cache_key('ai_seo_retry_count')

                # Lazy load SEO recommendations
                ai_seo = None
                if GEMINI_NER_AVAILABLE:
                    # Retry logic: clear error state and try again if retry requested
                    if st.session_state.get('ai_seo_retry_requested'):
                        st.session_state[ai_seo_key] = None
                        st.session_state[ai_seo_error_key] = None
                        st.session_state.ai_seo_retry_requested = False
                        st.session_state[ai_seo_retry_key] = st.session_state.get(ai_seo_retry_key, 0) + 1
                        # Force reinit of Gemini client
                        if reinit_gemini:
                            reinit_gemini()

                    if st.session_state.get(ai_seo_key) is None and st.session_state.get(ai_seo_error_key) is None:
                        try:
                            from src.gemini_ner_analysis import get_ai_seo_recommendations

                            # No spinner - function has disk cache for instant retrieval
                            # Only shows delay on first-ever call for this data combination
                            ai_seo_result = get_ai_seo_recommendations(
                                seo_insights,
                                filtered_df.to_dict('records')[:30]
                            )
                            if ai_seo_result and 'error' not in ai_seo_result:
                                st.session_state[ai_seo_key] = ai_seo_result
                                st.session_state[ai_seo_retry_key] = 0  # Reset on success
                            else:
                                st.session_state[ai_seo_error_key] = ai_seo_result.get('error', 'Unknown error') if ai_seo_result else 'No response'
                        except Exception as e:
                            st.session_state[ai_seo_error_key] = str(e)

                ai_seo = st.session_state.get(ai_seo_key)

                # ===== SECTION 1: Quick Summary Metrics =====
                col1, col2, col3 = st.columns(3)
                with col1:
                    opps = keyword_analysis.get('competitor_opportunities', 0)
                    st.metric("🎯 Opportunities", opps,
                             help="Keywords where competitors outpace us")
                with col2:
                    strengths = keyword_analysis.get('our_strengths', 0)
                    st.metric("💪 Strengths", strengths,
                             help="Keywords where we lead")
                with col3:
                    balanced = keyword_analysis.get('balanced_coverage', 0)
                    st.metric("⚖️ Balanced", balanced,
                             help="Keywords with similar coverage")

                st.markdown("---")

                # ===== SECTION 2: Priority Actions (Collapsed by default) =====
                with st.expander("🚀 Priority Actions", expanded=True):
                    # Show AI status and retry button if there's an error
                    ai_seo_error = st.session_state.get(ai_seo_error_key)
                    if ai_seo_error and GEMINI_NER_AVAILABLE:
                        retry_count = st.session_state.get(ai_seo_retry_key, 0)
                        col_err, col_retry = st.columns([3, 1])
                        with col_err:
                            st.warning(f"AI insights unavailable: {ai_seo_error[:60]}...")
                        with col_retry:
                            if retry_count < 3:
                                if st.button("🔄 Retry AI", key="retry_ai_seo"):
                                    st.session_state.ai_seo_retry_requested = True
                                    st.rerun()
                            else:
                                st.caption("Max retries reached")

                    # Sub-tabs for organization
                    action_tab1, action_tab2 = st.tabs(["📝 This Week", "📅 This Month"])

                    with action_tab1:
                        st.markdown("**Quick Wins (implement now):**")

                        # Combine AI quick wins with keyword opportunities
                        if ai_seo and ai_seo.get('quick_wins'):
                            for win in ai_seo['quick_wins'][:3]:
                                st.markdown(f"• {win}")
                        else:
                            # Fallback to keyword-based recommendations with specific actionable items
                            opps_list = [k for k in trending if k.get('trend') == 'competitor_focus'][:3]
                            if opps_list:
                                keywords = [k['keyword'] for k in opps_list]
                                for kw in keywords:
                                    gap = next((k.get('rate_gap', 0) for k in opps_list if k['keyword'] == kw), 0)
                                    st.markdown(f"• Write article covering **{kw}** (competitor lead: +{abs(gap):.1f}pp)")
                            else:
                                st.info("No immediate action items - your coverage is strong!")
                            # Show hint that this is fallback data
                            if not ai_seo and GEMINI_NER_AVAILABLE and not ai_seo_error:
                                st.caption("*Loading AI insights...*")

                    with action_tab2:
                        st.markdown("**Content Calendar:**")

                        if ai_seo and ai_seo.get('content_calendar'):
                            for item in ai_seo['content_calendar'][:4]:
                                topic = item.get('topic', 'TBD')
                                timing = item.get('timing', '')
                                format_type = item.get('format', 'Article')
                                st.markdown(f"• **{topic}**: {timing} ({format_type})")
                        else:
                            # Fallback based on strategic gaps - show full topic name
                            gaps = seo_insights.get('content_gaps', [])[:3]
                            if gaps:
                                for gap in gaps:
                                    topic = gap.get('topic', 'Unknown topic')
                                    priority = gap.get('priority', 'Medium')
                                    st.markdown(f"• **{topic}** (Priority: {priority})")
                            else:
                                st.info("No content gaps identified - consider expanding into new topics.")
                            # Show hint that this is fallback data
                            if not ai_seo and GEMINI_NER_AVAILABLE and not ai_seo_error:
                                st.caption("*Loading AI insights...*")

                # ===== SECTION 3: Keyword Intelligence (Collapsed) =====
                with st.expander("🔑 Keyword Analysis", expanded=False):
                    if trending:
                        st.caption("Comparing % of articles mentioning each keyword (normalized for article volume)")

                        # Simple table view instead of cards
                        keyword_df = pd.DataFrame([{
                            'Keyword': k['keyword'],
                            'Our Coverage': f"{k.get('internal_rate', 0)}%",
                            'Competitor Coverage': f"{k.get('competitor_rate', 0)}%",
                            'Gap': f"{k.get('rate_gap', 0):+.1f}pp",
                            'Status': k.get('trend', '').replace('_', ' ').title()
                        } for k in trending[:12]])

                        st.dataframe(keyword_df, hide_index=True, **_get_width_kwargs())

                        st.caption("*Gap = Competitor % - Our %. Positive = opportunity, Negative = our strength*")
                    else:
                        st.info("No keyword analysis available.")

                # ===== AI KEYWORD RECOMMENDATIONS =====
                if GEMINI_NER_AVAILABLE:
                    with st.expander("🤖 AI Keyword Recommendations", expanded=True):

                        # Filter-keyed session state for AI keywords
                        ai_kw_key = get_ai_cache_key('ai_keywords')
                        ai_kw_error_key = get_ai_cache_key('ai_keywords_error')
                        ai_kw_fallback_key = get_ai_cache_key('ai_keywords_is_fallback')

                        # Generate keywords if not cached for this filter
                        if st.session_state.get(ai_kw_key) is None and st.session_state.get(ai_kw_error_key) is None:
                            try:
                                from src.gemini_ner_analysis import get_ai_keyword_recommendations

                                # No spinner - function has disk cache for instant retrieval
                                # Get competitor articles for context (JSON-safe)
                                comp_df = filtered_df[filtered_df['category'] != 'internal']

                                ai_keywords = get_ai_keyword_recommendations(
                                    json.dumps(trending[:15]) if trending else '[]',
                                    json.dumps(seo_insights.get('content_gaps', [])),
                                    dataframe_to_json_safe(comp_df, max_records=30)
                                )

                                if ai_keywords and 'error' not in ai_keywords:
                                    st.session_state[ai_kw_key] = ai_keywords
                                    # Note if using fallback (still valid data)
                                    if ai_keywords.get('is_fallback'):
                                        st.session_state[ai_kw_fallback_key] = True
                                else:
                                    st.session_state[ai_kw_error_key] = ai_keywords.get('error', 'Unknown error') if ai_keywords else 'No response'
                            except Exception as e:
                                st.session_state[ai_kw_error_key] = str(e)

                        # Display keywords
                        ai_keywords_result = st.session_state.get(ai_kw_key)
                        if ai_keywords_result:
                            if st.session_state.get(ai_kw_fallback_key):
                                st.info("📊 Keyword analysis based on trend data (AI enhancement unavailable)")
                            else:
                                st.success("✅ AI keyword analysis complete")

                            # Priority Keywords Table
                            priority_kws = ai_keywords_result.get('priority_keywords', [])
                            if priority_kws:
                                st.markdown("**🎯 Priority Keywords to Target:**")

                                kw_df = pd.DataFrame([{
                                    'Keyword': k.get('keyword', ''),
                                    'Intent': k.get('search_intent', ''),
                                    'Difficulty': k.get('estimated_difficulty', ''),
                                    'Content Type': k.get('content_type', '')
                                } for k in priority_kws])

                                st.dataframe(kw_df, hide_index=True, **_get_width_kwargs())

                                # Show rationale (use checkbox toggle instead of nested expander)
                                if st.checkbox("📖 Show keyword rationales", key="show_kw_rationales"):
                                    for k in priority_kws:
                                        st.markdown(f"**{k.get('keyword', '')}:** {k.get('rationale', 'N/A')}")

                            # Quick Wins
                            quick_wins = ai_keywords_result.get('quick_win_keywords', [])
                            if quick_wins:
                                st.markdown("**⚡ Quick Win Keywords (low competition):**")
                                st.code(", ".join(quick_wins))

                            # Strategy Note
                            strategy_note = ai_keywords_result.get('content_strategy_note')
                            if strategy_note:
                                st.info(f"💡 **Strategy:** {strategy_note}")

                            # Refresh button
                            col1, col2 = st.columns([3, 1])
                            with col2:
                                if st.button("🔄 Refresh", key="refresh_keywords"):
                                    st.session_state[ai_kw_key] = None
                                    st.session_state[ai_kw_error_key] = None
                                    st.rerun()

                        elif st.session_state.get(ai_kw_error_key):
                            col_err, col_retry = st.columns([3, 1])
                            with col_err:
                                st.warning(f"⚠️ AI keyword analysis unavailable: {st.session_state.get(ai_kw_error_key, '')[:60]}...")
                            with col_retry:
                                if st.button("🔄 Retry AI", key="retry_keywords"):
                                    st.session_state[ai_kw_key] = None
                                    st.session_state[ai_kw_error_key] = None
                                    if reinit_gemini:
                                        reinit_gemini()
                                    st.rerun()
                        else:
                            st.info("Loading AI keyword recommendations...")

            # Download buttons
            st.markdown("---")
            col1, col2 = st.columns(2)

            with col1:
                # Download JSON
                json_str = json.dumps(analysis_json, indent=2, ensure_ascii=False)
                st.download_button(
                    label="📥 Download JSON Data",
                    data=json_str,
                    file_name=f"analysis_{datetime.now().strftime('%Y%m%d')}.json",
                    mime="application/json"
                )

            with col2:
                # Download markdown (if exists, with backward compatibility)
                try:
                    if DAILY_BRIEFING_MD.exists():
                        with open(DAILY_BRIEFING_MD, 'r', encoding='utf-8') as f:
                            briefing_md = f.read()
                        st.download_button(
                            label="📥 Download Markdown Report",
                            data=briefing_md,
                            file_name=f"briefing_{datetime.now().strftime('%Y%m%d')}.md",
                            mime="text/markdown"
                        )
                except FileNotFoundError:
                    pass

        else:
            st.warning("⚠️ No analysis found. Please run analysis.py to generate the AI briefing.")
            st.info("💡 Run the following command:\n```bash\npython scripts/analysis.py\n```")

            # Fallback to markdown if JSON doesn't exist
            briefing = load_briefing()
            if briefing:
                st.markdown("---")
                st.markdown("### Legacy Markdown Briefing")
                st.markdown(briefing, unsafe_allow_html=True)

    # Tab 2: News Feed
    elif selected_tab == TAB_OPTIONS[1]:
        st.header("📰 Latest News Articles")
        st.caption(f"Showing deduplicated articles from {start_date.isoformat()} to {end_date.isoformat()} ({window_option})")

        # ================================================================
        # SMART SEARCH SECTION (moved from Context Explorer)
        # ================================================================
        st.markdown("---")

        # Build quick-select options from gaps and topics
        candidate_keywords = []

        # Add strategic gap titles from AI analysis
        if analysis_json and 'strategic_gaps' in analysis_json:
            gap_titles = [g.get('gap_title', '') for g in analysis_json['strategic_gaps'] if g.get('gap_title')]
            candidate_keywords.extend(gap_titles)

        # Add topics from market_pulse themes
        if analysis_json and 'market_pulse' in analysis_json:
            theme_names = [t.get('theme', '') for t in analysis_json['market_pulse'] if t.get('theme')]
            candidate_keywords.extend(theme_names)

        # Add sponsor companies from AI analysis
        if analysis_json and 'commercial_radar' in analysis_json:
            sponsors = analysis_json['commercial_radar'].get('potential_sponsors', [])
            sponsor_names = [s.get('company_name', '').strip() for s in sponsors if s.get('company_name')]
            candidate_keywords.extend(sponsor_names)

        # Filter to keywords that have results in current window
        # Use filter-keyed session state to avoid recomputation on tab switches
        keyword_counts_key = get_ai_cache_key('keyword_counts')
        if st.session_state.get(keyword_counts_key) is not None:
            keyword_counts = st.session_state[keyword_counts_key]
        else:
            keyword_counts = filter_keywords_with_results(
                filtered_df,  # Search within current date window
                candidate_keywords,
                search_fields=SEARCH_FIELDS_DEFAULT
            )
            st.session_state[keyword_counts_key] = keyword_counts

        # Format dropdown options with counts
        search_options = ["None - Type your own search"]
        keyword_to_formatted = {}
        for keyword, count in keyword_counts:
            formatted = format_keyword_option(keyword, count)
            search_options.append(formatted)
            keyword_to_formatted[formatted] = keyword

        # ================================================================
        # SMART SEARCH SECTION - Fixed session_state handling
        # ================================================================

        # Initialize session state values BEFORE widgets
        if 'news_feed_search_value' not in st.session_state:
            st.session_state.news_feed_search_value = ""
        if 'news_feed_prev_selection' not in st.session_state:
            st.session_state.news_feed_prev_selection = "None - Type your own search"

        # Callback function to handle dropdown selection
        def on_dropdown_change():
            selected = st.session_state.news_feed_dropdown
            if selected != "None - Type your own search":
                # Extract keyword from formatted option and sync to text input widget
                keyword = parse_keyword_from_option(selected)
                st.session_state.news_feed_search_value = keyword
                st.session_state.news_feed_search_input = keyword  # Sync widget key!
            else:
                # Clear search when "None" selected (only if previously had a selection)
                if st.session_state.news_feed_prev_selection != "None - Type your own search":
                    st.session_state.news_feed_search_value = ""
                    st.session_state.news_feed_search_input = ""  # Sync widget key!
            st.session_state.news_feed_prev_selection = selected

        # Callback function to sync text input changes
        def on_search_change():
            st.session_state.news_feed_search_value = st.session_state.news_feed_search_input

        # Initialize text input widget key if not exists
        if 'news_feed_search_input' not in st.session_state:
            st.session_state.news_feed_search_input = st.session_state.news_feed_search_value

        # Quick select dropdown and search input (aligned labels)
        col1, col2 = st.columns([1, 2])

        with col1:
            selected_option = st.selectbox(
                "🎯 Quick select from AI insights:",
                options=search_options,
                index=0,
                key="news_feed_dropdown",
                on_change=on_dropdown_change
            )

        with col2:
            search_query = st.text_input(
                "🔍 Search articles by keyword",
                placeholder="e.g., regulation, AI, Brazil, \"sports betting\"",
                key="news_feed_search_input",
                on_change=on_search_change
            )

        # Use session state value for search (synced from both dropdown and text input)
        search_query = st.session_state.news_feed_search_value

        # Search syntax help (collapsible)
        with st.expander("💡 Search syntax examples", expanded=False):
            st.markdown("""
| Query | Meaning |
|-------|---------|
| `Brazil regulation` | Articles with BOTH words (AND is default) |
| `Brazil OR regulation` | Articles with EITHER word |
| `"sports betting"` | Exact phrase match |
| `"sports betting" Brazil` | Phrase AND keyword combined |
            """)

        # ================================================================
        # SEARCH EXECUTION
        # ================================================================
        if search_query:
            search_results = search_all_time(
                filtered_df,
                search_query,
                search_fields=SEARCH_FIELDS_DEFAULT
            )

            if not search_results.empty:
                matching_ids = set(search_results['article_id'].astype(str))
                display_df = filtered_df[filtered_df['article_id'].astype(str).isin(matching_ids)]
            else:
                display_df = filtered_df.iloc[0:0]  # Empty DataFrame

            # Show coverage insight (affiliates grouped with external)
            competitor_count = len(display_df[display_df['category'] == 'competitor'])
            affiliate_count = len(display_df[display_df['category'] == 'affiliate'])
            internal_count = len(display_df[display_df['category'] == 'internal'])
            external_count = competitor_count + affiliate_count

            if external_count > internal_count:
                gap = external_count - internal_count
                st.warning(f"⚠️ **Coverage Gap:** External sources have {gap} more articles about '{search_query}' ({competitor_count} competitor + {affiliate_count} affiliate)")
            elif internal_count > external_count:
                lead = internal_count - external_count
                st.success(f"✅ **Clarion Lead:** We have {lead} more articles about '{search_query}'")
            elif external_count == internal_count and external_count > 0:
                st.info(f"⚖️ **Even Coverage:** Equal coverage of '{search_query}'")

            # Gemini AI search suggestions (optional)
            if GEMINI_SEARCH_AVAILABLE and expand_query is not None:
                try:
                    with st.expander("🤖 AI Search Suggestions", expanded=False):
                        suggestions = expand_query(search_query)
                        if suggestions:
                            st.caption("Related terms you might want to search:")
                            cols = st.columns(min(len(suggestions), 5))
                            for i, suggestion in enumerate(suggestions[:5]):
                                with cols[i]:
                                    if st.button(suggestion, key=f"suggest_{i}"):
                                        st.session_state.news_feed_search_value = suggestion
                                        st.rerun()
                        else:
                            st.caption("No additional suggestions available.")
                except Exception as e:
                    st.caption(f"AI suggestions unavailable: {str(e)[:50]}")
        else:
            display_df = filtered_df

        # ================================================================
        # PAGINATION - Reduces render time and eliminates fade/flash
        # ================================================================
        ARTICLES_PER_PAGE = 20
        total_articles = len(display_df)
        total_pages = max(1, (total_articles + ARTICLES_PER_PAGE - 1) // ARTICLES_PER_PAGE)

        # Initialize page number in session state
        if 'news_feed_page' not in st.session_state:
            st.session_state.news_feed_page = 1

        # Reset to page 1 when filters or search changes
        page_reset_key = f"page_reset_{current_filter_key}_{search_query}"
        if st.session_state.get('news_feed_page_reset_key') != page_reset_key:
            st.session_state.news_feed_page = 1
            st.session_state.news_feed_page_reset_key = page_reset_key

        current_page = st.session_state.news_feed_page

        # Calculate slice for current page
        start_idx = (current_page - 1) * ARTICLES_PER_PAGE
        end_idx = min(start_idx + ARTICLES_PER_PAGE, total_articles)

        # Show count with pagination info
        if total_articles > 0:
            st.caption(f"Showing {start_idx + 1}-{end_idx} of {total_articles} articles (Page {current_page}/{total_pages})")
        else:
            st.caption(f"Showing 0 of {len(filtered_df)} articles")

        # Pagination controls (top)
        if total_pages > 1:
            col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
            with col1:
                if st.button("⏮️ First", disabled=current_page == 1, key="news_first"):
                    st.session_state.news_feed_page = 1
                    st.rerun()
            with col2:
                if st.button("◀️ Prev", disabled=current_page == 1, key="news_prev"):
                    st.session_state.news_feed_page = current_page - 1
                    st.rerun()
            with col3:
                st.markdown(f"<div style='text-align: center; padding-top: 5px;'>Page {current_page} of {total_pages}</div>", unsafe_allow_html=True)
            with col4:
                if st.button("Next ▶️", disabled=current_page == total_pages, key="news_next"):
                    st.session_state.news_feed_page = current_page + 1
                    st.rerun()
            with col5:
                if st.button("Last ⏭️", disabled=current_page == total_pages, key="news_last"):
                    st.session_state.news_feed_page = total_pages
                    st.rerun()

        # Display articles as cards (paginated)
        page_df = display_df.iloc[start_idx:end_idx]
        for idx, article in page_df.iterrows():
            with st.container():
                # Badge and title
                col1, col2 = st.columns([1, 10])

                with col1:
                    if article['category'] == 'competitor':
                        st.markdown("🔴 **COMPETITOR**")
                    elif article['category'] == 'affiliate':
                        st.markdown("🟠 **AFFILIATE**")
                    else:
                        st.markdown("🔵 **INTERNAL**")

                with col2:
                    # Title as clickable link
                    st.markdown(f"### [{article['title']}]({article['link']})")

                    # Source and date
                    st.caption(f"**{article['source']}** • {article.get('published_date', 'No date')}")

                    # Summary
                    if article.get('summary'):
                        st.markdown(article['summary'])
                    else:
                        st.markdown("_No summary available_")

                st.markdown("---")

        # Debug search parity expander (only visible when DEBUG_MODE=1)
        if DEBUG_MODE and search_query:
            with st.expander("🔧 Debug search parity", expanded=False):
                st.caption("Compares News Feed search results with Context Explorer (windowed to same date range)")

                parity = compute_search_parity(
                    search_query,
                    filtered_df,
                    df_history,
                    SEARCH_FIELDS_DEFAULT
                )

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("News Feed", parity['news_feed_count'])
                with col2:
                    st.metric("Context Explorer (in window)", parity['context_explorer_count'])
                with col3:
                    if parity['is_parity']:
                        st.success("✅ PARITY")
                    else:
                        st.error(f"❌ {parity['diff_count']} diff")

                if not parity['is_parity']:
                    if parity['news_feed_only_details']:
                        st.markdown("**Only in News Feed:**")
                        for item in parity['news_feed_only_details'][:25]:
                            st.caption(f"- [{item['id']}] {item['title']}")

                    if parity['context_explorer_only_details']:
                        st.markdown("**Only in Context Explorer:**")
                        for item in parity['context_explorer_only_details'][:25]:
                            st.caption(f"- [{item['id']}] {item['title']}")
                else:
                    st.caption("Both pipelines return identical results for this query.")

    # Tab 3: Intelligence Battleground (NER-Based)
    elif selected_tab == TAB_OPTIONS[2]:
        st.header("⚔️ Intelligence Battleground: NER-Powered Analysis")
        st.markdown("**Using spaCy Named Entity Recognition for precise entity extraction**")
        st.caption(f"📅 **Date range:** {start_date.isoformat()} to {end_date.isoformat()} ({window_option})")
        st.markdown("---")

        # Pre-initialize variables for export section and dropdown (prevents NameError and scope issues)
        geo_comparison = []
        top_companies = []
        topic_comparison = []
        topic_gap_df = None  # Initialize to prevent locals() check failure in dropdown

        # Check if we have both categories
        # Note: 'affiliate' sources are treated as competitors in Intelligence Battleground
        has_competitor = len(filtered_df[filtered_df['category'].isin(['competitor', 'affiliate'])]) > 0
        has_internal = len(filtered_df[filtered_df['category'] == 'internal']) > 0

        if not has_competitor or not has_internal:
            st.warning("⚠️ Need both competitor and internal articles for analysis. Check your filters.")
            return

        # Process with NLP (or skip if not available)
        # Use filter-keyed session state to avoid recomputation spinners
        nlp_cache_key = get_ai_cache_key('nlp_results')

        if nlp is None:
            st.info("ℹ️ spaCy NER not available. Entity extraction charts will be empty. Install spaCy model to enable.")
            nlp_results = process_articles_with_nlp(filtered_df, None)
        else:
            # Check session state first for instant retrieval
            if st.session_state.get(nlp_cache_key) is not None:
                nlp_results = st.session_state[nlp_cache_key]
            else:
                # No spinner - @st.cache_data on process_articles_with_nlp handles caching
                # Function returns instantly if DataFrame hash matches previous call
                nlp_results = process_articles_with_nlp(filtered_df, nlp)
                st.session_state[nlp_cache_key] = nlp_results

        # Get article counts (affiliates grouped with competitors for comparison)
        competitor_article_count = len(filtered_df[filtered_df['category'] == 'competitor'])
        affiliate_article_count = len(filtered_df[filtered_df['category'] == 'affiliate'])
        internal_article_count = len(filtered_df[filtered_df['category'] == 'internal'])
        external_article_count = competitor_article_count + affiliate_article_count

        # CHART A: Market Focus (Geographic - GPE Entities)
        st.subheader("🌍 Chart A: Market Focus - Geographic Coverage (%)")
        st.caption("❓ **Question this answers:** Where are competitors talking more than us geographically?")
        st.caption("Percentage of articles mentioning each location (fixes volume bias)")

        geo_comparison = get_top_entities_comparison(
            nlp_results['competitor_locations_per_article'],
            nlp_results['internal_locations_per_article'],
            top_n=15
        )

        if geo_comparison:
            locations = [item['entity'] for item in geo_comparison]
            competitor_pct = [item['competitor_pct'] for item in geo_comparison]
            internal_pct = [item['internal_pct'] for item in geo_comparison]

            fig_geo = go.Figure(data=[
                go.Bar(
                    name='Competitor Coverage (%)',
                    x=locations,
                    y=competitor_pct,
                    marker_color='#FF4B4B',
                    text=[f"{pct:.1f}%" for pct in competitor_pct],
                    textposition='auto',
                ),
                go.Bar(
                    name='Clarion Coverage (%)',
                    x=locations,
                    y=internal_pct,
                    marker_color='#0068C9',
                    text=[f"{pct:.1f}%" for pct in internal_pct],
                    textposition='auto',
                )
            ])

            fig_geo.update_layout(
                barmode='group',
                title='Geographic Market Focus: Percentage of Coverage',
                xaxis_title='Location (GPE)',
                yaxis_title='Percentage of Articles (%)',
                xaxis_tickangle=-45,
                height=500,
                hovermode='x unified'
            )

            st.plotly_chart(fig_geo, **_get_width_kwargs())

            # Geographic Gap Table
            st.markdown("---")
            st.subheader("📊 Geo Gap Table: Where competitors talk more than us")
            st.caption("Percentages represent share of articles mentioning each region. Positive gap = competitor advantage.")

            # Build gap table
            gap_rows = []
            for item in geo_comparison:
                region = item['entity']
                comp_pct = item['competitor_pct']
                clar_pct = item['internal_pct']
                gap = comp_pct - clar_pct

                # Priority rules
                if gap >= 5 and comp_pct >= 5:
                    priority = "🔴 High"
                elif gap >= 3:
                    priority = "🟡 Medium"
                else:
                    priority = "🟢 Low"

                gap_rows.append({
                    'Region': region,
                    'Competitor %': f"{comp_pct}%",
                    'Clarion %': f"{clar_pct}%",
                    'Gap %': f"{gap:+.1f}%",
                    'Priority': priority
                })

            # Filter to only show gaps where competitors lead
            gap_df = pd.DataFrame([row for row in gap_rows if float(row['Gap %'].strip('%+')) > 0])

            if not gap_df.empty:
                # Sort by gap descending
                gap_df['_sort_key'] = gap_df['Gap %'].apply(lambda x: float(x.strip('%+')))
                gap_df = gap_df.sort_values('_sort_key', ascending=False).drop(columns=['_sort_key'])
                gap_df = gap_df.reset_index(drop=True)

                st.dataframe(gap_df, hide_index=True, **_get_width_kwargs())

                # Show largest gap callout
                if len(gap_df) > 0:
                    top_row = gap_df.iloc[0]
                    top_region = top_row['Region']
                    top_comp = top_row['Competitor %'].strip('%')
                    top_clar = top_row['Clarion %'].strip('%')
                    st.info(f"📍 **Largest geo gap:** {top_region} where competitors cover {top_comp}% vs our {top_clar}%")
            else:
                st.info("✅ No geographic gaps detected. Clarion coverage matches or exceeds competitors across all regions.")

            # AI Insight for Chart A (Geographic) - filter-keyed for instant retrieval
            if GEMINI_NER_AVAILABLE and get_geo_insight is not None and geo_comparison:
                geo_insight_key = get_ai_cache_key('geo_insight')
                geo_insight = st.session_state.get(geo_insight_key)
                if geo_insight is None:
                    geo_insight = get_geo_insight(
                        json.dumps(geo_comparison),
                        competitor_article_count,
                        internal_article_count
                    )
                    st.session_state[geo_insight_key] = geo_insight
                if geo_insight and not geo_insight.startswith("Unable"):
                    st.info(f"🤖 **AI Insight:** {geo_insight}")

        else:
            st.info("📍 No geographic entities (GPE) detected in articles.")

        st.markdown("---")

        # CHART B: Commercial Radar (Company ORG Entities)
        st.subheader("🏢 Chart B: Commercial Radar - Most Mentioned Companies")
        st.caption("❓ **Question this answers:** Which brands are emerging as sponsor or partner targets?")
        st.caption("Top companies detected with AI-powered classification (excluding known competitors/internal brands)")

        # Get top companies from BOTH categories combined
        # Normalize company names BEFORE counting to deduplicate variants
        # e.g., "PMU" and "Pari Mutuel Urbain (PMU)" both become "PMU"
        all_companies_raw = nlp_results['competitor_companies'] + nlp_results['internal_companies']
        all_companies_normalized = [normalize_company(c) for c in all_companies_raw]
        company_counter = Counter(all_companies_normalized)
        top_companies_raw = [item for item in company_counter.most_common(30) if item[1] >= 2]

        # Populate top_companies for export section
        top_companies = [{'company': company, 'mentions': count} for company, count in top_companies_raw]

        # Extract sponsor companies from AI analysis (normalize for comparison)
        sponsor_companies = set()
        if analysis_json and 'commercial_radar' in analysis_json:
            sponsors_list = analysis_json['commercial_radar'].get('potential_sponsors', [])
            sponsor_companies = {
                normalize_company(s.get('company_name', '').strip())
                for s in sponsors_list if s.get('company_name')
            }

        if top_companies_raw:
            # Enrich with metadata and filter to gambling-industry companies only
            company_data = []
            gambling_types = {'operator', 'supplier', 'association', 'regulator'}

            for company_name, mention_count in top_companies_raw:
                # Skip companies in STOP_ORGS (generic tech/platform companies)
                if normalize_company(company_name).lower() in STOP_ORGS:
                    continue

                # Skip headline fragments (NER incorrectly extracting article title phrases)
                if is_headline_fragment(company_name):
                    continue

                metadata = get_company_metadata(company_name)
                company_type = metadata.get('type', 'unknown')

                # Filter out companies that are KNOWN to be non-gambling
                # Only exclude if explicitly marked as non-gambling (other, media, etc.)
                # Keep unknown companies (they might be gambling-related but not yet classified)
                non_gambling_types = {'other', 'media', 'publisher', 'tech_platform'}
                if company_type in non_gambling_types:
                    continue

                # Normalize company name for sponsor comparison
                is_sponsor = normalize_company(company_name) in sponsor_companies
                company_data.append({
                    'company': company_name,
                    'mentions': mention_count,
                    'type': company_type,
                    'segment': metadata.get('primary_segment', 'unknown'),
                    'is_regulator': metadata.get('is_regulator', False),
                    'is_sponsor': is_sponsor,
                    'confidence': metadata.get('confidence', 0.0),
                    'enriched': metadata.get('enriched', False)
                })

            df_companies = pd.DataFrame(company_data)

            # Check if metadata is available
            has_metadata = load_company_metadata() != {}

            # Filters (only show if metadata exists)
            if has_metadata:
                st.markdown("**Filter by metadata:**")
                col1, col2 = st.columns(2)

                with col1:
                    # Get unique types from current data
                    available_types = sorted(df_companies['type'].unique())
                    selected_types = st.multiselect(
                        "Company Type",
                        options=available_types,
                        default=available_types,
                        key="company_type_filter"
                    )

                with col2:
                    # Get unique segments from current data
                    available_segments = sorted(df_companies['segment'].unique())
                    selected_segments = st.multiselect(
                        "Business Segment",
                        options=available_segments,
                        default=available_segments,
                        key="company_segment_filter"
                    )

                # Apply filters
                df_filtered = df_companies[
                    (df_companies['type'].isin(selected_types)) &
                    (df_companies['segment'].isin(selected_segments))
                ]
            else:
                # No metadata available, use all companies
                df_filtered = df_companies
                st.info("💡 Run `python -m scripts.enrich_company_metadata_llm` to enable smart filtering")

            # Limit to top 15 after filtering
            df_filtered = df_filtered.head(15)

            if len(df_filtered) > 0:
                companies = df_filtered['company'].tolist()
                company_mentions = df_filtered['mentions'].tolist()
                is_sponsor_flags = df_filtered['is_sponsor'].tolist()

                # Color: Gold for sponsors, otherwise by type
                sponsor_color = '#FFD700'  # Gold for sponsors
                normal_color = '#0068C9'   # Blue for normal companies

                colors = []
                for i, company in enumerate(companies):
                    if is_sponsor_flags[i]:
                        colors.append(sponsor_color)
                    else:
                        colors.append(normal_color)

                # Create hover text with metadata
                hover_texts = []
                for _, row in df_filtered.iterrows():
                    hover_text = f"<b>{row['company']}</b><br>"
                    hover_text += f"Mentions: {row['mentions']}<br>"
                    if row['is_sponsor']:
                        hover_text += "⭐ AI-Flagged Sponsor<br>"
                    if has_metadata:
                        # Add (inferred) badge if enriched
                        type_display = f"{row['type']} (inferred)" if row.get('enriched', False) else row['type']
                        hover_text += f"Type: {type_display}<br>"
                        hover_text += f"Segment: {row['segment']}<br>"
                        hover_text += f"Confidence: {row['confidence']:.2f}"
                    hover_texts.append(hover_text)

                fig_companies = go.Figure(data=[
                    go.Bar(
                        x=companies,
                        y=company_mentions,
                        marker_color=colors,
                        text=company_mentions,
                        textposition='auto',
                        hovertext=hover_texts,
                        hoverinfo='text'
                    )
                ])

                fig_companies.update_layout(
                    title='Most Mentioned Companies (Potential Sponsors)',
                    xaxis_title='Company (ORG)',
                    yaxis_title='Total Mentions',
                    xaxis_tickangle=-45,
                    height=500
                )

                st.plotly_chart(fig_companies, **_get_width_kwargs())
                st.caption("⭐ Gold bars are flagged as potential sponsors by the LLM analysis.")

                # Show summary with metadata breakdown
                sponsor_count = sum(is_sponsor_flags)
                if sponsor_count > 0:
                    st.info(f"⭐ **{sponsor_count} AI-flagged sponsors** out of {len(df_filtered)} companies shown")

                # Show detailed table
                if has_metadata:
                    with st.expander("📊 View Detailed Company Data"):
                        display_cols = ['company', 'mentions', 'is_sponsor', 'type', 'segment', 'confidence']
                        st.dataframe(
                            df_filtered[display_cols].sort_values('mentions', ascending=False),
                            hide_index=True,
                            **_get_width_kwargs()
                        )
            else:
                st.warning("No companies match the selected filters")

            # AI Insight for Chart B (Companies) - filter-keyed for instant retrieval
            if GEMINI_NER_AVAILABLE and get_company_insight is not None and top_companies:
                company_insight_key = get_ai_cache_key('company_insight')
                company_insight = st.session_state.get(company_insight_key)
                if company_insight is None:
                    company_insight = get_company_insight(json.dumps(top_companies[:15]))
                    st.session_state[company_insight_key] = company_insight
                if company_insight and not company_insight.startswith("Unable"):
                    st.info(f"🤖 **AI Insight:** {company_insight}")

        else:
            st.info("🔍 No significant company entities (ORG) detected.")

        st.markdown("---")

        # CHART C: Strategic Topics (Keyword-Based Classification)
        st.subheader("📝 Chart C: Strategic Topics - Topic Clusters")
        st.caption("❓ **Question this answers:** Which topic themes are hot for competitors but under-covered by us?")
        st.caption("Top topic clusters based on keyword classification (regulation, market expansion, responsible gaming, etc.)")

        topic_comparison = get_top_entities_comparison(
            nlp_results['competitor_topics_per_article'],
            nlp_results['internal_topics_per_article'],
            top_n=15
        )

        if topic_comparison:
            topics = [item['entity'] for item in topic_comparison]
            topic_competitor_pct = [item['competitor_pct'] for item in topic_comparison]
            topic_internal_pct = [item['internal_pct'] for item in topic_comparison]

            fig_topics = go.Figure(data=[
                go.Bar(
                    name='Competitor Coverage (%)',
                    x=topics,
                    y=topic_competitor_pct,
                    marker_color='#FF4B4B',
                    text=[f"{pct:.1f}%" for pct in topic_competitor_pct],
                    textposition='auto',
                ),
                go.Bar(
                    name='Clarion Coverage (%)',
                    x=topics,
                    y=topic_internal_pct,
                    marker_color='#0068C9',
                    text=[f"{pct:.1f}%" for pct in topic_internal_pct],
                    textposition='auto',
                )
            ])

            fig_topics.update_layout(
                barmode='group',
                title='Strategic Topic Coverage: Keyword-Based Clusters',
                xaxis_title='Topic Cluster',
                yaxis_title='Percentage of Articles (%)',
                xaxis_tickangle=-45,
                height=500,
                hovermode='x unified'
            )

            st.plotly_chart(fig_topics, **_get_width_kwargs())

            # Build topic gap table
            topic_gap_rows = []
            for item in topic_comparison:
                if item['competitor_pct'] > item['internal_pct']:
                    topic_gap_rows.append({
                        'Topic': item['entity'],
                        'Competitor %': f"{item['competitor_pct']}%",
                        'Clarion %': f"{item['internal_pct']}%",
                        'Gap %': f"{item['competitor_pct'] - item['internal_pct']:.1f}%"
                    })

            if topic_gap_rows:
                # Sort by gap descending
                topic_gap_df = pd.DataFrame(topic_gap_rows)
                topic_gap_df['_sort_key'] = topic_gap_df['Gap %'].apply(lambda x: float(x.strip('%')))
                topic_gap_df = topic_gap_df.sort_values('_sort_key', ascending=False).drop(columns=['_sort_key'])

                st.markdown("---")
                st.markdown("**📊 Topic Gap Table**")
                st.dataframe(topic_gap_df.head(5), hide_index=True, **_get_width_kwargs())

                # Show largest topic gap callout
                if len(topic_gap_df) > 0:
                    top_row = topic_gap_df.iloc[0]
                    top_topic = top_row['Topic']
                    top_comp_pct = top_row['Competitor %'].strip('%')
                    top_clar_pct = top_row['Clarion %'].strip('%')
                    st.info(f"📊 **Largest topic gap:** {top_topic} where competitors write about it {top_comp_pct}% of the time vs our {top_clar_pct}%")

            # AI Insight for Chart C (Topics) - filter-keyed for instant retrieval
            if GEMINI_NER_AVAILABLE and get_topic_insight is not None and topic_comparison:
                topic_insight_key = get_ai_cache_key('topic_insight')
                topic_insight = st.session_state.get(topic_insight_key)
                if topic_insight is None:
                    topic_insight = get_topic_insight(json.dumps(topic_comparison))
                    st.session_state[topic_insight_key] = topic_insight
                if topic_insight and not topic_insight.startswith("Unable"):
                    st.info(f"🤖 **AI Insight:** {topic_insight}")

        # Fallback: Show strategic gaps from JSON even if no topics detected via NER
        elif analysis_json and 'strategic_gaps' in analysis_json:
            st.info("📊 No topic clusters detected via NER. Showing AI-identified strategic gaps instead:")
            strategic_gaps = analysis_json['strategic_gaps']

            for idx, gap in enumerate(strategic_gaps[:5], 1):
                with st.expander(f"{idx}. {gap.get('gap_title', 'Unknown Topic')}", expanded=(idx == 1)):
                    st.markdown(f"**Gap Details:** {gap.get('description', 'N/A')}")
                    st.markdown(f"**Commercial Value:** {gap.get('priority', 'N/A')}")
                    st.markdown("**Content Opportunity:**")
                    st.write(gap.get('opportunity', ''))

        else:
            st.info("📊 No strategic topics detected in this batch.")

        st.markdown("---")

        # CHART D: Regional Breakdown (Pie Chart)
        st.subheader("🌎 Chart D: Regional Breakdown - Geographic Distribution")
        st.caption("Distribution of coverage across major geographic regions")

        # Count regions from normalized locations
        all_competitor_regions = Counter(nlp_results['competitor_locations'])
        all_internal_regions = Counter(nlp_results['internal_locations'])

        # Create side-by-side pie charts
        col1, col2 = st.columns(2)

        with col1:
            if all_competitor_regions:
                regions_comp = list(all_competitor_regions.keys())
                counts_comp = list(all_competitor_regions.values())

                fig_pie_comp = go.Figure(data=[go.Pie(
                    labels=regions_comp,
                    values=counts_comp,
                    marker=dict(colors=['#FF4B4B', '#FF6B6B', '#FF8B8B', '#FFABAB', '#FFCBCB']),
                    hole=0.3
                )])

                fig_pie_comp.update_layout(
                    title='Competitor Regional Focus',
                    height=400
                )

                st.plotly_chart(fig_pie_comp, **_get_width_kwargs())
            else:
                st.info("No competitor regional data")

        with col2:
            if all_internal_regions:
                regions_int = list(all_internal_regions.keys())
                counts_int = list(all_internal_regions.values())

                fig_pie_int = go.Figure(data=[go.Pie(
                    labels=regions_int,
                    values=counts_int,
                    marker=dict(colors=['#0068C9', '#2078D9', '#4088E9', '#6098F9', '#80A8FF']),
                    hole=0.3
                )])

                fig_pie_int.update_layout(
                    title='Clarion Regional Focus',
                    height=400
                )

                st.plotly_chart(fig_pie_int, **_get_width_kwargs())
            else:
                st.info("No Clarion regional data")

        # Regional insights
        if all_competitor_regions and all_internal_regions:
            # Find regions competitors cover but we don't
            competitor_only = set(all_competitor_regions.keys()) - set(all_internal_regions.keys())
            if competitor_only:
                st.warning(f"⚠️ **Regional Gaps:** Competitors are covering {', '.join(competitor_only)} but we have zero coverage in these regions!")

            # AI Insight for Chart D (Regional) - filter-keyed for instant retrieval
            if GEMINI_NER_AVAILABLE and get_regional_insight is not None:
                regional_insight_key = get_ai_cache_key('regional_insight')
                regional_insight = st.session_state.get(regional_insight_key)
                if regional_insight is None:
                    # Prepare regional data for insight
                    competitor_regions = dict(all_competitor_regions.most_common(5))
                    internal_regions = dict(all_internal_regions.most_common(5))
                    regional_insight = get_regional_insight(
                        json.dumps(competitor_regions),
                        json.dumps(internal_regions)
                    )
                    st.session_state[regional_insight_key] = regional_insight
                if regional_insight and not regional_insight.startswith("Unable"):
                    st.info(f"🤖 **AI Insight:** {regional_insight}")

        # ========================================
        # AFFILIATE ANALYSIS SECTION
        # ========================================
        st.markdown("---")
        st.subheader("📊 Affiliate Space Analysis")
        st.caption("Compare affiliate-focused sources against non-affiliate sources (ignores Space filter)")

        # Define affiliate sources (same as sidebar)
        AFFILIATE_SOURCES_SET = {
            "iGaming Afrika", "iGaming Expert", "Gambling Insider",
            "Game Lounge", "Gaming and Co", "North Star Network", "iGB Affiliate"
        }

        # Use df filtered by date/category but NOT by source (ignore Space filter for this analysis)
        # This ensures we always compare ALL affiliate vs ALL non-affiliate sources
        affiliate_analysis_df = df[df['category'].isin(selected_categories)].copy()

        # Split data from the full dataset (not filtered_df which may be space-filtered)
        affiliate_df = affiliate_analysis_df[affiliate_analysis_df['source'].isin(AFFILIATE_SOURCES_SET)]
        non_affiliate_df = affiliate_analysis_df[~affiliate_analysis_df['source'].isin(AFFILIATE_SOURCES_SET)]

        # Metrics row
        aff_col1, aff_col2, aff_col3 = st.columns(3)
        with aff_col1:
            st.metric("Affiliate Articles", len(affiliate_df))
        with aff_col2:
            st.metric("Non-Affiliate Articles", len(non_affiliate_df))
        with aff_col3:
            ratio = len(affiliate_df) / len(non_affiliate_df) if len(non_affiliate_df) > 0 else 0
            st.metric("Ratio", f"{ratio:.2f}")

        # Topic comparison between affiliate and non-affiliate sources
        if len(affiliate_df) > 5 and len(non_affiliate_df) > 5:
            # Process NLP for each group
            affiliate_nlp = process_articles_with_nlp(affiliate_df, nlp)
            non_affiliate_nlp = process_articles_with_nlp(non_affiliate_df, nlp)

            # Compare topics
            affiliate_topics = calculate_entity_article_coverage(
                affiliate_nlp.get('competitor_topics_per_article', []) +
                affiliate_nlp.get('internal_topics_per_article', [])
            )
            non_affiliate_topics = calculate_entity_article_coverage(
                non_affiliate_nlp.get('competitor_topics_per_article', []) +
                non_affiliate_nlp.get('internal_topics_per_article', [])
            )

            # Build comparison
            st.markdown("#### Topic Focus: Affiliate vs Non-Affiliate Sources")

            # Create comparison dataframe
            all_topics = set(t['entity'] for t in affiliate_topics) | set(t['entity'] for t in non_affiliate_topics)
            comparison_data = []

            for topic in all_topics:
                aff_pct = next((t['percentage'] for t in affiliate_topics if t['entity'] == topic), 0)
                non_aff_pct = next((t['percentage'] for t in non_affiliate_topics if t['entity'] == topic), 0)
                comparison_data.append({
                    'topic': topic,
                    'affiliate_pct': aff_pct,
                    'non_affiliate_pct': non_aff_pct,
                    'diff': aff_pct - non_aff_pct
                })

            comp_df = pd.DataFrame(comparison_data)
            comp_df = comp_df.sort_values('diff', ascending=False).head(15)

            if len(comp_df) > 0:
                # Bar chart
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    name='Affiliate Sources',
                    x=comp_df['topic'],
                    y=comp_df['affiliate_pct'],
                    marker_color='#FF6B6B'
                ))
                fig.add_trace(go.Bar(
                    name='Non-Affiliate Sources',
                    x=comp_df['topic'],
                    y=comp_df['non_affiliate_pct'],
                    marker_color='#4ECDC4'
                ))
                fig.update_layout(
                    barmode='group',
                    title='Topic Coverage: Affiliate vs Non-Affiliate',
                    xaxis_tickangle=-45,
                    height=400,
                    yaxis_title='% of Articles',
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig, **_get_width_kwargs())

                # AI Insight for affiliate comparison
                if GEMINI_NER_AVAILABLE:
                    try:
                        from src.gemini_ner_analysis import get_affiliate_comparison_insight
                        # Cached, no spinner needed
                        affiliate_insight = get_affiliate_comparison_insight(
                            json.dumps(comparison_data[:10]),
                            len(affiliate_df),
                            len(non_affiliate_df)
                        )
                        if affiliate_insight and not affiliate_insight.startswith("Unable"):
                            st.info(f"🤖 **AI Insight:** {affiliate_insight}")
                    except ImportError:
                        pass  # Function not yet available
        else:
            st.info("Need at least 5 articles from both affiliate and non-affiliate sources for comparison.")

        st.markdown("---")

        # Export section
        st.subheader("📥 Export Intelligence Data")

        col1, col2, col3 = st.columns(3)

        with col1:
            if geo_comparison:
                geo_df = pd.DataFrame(geo_comparison)
                st.download_button(
                    label="Download Geographic Data (CSV)",
                    data=geo_df.to_csv(index=False),
                    file_name=f"geographic_analysis_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

        with col2:
            if top_companies:
                comp_df = pd.DataFrame(top_companies)
                st.download_button(
                    label="Download Company List (CSV)",
                    data=comp_df.to_csv(index=False),
                    file_name=f"company_mentions_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

        with col3:
            if topic_comparison:
                topic_df = pd.DataFrame(topic_comparison)
                st.download_button(
                    label="Download Topic Analysis (CSV)",
                    data=topic_df.to_csv(index=False),
                    file_name=f"topic_analysis_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

        # AI insights are now shown inline with each chart above


if __name__ == "__main__":
    main()
