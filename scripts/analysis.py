#!/usr/bin/env python3
"""
iGaming News Gap Analysis Script - Batched Analysis Approach

Compares the tracked portfolio's internal coverage against competitors and identifies content
gaps, wins, and commercial opportunities. Powered by the provider-agnostic
``src.llm_client`` (Cerebras / Groq / OpenRouter failover) — no Google
dependency.

BATCHING: Processes ALL articles in the window by splitting into batches,
then aggregating batch summaries into a final briefing. No article loss due to caps.
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pandas as pd
from dotenv import load_dotenv

# Centralized file paths
from paths import DAILY_ANALYSIS_JSON, DAILY_BRIEFING_MD, LATEST_RUN_INFO_JSON, NEWS_HISTORY_CSV
from scripts.reader_advantages import build_reader_advantages

# Import configuration
from src import llm_client
from src.config import (
    ANALYSIS_BATCH_SIZE_ARTICLES,
    ANALYSIS_CONTENT_TRUNCATE_CHARS,
    ANALYSIS_LOOKBACK_DAYS_DEFAULT,
)
from src.differentiators import extract_all_differentiators
from src.differentiators_v2 import build_differentiators_v2
from src.topic_classifier import article_matches_topic, classify_gap_topic

load_dotenv()


# ---------------------------------------------------------------------------
# Aggregation tuning + JSON recovery helpers
# ---------------------------------------------------------------------------

# The aggregation prompt asks the LLM to deduplicate themes/gaps/wins AND
# produce a three-array commercial_radar block. With the default 4096-token
# cap the response was truncating mid-string (observed at ~16KB), losing the
# tail of commercial_radar entirely. 32K leaves ample headroom across
# Cerebras gpt-oss-120b, Groq llama-3.3-70b-versatile, and OpenRouter
# llama-3.3-70b-instruct:free (all support >=32K completion tokens).
AGGREGATION_MAX_TOKENS = 32768


def _repair_truncated_json(text: str) -> dict | None:
    """
    Best-effort recovery for a JSON object truncated mid-stream.

    Walks the string tracking the open-container stack (``{`` and ``[``)
    while ignoring braces that appear inside strings. After every
    balanced inner value at depth >=1 we record a "safe cut" index AND a
    snapshot of the still-open containers at that point. We try the
    deepest (latest) safe cut first, close each remaining open container
    with its matching token, and attempt ``json.loads``. If that still
    fails we walk back through earlier safe cuts.

    Returns the parsed dict on success, or None if recovery was not
    possible.
    """
    if not text:
        return None

    in_string = False
    escape = False
    stack: list[str] = []
    # List of (cut_index_inclusive, stack_after_close_copy). The stack
    # snapshot tells us exactly how many ``}`` / ``]`` to append.
    cut_points: list[tuple[int, list[str]]] = []

    for idx, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            stack.append('}')
        elif ch == '[':
            stack.append(']')
        elif ch == '}' or ch == ']':
            if stack and stack[-1] == ch:
                stack.pop()
                # Record a cut after every completed inner value. We do
                # NOT record cuts when the stack is now empty — that's
                # the end of the document itself, no repair needed.
                if stack:
                    cut_points.append((idx, list(stack)))

    if not cut_points:
        return None

    # Try the latest (deepest into the response) safe cut first, then
    # walk back if it doesn't parse.
    for cut_idx, open_containers in reversed(cut_points):
        candidate = text[: cut_idx + 1]
        stripped = candidate.rstrip()
        if stripped.endswith(','):
            stripped = stripped[:-1]
        # Close each remaining open container in LIFO order.
        repaired = stripped + ''.join(reversed(open_containers))
        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    return None


def _synthesize_commercial_radar_from_batches(batch_results: list[dict]) -> dict:
    """
    Build a commercial_radar payload from per-batch findings when the
    aggregation LLM call fails or truncates.

    Sponsors and speakers are drawn from ``batch_companies`` (companies the
    per-batch model already flagged as relevant). Exhibitor categories are
    seeded from ``batch_themes`` (High/Medium importance themes are a
    reasonable proxy for emerging exhibitor interest areas).
    """
    # Aggregate company mentions with frequency + first-seen context.
    company_to_meta: dict[str, dict] = {}
    for batch in batch_results:
        for company in batch.get('batch_companies', []) or []:
            name = (company.get('company_name') or '').strip()
            if not name:
                continue
            entry = company_to_meta.setdefault(
                name,
                {'count': 0, 'context': company.get('context', '') or ''},
            )
            entry['count'] += 1
            # Prefer the longest non-empty context we have seen.
            ctx = company.get('context', '') or ''
            if ctx and len(ctx) > len(entry['context']):
                entry['context'] = ctx

    # Rank by mention frequency (most-cited first), then alphabetically.
    ranked = sorted(
        company_to_meta.items(),
        key=lambda kv: (-kv[1]['count'], kv[0].lower()),
    )

    sponsors: list[dict] = []
    speakers: list[dict] = []
    for name, meta in ranked[:10]:
        rationale = meta['context'] or (
            f"Mentioned in {meta['count']} batch(es) of competitor/internal coverage."
        )
        sponsors.append({
            'company_name': name,
            'rationale': rationale,
            'engagement_angle': (
                'Auto-derived from batch-level company mentions; '
                'validate fit before outreach.'
            ),
        })
        speakers.append({
            'name_or_company': name,
            'expertise_area': rationale,
            'session_fit': 'TBD — derived from batch-level mentions.',
        })

    # Emerging exhibitor categories: pull themes (deduplicated by name) from
    # the per-batch results, keeping the highest-importance occurrence.
    importance_rank = {'High': 0, 'Medium': 1, 'Low': 2}
    theme_to_meta: dict[str, dict] = {}
    for batch in batch_results:
        for theme in batch.get('batch_themes', []) or []:
            name = (theme.get('theme') or '').strip()
            if not name:
                continue
            existing = theme_to_meta.get(name)
            new_rank = importance_rank.get(theme.get('importance', 'Medium'), 1)
            if existing is None or new_rank < importance_rank.get(existing.get('importance', 'Medium'), 1):
                theme_to_meta[name] = theme

    categories: list[dict] = []
    for name, theme in list(theme_to_meta.items())[:5]:
        categories.append({
            'category': name,
            'evidence': theme.get('narrative', '') or 'Recurring across batched coverage.',
            'opportunity': (
                'Auto-derived from batch themes; validate exhibitor demand before pitching.'
            ),
        })

    return {
        'potential_sponsors': sponsors,
        'potential_speakers': speakers,
        'emerging_exhibitor_categories': categories,
    }


def _ensure_commercial_radar(analysis: dict, batch_results: list[dict]) -> dict:
    """
    Guarantee the analysis dict carries a populated commercial_radar.

    If repair produced a partial briefing where commercial_radar is missing
    or empty, fill it in from batch_companies / batch_themes so the
    dashboard surfaces non-zero counts.
    """
    radar = analysis.get('commercial_radar') or {}
    needs_fill = (
        not radar
        or not radar.get('potential_sponsors')
        or not radar.get('potential_speakers')
        or not radar.get('emerging_exhibitor_categories')
    )
    if needs_fill:
        synthesized = _synthesize_commercial_radar_from_batches(batch_results)
        for key, value in synthesized.items():
            # Only fill empty/missing keys; keep whatever the LLM did emit.
            if not radar.get(key):
                radar[key] = value
        analysis['commercial_radar'] = radar
    return analysis


class NewsAnalyzer:
    """Analyzes iGaming news using the open-source LLM failover chain."""

    def __init__(self, api_key: str = None, analysis_lookback_days: int = None):
        """Initialize the analyzer.

        Args:
            api_key: Ignored. Retained for backward compatibility with callers
                that still pass a Gemini key. Provider credentials are now read
                from CEREBRAS_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY.
            analysis_lookback_days: Days of history to analyze (default from config).
        """
        # Force re-discovery so the script works in long-lived processes where
        # env vars changed since the module was first imported.
        if not llm_client.reinit():
            # Graceful degradation: write a marker file the dashboard can surface
            # and exit cleanly (NOT non-zero — non-zero would break the GH Action).
            reason = (
                "No LLM provider credentials found. Set at least one of: "
                "CEREBRAS_API_KEY (recommended — 1M tokens/day free, fastest), "
                "GROQ_API_KEY (14.4k req/day free, JSON-mode support), "
                "OPENROUTER_API_KEY (multi-model fallback)."
            )
            print(f"WARNING: {reason}")
            print("WARNING: All LLM providers unavailable — writing marker file and exiting cleanly.")
            try:
                marker_path = Path(DAILY_ANALYSIS_JSON).parent / "analysis_failed.json"
                marker = {
                    "reason": "all LLM providers failed",
                    "detail": reason,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                tmp_marker = marker_path.with_suffix(".json.tmp")
                with open(tmp_marker, "w", encoding="utf-8") as f:
                    json.dump(marker, f, indent=2)
                os.replace(tmp_marker, marker_path)
                print(f"WARNING: Marker written to {marker_path}")
            except Exception as marker_err:
                print(f"WARNING: Failed to write marker file: {marker_err}")
            sys.exit(0)

        self.analysis_lookback_days = analysis_lookback_days or ANALYSIS_LOOKBACK_DAYS_DEFAULT
        self.batch_size = ANALYSIS_BATCH_SIZE_ARTICLES
        self.content_truncate_chars = ANALYSIS_CONTENT_TRUNCATE_CHARS

        active = llm_client.active_providers()
        self.model_name = f"open-llm ({'/'.join(active)})"
        print(f"✓ LLM client initialized — provider chain: {' → '.join(active)}")

    def load_news_data_df(self) -> pd.DataFrame:
        """
        Load news articles from CSV history file into a DataFrame.
        Normalizes published_date to UTC datetime.

        Returns:
            DataFrame with all articles, published_date_utc column added
        """
        if not NEWS_HISTORY_CSV.exists():
            raise FileNotFoundError(
                f"File not found: {NEWS_HISTORY_CSV}\n"
                f"Please run scripts/main.py first to collect news data."
            )

        df = pd.read_csv(NEWS_HISTORY_CSV)

        # Normalize published_date to UTC-aware datetime
        df['published_date_utc'] = pd.to_datetime(df['published_date'], errors='coerce', utc=True)

        # Drop rows without valid dates
        initial_count = len(df)
        df = df.dropna(subset=['published_date_utc'])
        dropped = initial_count - len(df)
        if dropped > 0:
            print(f"  ⚠ Dropped {dropped} rows with invalid dates")

        print(f"✓ Loaded {len(df)} articles from {NEWS_HISTORY_CSV}")

        # Count by category (including affiliate)
        internal_count = len(df[df['category'] == 'internal'])
        competitor_count = len(df[df['category'] == 'competitor'])
        affiliate_count = len(df[df['category'] == 'affiliate'])
        print(f"  → Competitor articles: {competitor_count}")
        print(f"  → Affiliate articles: {affiliate_count}")
        print(f"  → Internal (Portfolio) articles: {internal_count}")

        return df

    def get_window_articles(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
        """
        Get articles within the rolling N-day window.
        NO CAPS - returns ALL articles in the window.

        Args:
            df: DataFrame with all articles (must have published_date_utc column)

        Returns:
            Tuple of (competitor_df, internal_df, stats_dict)
        """
        print(f"\n📋 Selecting Articles (Rolling {self.analysis_lookback_days}-Day Window):")
        print("  → Date-based filtering (UTC)")
        print("  → NO CAPS - all articles in window will be analyzed via batching")
        print()

        # Use UTC for consistent date comparisons
        utc_now = datetime.now(UTC)
        window_start = utc_now - timedelta(days=self.analysis_lookback_days)

        # Filter to window
        mask = (df['published_date_utc'] >= window_start) & (df['published_date_utc'] <= utc_now)
        df_window = df[mask].copy()

        # Sort by article_id for deterministic ordering
        if 'article_id' in df_window.columns:
            df_window = df_window.sort_values('article_id')
        else:
            df_window = df_window.sort_values('published_date_utc')

        # Split by category
        # Treat affiliates as external (competitor-like) for gap analysis
        competitor_df = df_window[df_window['category'].isin(['competitor', 'affiliate'])].copy()
        internal_df = df_window[df_window['category'] == 'internal'].copy()

        # Calculate stats (with affiliate breakdown)
        stats = {
            "total_articles_csv": len(df),
            "total_window_articles": len(df_window),
            "total_window_competitor": len(df_window[df_window['category'] == 'competitor']),
            "total_window_affiliate": len(df_window[df_window['category'] == 'affiliate']),
            "total_window_external": len(competitor_df),  # competitor + affiliate combined
            "total_window_internal": len(internal_df),
            "analysis_lookback_days": self.analysis_lookback_days,
            "window_start_utc": window_start.isoformat(),
            "window_end_utc": utc_now.isoformat(),
            "batched": True,
            "batch_size_articles": self.batch_size
        }

        # Log results
        print("✓ Window Selection Complete:")
        print(f"  → Total in CSV: {stats['total_articles_csv']} articles")
        print(f"  → In {self.analysis_lookback_days}-day window: {stats['total_window_articles']}")
        print(f"      • Competitors: {stats['total_window_competitor']}")
        print(f"      • Affiliates: {stats['total_window_affiliate']}")
        print(f"      • External (combined): {stats['total_window_external']}")
        print(f"      • Internal: {stats['total_window_internal']}")
        print(f"  → ALL will be analyzed (batched, {self.batch_size} per batch)")
        print()

        return competitor_df, internal_df, stats

    def batch_iter(self, df: pd.DataFrame) -> Iterator[list[dict]]:
        """
        Yield batches of articles in deterministic order.

        Args:
            df: DataFrame with articles

        Yields:
            List of article dicts (max batch_size per batch)
        """
        articles = []
        for _, row in df.iterrows():
            # Truncate content to save tokens
            content = str(row.get('content', '') or '')
            if len(content) > self.content_truncate_chars:
                content = content[:self.content_truncate_chars] + '...'

            articles.append({
                'article_id': row.get('article_id', ''),
                'source': row.get('source', 'Unknown'),
                'title': row.get('title', ''),
                'summary': row.get('summary', ''),
                'content': content,
                'published_date': str(row.get('published_date', '')),
                'category': row.get('category', ''),
                'link': row.get('link', '')
            })

        # Yield in batches
        for i in range(0, len(articles), self.batch_size):
            yield articles[i:i + self.batch_size]

    def create_batch_prompt(self, batch_articles: list[dict], batch_num: int, total_batches: int) -> str:
        """
        Create a focused analysis prompt for a single batch.
        """
        # Separate by category
        competitor_articles = [a for a in batch_articles if a['category'] == 'competitor']
        internal_articles = [a for a in batch_articles if a['category'] == 'internal']

        def simplify_article(article):
            return {
                "source": article.get("source", "Unknown"),
                "published_date": article.get("published_date", ""),
                "title": article.get("title", ""),
                "summary": article.get("summary", ""),
                "content_preview": article.get("content", "")[:300] if article.get("content") else ""
            }

        competitor_json = json.dumps([simplify_article(a) for a in competitor_articles], indent=2, ensure_ascii=False)
        internal_json = json.dumps([simplify_article(a) for a in internal_articles], indent=2, ensure_ascii=False)

        prompt = f"""You are analyzing batch {batch_num} of {total_batches} for iGaming competitive intelligence.

**BATCH CONTAINS:**
- {len(internal_articles)} Internal (Tracked Portfolio) articles
- {len(competitor_articles)} Competitor articles

**INTERNAL COVERAGE:**
```json
{internal_json}
```

**COMPETITOR COVERAGE:**
```json
{competitor_json}
```

Respond with ONLY valid JSON containing these findings from THIS BATCH:

{{
  "batch_themes": [
    {{
      "theme": "Theme name",
      "competitors_covering": ["Source1"],
      "narrative": "What's happening",
      "importance": "High|Medium|Low"
    }}
  ],
  "batch_gaps": [
    {{
      "gap_title": "Gap title",
      "description": "What competitors cover that we miss",
      "competitor_coverage": "Summary",
      "our_coverage": "Summary or 'Minimal'",
      "priority": "High|Medium|Low",
      "evidence_article_titles": ["Exact title of competitor article 1", "Exact title 2"]
    }}
  ],
  "batch_wins": [
    {{
      "topic": "Topic where the portfolio leads",
      "our_narrative": "Our strength",
      "evidence_article_titles": ["Exact title of internal article"]
    }}
  ],
  "batch_companies": [
    {{
      "company_name": "Company mentioned",
      "context": "Why relevant"
    }}
  ]
}}

IMPORTANT: For each gap and win, include the EXACT article titles from the input that support it.
Copy the titles exactly as they appear in the article data above.

Return ONLY JSON, no other text."""

        return prompt

    def create_aggregation_prompt(self, batch_results: list[dict], stats: dict) -> str:
        """
        Create prompt to aggregate batch results into final briefing.
        """
        # Collect all themes, gaps, wins, companies from batches
        all_themes = []
        all_gaps = []
        all_wins = []
        all_companies = []

        for batch in batch_results:
            all_themes.extend(batch.get('batch_themes', []))
            all_gaps.extend(batch.get('batch_gaps', []))
            all_wins.extend(batch.get('batch_wins', []))
            all_companies.extend(batch.get('batch_companies', []))

        batch_data = {
            "themes": all_themes,
            "gaps": all_gaps,
            "wins": all_wins,
            "companies": all_companies
        }

        batch_json = json.dumps(batch_data, indent=2, ensure_ascii=False)

        prompt = f"""You are the Strategic Content Director for an iGaming trade-media portfolio (iGaming Business, iGB Affiliate, GGB Magazine).
I have analyzed {stats['total_window_articles']} articles from the last {stats['analysis_lookback_days']} days
({stats['total_window_competitor']} competitor, {stats['total_window_internal']} internal).

Here are the aggregated findings from all batches:

```json
{batch_json}
```

Create a FINAL executive briefing by:
1. Deduplicating similar themes/gaps
2. Ranking by importance and frequency
3. Synthesizing into actionable insights
4. PRESERVING the evidence_article_titles from the original gaps (merge related gaps' evidence)

Respond with ONLY valid JSON in this exact schema:

{{
  "executive_summary": "2-3 paragraph executive summary for C-level executives",

  "market_pulse": [
    {{
      "theme": "Theme Name",
      "competitors_covering": ["Source1", "Source2"],
      "narrative": "2-3 sentences explaining what's happening",
      "importance": "High|Medium|Low",
      "recommended_action": "Specific action for ICE/iGB"
    }}
  ],

  "strategic_gaps": [
    {{
      "gap_title": "Clear, actionable gap title",
      "description": "What competitors cover that we miss",
      "competitor_coverage": "Summary of competitor coverage",
      "our_coverage": "Our coverage or 'Minimal'",
      "opportunity": "How ICE/iGB can fill this gap",
      "priority": "High|Medium|Low",
      "potential_impact": "Business impact",
      "evidence_article_titles": ["Article title 1", "Article title 2"]
    }}
  ],

  "portfolio_wins": [
    {{
      "topic": "Topic where we're leading",
      "our_narrative": "What makes our coverage strong",
      "competitive_gap": "What competitors are missing",
      "amplification_opportunity": "How to amplify at ICE/iGB"
    }}
  ],

  "commercial_radar": {{
    "potential_sponsors": [
      {{
        "company_name": "Company Name",
        "rationale": "Why relevant",
        "engagement_angle": "Pitch angle"
      }}
    ],
    "potential_speakers": [
      {{
        "name_or_company": "Name or Company",
        "expertise_area": "Expertise",
        "session_fit": "Which track"
      }}
    ],
    "emerging_exhibitor_categories": [
      {{
        "category": "Category name",
        "evidence": "What news suggests growth",
        "opportunity": "How to attract exhibitors"
      }}
    ]
  }}
}}

Return ONLY the JSON object. No other text."""

        return prompt

    def analyze_batch(self, prompt: str, batch_num: int) -> dict:
        """Send batch prompt to the LLM provider chain and parse the response."""
        print(f"  → Analyzing batch {batch_num}...")

        empty = {"batch_themes": [], "batch_gaps": [], "batch_wins": [], "batch_companies": []}

        try:
            response_text = llm_client.generate(prompt)
            if not response_text:
                print(f"    ⚠ No LLM response for batch {batch_num} (all providers failed)")
                return empty

            # Strip code fences if the model wrapped its JSON output.
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "", 1)
            if response_text.startswith("```"):
                response_text = response_text.replace("```", "", 1)
            if response_text.endswith("```"):
                response_text = response_text.rsplit("```", 1)[0]
            response_text = response_text.strip()

            try:
                return json.loads(response_text)
            except json.JSONDecodeError as parse_err:
                # Salvage what we can if the model truncated mid-stream.
                repaired = _repair_truncated_json(response_text)
                if repaired is not None:
                    print(
                        f"    ⚠ Batch {batch_num} JSON truncated ({parse_err}); "
                        f"recovered partial result via repair."
                    )
                    return repaired
                raise

        except json.JSONDecodeError as e:
            print(f"    ⚠ JSON parse error in batch {batch_num}: {str(e)}")
            return empty
        except Exception as e:
            print(f"    ⚠ Error in batch {batch_num}: {str(e)}")
            return empty

    def run_batched_analysis(self, competitor_df: pd.DataFrame, internal_df: pd.DataFrame, stats: dict) -> dict:
        """
        Run batched analysis on all articles and aggregate results.

        Returns:
            Final aggregated analysis dict
        """
        print("\n" + "=" * 70)
        print("BATCHED ANALYSIS")
        print("=" * 70)

        # Combine for batching (but track category)
        all_df = pd.concat([competitor_df, internal_df], ignore_index=True)

        # Sort for deterministic order
        if 'article_id' in all_df.columns:
            all_df = all_df.sort_values('article_id')

        # Calculate batch count
        total_articles = len(all_df)
        total_batches = (total_articles + self.batch_size - 1) // self.batch_size

        print(f"Processing {total_articles} articles in {total_batches} batches...")
        print()

        # Process batches
        batch_results = []
        for batch_num, batch_articles in enumerate(self.batch_iter(all_df), 1):
            prompt = self.create_batch_prompt(batch_articles, batch_num, total_batches)
            result = self.analyze_batch(prompt, batch_num)
            batch_results.append(result)

        print()
        print(f"✓ All {total_batches} batches processed")

        # Aggregate results
        print("\n" + "=" * 70)
        print("AGGREGATING BATCH RESULTS")
        print("=" * 70)

        aggregation_prompt = self.create_aggregation_prompt(batch_results, stats)

        try:
            # Aggregation prompt is large and the response JSON includes
            # commercial_radar with three arrays — empirically truncates at
            # the default 4096-token cap. Bump explicitly to 32K so the
            # response fits whole.
            response_text = llm_client.generate(
                aggregation_prompt,
                max_tokens=AGGREGATION_MAX_TOKENS,
            )
            if not response_text:
                raise json.JSONDecodeError("LLM returned no response", "", 0)

            # Clean up
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "", 1)
            if response_text.startswith("```"):
                response_text = response_text.replace("```", "", 1)
            if response_text.endswith("```"):
                response_text = response_text.rsplit("```", 1)[0]
            response_text = response_text.strip()

            try:
                final_analysis = json.loads(response_text)
                print("✓ Successfully aggregated results!")
                return final_analysis
            except json.JSONDecodeError as parse_err:
                # The aggregation response is large; if the LLM still
                # truncates we attempt to salvage what we have so the
                # dashboard surfaces real data instead of empty arrays.
                repaired = _repair_truncated_json(response_text)
                if repaired is not None:
                    print(
                        f"⚠ Aggregation JSON truncated ({parse_err}); "
                        f"recovered partial briefing via repair."
                    )
                    final_analysis = _ensure_commercial_radar(repaired, batch_results)
                    return final_analysis
                # Re-raise into the outer handler so we synthesize from batches.
                raise

        except json.JSONDecodeError as e:
            print(f"⚠ JSON parse error in aggregation: {str(e)}")
            # Return structure with meaningful defaults - NEVER say "failed"
            # Collect what we have from batches directly
            all_themes = []
            all_gaps = []
            all_wins = []
            for batch in batch_results:
                all_themes.extend(batch.get('batch_themes', []))
                all_gaps.extend(batch.get('batch_gaps', []))
                all_wins.extend(batch.get('batch_wins', []))

            commercial_radar = _synthesize_commercial_radar_from_batches(batch_results)
            print(
                f"⚠ Synthesized commercial_radar from batch_companies "
                f"(sponsors={len(commercial_radar['potential_sponsors'])}, "
                f"speakers={len(commercial_radar['potential_speakers'])}, "
                f"exhibitors={len(commercial_radar['emerging_exhibitor_categories'])})."
            )

            return {
                "executive_summary": f"Analyzed {stats['total_window_articles']} articles ({stats['total_window_competitor']} competitor, {stats['total_window_internal']} internal). See differentiators and reader advantages sections for detailed topic analysis.",
                "market_pulse": [
                    {"theme": t.get('theme', ''), "narrative": t.get('narrative', ''),
                     "competitors_covering": t.get('competitors_covering', []),
                     "importance": t.get('importance', 'Medium'),
                     "recommended_action": "Review competitor coverage for opportunities"}
                    for t in all_themes[:5]
                ],
                "strategic_gaps": [
                    {"gap_title": g.get('gap_title', ''), "description": g.get('description', ''),
                     "competitor_coverage": g.get('competitor_coverage', ''),
                     "our_coverage": g.get('our_coverage', 'Minimal'),
                     "priority": g.get('priority', 'Medium'),
                     "opportunity": "Opportunity to fill coverage gap",
                     "potential_impact": "Increase audience relevance"}
                    for g in all_gaps[:5]
                ],
                "portfolio_wins": [
                    {"topic": w.get('topic', ''), "our_narrative": w.get('our_narrative', ''),
                     "competitive_gap": "Competitors have limited coverage",
                     "amplification_opportunity": "Leverage in upcoming events"}
                    for w in all_wins[:5]
                ],
                "commercial_radar": commercial_radar,
            }
        except Exception as e:
            print(f"⚠ Error in aggregation: {str(e)}")
            commercial_radar = _synthesize_commercial_radar_from_batches(batch_results)
            return {
                "executive_summary": f"Analyzed {stats['total_window_articles']} articles. See differentiators section for detailed topic analysis.",
                "market_pulse": [],
                "strategic_gaps": [],
                "portfolio_wins": [],
                "commercial_radar": commercial_radar,
            }

    def enrich_gaps_with_evidence(self, analysis: dict, competitor_df: pd.DataFrame, internal_df: pd.DataFrame) -> dict:
        """
        Add supporting article references to strategic gaps.

        NEW LOGIC:
        1. Use article titles provided by Gemini (primary - most accurate)
        2. Fall back to keyword matching only if Gemini didn't provide titles
        3. Fall back to topic matching if no keyword matches found

        This ensures evidence articles are actually about the gap topic,
        leveraging Gemini's understanding of which articles support each gap.
        """
        from src.topic_classifier import extract_gap_keywords

        print("\n" + "=" * 70)
        print("Enriching strategic gaps with supporting articles...")
        print("=" * 70)

        strategic_gaps = analysis.get("strategic_gaps", [])
        total_added = 0

        # Build title lookup index for fast matching
        title_to_article = {}
        for _, row in competitor_df.iterrows():
            title = str(row.get('title', '')).strip()
            title_lower = title.lower()
            title_to_article[title_lower] = {
                "source": row.get("source"),
                "title": title,
                "date": str(row.get("published_date", "")),
                "link": row.get("link"),
                "category": row.get("category", "competitor"),
            }

        for gap in strategic_gaps:
            gap_title = gap.get("gap_title", "")
            gap_desc = gap.get("description", "")

            # Try Gemini-provided article titles first (MOST ACCURATE)
            gemini_titles = gap.get("evidence_article_titles", [])

            print(f"  → Gap: '{gap_title[:50]}...'")
            print(f"    Gemini provided {len(gemini_titles)} article titles")

            relevant_articles = []
            match_method = "none"

            if gemini_titles:
                # Match by title (case-insensitive, partial match)
                for gemini_title in gemini_titles[:5]:
                    gemini_title_lower = gemini_title.lower().strip()

                    # Try exact match first
                    if gemini_title_lower in title_to_article:
                        article = title_to_article[gemini_title_lower].copy()
                        article["match_type"] = "gemini_exact"
                        relevant_articles.append(article)
                        continue

                    # Try partial match (title contains or is contained)
                    for title_lower, article_data in title_to_article.items():
                        if gemini_title_lower in title_lower or title_lower in gemini_title_lower:
                            article = article_data.copy()
                            article["match_type"] = "gemini_partial"
                            if article not in relevant_articles:
                                relevant_articles.append(article)
                            break

                if relevant_articles:
                    match_method = "gemini"

            # Fall back to keyword matching if Gemini didn't provide titles
            if not relevant_articles:
                required_keywords = extract_gap_keywords(gap_title, gap_desc)
                topic = classify_gap_topic(gap_title, gap_desc)
                print(f"    Falling back to keywords: {required_keywords[:3]}...")

                keyword_matches = []
                topic_matches = []

                for _, row in competitor_df.iterrows():
                    article_text = f"{row.get('title', '')} {row.get('summary', '')}".lower()

                    keyword_found = any(kw.lower() in article_text for kw in required_keywords)

                    if keyword_found:
                        keyword_matches.append({
                            "source": row.get("source"),
                            "title": row.get("title"),
                            "date": str(row.get("published_date", "")),
                            "link": row.get("link"),
                            "category": row.get("category", "competitor"),
                            "match_type": "keyword"
                        })
                    elif article_matches_topic(row, topic):
                        topic_matches.append({
                            "source": row.get("source"),
                            "title": row.get("title"),
                            "date": str(row.get("published_date", "")),
                            "link": row.get("link"),
                            "category": row.get("category", "competitor"),
                            "match_type": "topic"
                        })

                if keyword_matches:
                    relevant_articles = keyword_matches[:5]
                    match_method = "keyword_fallback"
                elif topic_matches:
                    relevant_articles = topic_matches[:5]
                    match_method = "topic_fallback"

            if relevant_articles:
                gap["supporting_articles"] = relevant_articles[:5]
                gap["match_method"] = match_method
                total_added += len(relevant_articles[:5])
                print(f"    ✓ Found {len(relevant_articles[:5])} articles via {match_method}")
            else:
                gap["supporting_articles"] = []
                gap["match_method"] = "none"
                print("    ⚠ No matching articles found")

        print(f"\n✓ Added {total_added} supporting article references across {len(strategic_gaps)} gaps")
        return analysis

    def save_briefing(self, analysis_json: dict, stats: dict):
        """Save the analysis in both JSON and markdown formats."""
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

        print("\n" + "=" * 70)
        print("GAP ANALYSIS RESULTS")
        print("=" * 70)
        print()
        print(f"✓ Market Pulse Themes: {len(analysis_json.get('market_pulse', []))}")
        print(f"✓ Strategic Gaps Identified: {len(analysis_json.get('strategic_gaps', []))}")
        print(f"✓ Portfolio Wins: {len(analysis_json.get('portfolio_wins', []))}")

        commercial = analysis_json.get('commercial_radar', {})
        print(f"✓ Potential Sponsors: {len(commercial.get('potential_sponsors', []))}")
        print(f"✓ Potential Speakers: {len(commercial.get('potential_speakers', []))}")
        print(f"✓ Emerging Exhibitor Categories: {len(commercial.get('emerging_exhibitor_categories', []))}")
        print()

        # Show executive summary
        print("Executive Summary:")
        print("-" * 70)
        print(analysis_json.get("executive_summary", "N/A"))
        print()

        try:
            # Load run metadata
            try:
                with LATEST_RUN_INFO_JSON.open("r", encoding="utf-8") as f:
                    run_meta = json.load(f)
            except FileNotFoundError:
                run_meta = {}

            # Build metadata - CRITICAL: analyzed must equal window totals (no cap loss)
            analysis_json["run_id"] = run_meta.get("run_id")
            analysis_json["generated_at"] = run_meta.get("generated_at")
            analysis_json["analysis_period_days"] = self.analysis_lookback_days

            # Metadata object for dashboard compatibility
            # IMPORTANT: articles_analyzed EQUALS total_window_articles (no loss!)
            analysis_json["metadata"] = {
                "total_window_articles": stats['total_window_articles'],
                "total_window_competitor": stats['total_window_competitor'],
                "total_window_internal": stats['total_window_internal'],
                "articles_analyzed": stats['total_window_articles'],  # EQUALS window total - no loss!
                "analysis_date": timestamp.split()[0],
                "analysis_period_days": self.analysis_lookback_days,
                "window_start_utc": stats['window_start_utc'],
                "window_end_utc": stats['window_end_utc'],
                "batched": True,
                "batch_size_articles": self.batch_size,
                "soft_capped": False  # No more soft cap!
            }

            # Legacy fields for backward compat
            analysis_json["articles_analyzed_count"] = stats['total_window_articles']

            # Save JSON atomically (write to temp then rename)
            tmp = DAILY_ANALYSIS_JSON.with_suffix('.json.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(analysis_json, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DAILY_ANALYSIS_JSON)
            print(f"✓ JSON analysis saved to {DAILY_ANALYSIS_JSON}")

            # Convert to markdown
            markdown_content = self.json_to_markdown(analysis_json)

            briefing_content = f"""# iGaming Competitive Intelligence: Gap Analysis Briefing
**Generated:** {timestamp}
**Type:** Internal vs. Competitor Coverage Analysis
**Purpose:** Identify content gaps, wins, and commercial opportunities
**Analysis Period:** Last {self.analysis_lookback_days} days
**Articles Analyzed:** {stats['total_window_articles']} ({stats['total_window_competitor']} competitors, {stats['total_window_internal']} internal)
**Method:** Batched analysis (all articles processed, no cap loss)

---

{markdown_content}

---

*Generated by the Portfolio Competitive Intelligence System*
*LLM backend: {self.model_name}*
*Run ID: {run_meta.get('run_id', 'N/A')}*
"""

            # Save Markdown briefing atomically
            tmp_md = DAILY_BRIEFING_MD.with_suffix('.md.tmp')
            with open(tmp_md, 'w', encoding='utf-8') as f:
                f.write(briefing_content)
            os.replace(tmp_md, DAILY_BRIEFING_MD)
            print(f"✓ Markdown briefing saved to {DAILY_BRIEFING_MD}")

        except Exception as e:
            print(f"✗ Error saving briefing: {str(e)}")
            raise

    def json_to_markdown(self, analysis: dict) -> str:
        """Convert analysis JSON to formatted markdown."""
        md = []

        # Executive Summary
        md.append("## Executive Summary\n")
        md.append(analysis.get("executive_summary", "N/A"))
        md.append("\n")

        # Market Pulse
        market_pulse = analysis.get("market_pulse", [])
        if market_pulse:
            md.append("## Market Pulse: Key Themes\n")
            for i, theme in enumerate(market_pulse, 1):
                md.append(f"### {i}. {theme.get('theme', 'Unknown Theme')}\n")
                md.append(f"**Importance:** {theme.get('importance', 'N/A')}\n\n")
                md.append(f"{theme.get('narrative', 'No narrative')}\n\n")
                covering = theme.get('competitors_covering', [])
                if covering:
                    md.append(f"**Who's Covering:** {', '.join(covering)}\n\n")
                md.append(f"**Recommended Action:** {theme.get('recommended_action', 'No action specified')}\n\n")
                md.append("---\n\n")

        # Strategic Gaps
        strategic_gaps = analysis.get("strategic_gaps", [])
        if strategic_gaps:
            md.append("## Strategic Gaps: Where We're Missing Out\n")
            for i, gap in enumerate(strategic_gaps, 1):
                md.append(f"### {i}. {gap.get('gap_title', 'Unknown Gap')}\n")
                md.append(f"**Priority:** {gap.get('priority', 'N/A')}\n\n")
                md.append(f"**Description:** {gap.get('description', 'No description')}\n\n")
                md.append(f"**Competitor Coverage:** {gap.get('competitor_coverage', 'None')}\n\n")
                md.append(f"**Our Coverage:** {gap.get('our_coverage', 'Minimal')}\n\n")
                md.append(f"**Opportunity:** {gap.get('opportunity', 'No opportunity specified')}\n\n")
                md.append(f"**Potential Impact:** {gap.get('potential_impact', 'Not specified')}\n\n")

                supporting = gap.get('supporting_articles', [])
                if supporting:
                    md.append("**Supporting Articles:**\n")
                    for article in supporting:
                        md.append(f"- [{article.get('title')}] - {article.get('source')} ({article.get('date')})\n")
                    md.append("\n")
                md.append("---\n\n")

        # Portfolio Wins
        portfolio_wins = analysis.get("portfolio_wins", [])
        if portfolio_wins:
            md.append("## Portfolio Wins: Where We're Leading\n")
            for i, win in enumerate(portfolio_wins, 1):
                md.append(f"### {i}. {win.get('topic', 'Unknown Topic')}\n")
                md.append(f"**Our Narrative:** {win.get('our_narrative', 'N/A')}\n\n")
                md.append(f"**Competitive Gap:** {win.get('competitive_gap', 'N/A')}\n\n")
                md.append(f"**Amplification Opportunity:** {win.get('amplification_opportunity', 'N/A')}\n\n")
                md.append("---\n\n")

        # Commercial Radar
        commercial = analysis.get("commercial_radar", {})
        if commercial:
            md.append("## Commercial Radar: Business Opportunities\n")

            sponsors = commercial.get("potential_sponsors", [])
            if sponsors:
                md.append("### Potential Sponsors\n")
                for sponsor in sponsors:
                    md.append(f"- **{sponsor.get('company_name', 'Unknown')}**\n")
                    md.append(f"  - Rationale: {sponsor.get('rationale', 'N/A')}\n")
                    md.append(f"  - Engagement Angle: {sponsor.get('engagement_angle', 'N/A')}\n\n")

            speakers = commercial.get("potential_speakers", [])
            if speakers:
                md.append("### Potential Speakers\n")
                for speaker in speakers:
                    md.append(f"- **{speaker.get('name_or_company', 'Unknown')}**\n")
                    md.append(f"  - Expertise: {speaker.get('expertise_area', 'N/A')}\n")
                    md.append(f"  - Session Fit: {speaker.get('session_fit', 'N/A')}\n\n")

            categories = commercial.get("emerging_exhibitor_categories", [])
            if categories:
                md.append("### Emerging Exhibitor Categories\n")
                for category in categories:
                    md.append(f"- **{category.get('category', 'Unknown')}**\n")
                    md.append(f"  - Evidence: {category.get('evidence', 'N/A')}\n")
                    md.append(f"  - Opportunity: {category.get('opportunity', 'N/A')}\n\n")

        return "".join(md)

    def run_analysis(self):
        """Execute the full batched analysis pipeline."""
        print("=" * 70)
        print("iGAMING COMPETITIVE INTELLIGENCE: BATCHED GAP ANALYSIS")
        print("=" * 70)
        print("Comparing Internal (Portfolio) vs. Competitor Coverage")
        print("Method: Batched processing - ALL articles analyzed, no cap loss")
        print("=" * 70)
        print()

        # Load data as DataFrame
        df = self.load_news_data_df()

        # Get window articles (NO CAPS)
        competitor_df, internal_df, stats = self.get_window_articles(df)

        if len(competitor_df) == 0 and len(internal_df) == 0:
            print("⚠ No articles found in window. Writing empty-window marker.")
            empty_payload = {
                "empty_window": True,
                "timestamp": datetime.now(UTC).isoformat(),
                "competitor_count": 0,
                "internal_count": 0,
                "analysis_period_days": self.analysis_lookback_days,
            }
            try:
                tmp_empty = DAILY_ANALYSIS_JSON.with_suffix(".json.tmp")
                with open(tmp_empty, "w", encoding="utf-8") as f:
                    json.dump(empty_payload, f, ensure_ascii=False, indent=2)
                os.replace(tmp_empty, DAILY_ANALYSIS_JSON)
                print(f"✓ Empty-window marker saved to {DAILY_ANALYSIS_JSON}")
            except Exception as e:
                print(f"⚠ Failed to write empty-window marker: {e}")
            return

        # Run batched analysis
        analysis = self.run_batched_analysis(competitor_df, internal_df, stats)

        # Enrich with supporting articles
        analysis = self.enrich_gaps_with_evidence(analysis, competitor_df, internal_df)

        # Extract differentiators (what the portfolio does that competitors don't)
        print("\n" + "=" * 70)
        print("EXTRACTING DIFFERENTIATORS")
        print("=" * 70)
        try:
            differentiators = extract_all_differentiators(
                internal_df, competitor_df,
                analysis_days=self.analysis_lookback_days
            )
            analysis['differentiators'] = differentiators
            print(f"✓ Language differentiators: {len(differentiators.get('language_differentiators', []))}")
            print(f"✓ Company differentiators: {len(differentiators.get('company_differentiators', []))}")
            print(f"✓ Region differentiators: {len(differentiators.get('region_differentiators', []))}")
            print(f"✓ Format differentiators: {len(differentiators.get('format_differentiators', []))}")
        except Exception as e:
            print(f"⚠ Error extracting differentiators: {str(e)}")
            analysis['differentiators'] = None

        # Extract differentiators v2 (topic-level scorecard)
        print("\n" + "=" * 70)
        print("EXTRACTING DIFFERENTIATORS V2 (Topic Scorecard)")
        print("=" * 70)
        try:
            # Load full history for topic clustering
            df_full = pd.read_csv(NEWS_HISTORY_CSV)
            differentiators_v2 = build_differentiators_v2(
                df_full,
                window_days=self.analysis_lookback_days
            )
            analysis['differentiators_v2'] = differentiators_v2
            topics_count = len(differentiators_v2.get('topics', []))
            print(f"✓ Topics surfaced: {topics_count}")
            print(f"✓ Internal articles in window: {differentiators_v2.get('internal_articles', 0)}")
            print(f"✓ Competitor articles in window: {differentiators_v2.get('competitor_articles', 0)}")
            if topics_count > 0:
                top_topic = differentiators_v2['topics'][0]
                print(f"✓ Top differentiator: '{top_topic['label']}' (score: {top_topic['score']:.2f})")
        except Exception as e:
            print(f"⚠ Error extracting differentiators v2: {str(e)}")
            import traceback
            traceback.print_exc()
            analysis['differentiators_v2'] = None

        # Extract reader advantages (brand-neutral topic analysis)
        print("\n" + "=" * 70)
        print("EXTRACTING READER ADVANTAGES")
        print("=" * 70)
        try:
            # Load full history for reader advantages
            df_full = pd.read_csv(NEWS_HISTORY_CSV)
            reader_advantages = build_reader_advantages(
                df_full,
                window_days=self.analysis_lookback_days
            )
            analysis['reader_advantages'] = reader_advantages
            topics_count = len(reader_advantages.get('topics', []))
            near_count = len(reader_advantages.get('near_advantages', []))
            diagnostics = reader_advantages.get('diagnostics', {})
            print(f"✓ Reader advantage topics: {topics_count}")
            print(f"✓ Near advantages: {near_count}")
            print(f"✓ Internal articles analyzed: {diagnostics.get('total_internal_articles', 0)}")
            print(f"✓ Competitor articles analyzed: {diagnostics.get('total_competitor_articles', 0)}")
            if topics_count > 0:
                top = reader_advantages['topics'][0]
                print(f"✓ Top advantage: '{top['topic']}' (us: {top['our_count']}, them: {top['their_count']}, share: {top['our_share']*100:.0f}%)")
        except Exception as e:
            print(f"⚠ Error extracting reader advantages: {str(e)}")
            import traceback
            traceback.print_exc()
            analysis['reader_advantages'] = None

        # Save results
        self.save_briefing(analysis, stats)

        print("\n" + "=" * 70)
        print("✅ Analysis complete!")
        print(f"   📄 Structured data: {DAILY_ANALYSIS_JSON}")
        print(f"   📝 Markdown report: {DAILY_BRIEFING_MD}")
        print(f"   📊 Articles analyzed: {stats['total_window_articles']} (ALL in window)")
        print("=" * 70)


def main():
    """Main entry point."""
    try:
        analyzer = NewsAnalyzer()
        analyzer.run_analysis()
    except KeyboardInterrupt:
        print("\n\n✗ Analysis interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
