#!/usr/bin/env python3
"""
Competitive Intelligence Tool for iGaming Industry
Hybrid approach: Direct RSS for working feeds, Google News RSS proxy for blocked sites.
Includes self-audit feature for Clarion's own brands (all via Google News proxy).
SSL-safe implementation using requests + feedparser for macOS compatibility.
"""

import sys
from pathlib import Path

# Add project root to sys.path
# (This allows importing from 'paths.py' and 'src/' even when running from scripts/)
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

import hashlib
import json
import logging
import re
import time
from datetime import UTC, datetime
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse, urlunparse

import feedparser
import pandas as pd
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Centralized file paths
from paths import LATEST_NEWS_JSON, NEWS_HISTORY_CSV

# Sources configuration file
SOURCES_CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config' / 'sources.json'


# Blocklists - prevent articles from these sources/domains from entering the system
BLOCKED_SOURCES = {"ice gaming", "ice"}  # Normalized (lowercase, trimmed)
BLOCKED_DOMAINS = {"icegaming.com"}


def normalize_domain(url: str) -> str:
    """
    Extract and normalize domain from URL for blocklist matching.

    Args:
        url: URL string to extract domain from

    Returns:
        Lowercase domain without port, or empty string if parsing fails

    Example:
        >>> normalize_domain("https://www.icegaming.com:443/article")
        'icegaming.com'
    """
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        # Strip port number if present
        host = host.split(":")[0]
        # Remove www. prefix for consistency
        if host.startswith('www.'):
            host = host[4:]
        return host
    except Exception as e:
        logger.warning(f"Domain normalization failed for '{url}': {type(e).__name__}: {str(e)}")
        return ""


def is_blocked(url: str) -> bool:
    """
    Check if URL belongs to a blocked domain.

    Handles both exact matches and subdomains.

    Args:
        url: URL to check against blocklist

    Returns:
        True if URL is from a blocked domain, False otherwise

    Example:
        >>> is_blocked("https://icegaming.com/article")
        True
        >>> is_blocked("https://www.icegaming.com/article")
        True
        >>> is_blocked("https://blog.icegaming.com/article")
        True
        >>> is_blocked("https://example.com/article")
        False
    """
    host = normalize_domain(url)
    if not host:
        return False

    # Check exact match or subdomain
    return any(host == domain or host.endswith("." + domain) for domain in BLOCKED_DOMAINS)


def norm_source(source: str) -> str:
    """
    Normalize source name for consistent blocking.

    Args:
        source: Source name string

    Returns:
        Normalized source (lowercase, collapsed whitespace, stripped)

    Example:
        >>> norm_source("  ICE  Gaming  ")
        'ice gaming'
        >>> norm_source("ICE")
        'ice'
    """
    return re.sub(r"\s+", " ", (source or "")).strip().lower()


def is_blocked_article(source: str, link: str) -> bool:
    """
    Check if article should be blocked by source name OR domain.

    Args:
        source: Article source name
        link: Article URL

    Returns:
        True if article should be blocked, False otherwise

    Example:
        >>> is_blocked_article("ICE Gaming", "https://example.com")
        True
        >>> is_blocked_article("SBC News", "https://icegaming.com/article")
        True
        >>> is_blocked_article("SBC News", "https://sbcnews.co.uk/article")
        False
    """
    # Check source name (normalized)
    normalized_source = norm_source(source)
    if normalized_source in BLOCKED_SOURCES:
        return True

    # Check domain
    host = normalize_domain(link)
    if not host:
        return False

    return any(host == domain or host.endswith("." + domain) for domain in BLOCKED_DOMAINS)


def strip_tracking_params(url: str) -> str:
    """
    Strip tracking parameters from URL for canonical link generation.

    More aggressive than normalize_url - removes all tracking/attribution params.

    Args:
        url: URL to clean

    Returns:
        URL without tracking parameters or fragment

    Example:
        >>> strip_tracking_params("https://example.com/article?utm_source=twitter&id=123#comment")
        'https://example.com/article?id=123'
    """
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        # Keep only non-tracking parameters
        allowed_params = []
        for key, values in query_params.items():
            key_lower = key.lower()
            # Block common tracking parameters
            if not (key_lower.startswith("utm_") or
                    key_lower in {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source", "campaign"}):
                allowed_params.append((key, values[0]))

        # Rebuild query string
        new_query = "&".join(f"{k}={quote(v)}" for k, v in allowed_params)

        # Reconstruct URL without fragment
        return urlunparse(parsed._replace(query=new_query, fragment=""))
    except Exception:
        # Fallback: at least remove fragment
        return url.split("#")[0]


def normalize_url(url: str) -> str:
    """
    Normalize URL to reduce duplicates caused by tracking parameters.

    Normalization steps:
    - Lowercase scheme and netloc (domain)
    - Remove known tracking parameters (utm_*, fbclid, gclid, mc_*, ref, source, campaign)
    - Strip URL fragments (#...)
    - Remove duplicate trailing slashes

    Args:
        url: Raw URL string

    Returns:
        Normalized URL string

    Example:
        >>> normalize_url("https://Example.com/article?utm_source=twitter&id=123#comments")
        'https://example.com/article?id=123'
    """
    if not url:
        return url

    try:
        parsed = urlparse(url)

        # Lowercase scheme and netloc
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Parse query parameters
        query_params = parse_qs(parsed.query, keep_blank_values=True)

        # Filter out tracking parameters
        tracking_prefixes = ('utm_', 'fbclid', 'gclid', 'mc_cid', 'mc_eid', 'ref', 'source', 'campaign')
        cleaned_params = {
            key: value
            for key, value in query_params.items()
            if not any(key.lower().startswith(prefix) for prefix in tracking_prefixes)
        }

        # Rebuild query string (sorted for consistency)
        cleaned_query = urlencode(sorted(cleaned_params.items()), doseq=True) if cleaned_params else ''

        # Remove duplicate trailing slashes from path
        path = parsed.path.rstrip('/') if parsed.path != '/' else parsed.path

        # Reconstruct URL without fragment
        normalized = urlunparse((
            scheme,
            netloc,
            path,
            parsed.params,
            cleaned_query,
            ''  # Remove fragment
        ))

        return normalized

    except Exception:
        # If parsing fails, return original URL
        return url


class NewsAggregator:
    """Aggregates news from various iGaming competitor websites and Clarion's own brands."""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        self.timeout = 10
        self.all_articles = []
        self.run_timestamp = datetime.now(UTC).isoformat()  # Single timestamp for entire run
        # Rate limiting
        self.request_delay = 0.5  # 500ms between requests
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce minimum delay between HTTP requests to avoid rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time = time.time()

    def _load_sources_config(self) -> dict:
        """
        Load news sources from config/sources.json.

        This is the single source of truth for news sources.
        Edit config/sources.json to add/remove sources.

        Returns:
            Dict with source configuration, or default fallback if file not found.
        """
        if SOURCES_CONFIG_PATH.exists():
            try:
                with open(SOURCES_CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                    logger.info(f"Loaded sources config from {SOURCES_CONFIG_PATH}")
                    return config
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in sources config: {e}")
            except Exception as e:
                logger.error(f"Error loading sources config: {e}")

        # Fallback to hardcoded defaults if config file is missing/invalid
        logger.warning("Using fallback hardcoded sources (config/sources.json not found)")
        return {
            'direct_rss': {
                'sources': [
                    {'name': 'SBC News', 'url': 'https://sbcnews.co.uk/feed/', 'category': 'competitor'},
                    {'name': 'iGaming Future', 'url': 'https://igamingfuture.com/feed/', 'category': 'competitor'},
                ]
            },
            'google_news_proxy': {
                'competitor': [
                    {'name': 'Next.io', 'domain': 'next.io'},
                    {'name': 'EGR Global', 'domain': 'egr.global'},
                ],
                'internal': [
                    {'name': 'iGaming Business', 'domain': 'igamingbusiness.com'},
                ]
            }
        }

    def generate_article_id(self, source: str, link: str) -> str:
        """
        Generate a unique article ID based on normalized source and canonical link.
        Uses SHA256 hash, shortened to 16 hex characters.

        Normalization:
        - Source: lowercase, collapsed whitespace
        - Link: resolve Google redirects, strip tracking params, remove fragment
        """
        # Normalize source
        clean_source = norm_source(source)

        # Canonicalize link
        try:
            # Resolve Google News redirects if present
            link = self.resolve_google_redirect(link)
        except Exception:
            pass

        # CRITICAL FIX (P0-1): Use normalize_url for consistency with stored link field
        # Previously used strip_tracking_params which produced different output,
        # causing same URL to get different article_ids on different scrape runs
        link = normalize_url(link)

        id_string = f"{clean_source}|{link}"
        return hashlib.sha256(id_string.encode("utf-8")).hexdigest()[:16]

    def standardize_date(self, date_string: str) -> str:
        """
        Parse date and normalize to UTC naive ISO format.
        Ensures all dates comparable regardless of source timezone.
        Returns YYYY-MM-DD HH:MM format in UTC, empty string on failure.
        """
        if not date_string:
            return ""

        try:
            # dateutil.parser handles RFC 822 and most other formats
            parsed_date = date_parser.parse(date_string)

            # Normalize to UTC
            if parsed_date.tzinfo is not None:
                # Has timezone info - convert to UTC
                parsed_date = parsed_date.astimezone(UTC)
            else:
                # Naive datetime - assume UTC
                parsed_date = parsed_date.replace(tzinfo=UTC)

            # Return as naive UTC (removes timezone for CSV compatibility)
            parsed_naive = parsed_date.replace(tzinfo=None)
            return parsed_naive.strftime("%Y-%m-%d %H:%M")

        except Exception as e:
            logger.warning(f"Date parse failed for '{date_string}': {type(e).__name__}: {str(e)}")
            return ""

    def resolve_google_redirect(self, google_url: str) -> str:
        """
        Attempt to resolve Google News redirect URLs to actual article URLs.
        If resolution hits consent.google.com, accounts.google.com, or fails,
        return the original Google News URL (ugly but clickable).
        """
        if not google_url or 'google.com' not in google_url:
            return google_url

        try:
            # Try to extract the actual URL from Google's redirect
            # Google News URLs often have the format: https://news.google.com/rss/articles/...
            # They redirect to the actual article

            response = requests.head(
                google_url,
                headers=self.headers,
                allow_redirects=True,
                timeout=5
            )

            resolved_url = response.url if response.url else google_url

            # Check if we hit the consent wall or account login - if so, revert to original
            if 'consent.google.com' in resolved_url or 'accounts.google.com' in resolved_url:
                return google_url

            # If we got a valid resolved URL, return it
            return resolved_url

        except Exception:
            # If resolution fails, try to parse URL parameter
            try:
                parsed = urlparse(google_url)
                params = parse_qs(parsed.query)

                # Look for common URL parameters
                for param in ['url', 'q', 'link']:
                    if param in params:
                        potential_url = unquote(params[param][0])
                        if potential_url.startswith('http'):
                            # Don't return consent or account URLs
                            if 'consent.google.com' not in potential_url and 'accounts.google.com' not in potential_url:
                                return potential_url
            except Exception:
                pass

            # If all else fails, return the original Google URL (clickable fallback)
            return google_url

    def fetch_direct_rss(self, source: str, url: str, category: str = 'competitor', is_affiliate: bool = False) -> list[dict]:
        """
        Fetch and parse direct RSS feed using requests + feedparser.
        This approach bypasses macOS SSL certificate issues.
        """
        articles = []

        try:
            print(f"  → Fetching direct RSS from {source}...")

            # Rate limit before request
            self._rate_limit()

            # Step 1: Use requests to fetch the raw RSS data (SSL-safe)
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()

            # Step 2: Parse the response content with feedparser (not the URL)
            feed = feedparser.parse(response.content)

            # Only fail if bozo error AND no entries parsed
            # Some feeds have minor XML issues but still parse entries successfully
            if feed.bozo and not feed.entries:
                # Try parsing as text (sometimes encoding issues cause problems with bytes)
                feed = feedparser.parse(response.text)
                if feed.bozo and not feed.entries:
                    raise Exception(f"Failed to parse RSS feed: {feed.get('bozo_exception', 'Unknown error')}")

            for entry in feed.entries[:50]:  # Limit to 50 most recent articles
                raw_link = entry.get('link', '')

                # Normalize URL to remove tracking parameters and reduce duplicates
                link = normalize_url(raw_link)

                # Block articles from blocked sources/domains at ingestion
                if is_blocked_article(source, link):
                    continue

                article = {
                    'article_id': self.generate_article_id(source, link),
                    'source': source,
                    'title': entry.get('title', 'No title'),
                    'link': link,
                    'published_date': self.standardize_date(entry.get('published', entry.get('updated', ''))),
                    'summary': entry.get('summary', entry.get('description', '')),
                    'category': category,
                    'is_affiliate': is_affiliate,
                    'run_timestamp': self.run_timestamp
                }

                # Clean HTML from summary if present
                if article['summary']:
                    soup = BeautifulSoup(article['summary'], 'html.parser')
                    article['summary'] = soup.get_text().strip()[:300]  # Limit summary length

                articles.append(article)

            print(f"    ✓ Successfully fetched {len(articles)} articles from {source}")

        except requests.exceptions.SSLError as e:
            logger.error(f"SSL Error fetching {source}: {str(e)} - certificate verification failed")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection Error fetching {source}: {str(e)}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout Error fetching {source}: {str(e)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request Error fetching {source}: {str(e)}")
        except Exception as e:
            logger.exception(f"Unexpected error fetching {source}: {str(e)}")

        return articles

    def fetch_via_google_news(self, source: str, site_domain: str, category: str = 'competitor', is_affiliate: bool = False) -> list[dict]:
        """
        Fetch news via Google News RSS proxy using requests + feedparser.
        This bypasses direct scraping blocks and SSL issues.
        """
        articles = []

        try:
            # Construct Google News RSS search URL
            google_rss_url = f"https://news.google.com/rss/search?q=site:{site_domain}&hl=en-US&gl=US&ceid=US:en"

            print(f"  → Fetching {source} via Google News proxy...")

            # Rate limit before request
            self._rate_limit()

            # Step 1: Use requests to fetch the raw RSS data (SSL-safe)
            response = requests.get(google_rss_url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()

            # Step 2: Parse the response content with feedparser (not the URL)
            feed = feedparser.parse(response.content)

            if feed.bozo and not feed.entries:
                raise Exception(f"Failed to parse Google News feed: {feed.get('bozo_exception', 'Unknown error')}")

            for entry in feed.entries[:50]:  # Limit to 50 most recent articles
                # Get the link (may be Google redirect)
                original_link = entry.get('link', '')

                # Try to resolve the Google redirect to actual article URL
                resolved_link = self.resolve_google_redirect(original_link)

                # Normalize URL to remove tracking parameters and reduce duplicates
                link = normalize_url(resolved_link)

                # Block articles from blocked sources/domains at ingestion
                if is_blocked_article(source, link):
                    continue

                article = {
                    'article_id': self.generate_article_id(source, link),
                    'source': source,
                    'title': entry.get('title', 'No title'),
                    'link': link,
                    'published_date': self.standardize_date(entry.get('published', entry.get('updated', ''))),
                    'summary': entry.get('summary', entry.get('description', '')),
                    'category': category,
                    'is_affiliate': is_affiliate,
                    'run_timestamp': self.run_timestamp
                }

                # Clean HTML from summary if present
                if article['summary']:
                    soup = BeautifulSoup(article['summary'], 'html.parser')
                    article['summary'] = soup.get_text().strip()[:300]  # Limit summary length

                articles.append(article)

            print(f"    ✓ Successfully fetched {len(articles)} articles from {source} (via Google News)")

        except requests.exceptions.SSLError as e:
            logger.error(f"SSL Error fetching {source} via Google News: {str(e)} - certificate verification failed")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection Error fetching {source} via Google News: {str(e)}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout Error fetching {source} via Google News: {str(e)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request Error fetching {source} via Google News: {str(e)}")
        except Exception as e:
            logger.exception(f"Unexpected error fetching {source} via Google News: {str(e)}")

        return articles

    def deduplicate_articles(self, articles: list[dict]) -> list[dict]:
        """
        Deduplicate articles by article_id, keeping the one with the latest published_date.

        Returns:
            List of unique articles
        """
        deduped = {}
        for article in articles:
            article_id = article["article_id"]

            if article_id not in deduped:
                deduped[article_id] = article
            else:
                # Keep the article with the more recent published_date
                # If dates are equal or unparseable, keep the first one
                existing_date = deduped[article_id].get("published_date", "")
                new_date = article.get("published_date", "")

                if new_date > existing_date:
                    deduped[article_id] = article

        return list(deduped.values())

    def save_to_history(self, articles: list[dict]):
        """
        Save articles to data/news_history.csv with improved deduplication and date handling.

        - Adds scrape_timestamp to track when we collected each article
        - Falls back published_date to scrape_timestamp when missing
        - Deduplicates by article_id, keeping earliest scrape_timestamp
        - Stores dates as ISO strings for CSV compatibility
        - Normalizes all timestamps to naive UTC to avoid tz-mixing errors

        Args:
            articles: List of deduplicated articles from current run
        """
        NEWS_HISTORY_CSV.parent.mkdir(parents=True, exist_ok=True)

        # 1. Convert current run to DataFrame
        df_new = pd.DataFrame(articles).copy()

        # 2. Add scrape_timestamp (naive UTC)
        now_utc = pd.Timestamp.utcnow()  # naive, in UTC
        df_new["scrape_timestamp"] = now_utc

        # 3. Parse published_date and fall back to scrape_timestamp when missing
        df_new["published_date"] = pd.to_datetime(df_new["published_date"], errors="coerce")
        df_new["published_date"] = df_new["published_date"].fillna(df_new["scrape_timestamp"])

        # 4. Load existing history if present
        if NEWS_HISTORY_CSV.exists():
            df_hist = pd.read_csv(NEWS_HISTORY_CSV)

            # Align columns between old and new
            for col in df_new.columns:
                if col not in df_hist.columns:
                    df_hist[col] = pd.NA
            for col in df_hist.columns:
                if col not in df_new.columns:
                    df_new[col] = pd.NA

            df_all = pd.concat([df_hist, df_new], ignore_index=True)
        else:
            df_all = df_new

        # 5. Normalize timestamps to naive UTC (fixes tz-mixing from old CSV rows)
        if "scrape_timestamp" in df_all.columns:
            df_all["scrape_timestamp"] = (
                pd.to_datetime(df_all["scrape_timestamp"], errors="coerce", utc=True)
                  .dt.tz_localize(None)
            )

        if "published_date" in df_all.columns:
            df_all["published_date"] = (
                pd.to_datetime(df_all["published_date"], errors="coerce", utc=True)
                  .dt.tz_localize(None)
            )

        before = len(df_all)

        # 6. Deduplicate by article_id keeping the earliest scrape_timestamp
        df_all = df_all.sort_values("scrape_timestamp").drop_duplicates("article_id", keep="first")

        # CRITICAL FIX (P0-3): Secondary deduplication by normalized URL
        # Catches edge cases where same URL might have different article_ids
        # (e.g., from legacy data before P0-1 fix was applied)
        df_all['_link_norm'] = df_all['link'].str.lower().str.strip()
        df_all = df_all.drop_duplicates("_link_norm", keep="first")
        df_all = df_all.drop(columns=['_link_norm'])

        after = len(df_all)

        added = after - (before - len(df_new))
        duplicates = len(df_new) - added

        # 7. Save back with ISO strings for dates
        df_all["published_date"] = df_all["published_date"].dt.strftime("%Y-%m-%d %H:%M")
        df_all["scrape_timestamp"] = df_all["scrape_timestamp"].dt.strftime("%Y-%m-%d %H:%M")

        # CRITICAL FIX (P0-2): Atomic write to prevent corruption on crash
        # Write to temp file first, then atomically rename to target
        temp_csv = NEWS_HISTORY_CSV.with_suffix('.tmp')
        df_all.to_csv(temp_csv, index=False)
        import os
        os.replace(temp_csv, NEWS_HISTORY_CSV)  # Atomic on POSIX systems

        print()
        print("=" * 70)
        print("SAVING TO HISTORY")
        print("=" * 70)
        print(f"✓ Added {added} new articles to history (skipped {duplicates} duplicates)")
        print(f"✓ History file rows: {len(df_all)}")

    def aggregate_all_news(self):
        """
        Aggregate news from all sources: competitors and internal Clarion brands.

        Processing flow:
        1. Fetch articles from all sources (each gets article_id and run_timestamp)
        2. Deduplicate within the run (by article_id, keeping latest published_date)
        3. Save deduplicated articles to latest_competitor_news.json
        4. Append new articles to data/news_history.csv (append-only log)

        Returns:
            List of deduplicated articles (typically 100-200 on a normal run)
        """

        # Load sources from config file (single source of truth)
        sources_config = self._load_sources_config()

        print("\n" + "=" * 70)
        print("GROUP A: Direct RSS Feeds (Working Feeds)")
        print("=" * 70)
        print("Method: Direct RSS extraction (requests + feedparser)")
        print()

        # Group A: Direct RSS feeds from config
        for src in sources_config.get('direct_rss', {}).get('sources', []):
            articles = self.fetch_direct_rss(
                src['name'],
                src['url'],
                category=src.get('category', 'competitor'),
                is_affiliate=src.get('is_affiliate', False)
            )
            self.all_articles.extend(articles)

        print("\n" + "=" * 70)
        print("GROUP B: Google News Proxy Sources")
        print("=" * 70)
        print("Method: Google News RSS proxy (bypasses bot protection)")
        print()

        # Group B: All Google News proxy sources (category from config)
        for src in sources_config.get('google_news_proxy', {}).get('sources', []):
            articles = self.fetch_via_google_news(
                src['name'],
                src['domain'],
                category=src.get('category', 'competitor'),
                is_affiliate=src.get('is_affiliate', False)
            )
            self.all_articles.extend(articles)

        # Deduplicate articles within this run
        print("\n" + "=" * 70)
        print("DEDUPLICATION")
        print("=" * 70)
        original_count = len(self.all_articles)
        self.all_articles = self.deduplicate_articles(self.all_articles)
        print(f"✓ Deduplicated: {original_count} → {len(self.all_articles)} articles")
        print(f"  (Removed {original_count - len(self.all_articles)} duplicates within this run)")

        # Final safety filter: remove any blocked articles that slipped through
        print("\n" + "=" * 70)
        print("FINAL SAFETY FILTER")
        print("=" * 70)
        before_filter = len(self.all_articles)
        self.all_articles = [
            article for article in self.all_articles
            if not is_blocked_article(article.get('source', ''), article.get('link', ''))
        ]
        filtered_count = before_filter - len(self.all_articles)
        if filtered_count > 0:
            print(f"✓ Removed {filtered_count} blocked articles (safety filter)")
        else:
            print("✓ No blocked articles found (all clean)")

        return self.all_articles

    def save_to_json(self):
        """Save aggregated news to JSON file in outputs/ directory."""
        try:
            # Ensure outputs directory exists
            LATEST_NEWS_JSON.parent.mkdir(parents=True, exist_ok=True)

            with open(LATEST_NEWS_JSON, 'w', encoding='utf-8') as f:
                json.dump(self.all_articles, f, ensure_ascii=False, indent=2)
            print(f"\n✓ Successfully saved {len(self.all_articles)} articles to {LATEST_NEWS_JSON}")
        except Exception as e:
            logger.exception(f"Error saving to JSON: {str(e)}")

    def print_summary(self):
        """Print a summary of collected articles by source and category."""
        print("\n" + "=" * 70)
        print("COLLECTION SUMMARY")
        print("=" * 70)

        # Count by category
        category_counts = {}
        source_counts = {}

        for article in self.all_articles:
            category = article.get('category', 'unknown')
            source = article['source']

            category_counts[category] = category_counts.get(category, 0) + 1
            source_counts[source] = source_counts.get(source, 0) + 1

        print("\n📊 By Category:")
        for cat in ['competitor', 'affiliate', 'internal']:
            count = category_counts.get(cat, 0)
            if count > 0:
                print(f"   {cat.capitalize()}: {count} articles")

        print("\n📰 By Source:")
        # Group sources by category
        for category in ['competitor', 'affiliate', 'internal']:
            sources_in_cat = [
                (src, source_counts[src])
                for src in source_counts
                if any(a['source'] == src and a['category'] == category for a in self.all_articles)
            ]
            if sources_in_cat:
                print(f"\n   {category.capitalize()}:")
                for source, count in sorted(sources_in_cat, key=lambda x: -x[1]):
                    print(f"     • {source}: {count} articles")

        print("\n" + "=" * 70)
        print(f"TOTAL ARTICLES COLLECTED: {len(self.all_articles)}")
        print("=" * 70)


def main():
    """Main execution function."""
    print("=" * 70)
    print("iGAMING COMPETITIVE INTELLIGENCE NEWS AGGREGATOR")
    print("=" * 70)
    print("Strategy: Direct RSS + Google News Proxy")
    print("Features: Competitor tracking + Clarion self-audit + History tracking")
    print("SSL-Safe: Using requests + feedparser (macOS compatible)")
    print("=" * 70)

    aggregator = NewsAggregator()
    aggregator.aggregate_all_news()
    aggregator.save_to_json()

    # Save to history (append-only log)
    print("\n" + "=" * 70)
    print("SAVING TO HISTORY")
    print("=" * 70)
    aggregator.save_to_history(aggregator.all_articles)

    aggregator.print_summary()

    # Save run metadata for timestamp tracking
    from datetime import datetime

    from paths import LATEST_RUN_INFO_JSON

    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%d%H%M%S")
    generated_at = now.isoformat()

    run_info = {
        "run_id": run_id,
        "generated_at": generated_at,
        "article_count": len(aggregator.all_articles),
    }

    with LATEST_RUN_INFO_JSON.open("w", encoding="utf-8") as f:
        json.dump(run_info, f, indent=2)

    print("\n✅ Aggregation complete!")
    print(f"   📄 Latest articles: {LATEST_NEWS_JSON} ({len(aggregator.all_articles)} articles)")
    print(f"   📚 History log: {NEWS_HISTORY_CSV} (append-only)")
    print(f"   🕒 Run metadata: {LATEST_RUN_INFO_JSON} (run_id: {run_id})")
    print("\n💡 Normal run stats:")
    print("   - Fetched: ~180-220 articles (20 per source × 11 sources)")
    print("   - After deduplication: ~100-200 articles (saved to JSON)")
    print("   - New articles added to history: varies (depends on overlap with existing)")


if __name__ == "__main__":
    main()
