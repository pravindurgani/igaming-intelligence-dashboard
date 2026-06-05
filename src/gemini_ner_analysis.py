"""
LLM-powered analysis for Intelligence Battleground NER results.

Provides inline insights for each chart. Originally Gemini-only; now backed by
the provider-agnostic ``src.llm_client`` so the dashboard can fail over across
Cerebras / Groq / OpenRouter without code changes here.

Public function names (``init_gemini``, ``is_gemini_available`` etc.) are kept
for backward compatibility with ``app/dashboard.py`` and ``run_pipeline.py``.
"""

import json

import streamlit as st

from src import llm_client

# Import disk cache for persistent storage across deployments
from src.gemini_cache import (
    get_cache_key,
    load_from_disk_cache,
    save_to_disk_cache,
)

# Cache TTL: 24 hours (aligns with daily 8am pipeline run).
# All LLM results are cached until the next pipeline run.
CACHE_TTL_SECONDS = 86400


def _ensure_gemini_initialized() -> bool:
    """Return True if at least one LLM provider has credentials configured."""
    return llm_client.is_available()


def _generate_content(prompt: str, retries: int = 3) -> str | None:
    """
    Generate content via the configured LLM failover chain.

    ``retries`` is retained for backward compatibility but is unused — retry
    + provider failover are handled inside ``llm_client.generate``.
    """
    return llm_client.generate(prompt)


def init_gemini() -> bool:
    """Public availability check. Name kept for dashboard compatibility."""
    return llm_client.is_available()


def reinit_gemini() -> bool:
    """Force re-discovery of LLM providers (e.g. after env vars change)."""
    return llm_client.reinit()


def is_gemini_available() -> bool:
    """Check if any LLM provider is currently usable."""
    return llm_client.is_available()


def _fix_json_string(json_str: str) -> str:
    """
    Fix common JSON issues from LLM output.

    Handles:
    - Trailing commas before } or ]
    - Unescaped newlines in strings
    - Other common LLM JSON mistakes
    """
    import re

    # Remove trailing commas before } or ]
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

    # Remove any control characters that might cause issues
    json_str = ''.join(char for char in json_str if ord(char) >= 32 or char in '\n\r\t')

    return json_str


def _clean_and_parse_json(response_text: str) -> dict | None:
    """
    Clean markdown formatting and parse JSON from Gemini response.

    Args:
        response_text: Raw response from Gemini

    Returns:
        Parsed dict or None if parsing fails
    """
    import re

    if not response_text:
        return None

    # Clean markdown formatting
    text = response_text.strip()

    # Handle ```json ... ``` blocks (more robust regex approach)
    # Match ```json or ```JSON or just ```
    code_block_match = re.search(r'```(?:json|JSON)?\s*([\s\S]*?)```', text)
    if code_block_match:
        text = code_block_match.group(1).strip()
    else:
        # Fallback to original approach
        if text.startswith('```'):
            parts = text.split('```')
            if len(parts) >= 2:
                text = parts[1]
                if text.startswith('json'):
                    text = text[4:]
                elif text.startswith('JSON'):
                    text = text[4:]

        # Also handle trailing ```
        if text.endswith('```'):
            text = text.rsplit('```', 1)[0]

    text = text.strip()

    # First attempt: try parsing as-is
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Second attempt: fix common issues and retry
    try:
        fixed_text = _fix_json_string(text)
        return json.loads(fixed_text)
    except json.JSONDecodeError:
        pass

    # Third attempt: extract JSON object from surrounding text
    try:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end + 1]
            json_str = _fix_json_string(json_str)
            return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Fourth attempt: try to find balanced braces
    try:
        start = text.find('{')
        if start != -1:
            brace_count = 0
            end = start
            for i, char in enumerate(text[start:], start):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i
                        break
            if end > start:
                json_str = text[start:end + 1]
                json_str = _fix_json_string(json_str)
                return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    return None


# ============================================================
# CHART A: Geographic Insights
# ============================================================
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_geo_insight(geo_data_json: str, competitor_count: int, internal_count: int) -> str:
    """
    Generate a concise insight for Chart A (Geographic Coverage).
    Cached for 1 hour to avoid repeated API calls.

    Returns a 2-3 sentence insight string, or fallback insight if Gemini unavailable.
    """
    # Check disk cache first (for Streamlit Cloud persistence)
    cache_key = get_cache_key("get_geo_insight", geo_data_json, competitor_count, internal_count)
    cached_result = load_from_disk_cache(cache_key)
    if cached_result is not None:
        return str(cached_result)

    # Parse data for fallback
    try:
        geo_data = json.loads(geo_data_json)
        gaps = sorted(
            [g for g in geo_data if g.get('competitor_pct', 0) > g.get('internal_pct', 0)],
            key=lambda x: x.get('competitor_pct', 0) - x.get('internal_pct', 0),
            reverse=True
        )[:3]
    except Exception:
        gaps = []

    # Fallback insight from data
    def fallback_insight():
        if gaps:
            top_gap = gaps[0]
            gap_pct = top_gap.get('competitor_pct', 0) - top_gap.get('internal_pct', 0)
            return f"📊 Top opportunity: {top_gap.get('entity', 'Unknown')} - external sources lead by {gap_pct:.1f}%"
        return ""

    if not _ensure_gemini_initialized():
        return fallback_insight()

    prompt = f"""As an iGaming industry analyst, provide ONE brief insight (2-3 sentences max) about this geographic coverage data:

Top geographic gaps where external sources lead:
{json.dumps(gaps, indent=2)}

Total: {competitor_count} external articles vs {internal_count} internal articles.

Focus on: Which region is the biggest opportunity and ONE specific action. Be concise and actionable."""

    result = _generate_content(prompt)
    final_result = result if result else fallback_insight()
    # Save to disk cache for Streamlit Cloud persistence
    if result:
        save_to_disk_cache(cache_key, final_result)
    return final_result


# ============================================================
# CHART B: Company Landscape Insights
# ============================================================
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_company_insight(companies_json: str) -> str:
    """
    Generate a concise insight for Chart B (Company Mentions).

    Returns a 2-3 sentence insight string, or fallback insight if Gemini unavailable.
    """
    # Check disk cache first (for Streamlit Cloud persistence)
    cache_key = get_cache_key("get_company_insight", companies_json)
    cached_result = load_from_disk_cache(cache_key)
    if cached_result is not None:
        return str(cached_result)

    # Parse data for fallback
    try:
        companies = json.loads(companies_json)[:10]
    except Exception:
        companies = []

    # Fallback insight from data
    def fallback_insight():
        if companies:
            top_3 = [c[0] if isinstance(c, (list, tuple)) else c.get('name', str(c)) for c in companies[:3]]
            return f"📊 Most mentioned: {', '.join(top_3)}"
        return ""

    if not _ensure_gemini_initialized():
        return fallback_insight()

    prompt = f"""As an iGaming industry analyst tracking a portfolio of trade-media brands (iGaming Business, iGB Affiliate, GGB Magazine), provide ONE brief insight (2-3 sentences max) about these most-mentioned companies:

{json.dumps(companies, indent=2)}

Focus on: Who are the market movers and ONE sponsorship or speaker opportunity. Be concise and actionable."""

    result = _generate_content(prompt)
    final_result = result if result else fallback_insight()
    # Save to disk cache for Streamlit Cloud persistence
    if result:
        save_to_disk_cache(cache_key, final_result)
    return final_result


# ============================================================
# CHART C: Topic Trends Insights
# ============================================================
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_topic_insight(topic_data_json: str) -> str:
    """
    Generate a concise insight for Chart C (Strategic Topics).

    Returns a 2-3 sentence insight string, or fallback insight if Gemini unavailable.
    """
    # Check disk cache first (for Streamlit Cloud persistence)
    cache_key = get_cache_key("get_topic_insight", topic_data_json)
    cached_result = load_from_disk_cache(cache_key)
    if cached_result is not None:
        return str(cached_result)

    # Parse data for fallback
    try:
        topic_data = json.loads(topic_data_json)
        gaps = [t for t in topic_data if t.get('competitor_pct', 0) > t.get('internal_pct', 0)][:3]
        strengths = [t for t in topic_data if t.get('internal_pct', 0) > t.get('competitor_pct', 0)][:2]
    except Exception:
        gaps = []
        strengths = []

    # Fallback insight from data
    def fallback_insight():
        if gaps:
            top_gap = gaps[0]
            return f"📊 Top topic gap: {top_gap.get('entity', 'Unknown')} ({top_gap.get('competitor_pct', 0):.0f}% external vs {top_gap.get('internal_pct', 0):.0f}% internal)"
        return ""

    if not _ensure_gemini_initialized():
        return fallback_insight()

    prompt = f"""As an iGaming content strategist, provide ONE brief insight (2-3 sentences max) about this topic coverage:

Topics where external sources lead (gaps):
{json.dumps(gaps, indent=2)}

Topics where we lead (strengths):
{json.dumps(strengths, indent=2)}

Focus on: The biggest content opportunity and ONE specific article idea. Be concise and actionable."""

    result = _generate_content(prompt)
    final_result = result if result else fallback_insight()
    # Save to disk cache for Streamlit Cloud persistence
    if result:
        save_to_disk_cache(cache_key, final_result)
    return final_result


# ============================================================
# CHART D: Regional Distribution Insights
# ============================================================
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_regional_insight(competitor_regions_json: str, internal_regions_json: str) -> str:
    """
    Generate a concise insight for Chart D (Regional Breakdown pie charts).

    Returns a 2-3 sentence insight string, or fallback insight if Gemini unavailable.
    """
    # Check disk cache first (for Streamlit Cloud persistence)
    cache_key = get_cache_key("get_regional_insight", competitor_regions_json, internal_regions_json)
    cached_result = load_from_disk_cache(cache_key)
    if cached_result is not None:
        return str(cached_result)

    # Parse data for fallback
    try:
        comp_regions = json.loads(competitor_regions_json)
        int_regions = json.loads(internal_regions_json)
    except Exception:
        comp_regions = {}
        int_regions = {}

    # Fallback insight from data
    def fallback_insight():
        if comp_regions:
            top_comp = max(comp_regions.items(), key=lambda x: x[1]) if comp_regions else ('N/A', 0)
            return f"📊 External focus: {top_comp[0]} ({top_comp[1]} mentions)"
        return ""

    if not _ensure_gemini_initialized():
        return fallback_insight()

    prompt = f"""As an iGaming industry analyst, provide ONE brief insight (2-3 sentences max) comparing regional focus:

External regional distribution: {comp_regions}
Our regional distribution: {int_regions}

Focus on: Which region shows the biggest opportunity gap and ONE expansion recommendation. Be concise."""

    result = _generate_content(prompt)
    final_result = result if result else fallback_insight()
    # Save to disk cache for Streamlit Cloud persistence
    if result:
        save_to_disk_cache(cache_key, final_result)
    return final_result


# ============================================================
# Legacy functions for backward compatibility
# ============================================================
def analyze_geographic_gaps(
    geo_comparison: list[dict],
    competitor_article_count: int,
    internal_article_count: int
) -> dict:
    """
    Use Gemini to analyze geographic coverage gaps and provide strategic insights.
    Legacy function - use get_geo_insight for inline insights.
    """
    if not _ensure_gemini_initialized():
        return {"error": "Gemini not available"}

    try:
        gaps = [
            g for g in geo_comparison
            if g['competitor_pct'] > g['internal_pct']
        ]

        prompt = f"""You are an iGaming industry analyst for the tracked portfolio (iGaming Business, iGB Affiliate, GGB Magazine).

Analyze this geographic coverage data:
- Total articles: {competitor_article_count} external vs {internal_article_count} internal
- Geographic gaps (where external sources cover more):
{json.dumps(gaps[:10], indent=2)}

Provide a JSON response with:
{{
  "key_insight": "One-sentence summary of the most important geographic gap",
  "priority_regions": ["Top 3 regions to focus on"],
  "market_context": "Brief context on why these regions matter for iGaming",
  "recommended_actions": ["2-3 specific content recommendations"],
  "emerging_markets": ["Any emerging markets external sources are tracking"]
}}

Return ONLY valid JSON, no explanation."""

        response_text = _generate_content(prompt)
        if not response_text:
            return {"error": "Generation failed"}

        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]

        return json.loads(response_text.strip())
    except Exception as e:
        return {"error": str(e)}


def analyze_company_landscape(
    top_companies: list[dict],
    analysis_json: dict | None = None
) -> dict:
    """
    Use Gemini to analyze company mentions and identify strategic insights.
    Legacy function - use get_company_insight for inline insights.
    """
    if not _ensure_gemini_initialized():
        return {"error": "Gemini not available"}

    try:
        sponsors = []
        if analysis_json and 'commercial_radar' in analysis_json:
            sponsors = [
                s.get('company_name', '')
                for s in analysis_json['commercial_radar'].get('potential_sponsors', [])
            ]

        prompt = f"""You are an iGaming industry analyst for the tracked portfolio (iGaming Business, iGB Affiliate, GGB Magazine).

Analyze these most-mentioned companies from news coverage:
{json.dumps(top_companies[:15], indent=2)}

AI-identified potential sponsors: {sponsors[:5] if sponsors else 'Not available'}

Provide a JSON response with:
{{
  "market_movers": ["Top 3 companies making the most news"],
  "rising_players": ["2-3 companies showing increased activity"],
  "partnership_patterns": "Brief insight on partnership/M&A trends observed",
  "sponsor_opportunities": ["2-3 companies worth approaching for sponsorship"],
  "speaker_candidates": ["2-3 executives/companies for conference speaking"],
  "watch_list": ["Companies to monitor for future developments"]
}}

Return ONLY valid JSON, no explanation."""

        response_text = _generate_content(prompt)
        if not response_text:
            return {"error": "Generation failed"}

        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]

        return json.loads(response_text.strip())
    except Exception as e:
        return {"error": str(e)}


def analyze_topic_trends(
    topic_comparison: list[dict],
    strategic_gaps: list[dict] | None = None
) -> dict:
    """
    Use Gemini to analyze topic trends and identify content opportunities.
    Legacy function - use get_topic_insight for inline insights.
    """
    if not _ensure_gemini_initialized():
        return {"error": "Gemini not available"}

    try:
        gaps = [
            g for g in topic_comparison
            if g['competitor_pct'] > g['internal_pct']
        ]

        strengths = [
            g for g in topic_comparison
            if g['internal_pct'] > g['competitor_pct']
        ]

        gap_titles = []
        if strategic_gaps:
            gap_titles = [g.get('gap_title', '') for g in strategic_gaps[:5]]

        prompt = f"""You are an iGaming industry content strategist for the tracked portfolio (iGaming Business, iGB Affiliate, GGB Magazine).

Analyze this topic coverage data:

Topics where external sources lead (gaps):
{json.dumps(gaps[:8], indent=2)}

Topics where we lead (strengths):
{json.dumps(strengths[:5], indent=2)}

AI-identified strategic gaps: {gap_titles if gap_titles else 'Not available'}

Provide a JSON response with:
{{
  "trending_topics": ["Top 3 hot topics in the industry right now"],
  "content_priorities": ["Top 3 topics we should cover more"],
  "double_down_areas": ["2 strengths we should amplify"],
  "emerging_themes": ["New themes external sources are starting to cover"],
  "conference_tracks": ["Suggested conference session themes based on trends"],
  "content_calendar_ideas": ["3 specific article/content ideas for next month"]
}}

Return ONLY valid JSON, no explanation."""

        response_text = _generate_content(prompt)
        if not response_text:
            return {"error": "Generation failed"}

        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]

        return json.loads(response_text.strip())
    except Exception as e:
        return {"error": str(e)}


def generate_battleground_summary(
    geo_json: str,
    company_json: str,
    competitor_count: int,
    internal_count: int,
) -> str:
    """Generate an executive summary of the competitive battleground.

    Args accept pre-serialised JSON so the caller controls the data shape
    sent to the model. Counts contextualize the sample volume.
    """
    if not _ensure_gemini_initialized():
        return "LLM not available for summary generation."

    prompt = f"""Create a brief executive summary (3-4 sentences) synthesizing this iGaming competitive intelligence snapshot:

Top regions by article volume: {geo_json}
Top companies by mention count: {company_json}
Article sample: {competitor_count} competitor / {internal_count} internal over the last 30 days.

Focus on actionable takeaways for a media/events company. Be concise and specific."""

    result = _generate_content(prompt)
    return result if result else "Summary generation failed."


# ============================================================
# AFFILIATE COMPARISON INSIGHTS
# ============================================================
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_affiliate_comparison_insight(
    comparison_json: str,
    affiliate_count: int,
    non_affiliate_count: int
) -> str:
    """
    Generate insight comparing affiliate vs non-affiliate topic coverage.

    Args:
        comparison_json: JSON string of topic comparison data
        affiliate_count: Number of affiliate articles
        non_affiliate_count: Number of non-affiliate articles

    Returns:
        A 2-3 sentence insight string, or empty string if Gemini unavailable.
    """
    # Check disk cache first (for Streamlit Cloud persistence)
    cache_key = get_cache_key("get_affiliate_comparison_insight", comparison_json, affiliate_count, non_affiliate_count)
    cached_result = load_from_disk_cache(cache_key)
    if cached_result is not None:
        return str(cached_result)

    # Parse data for fallback
    try:
        comparison_data = json.loads(comparison_json)
        # Find topics where affiliate leads
        affiliate_focus = sorted(
            [c for c in comparison_data if c.get('diff', 0) > 0],
            key=lambda x: x.get('diff', 0),
            reverse=True
        )[:3]
    except Exception:
        affiliate_focus = []

    # Fallback insight from data
    def fallback_insight():
        if affiliate_focus:
            top = affiliate_focus[0]
            return f"📊 Affiliate sources focus more on: {top.get('topic', 'Unknown')} ({top.get('affiliate_pct', 0):.0f}% vs {top.get('non_affiliate_pct', 0):.0f}%)"
        return ""

    if not _ensure_gemini_initialized():
        return fallback_insight()

    prompt = f"""As an iGaming industry analyst, compare affiliate-focused sources vs general news sources:

Topic Coverage Comparison (affiliate_pct vs non_affiliate_pct):
{comparison_json}

Article Counts: {affiliate_count} affiliate, {non_affiliate_count} non-affiliate

Provide ONE brief insight (2-3 sentences) about:
1. What topics do affiliate sources focus on MORE than general news?
2. What does this suggest about affiliate industry priorities?

Be concise and actionable."""

    result = _generate_content(prompt)
    final_result = result if result else fallback_insight()
    # Save to disk cache for Streamlit Cloud persistence
    if result:
        save_to_disk_cache(cache_key, final_result)
    return final_result


# ============================================================
# COMMERCIAL RADAR ENHANCEMENT
# ============================================================
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_commercial_enhancement(
    existing_commercial: dict,
    recent_articles: list[dict]
) -> dict:
    """
    Enhance Commercial Radar with fresh Gemini analysis based on recent articles.

    Args:
        existing_commercial: Current commercial_radar data from analysis.json
        recent_articles: List of recent article dicts for context

    Returns:
        Enhanced commercial insights
    """
    # Check disk cache first (for Streamlit Cloud persistence)
    cache_key = get_cache_key(
        "get_commercial_enhancement",
        json.dumps(existing_commercial, sort_keys=True, default=str),
        json.dumps([a.get('title', '') for a in recent_articles[:10]], sort_keys=True)
    )
    cached_result = load_from_disk_cache(cache_key)
    if cached_result is not None and isinstance(cached_result, dict):
        return cached_result

    if not _ensure_gemini_initialized():
        return {"error": "Gemini not available"}

    try:
        # Prepare article summaries for context
        article_context = "\n".join([
            f"- {a.get('title', '')[:80]} ({a.get('source', '')})"
            for a in recent_articles[:30]
        ])

        existing_sponsors = [s.get('company_name', '') for s in existing_commercial.get('potential_sponsors', [])]
        existing_speakers = [s.get('name_or_company', '') for s in existing_commercial.get('potential_speakers', [])]

        prompt = f"""As an iGaming industry commercial analyst for the tracked iGaming trade-media portfolio,
analyze these recent news headlines and enhance our commercial intelligence:

Recent Headlines:
{article_context}

Currently identified sponsors: {existing_sponsors}
Currently identified speakers: {existing_speakers}

Provide additional commercial insights as JSON:
{{
  "additional_sponsor_opportunities": [
    {{
      "company": "Company name",
      "news_trigger": "What recent news makes them relevant",
      "pitch_angle": "How to approach them",
      "urgency": "High/Medium/Low"
    }}
  ],
  "speaker_recommendations": [
    {{
      "person_or_company": "Name",
      "topic_expertise": "Area of expertise",
      "news_relevance": "Why they're newsworthy now",
      "session_type": "Keynote/Panel/Workshop"
    }}
  ],
  "partnership_alerts": [
    {{
      "companies_involved": ["Company A", "Company B"],
      "partnership_type": "M&A/Investment/Product",
      "opportunity": "How the portfolio can engage"
    }}
  ],
  "timing_recommendations": "Any time-sensitive opportunities"
}}

Focus on companies NOT already in our sponsor/speaker lists.
Return ONLY valid JSON."""

        response_text = _generate_content(prompt)
        if not response_text:
            return {"error": "Generation failed"}

        # Clean markdown formatting
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
        if response_text.endswith('```'):
            response_text = response_text.rsplit('```', 1)[0]

        result = json.loads(response_text.strip())
        # Save to disk cache for Streamlit Cloud persistence
        save_to_disk_cache(cache_key, result)
        return result
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# SEO INTELLIGENCE
# ============================================================
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_ai_seo_recommendations(seo_insights: dict, recent_articles: list[dict]) -> dict:
    """
    Generate AI-powered SEO recommendations using Gemini.

    Args:
        seo_insights: Basic SEO insights dict
        recent_articles: Recent articles for context

    Returns:
        Dict with AI-generated SEO recommendations
    """
    # Check disk cache first (for Streamlit Cloud persistence)
    cache_key = get_cache_key(
        "get_ai_seo_recommendations",
        json.dumps(seo_insights, sort_keys=True, default=str),
        json.dumps([a.get('title', '') for a in recent_articles[:5]], sort_keys=True)
    )
    cached_result = load_from_disk_cache(cache_key)
    if cached_result is not None and isinstance(cached_result, dict):
        return cached_result

    if not _ensure_gemini_initialized():
        return {"error": "Gemini not available"}

    try:
        # Prepare context
        gaps = [g.get('topic', '') for g in seo_insights.get('content_gaps', [])]
        strengths = [s.get('topic', '') for s in seo_insights.get('strengths_to_amplify', [])]

        article_titles = [a.get('title', '')[:60] for a in recent_articles[:20]]

        prompt = f"""As an SEO strategist for an iGaming trade-media portfolio (iGaming Business, iGB Affiliate, GGB Magazine),
provide actionable SEO recommendations based on this competitive intelligence:

Content Gaps (competitors cover, we don't):
{json.dumps(gaps, indent=2)}

Our Strengths (we cover better than competitors):
{json.dumps(strengths, indent=2)}

Recent headline themes:
{json.dumps(article_titles[:10], indent=2)}

Provide SEO strategy as JSON:
{{
  "quick_wins": [
    "3-5 SEO improvements that can be done this week"
  ],
  "content_calendar": [
    {{
      "topic": "Topic to cover",
      "timing": "When to publish (e.g., 'Next week', 'Before ICE')",
      "format": "Article/Guide/Infographic/Video",
      "target_keywords": ["keyword1", "keyword2"]
    }}
  ],
  "competitor_keywords_to_target": [
    "5-10 specific keywords competitors rank for that we should target"
  ],
  "internal_linking_opportunities": [
    {{
      "from_topic": "Source topic area",
      "to_topic": "Destination topic to link to",
      "rationale": "Why this link helps SEO"
    }}
  ],
  "technical_seo_notes": [
    "Any technical SEO observations based on content patterns"
  ],
  "long_term_strategy": "One paragraph on 3-6 month SEO focus"
}}

Focus on actionable, specific recommendations for iGaming B2B content.
Return ONLY valid JSON."""

        # Helper function for data-derived fallback
        def _build_seo_fallback():
            """Build fallback SEO recommendations from input data."""
            return {
                "quick_wins": [
                    f"Create content on: {gaps[0]}" if gaps else "Audit existing content for keyword optimization",
                    f"Strengthen coverage of: {strengths[0]}" if strengths else "Add internal links between related articles",
                    "Update meta descriptions on top-performing articles"
                ],
                "content_calendar": [
                    {
                        "topic": gaps[0] if gaps else "Industry trend analysis",
                        "timing": "This week",
                        "format": "Article",
                        "target_keywords": gaps[:2] if gaps else ["iGaming", "industry news"]
                    }
                ],
                "competitor_keywords_to_target": gaps[:5] if gaps else [],
                "internal_linking_opportunities": [],
                "technical_seo_notes": ["Review site structure for content gaps"],
                "long_term_strategy": "Focus on building topical authority in underserved areas. (Fallback - AI analysis unavailable)",
                "is_fallback": True
            }

        response_text = _generate_content(prompt)
        if not response_text:
            return _build_seo_fallback()

        # Use robust JSON parsing
        result = _clean_and_parse_json(response_text)
        if result is None:
            print(f"JSON parse failed for SEO recommendations. Response preview: {response_text[:200]}")
            return _build_seo_fallback()

        # Save to disk cache for Streamlit Cloud persistence
        save_to_disk_cache(cache_key, result)
        return result
    except Exception as e:
        error_msg = str(e)
        if "quota" in error_msg.lower():
            return {"error": "Gemini API quota exceeded. Please try again later."}
        elif "rate" in error_msg.lower():
            return {"error": "Rate limited. Please wait a moment and refresh."}
        else:
            return {"error": f"AI analysis failed: {error_msg[:50]}"}


# ============================================================
# EXHIBITOR PROSPECTING
# ============================================================
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_exhibitor_prospects(
    recent_articles_json: str,
    emerging_categories: list[dict],
    existing_sponsors: list[str]
) -> dict:
    """
    Generate AI-powered exhibitor prospecting recommendations.
    Identifies companies that would benefit from exhibition presence at ICE/iGB.

    Args:
        recent_articles_json: JSON string of recent articles
        emerging_categories: List of emerging exhibitor category dicts
        existing_sponsors: List of company names already in sponsor pipeline

    Returns:
        Dict with exhibitor prospects and category gaps
    """
    # Check disk cache first (for Streamlit Cloud persistence)
    cache_key = get_cache_key(
        "get_exhibitor_prospects",
        recent_articles_json[:500],  # Use subset for key stability
        json.dumps(emerging_categories, sort_keys=True, default=str),
        json.dumps(existing_sponsors, sort_keys=True)
    )
    cached_result = load_from_disk_cache(cache_key)
    if cached_result is not None and isinstance(cached_result, dict):
        return cached_result

    if not _ensure_gemini_initialized():
        return {"error": "Gemini not available"}

    try:
        recent_articles = json.loads(recent_articles_json)

        categories_list = [c.get('category', '') for c in emerging_categories]

        prompt = f"""You are an exhibition sales strategist for an iGaming trade-media portfolio (iGaming Business, iGB Affiliate, GGB Magazine).
Your goal is to identify companies that should exhibit at the next ICE/iGB event.

CONTEXT:
Recent industry news headlines:
{chr(10).join([f"- {a.get('title', '')[:100]}" for a in recent_articles[:30]])}

Emerging exhibitor categories we're targeting:
{chr(10).join([f"- {c}" for c in categories_list]) if categories_list else "- General iGaming/Sports Betting"}

Companies already in our sponsor pipeline: {existing_sponsors}

TASK:
Identify 5-8 companies that should be prospected as potential exhibitors.
Focus on companies that:
1. Are expanding or launching new products (newsworthy)
2. Fit our emerging exhibitor categories
3. Would benefit from B2B networking at ICE/iGB
4. Are NOT already in our sponsor pipeline

Return JSON:
{{
  "exhibitor_prospects": [
    {{
      "company": "Company Name",
      "category_fit": "Which exhibition category they fit",
      "news_trigger": "Recent news that makes them a good prospect",
      "booth_pitch": "Suggested booth package and value proposition",
      "contact_urgency": "High/Medium/Low",
      "estimated_booth_size": "Small (10sqm) / Medium (20sqm) / Large (50sqm+)"
    }}
  ],
  "category_gaps": [
    {{
      "category": "Exhibition category with few exhibitors",
      "opportunity": "Why this gap matters",
      "target_company_types": ["Type 1", "Type 2"]
    }}
  ],
  "timing_note": "Best time to reach out and why"
}}

Return ONLY valid JSON."""

        # Helper function for data-derived fallback
        def _build_exhibitor_fallback():
            """Build fallback exhibitor prospects from input data."""
            # Extract company mentions from articles
            company_mentions = []
            for article in recent_articles[:20]:
                title = article.get('title', '')
                # Look for company-like capitalized words
                words = title.split()
                for word in words:
                    if word and word[0].isupper() and len(word) > 3:
                        if word not in existing_sponsors and word not in ['The', 'New', 'How', 'Why', 'What', 'Top']:
                            company_mentions.append(word)

            unique_mentions = list(dict.fromkeys(company_mentions))[:5]

            return {
                "exhibitor_prospects": [
                    {
                        "company": name,
                        "category_fit": categories_list[0] if categories_list else "General iGaming",
                        "news_trigger": "Mentioned in recent industry news",
                        "booth_pitch": "Standard exhibition package",
                        "contact_urgency": "Medium",
                        "estimated_booth_size": "Medium (20sqm)"
                    }
                    for name in unique_mentions
                ],
                "category_gaps": [
                    {
                        "category": cat,
                        "opportunity": "Emerging category with growth potential",
                        "target_company_types": ["Startups", "Scale-ups"]
                    }
                    for cat in categories_list[:2]
                ] if categories_list else [],
                "timing_note": "Reach out 6-8 weeks before event deadlines. (Fallback - AI analysis unavailable)",
                "is_fallback": True
            }

        response_text = _generate_content(prompt)
        if not response_text:
            return _build_exhibitor_fallback()

        # Use robust JSON parsing
        result = _clean_and_parse_json(response_text)
        if result is None:
            print(f"JSON parse failed for exhibitor prospects. Response preview: {response_text[:200]}")
            return _build_exhibitor_fallback()

        # Save to disk cache for Streamlit Cloud persistence
        save_to_disk_cache(cache_key, result)
        return result
    except Exception as e:
        error_msg = str(e)
        if "quota" in error_msg.lower():
            return {"error": "Gemini API quota exceeded. Please try again later."}
        elif "rate" in error_msg.lower():
            return {"error": "Rate limited. Please wait a moment and refresh."}
        else:
            return {"error": f"AI analysis failed: {error_msg[:50]}"}


# ============================================================
# AI KEYWORD RECOMMENDATIONS (get_ai_keyword_recommendations)
# ============================================================
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_ai_keyword_recommendations(
    current_keywords_json: str,
    content_gaps_json: str,
    competitor_articles_json: str
) -> dict:
    """
    Generate AI-powered keyword recommendations for SEO.
    Suggests high-value keywords to target for Google ranking.

    Args:
        current_keywords_json: JSON string of current keyword analysis
        content_gaps_json: JSON string of content gaps
        competitor_articles_json: JSON string of competitor articles

    Returns:
        Dict with priority keywords and strategy recommendations
    """
    # Check disk cache first (for Streamlit Cloud persistence)
    cache_key = get_cache_key(
        "get_ai_keyword_recommendations",
        current_keywords_json[:500],  # Use subset for key stability
        content_gaps_json[:500],
        competitor_articles_json[:500]
    )
    cached_result = load_from_disk_cache(cache_key)
    if cached_result is not None and isinstance(cached_result, dict):
        return cached_result

    if not _ensure_gemini_initialized():
        return {"error": "Gemini not available"}

    try:
        current_keywords = json.loads(current_keywords_json)
        content_gaps = json.loads(content_gaps_json)
        competitor_articles = json.loads(competitor_articles_json)

        # Extract competitor-focused keywords
        comp_keywords = [k['keyword'] for k in current_keywords if k.get('trend') == 'competitor_focus'][:10]
        our_keywords = [k['keyword'] for k in current_keywords if k.get('trend') == 'our_strength'][:5]
        gap_topics = [g.get('topic', '')[:50] for g in content_gaps[:5]]

        # Get sample competitor headlines
        comp_headlines = [a.get('title', '')[:80] for a in competitor_articles[:20]]

        prompt = f"""You are an SEO strategist for an iGaming trade-media portfolio (iGaming Business, iGB Affiliate, GGB Magazine).
Your goal is to identify high-value keywords that will help us rank higher on Google.

CURRENT STATE:
Keywords where competitors outrank us: {comp_keywords}
Keywords where we lead: {our_keywords}
Content gaps to fill: {gap_topics}

Competitor headlines (for context):
{chr(10).join([f"- {h}" for h in comp_headlines[:15]])}

TASK:
Recommend 8-12 high-value keywords/phrases we should target to improve Google ranking.
Focus on:
1. Long-tail keywords with buying intent
2. Keywords competitors rank for but we don't
3. Emerging topics with growing search volume
4. Keywords that align with our content gaps

Return JSON:
{{
  "priority_keywords": [
    {{
      "keyword": "exact keyword or phrase",
      "search_intent": "informational/transactional/navigational",
      "estimated_difficulty": "Low/Medium/High",
      "content_type": "Article/Guide/News/Analysis",
      "rationale": "Why this keyword matters"
    }}
  ],
  "quick_win_keywords": [
    "Low competition keywords we could rank for quickly"
  ],
  "avoid_keywords": [
    "Keywords that are too competitive or off-brand"
  ],
  "content_strategy_note": "Overall keyword strategy recommendation"
}}

Return ONLY valid JSON."""

        # Helper function for data-derived fallback
        def _build_fallback():
            """Build fallback recommendations from input data when Gemini fails."""
            fallback_keywords = []
            # Use competitor-focus keywords as priority
            for kw in comp_keywords[:5]:
                fallback_keywords.append({
                    "keyword": kw,
                    "search_intent": "informational",
                    "estimated_difficulty": "Medium",
                    "content_type": "Article",
                    "rationale": "Competitor focus - opportunity to increase coverage"
                })
            # Add gap topics
            for topic in gap_topics[:3]:
                if topic:
                    fallback_keywords.append({
                        "keyword": topic,
                        "search_intent": "informational",
                        "estimated_difficulty": "Medium",
                        "content_type": "Guide",
                        "rationale": "Content gap identified in analysis"
                    })
            return {
                "priority_keywords": fallback_keywords,
                "quick_win_keywords": our_keywords[:3],
                "avoid_keywords": [],
                "content_strategy_note": "Focus on competitor gaps and emerging topics. (Fallback - AI analysis unavailable)",
                "is_fallback": True
            }

        response_text = _generate_content(prompt)
        if not response_text:
            # Return fallback with data-derived recommendations
            return _build_fallback()

        # Use robust JSON parsing
        result = _clean_and_parse_json(response_text)
        if result is None:
            # Log the issue for debugging but return fallback
            print(f"JSON parse failed for keyword recommendations. Response preview: {response_text[:200]}")
            return _build_fallback()

        # Save to disk cache for Streamlit Cloud persistence
        save_to_disk_cache(cache_key, result)
        return result
    except Exception as e:
        error_msg = str(e)
        if "quota" in error_msg.lower():
            return {"error": "Gemini API quota exceeded. Please try again later."}
        elif "rate" in error_msg.lower():
            return {"error": "Rate limited. Please wait a moment and refresh."}
        else:
            return {"error": f"AI analysis failed: {error_msg[:50]}"}


# ============================================================================
# READER ADVANTAGES - GEMINI AI ENHANCEMENT
# ============================================================================

@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def enhance_reader_advantages_with_gemini(
    pattern_data_json: str,
    internal_articles_json: str,
    competitor_articles_json: str,
    window_days: int = 90
) -> dict:
    """
    Enhance Python-detected reader advantages with Gemini AI.

    This creates compelling, reader-focused copy while maintaining accuracy.
    The AI validates patterns and may identify additional advantages.

    Args:
        pattern_data_json: JSON string from detect_all_advantages()
        internal_articles_json: Sample of internal articles (JSON string)
        competitor_articles_json: Sample of competitor articles (JSON string)
        window_days: Analysis window (fixed at 90 days)

    Returns:
        {
            "enhanced_cards": [...],      # AI-polished advantage cards
            "ai_discovered": [...],       # Additional advantages found by AI
            "strategic_summary": str,     # One-line positioning statement
            "overall_confidence": float,  # 0.0-1.0
            "fallback_used": bool        # True if Gemini failed
        }
    """
    # Check disk cache first (for Streamlit Cloud persistence)
    cache_key = get_cache_key(
        "enhance_reader_advantages_with_gemini",
        pattern_data_json[:500],  # Use subset for key stability
        window_days
    )
    cached_result = load_from_disk_cache(cache_key)
    if cached_result is not None and isinstance(cached_result, dict):
        return cached_result

    # Parse JSON inputs
    try:
        pattern_data = json.loads(pattern_data_json)
        internal_articles = json.loads(internal_articles_json)
        competitor_articles = json.loads(competitor_articles_json)
    except json.JSONDecodeError as e:
        return {
            "enhanced_cards": [],
            "ai_discovered": [],
            "strategic_summary": "",
            "overall_confidence": 0.0,
            "fallback_used": True,
            "error": f"JSON parse error: {e}"
        }

    # Extract data
    python_cards = pattern_data.get('cards', [])
    diagnostics = pattern_data.get('diagnostics', {})
    internal_count = diagnostics.get('internal_articles', 0)
    competitor_count = diagnostics.get('competitor_articles', 0)

    # If no cards detected, return early
    if not python_cards:
        return {
            "enhanced_cards": [],
            "ai_discovered": [],
            "strategic_summary": "",
            "overall_confidence": 0.0,
            "fallback_used": True,
            "reason": "No patterns detected by Python analysis"
        }

    # Build the prompt
    prompt = f"""You are an expert editorial strategist analyzing competitive advantages for the tracked publications (iGaming Business, iGB Affiliate, GGB Magazine).

TASK: Transform detected coverage patterns into compelling "Why Readers Choose Us" cards.

DATA CONTEXT (Last {window_days} days):
- Internal articles analyzed: {internal_count}
- Competitor articles analyzed: {competitor_count}
- This is 1 publisher (the tracked portfolio) vs multiple competitor sources

PYTHON-DETECTED PATTERNS:
{json.dumps(python_cards[:5], indent=2)}

SAMPLE INTERNAL ARTICLES (titles):
{json.dumps([a.get('title', '')[:80] for a in internal_articles[:12]], indent=2)}

SAMPLE COMPETITOR ARTICLES (titles):
{json.dumps([a.get('title', '')[:80] for a in competitor_articles[:12]], indent=2)}

YOUR TASK:

1. VALIDATE each Python-detected pattern:
   - Does it represent REAL reader value?
   - Is the evidence strong (concentration ratio > 1.3)?
   - Mark confidence as "high", "medium", or "low"

2. REWRITE each valid advantage with:
   - headline: Compelling, reader-focused (8-12 words)
   - what_readers_get: Specific benefit in 1 sentence
   - why_it_matters: Industry context in 1 sentence
   - evidence_summary: The concentration metric in plain English

3. DISCOVER additional advantages by analyzing article titles:
   - Look for patterns Python might have missed
   - Only include if you see 2+ supporting articles
   - Mark these as "ai_discovered"

4. RANK all advantages by actual reader value (not just counts)

5. Write a strategic_summary: One sentence describing editorial positioning

CRITICAL RULES:
- Minimum evidence: 2 internal articles required
- Concentration matters more than raw counts
- Focus on READER benefit, not publisher bragging
- Be specific - avoid generic phrases like "comprehensive coverage"
- Confidence levels: high (ratio > 2), medium (1.5-2), low (1.3-1.5)

OUTPUT FORMAT (JSON only, no markdown):
{{
  "enhanced_cards": [
    {{
      "rank": 1,
      "headline": "Reader-focused headline here",
      "what_readers_get": "Specific benefit statement",
      "why_it_matters": "Industry context statement",
      "evidence_summary": "X% of our content vs Y% of competitors",
      "confidence": "high|medium|low",
      "original_type": "explainer|franchise|geography|event|followthrough",
      "internal_count": 0,
      "concentration_ratio": 0.0
    }}
  ],
  "ai_discovered": [
    {{
      "headline": "Newly identified advantage",
      "what_readers_get": "Benefit statement",
      "why_it_matters": "Context statement",
      "evidence": "Brief description of supporting articles",
      "confidence": "high|medium|low"
    }}
  ],
  "strategic_summary": "One sentence editorial positioning",
  "overall_confidence": 0.85
}}

Return ONLY valid JSON, no explanation or markdown."""

    # Call Gemini
    response_text = _generate_content(prompt)

    if not response_text:
        # Fallback to Python cards
        return {
            "enhanced_cards": python_cards,
            "ai_discovered": [],
            "strategic_summary": "",
            "overall_confidence": 0.5,
            "fallback_used": True
        }

    # Parse response with robust JSON handling
    result = _clean_and_parse_json(response_text)

    if result is None:
        return {
            "enhanced_cards": python_cards,
            "ai_discovered": [],
            "strategic_summary": "",
            "overall_confidence": 0.5,
            "fallback_used": True,
            "error": "Failed to parse AI response"
        }

    result['fallback_used'] = False
    # Save to disk cache for Streamlit Cloud persistence
    save_to_disk_cache(cache_key, result)
    return result
