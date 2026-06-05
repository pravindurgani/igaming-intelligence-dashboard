# Master Pipeline Guide

**Date:** 2025-12-12
**Status:** ✅ Complete

---

## Overview

The `run_pipeline.py` script is a **one-command solution** that runs the entire competitive intelligence workflow from data collection to dashboard visualization.

---

## What It Does

### Full Pipeline (5 Steps)

```
┌─────────────────────────────────────────────────────────────────────┐
│                      python run_pipeline.py                         │
└─────────────────────────────────────────────────────────────────────┘
           │
           ├─► Step 1: News Aggregation (scripts/main.py)
           │   • Scrapes 8 competitor sources + 3 Clarion brands
           │   • Deduplicates and saves to outputs/latest_competitor_news.json
           │   • Appends to data/news_history.csv
           │   ⏱️  30-60 seconds
           │
           ├─► Step 2: ML Topic Classifier Training (ml/train_topic_classifier.py)
           │   • Trains TF-IDF + Logistic Regression model
           │   • Saves to models/topic_classifier.joblib
           │   • Optional: Skipped if no historical data
           │   ⏱️  20-40 seconds
           │
           ├─► Step 3: Company Enrichment (src/enrich_companies.py)
           │   • Extracts companies using spaCy NER
           │   • Classifies using LLM (operator/supplier/regulator)
           │   • Saves to data/company_metadata_auto.json
           │   • Optional: Continues if fails
           │   ⏱️  30-90 seconds (LLM API calls)
           │
           ├─► Step 4: AI Gap Analysis (scripts/analysis.py)
           │   • Clusters articles by topic + region
           │   • Sends to Gemini API for gap identification
           │   • Generates outputs/daily_analysis.json
           │   • Critical: Pipeline aborts if fails
           │   ⏱️  10-30 seconds (Gemini API)
           │
           └─► Step 5: Dashboard Launch (app/dashboard.py)
               • Launches Streamlit at http://localhost:8501
               • Shows AI briefing, news feed, and analytics
               • Runs until Ctrl+C
               ⏱️  Instant startup

Total Runtime: 2-4 minutes (full pipeline)
```

---

## Command-Line Options

### Basic Usage

```bash
# Full pipeline (all 5 steps + dashboard)
python run_pipeline.py
```

### Skip Enrichment (Faster Execution)

```bash
# Skip steps 2 & 3 (ML training + company enrichment)
# Runs: scraping → analysis → dashboard
python run_pipeline.py --skip-enrichment
# Runtime: 40-90 seconds
```

### Skip Scraping (Analysis Only)

```bash
# Uses existing data, runs steps 2-5
# Useful for re-running analysis after tweaking prompts
python run_pipeline.py --skip-scrape
# Runtime: ~1-2 minutes
```

### No Dashboard Launch

```bash
# Runs pipeline but doesn't launch dashboard
# Useful when running remotely or in CI/CD
python run_pipeline.py --no-dashboard
```

### Headless Mode (Cron Jobs)

```bash
# Suppress all output except errors
# Doesn't launch dashboard
python run_pipeline.py --headless
```

### Combined Options

```bash
# Fast analysis on existing data without dashboard
python run_pipeline.py --skip-scrape --skip-enrichment --no-dashboard
# Runtime: 10-30 seconds

# Cron job: scrape and analyze daily
python run_pipeline.py --no-dashboard --headless
```

---

## Error Handling

### Critical Steps (Pipeline Aborts)

- **Step 1 (Scraping):** If scraping fails, pipeline stops
  - Reason: No data to analyze
  - Action: Check internet connection, RSS feed availability

- **Step 4 (Analysis):** If Gemini API fails, pipeline stops
  - Reason: Main deliverable (gap analysis) cannot be generated
  - Action: Check GEMINI_API_KEY in .env, API quota

### Non-Critical Steps (Pipeline Continues)

- **Step 2 (ML Training):** Warns and continues
  - Reason: Optional enhancement, not core functionality
  - Impact: Dashboard won't use ML predictions (falls back to keyword matching)

- **Step 3 (Company Enrichment):** Warns and continues
  - Reason: Optional enhancement, not core functionality
  - Impact: Dashboard won't show company classifications (operator/supplier/etc.)

---

## Output Files

| Step | File | Description |
|------|------|-------------|
| 1 | `outputs/latest_competitor_news.json` | Deduplicated articles from latest run (~100-200 articles) |
| 1 | `data/news_history.csv` | Append-only log of all articles ever collected |
| 1 | `outputs/latest_run_info.json` | Run metadata (timestamp, article count) |
| 2 | `models/topic_classifier.joblib` | Trained ML model for topic classification |
| 3 | `data/company_metadata_auto.json` | Company classifications (operator/supplier/etc.) |
| 4 | `outputs/daily_analysis.json` | Structured AI gap analysis (JSON) |
| 4 | `outputs/daily_briefing.md` | Human-readable gap analysis (Markdown) |

---

## Manual Step-by-Step Execution

If you need fine-grained control or debugging:

```bash
# 1. News aggregation
python scripts/main.py
# Verify: outputs/latest_competitor_news.json should exist

# 2. ML training (optional)
python ml/train_topic_classifier.py
# Verify: models/topic_classifier.joblib should exist

# 3. Company enrichment (optional)
python src/enrich_companies.py
# Verify: data/company_metadata_auto.json should exist

# 4. AI gap analysis
python scripts/analysis.py
# Verify: outputs/daily_analysis.json should exist

# 5. Dashboard
streamlit run app/dashboard.py
# Opens at http://localhost:8501
```

---

## Scheduling (Cron Jobs)

### Daily at 6 AM

```cron
0 6 * * * cd /path/to/spying_gaming_competitors_clarion && /path/to/.venv/bin/python run_pipeline.py --no-dashboard --headless >> /var/log/clarion_pipeline.log 2>&1
```

### Weekly on Monday

```cron
0 6 * * 1 cd /path/to/spying_gaming_competitors_clarion && /path/to/.venv/bin/python run_pipeline.py --no-dashboard --headless
```

---

## Troubleshooting

### Pipeline Stuck at Step 2 (ML Training)

**Symptom:** Training takes > 2 minutes or shows errors
**Solution:**
```bash
# Skip ML training temporarily
python run_pipeline.py --skip-enrichment
```

### Pipeline Stuck at Step 3 (Company Enrichment)

**Symptom:** LLM API calls timing out
**Solution:**
```bash
# Check .env for GEMINI_API_KEY
cat .env | grep GEMINI_API_KEY

# Skip enrichment temporarily
python run_pipeline.py --skip-enrichment
```

### Dashboard Doesn't Launch

**Symptom:** Step 5 shows error or dashboard doesn't open
**Solution:**
```bash
# Check if Streamlit is installed
streamlit --version

# Launch manually
streamlit run app/dashboard.py
```

### "File not found" errors

**Symptom:** Pipeline can't find inputs/outputs
**Solution:**
```bash
# Ensure you're in project root
pwd
# Should show: /path/to/spying_gaming_competitors_clarion

# Check data directories exist
ls -la outputs/ data/
```

---

## Performance Optimization

### Fastest Execution (30-40 seconds)

```bash
# Skip all optional steps
python run_pipeline.py --skip-scrape --skip-enrichment --no-dashboard

# Runs: Analysis only on existing data
```

### Production Recommended (90 seconds)

```bash
# Skip enrichment but run core pipeline
python run_pipeline.py --skip-enrichment

# Runs: Scraping → Analysis → Dashboard
```

### Full Feature Set (2-4 minutes)

```bash
# Everything enabled
python run_pipeline.py

# Runs: Scraping → ML Training → Enrichment → Analysis → Dashboard
```

---

## API Costs

### Per Full Pipeline Run

| Step | API | Calls | Cost (est.) |
|------|-----|-------|-------------|
| Scraping | None | 0 | $0.00 |
| ML Training | None | 0 | $0.00 |
| Company Enrichment | Gemini | 20-50 | $0.01-0.05 |
| Gap Analysis | Gemini | 1-3 | $0.01-0.02 |
| **Total** | | | **$0.02-0.07** |

**Cost per month (daily runs):** ~$0.60-2.10

---

## Comparison: Before vs After

### Before (Manual Multi-Step)

```bash
# User had to run 5 separate commands
python main.py
python ml/train_topic_classifier.py
python enrich_companies.py
python analysis.py
streamlit run dashboard.py

# Time: 5-10 minutes (including context switching)
# Error-prone: Easy to forget steps
```

### After (One Command)

```bash
# Single command
python run_pipeline.py

# Time: 2-4 minutes (fully automated)
# Error-handling: Automatic, continues when possible
# Convenient: Dashboard auto-launches
```

---

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | Pipeline completed successfully |
| 1 | Failure | Check logs for error details |

**Usage in shell scripts:**
```bash
python run_pipeline.py
if [ $? -eq 0 ]; then
    echo "Pipeline succeeded"
else
    echo "Pipeline failed"
    exit 1
fi
```

---

## Summary

**✅ What `run_pipeline.py` solves:**
- Eliminates manual multi-step execution
- Provides smart error handling (continues when safe, aborts when critical)
- Auto-launches dashboard for immediate results
- Supports flexible options (skip steps, headless mode, etc.)
- Perfect for both interactive use and automation (cron jobs)

**🎯 Recommended usage:**
- **Development:** `python run_pipeline.py` (full pipeline)
- **Production/Cron:** `python run_pipeline.py --no-dashboard --headless`
- **Quick Analysis:** `python run_pipeline.py --skip-scrape --skip-enrichment`

---

**Last Updated:** 2025-12-12
**Author:** Claude Code Assistant
