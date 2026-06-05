"""
LLM-powered search enhancements for the Clarion Intelligence Dashboard.

Features:
- Query expansion: Suggest related terms
- Natural language parsing: Convert questions to keywords
- Semantic suggestions: Find related concepts

Backed by ``src.llm_client`` so any configured open-source provider
(Cerebras / Groq / OpenRouter) can serve these calls.
"""

import json
from typing import Any

from src import llm_client

# Cache for query expansions to avoid repeated API calls
_EXPANSION_CACHE: dict[str, list[str]] = {}


def init_gemini() -> bool:
    """Public availability check. Name kept for dashboard compatibility."""
    return llm_client.is_available()


def expand_query(query: str, context: str = "iGaming industry news") -> list[str]:
    """
    Use Gemini to expand a search query with related terms.

    Args:
        query: User's search query
        context: Context for expansion (default: iGaming)

    Returns:
        List of suggested related search terms
    """
    if not query or len(query.strip()) < 2:
        return []

    # Check cache first
    cache_key = f"{query.lower().strip()}_{context}"
    if cache_key in _EXPANSION_CACHE:
        return _EXPANSION_CACHE[cache_key]

    if not llm_client.is_available():
        return []

    try:
        prompt = f"""You are a search query expansion assistant for {context}.

Given the search query: "{query}"

Suggest 3-5 related search terms or phrases that would help find relevant articles.
Focus on:
- Industry-specific synonyms
- Related company names or brands
- Geographic variations
- Regulatory/legal variations

Respond with ONLY a JSON array of strings, no explanation:
["term1", "term2", "term3"]

Keep terms concise (1-3 words each)."""

        response_text = llm_client.generate(prompt)
        if not response_text:
            return []
        response_text = response_text.strip()

        # Parse JSON response
        if response_text.startswith('['):
            suggestions = json.loads(response_text)
            if isinstance(suggestions, list):
                # Cache and return
                _EXPANSION_CACHE[cache_key] = suggestions[:5]
                return suggestions[:5]
    except Exception as e:
        print(f"LLM query expansion error: {e}")

    return []


def parse_natural_language_query(query: str) -> dict[str, Any]:
    """
    Parse a natural language question into structured search parameters.

    Args:
        query: Natural language query like "What are competitors saying about Brazil?"

    Returns:
        Dict with parsed components: keywords, intent, filters
    """
    if not query or len(query.strip()) < 5:
        return {"keywords": query, "intent": "search", "filters": {}}

    if not llm_client.is_available():
        return {"keywords": query, "intent": "search", "filters": {}}

    try:
        prompt = f"""Parse this iGaming industry search query into structured components:

Query: "{query}"

Respond with ONLY valid JSON:
{{
  "keywords": "main search keywords",
  "intent": "search|compare|trend|gap",
  "filters": {{
    "category": "competitor|internal|both",
    "region": "specific region or null",
    "company": "specific company or null"
  }},
  "suggested_query": "optimized search string"
}}"""

        response_text = llm_client.generate(prompt)
        if not response_text:
            return {"keywords": query, "intent": "search", "filters": {}}
        response_text = response_text.strip()

        # Clean markdown formatting
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]

        return json.loads(response_text.strip())
    except Exception as e:
        print(f"LLM NL parsing error: {e}")

    return {"keywords": query, "intent": "search", "filters": {}}


def get_search_suggestions(
    current_query: str,
    available_keywords: list[str],
    max_suggestions: int = 5
) -> list[str]:
    """
    Get smart search suggestions based on current query and available keywords.

    Uses Gemini to rank which available keywords are most relevant to the query.

    Args:
        current_query: What user has typed so far
        available_keywords: List of keywords that have results
        max_suggestions: Maximum suggestions to return

    Returns:
        List of suggested keywords from available_keywords
    """
    if not current_query or len(current_query.strip()) < 2:
        # Return top keywords by frequency
        return available_keywords[:max_suggestions]

    if not available_keywords:
        return []

    if not llm_client.is_available():
        # Fallback: simple prefix matching
        query_lower = current_query.lower()
        matches = [k for k in available_keywords if query_lower in k.lower()]
        return matches[:max_suggestions]

    try:
        # Limit keywords sent to API
        keywords_sample = available_keywords[:50]

        prompt = f"""Given a user searching for "{current_query}" in iGaming news,
rank these available keywords by relevance:

{json.dumps(keywords_sample)}

Respond with ONLY a JSON array of the top {max_suggestions} most relevant keywords:
["keyword1", "keyword2", ...]"""

        response_text = llm_client.generate(prompt)
        if not response_text:
            response_text = ""
        response_text = response_text.strip()

        if response_text.startswith('['):
            suggestions = json.loads(response_text)
            # Filter to only keywords that exist in available_keywords
            valid = [s for s in suggestions if s in available_keywords]
            return valid[:max_suggestions]
    except Exception as e:
        print(f"LLM suggestions error: {e}")

    # Fallback: simple prefix matching
    query_lower = current_query.lower()
    matches = [k for k in available_keywords if query_lower in k.lower()]
    return matches[:max_suggestions]
