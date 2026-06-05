"""
Configuration constants for the Clarion Intelligence Dashboard.
"""

# Analysis Configuration
ANALYSIS_LOOKBACK_DAYS_DEFAULT = 30
ANALYSIS_LOOKBACK_DAYS_MIN = 1
ANALYSIS_LOOKBACK_DAYS_MAX = 365

# Batching Configuration for Analysis
# Instead of capping articles, we batch them to process ALL articles in the window
ANALYSIS_BATCH_SIZE_ARTICLES = 60  # Articles per batch (keeps prompt under token limits)
ANALYSIS_CONTENT_TRUNCATE_CHARS = 500  # Max chars from content per article in prompt

# Search Configuration
# IMPORTANT: Search must include 'content' field to find keywords in article body
SEARCH_FIELDS_DEFAULT = ['title', 'summary', 'content']

# LLM Configuration (provider-agnostic)
# Concrete provider + model are selected in src/llm_client.py via env vars.
# See .env.example for CEREBRAS_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY.
LLM_MAX_TOKENS = 4096
LLM_TEMPERATURE = 0.3

# Article Fetch Limits
DAILY_FETCH_LIMIT = 50  # Max articles per source per regular run
BACKFILL_FETCH_LIMIT = 100  # Max articles per source during backfill
BACKFILL_START_DATE = "2025-01-01"  # Default backfill start date
