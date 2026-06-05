"""
Centralized file path constants for the competitive intelligence pipeline.

This module ensures all scripts (main.py, analysis.py, dashboard.py) use
the same canonical paths, preventing data sync issues.

IMPORTANT: All data files are now in data/ for Streamlit Cloud stability.
The outputs/ directory has been removed to ensure deployment reliability.

Usage:
    from paths import LATEST_NEWS_JSON, DAILY_ANALYSIS_JSON, NEWS_HISTORY_CSV
"""

import sys
from pathlib import Path

# Root directory (where this file lives)
ROOT = Path(__file__).resolve().parent

# Add project root to Python path so imports work from scripts/ and app/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Directories
DATA_DIR = ROOT / "data"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)

# All data files now in data/ (for Streamlit Cloud stability)
LATEST_NEWS_JSON = DATA_DIR / "latest_competitor_news.json"
LATEST_RUN_INFO_JSON = DATA_DIR / "latest_run_info.json"
DAILY_ANALYSIS_JSON = DATA_DIR / "daily_analysis.json"
DAILY_BRIEFING_MD = DATA_DIR / "daily_briefing.md"
NEWS_HISTORY_CSV = DATA_DIR / "news_history.csv"
COMPANY_METADATA_JSON = DATA_DIR / "company_metadata_auto.json"
COMPANY_CONTEXTS_JSON = DATA_DIR / "company_contexts_for_enrichment.json"

# Gemini AI cache file (persisted to disk for Streamlit Cloud)
# This stores pre-computed AI analysis from the daily pipeline run
GEMINI_CACHE_JSON = DATA_DIR / "gemini_cache.json"

# Legacy paths (deprecated - for backward compatibility only)
LEGACY_LATEST_NEWS_JSON = ROOT / "latest_competitor_news.json"
LEGACY_DAILY_ANALYSIS_JSON = ROOT / "daily_analysis.json"
LEGACY_DAILY_BRIEFING_MD = ROOT / "daily_briefing.md"
