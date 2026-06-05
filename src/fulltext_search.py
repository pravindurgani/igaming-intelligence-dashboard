"""
Full-text search functionality - REDIRECTS TO UNIFIED SEARCH MODULE.

This module is kept for backward compatibility. All search functionality
has been consolidated in src/search.py.

Use src/search.py directly for all new code.
"""

# Re-export from unified search module for backward compatibility
from src.search import (
    SearchIndex,
    build_keyword_index,
    execute_query,
    filter_keywords_with_results,
    get_or_build_index,
    parse_query,
    search_all_time,
    search_articles,
    tokenize,
)
from src.textnorm import (
    build_search_field,
    has_content,
    normalize_text,
)

# Keep backward compatibility
__all__ = [
    'search_articles',
    'search_all_time',
    'filter_keywords_with_results',
    'build_keyword_index',
    'SearchIndex',
    'parse_query',
    'execute_query',
    'tokenize',
    'normalize_text',
    'build_search_field',
    'has_content',
    'get_or_build_index',
]
