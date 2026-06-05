#!/usr/bin/env python3
"""
Master Pipeline Runner for Portfolio Competitive Intelligence

Runs the complete end-to-end pipeline:
1. News Aggregation (scripts/main.py)
2. AI Gap Analysis (scripts/analysis.py) - Uses Gemini
3. Dashboard Launch (app/dashboard.py) - Optional

Usage:
    python run_pipeline.py                    # Full pipeline + launch dashboard
    python run_pipeline.py --no-dashboard     # Full pipeline without dashboard
    python run_pipeline.py --skip-scrape      # Skip scraping, use existing data
    python run_pipeline.py --headless         # Run without output (for cron jobs)
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in path
from paths import DAILY_ANALYSIS_JSON, LATEST_NEWS_JSON, ROOT


def update_version_file():
    """
    Update the version file to trigger Streamlit Cloud redeployment.

    Streamlit Cloud monitors Python files for changes. By updating this
    file after each pipeline run, we force a redeployment which causes
    the app to reload fresh data.
    """
    version_file = ROOT / "src" / "_version.py"

    # Read current version if exists
    current_version = 1
    if version_file.exists():
        try:
            content = version_file.read_text()
            for line in content.split('\n'):
                if line.startswith('DATA_VERSION'):
                    current_version = int(line.split('=')[1].strip()) + 1
                    break
        except (ValueError, IndexError):
            pass

    timestamp = datetime.now(timezone.utc).isoformat()

    content = f'''"""
Auto-generated version file for cache invalidation.
Updated by the daily pipeline to trigger Streamlit Cloud redeployment.
DO NOT EDIT MANUALLY - This file is generated automatically.
"""

# Last pipeline run timestamp
PIPELINE_TIMESTAMP = "{timestamp}"

# Data version (incremented on each run)
DATA_VERSION = {current_version}
'''

    version_file.write_text(content)
    print(f"  -> Updated _version.py (v{current_version})")
    return True


def run_scraper():
    """Run the news scraping pipeline (scripts/main.py)."""
    print("\n" + "=" * 70)
    print("STEP 1/3: NEWS AGGREGATION")
    print("=" * 70)

    # Import and run main.py's main function
    sys.path.insert(0, str(ROOT / "scripts"))
    from scripts.main import main as scrape_main

    try:
        scrape_main()

        # Verify output file was created
        if not LATEST_NEWS_JSON.exists():
            print(f"\n✗ Error: Expected output file not found: {LATEST_NEWS_JSON}")
            return False

        print("\n✓ Scraping completed successfully!")
        return True

    except Exception as e:
        print(f"\n✗ Scraping failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def run_analysis():
    """Run the AI gap analysis pipeline (scripts/analysis.py)."""
    print("\n" + "=" * 70)
    print("STEP 2/3: AI GAP ANALYSIS (LLM)")
    print("=" * 70)

    # Check if news data exists
    if not LATEST_NEWS_JSON.exists():
        print(f"\n✗ Error: News data not found at {LATEST_NEWS_JSON}")
        print("   Please run the scraper first or use --skip-scrape=false")
        return False

    # Import and run analysis.py's main function
    sys.path.insert(0, str(ROOT / "scripts"))
    from scripts.analysis import main as analysis_main

    try:
        analysis_main()

        # Verify output files were created
        if not DAILY_ANALYSIS_JSON.exists():
            print(f"\n✗ Error: Expected output file not found: {DAILY_ANALYSIS_JSON}")
            return False

        print("\n✓ Analysis completed successfully!")
        return True

    except Exception as e:
        print(f"\n✗ Analysis failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def prewarm_all_gemini_caches():
    """
    Pre-warm ALL LLM caches after pipeline run.

    This ensures the dashboard loads instantly by pre-computing all AI analysis.
    Cache TTL is 24 hours, aligning with the daily 8am pipeline run.

    IMPORTANT: Results are saved to disk (gemini_cache.json) for persistence
    across Streamlit Cloud deployments. The @st.cache_data decorator only works
    in-process, so disk storage is required for cross-process persistence.

    Features pre-warmed:
    1. Reader Advantages (Why Readers Choose Us)
    2. Business Intelligence Hub (sponsors, speakers, topics)
    3. Geographic/Company/Topic insights
    4. Battleground summary
    """
    print("\n" + "=" * 70)
    print("CACHE PRE-WARMING: All LLM Features (Disk Persistence)")
    print("=" * 70)

    try:
        import json
        from collections import Counter
        from datetime import datetime, timedelta

        import pandas as pd

        from paths import DAILY_ANALYSIS_JSON, GEMINI_CACHE_JSON, NEWS_HISTORY_CSV

        # Import disk cache for persistence
        from src.gemini_cache import clear_disk_cache, get_cache_key, save_to_disk_cache
        from src import llm_client

        # Check if any LLM provider is configured
        if not llm_client.is_available():
            print("  ⏭️  Skipping: No LLM provider configured (set CEREBRAS_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY)")
            return True
        print(f"  → LLM providers available: {', '.join(llm_client.active_providers())}")

        # Load data
        if not NEWS_HISTORY_CSV.exists():
            print("  ⏭️  Skipping: No news history CSV found")
            return True

        # Clear old cache before pre-warming
        print("  → Clearing old Gemini cache...")
        clear_disk_cache()

        print("  → Loading article history...")
        df = pd.read_csv(NEWS_HISTORY_CSV)
        df['published_dt'] = pd.to_datetime(df['published_date'], errors='coerce')

        # Import ALL Gemini functions for comprehensive pre-warming
        from src.gemini_ner_analysis import (
            analyze_company_landscape,
            analyze_geographic_gaps,
            analyze_topic_trends,
            enhance_reader_advantages_with_gemini,
            generate_battleground_summary,
            get_affiliate_comparison_insight,
            get_ai_keyword_recommendations,
            get_ai_seo_recommendations,
            get_commercial_enhancement,
            get_company_insight,
            get_exhibitor_prospects,
            get_geo_insight,
            get_regional_insight,
            get_topic_insight,
        )
        from src.reader_advantages_v2 import detect_all_advantages

        # Helper: sanitize records for JSON
        def sanitize_for_json(records):
            for r in records:
                for k, v in list(r.items()):
                    if hasattr(v, 'isoformat'):
                        r[k] = v.isoformat()
                    elif pd.isna(v):
                        r[k] = None
            return records

        # Prepare common data
        cutoff_90d = datetime.now() - timedelta(days=90)
        cutoff_30d = datetime.now() - timedelta(days=30)

        df_90d = df[df['published_dt'] >= cutoff_90d].copy()
        df_30d = df[df['published_dt'] >= cutoff_30d].copy()

        internal_df = df_90d[df_90d['category'] == 'internal']
        competitor_df = df_90d[df_90d['category'] != 'internal']

        internal_count = len(internal_df)
        competitor_count = len(competitor_df)

        internal_sample = sanitize_for_json(internal_df.head(20).to_dict('records'))
        competitor_sample = sanitize_for_json(competitor_df.head(20).to_dict('records'))

        success_count = 0
        total_features = 11  # All Gemini-powered features

        # ============================================================
        # 1. READER ADVANTAGES
        # ============================================================
        print("\n  [1/6] Reader Advantages...")
        try:
            reader_adv_data = detect_all_advantages(df, window_days=90)
            cards = reader_adv_data.get('cards', [])

            if cards:
                result = enhance_reader_advantages_with_gemini(
                    json.dumps(reader_adv_data, default=str),
                    json.dumps(internal_sample, default=str),
                    json.dumps(competitor_sample, default=str),
                    90
                )
                if not result.get('fallback_used'):
                    print(f"       ✓ {len(result.get('enhanced_cards', []))} cards enhanced")
                    success_count += 1
                else:
                    print("       ⚠️ Fallback used")
            else:
                print("       ⏭️ No patterns detected")
        except Exception as e:
            print(f"       ⚠️ Error: {str(e)[:50]}")

        # ============================================================
        # 2. BATTLEGROUND SUMMARY
        # ============================================================
        print("  [2/6] Battleground Summary...")
        try:
            # Extract geo data from articles
            geo_counts = Counter()
            for _, row in df_30d.iterrows():
                region = row.get('region', 'Unknown')
                if pd.notna(region) and region != 'Unknown':
                    geo_counts[region] += 1

            geo_data = [{'region': k, 'count': v} for k, v in geo_counts.most_common(10)]

            # Extract company data
            company_counts = Counter()
            for _, row in df_30d.iterrows():
                company = row.get('company', '')
                if pd.notna(company) and company:
                    company_counts[company] += 1

            company_data = [{'company': k, 'count': v} for k, v in company_counts.most_common(15)]

            result = generate_battleground_summary(
                json.dumps(geo_data),
                json.dumps(company_data),
                competitor_count,
                internal_count
            )
            if result and 'error' not in result.lower():
                print("       ✓ Summary generated")
                success_count += 1
            else:
                print("       ⚠️ Generation failed")
        except Exception as e:
            print(f"       ⚠️ Error: {str(e)[:50]}")

        # ============================================================
        # 3. GEOGRAPHIC GAPS ANALYSIS
        # ============================================================
        print("  [3/6] Geographic Gaps...")
        try:
            # Build geo comparison data
            internal_geo = Counter()
            competitor_geo = Counter()

            for _, row in df_30d.iterrows():
                region = row.get('region', 'Unknown')
                if pd.notna(region) and region != 'Unknown':
                    if row.get('category') == 'internal':
                        internal_geo[region] += 1
                    else:
                        competitor_geo[region] += 1

            geo_comparison = []
            all_regions = set(internal_geo.keys()) | set(competitor_geo.keys())
            for region in all_regions:
                geo_comparison.append({
                    'region': region,
                    'internal': internal_geo.get(region, 0),
                    'competitor': competitor_geo.get(region, 0)
                })

            if geo_comparison:
                result = analyze_geographic_gaps(
                    json.dumps(geo_comparison),
                    competitor_count,
                    internal_count
                )
                if result and 'error' not in str(result).lower():
                    print("       ✓ Geographic analysis complete")
                    success_count += 1
                else:
                    print("       ⚠️ Analysis failed")
            else:
                print("       ⏭️ No geographic data")
        except Exception as e:
            print(f"       ⚠️ Error: {str(e)[:50]}")

        # ============================================================
        # 4. COMPANY LANDSCAPE
        # ============================================================
        print("  [4/6] Company Landscape...")
        try:
            company_data = [{'company': k, 'mentions': v} for k, v in company_counts.most_common(20)]

            if company_data:
                result = analyze_company_landscape(json.dumps(company_data))
                if result and 'error' not in str(result).lower():
                    print("       ✓ Company analysis complete")
                    success_count += 1
                else:
                    print("       ⚠️ Analysis failed")
            else:
                print("       ⏭️ No company data")
        except Exception as e:
            print(f"       ⚠️ Error: {str(e)[:50]}")

        # ============================================================
        # 5. TOPIC TRENDS
        # ============================================================
        print("  [5/6] Topic Trends...")
        try:
            # Extract topic data
            topic_counts = Counter()
            for _, row in df_30d.iterrows():
                topic = row.get('topic', '')
                if pd.notna(topic) and topic:
                    topic_counts[topic] += 1

            topic_data = [{'topic': k, 'count': v} for k, v in topic_counts.most_common(15)]

            if topic_data:
                result = analyze_topic_trends(json.dumps(topic_data))
                if result and 'error' not in str(result).lower():
                    print("       ✓ Topic analysis complete")
                    success_count += 1
                else:
                    print("       ⚠️ Analysis failed")
            else:
                print("       ⏭️ No topic data")
        except Exception as e:
            print(f"       ⚠️ Error: {str(e)[:50]}")

        # ============================================================
        # 6. COMMERCIAL ENHANCEMENT (Business Intelligence Hub)
        # ============================================================
        print("  [6/6] Business Intelligence Hub...")
        try:
            # Load existing commercial data from daily analysis
            existing_commercial = {}
            if DAILY_ANALYSIS_JSON.exists():
                with open(DAILY_ANALYSIS_JSON) as f:
                    analysis_data = json.load(f)
                    existing_commercial = analysis_data.get('commercial_radar', {})

            recent_articles = sanitize_for_json(df_30d.head(30).to_dict('records'))

            if recent_articles:
                result = get_commercial_enhancement(existing_commercial, recent_articles)
                if result and not result.get('error'):
                    sponsors = len(result.get('sponsors', []))
                    speakers = len(result.get('speakers', []))
                    print(f"       ✓ {sponsors} sponsors, {speakers} speakers identified")
                    success_count += 1
                else:
                    print("       ⚠️ Enhancement failed")
            else:
                print("       ⏭️ No recent articles")
        except Exception as e:
            print(f"       ⚠️ Error: {str(e)[:50]}")

        # ============================================================
        # 7. CHART INSIGHTS (Geo, Company, Topic, Regional)
        # ============================================================
        print("  [7/11] Chart Insights...")
        try:
            insights_cached = 0

            # Geo insight
            if geo_data:
                result = get_geo_insight(json.dumps(geo_data), competitor_count, internal_count)
                if result and 'error' not in result.lower():
                    insights_cached += 1

            # Company insight
            if company_data:
                result = get_company_insight(json.dumps(company_data))
                if result and 'error' not in result.lower():
                    insights_cached += 1

            # Topic insight
            if topic_data:
                result = get_topic_insight(json.dumps(topic_data))
                if result and 'error' not in result.lower():
                    insights_cached += 1

            # Regional insight
            internal_regions = [{'region': k, 'count': v} for k, v in internal_geo.items()]
            competitor_regions = [{'region': k, 'count': v} for k, v in competitor_geo.items()]
            if internal_regions or competitor_regions:
                result = get_regional_insight(
                    json.dumps(competitor_regions),
                    json.dumps(internal_regions)
                )
                if result and 'error' not in result.lower():
                    insights_cached += 1

            if insights_cached > 0:
                print(f"       ✓ {insights_cached}/4 chart insights cached")
                success_count += 1
            else:
                print("       ⏭️ No chart data available")
        except Exception as e:
            print(f"       ⚠️ Error: {str(e)[:50]}")

        # ============================================================
        # 8. AFFILIATE COMPARISON
        # ============================================================
        print("  [8/11] Affiliate Comparison...")
        try:
            # Build affiliate vs non-affiliate comparison
            affiliate_df = df_30d[df_30d['source'].str.contains('affiliate', case=False, na=False)]
            non_affiliate_df = df_30d[~df_30d['source'].str.contains('affiliate', case=False, na=False)]

            affiliate_count = len(affiliate_df)
            non_affiliate_count = len(non_affiliate_df)

            if affiliate_count > 0 and non_affiliate_count > 0:
                # Build topic comparison
                aff_topics = Counter()
                non_aff_topics = Counter()
                for _, row in affiliate_df.iterrows():
                    topic = row.get('topic', '')
                    if pd.notna(topic) and topic:
                        aff_topics[topic] += 1
                for _, row in non_affiliate_df.iterrows():
                    topic = row.get('topic', '')
                    if pd.notna(topic) and topic:
                        non_aff_topics[topic] += 1

                comparison_data = []
                all_topics = set(aff_topics.keys()) | set(non_aff_topics.keys())
                for topic in list(all_topics)[:10]:
                    comparison_data.append({
                        'topic': topic,
                        'affiliate': aff_topics.get(topic, 0),
                        'non_affiliate': non_aff_topics.get(topic, 0)
                    })

                if comparison_data:
                    result = get_affiliate_comparison_insight(
                        json.dumps(comparison_data),
                        affiliate_count,
                        non_affiliate_count
                    )
                    if result and 'error' not in result.lower():
                        print("       ✓ Affiliate comparison cached")
                        success_count += 1
                    else:
                        print("       ⚠️ Analysis failed")
                else:
                    print("       ⏭️ No comparison data")
            else:
                print("       ⏭️ Insufficient affiliate data")
        except Exception as e:
            print(f"       ⚠️ Error: {str(e)[:50]}")

        # ============================================================
        # 9. SEO RECOMMENDATIONS
        # ============================================================
        print("  [9/11] SEO Recommendations...")
        try:
            # Build basic SEO insights
            seo_insights = {
                'top_keywords': [{'keyword': k, 'count': v} for k, v in topic_counts.most_common(10)],
                'coverage_gaps': [],
                'competitor_focus': []
            }
            recent_articles = sanitize_for_json(df_30d.head(20).to_dict('records'))

            if seo_insights['top_keywords']:
                result = get_ai_seo_recommendations(seo_insights, recent_articles)
                if result and not result.get('error'):
                    print("       ✓ SEO recommendations cached")
                    success_count += 1
                else:
                    print("       ⚠️ Analysis failed")
            else:
                print("       ⏭️ No SEO data available")
        except Exception as e:
            print(f"       ⚠️ Error: {str(e)[:50]}")

        # ============================================================
        # 10. EXHIBITOR PROSPECTS
        # ============================================================
        print("  [10/11] Exhibitor Prospects...")
        try:
            # Get emerging categories from topic trends
            emerging_categories = [{'category': k, 'growth': v} for k, v in topic_counts.most_common(5)]
            existing_sponsors = [c['company'] for c in company_data[:10]] if company_data else []

            recent_articles_json = json.dumps(sanitize_for_json(df_30d.head(25).to_dict('records')))

            result = get_exhibitor_prospects(
                recent_articles_json,
                emerging_categories,
                existing_sponsors
            )
            if result and not result.get('error'):
                prospects = len(result.get('prospects', []))
                print(f"       ✓ {prospects} exhibitor prospects identified")
                success_count += 1
            else:
                print("       ⚠️ Analysis failed")
        except Exception as e:
            print(f"       ⚠️ Error: {str(e)[:50]}")

        # ============================================================
        # 11. KEYWORD RECOMMENDATIONS
        # ============================================================
        print("  [11/11] Keyword Recommendations...")
        try:
            current_keywords = [{'keyword': k, 'count': v} for k, v in topic_counts.most_common(15)]
            content_gaps = [{'topic': k, 'gap': v} for k, v in topic_counts.most_common(5)]
            competitor_articles_sample = sanitize_for_json(competitor_df.head(15).to_dict('records'))

            if current_keywords:
                result = get_ai_keyword_recommendations(
                    json.dumps(current_keywords),
                    json.dumps(content_gaps),
                    json.dumps(competitor_articles_sample)
                )
                if result and not result.get('error'):
                    kw_count = len(result.get('priority_keywords', []))
                    print(f"       ✓ {kw_count} keyword recommendations cached")
                    success_count += 1
                else:
                    print("       ⚠️ Analysis failed")
            else:
                print("       ⏭️ No keyword data available")
        except Exception as e:
            print(f"       ⚠️ Error: {str(e)[:50]}")

        # ============================================================
        # SUMMARY
        # ============================================================
        # Verify cache file
        from src.gemini_cache import get_cache_stats
        stats = get_cache_stats()

        print("\n" + "-" * 50)
        print("  \u2713 Pre-warming complete:")
        print(f"     \u2022 Features cached: {success_count}/{total_features}")
        print(f"     \u2022 Valid cache entries: {stats['valid_entries']}")
        print(f"     \u2022 Cache file: {stats['cache_file']}")
        try:
            print(f"     \u2022 File size: {Path(stats['cache_file']).stat().st_size / 1024:.1f} KB")
        except OSError:
            pass
        print("     \u2022 Cache TTL: 24 hours (expires ~8am tomorrow)")
        print("-" * 50)

        return True

    except Exception as e:
        print(f"  ⚠️  Pre-warming failed (non-critical): {str(e)[:80]}")
        import traceback
        traceback.print_exc()
        return True  # Non-critical, don't fail pipeline


def launch_dashboard():
    """Launch Streamlit dashboard (app/dashboard.py)."""
    print("\n" + "=" * 70)
    print("STEP 3/3: LAUNCHING DASHBOARD")
    print("=" * 70)
    print("\n🚀 Starting Streamlit dashboard...")
    print("   Dashboard will open at: http://localhost:8501")
    print("   Press Ctrl+C to stop the dashboard\n")

    try:
        # Launch Streamlit dashboard
        dashboard_path = ROOT / "app" / "dashboard.py"
        subprocess.run(
            ["streamlit", "run", str(dashboard_path)],
            check=True
        )
        return True

    except subprocess.CalledProcessError as e:
        print(f"\n✗ Dashboard launch failed: {str(e)}")
        return False
    except KeyboardInterrupt:
        print("\n\n✓ Dashboard stopped by user")
        return True


def run_full_cycle(skip_scrape=False, launch_dash=True, headless=False):
    """
    Run the complete pipeline: scraping + analysis + dashboard.

    Args:
        skip_scrape: If True, skip scraping and use existing data
        launch_dash: If True, launch Streamlit dashboard at the end
        headless: If True, suppress non-essential output (for cron jobs)

    Returns:
        True if pipeline completed successfully, False otherwise
    """
    if headless:
        # Redirect stdout to suppress verbose output (keep stderr for errors)
        import io
        sys.stdout = io.StringIO()

    success = True

    print("\n" + "=" * 70)
    print("PORTFOLIO COMPETITIVE INTELLIGENCE - FULL PIPELINE")
    print("=" * 70)
    print("\nConfiguration:")
    print(f"  • Skip scraping: {skip_scrape}")
    print(f"  • Launch dashboard: {launch_dash}")
    print(f"  • Headless mode: {headless}")

    # Step 1: Scraping
    if not skip_scrape:
        success = run_scraper()
        if not success:
            print("\n✗ Pipeline aborted: Scraping failed", file=sys.stderr)
            return False
    else:
        print("\n⏭️  Skipping Step 1: Scraping (using existing data)")

    # Step 2: Analysis (critical step)
    success = run_analysis()
    if not success:
        print("\n✗ Pipeline aborted: Analysis failed", file=sys.stderr)
        return False

    # Step 2.5: Pre-warm ALL Gemini AI caches (optional, non-blocking)
    # This ensures the dashboard loads instantly - all AI analysis is pre-computed
    # Cache TTL is 24 hours, aligning with the daily 8am pipeline run
    prewarm_all_gemini_caches()

    # Step 2.6: Update version file to trigger Streamlit Cloud redeployment
    print("\n" + "=" * 70)
    print("UPDATING VERSION FILE (Triggers Streamlit Redeployment)")
    print("=" * 70)
    update_version_file()

    if headless:
        # Restore stdout
        sys.stdout = sys.__stdout__

    # Print summary
    print("\n" + "=" * 70)
    print("✅ PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 70)
    print("\n📊 Generated Files:")
    print(f"   • News data: {LATEST_NEWS_JSON}")
    print(f"   • AI analysis: {DAILY_ANALYSIS_JSON}")

    # Step 3: Launch Dashboard
    if launch_dash and not headless:
        launch_dashboard()
    else:
        print("\n🚀 To view results, run:")
        print("   streamlit run app/dashboard.py")

    return True


def main():
    """Parse arguments and run pipeline."""
    parser = argparse.ArgumentParser(
        description="Run the Portfolio Competitive Intelligence pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py                    # Full pipeline + launch dashboard
  python run_pipeline.py --no-dashboard     # Full pipeline without dashboard
  python run_pipeline.py --skip-scrape      # Skip scraping, use existing data
  python run_pipeline.py --headless         # Run without output (for cron jobs)
        """
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (suppress verbose output, useful for cron jobs)"
    )

    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Skip scraping step and use existing news data"
    )

    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Don't launch Streamlit dashboard at the end"
    )

    args = parser.parse_args()

    success = run_full_cycle(
        skip_scrape=args.skip_scrape,
        launch_dash=not args.no_dashboard,
        headless=args.headless
    )

    # Exit with appropriate code for shell scripts
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
