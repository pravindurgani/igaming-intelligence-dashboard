# Testing Checklist

This guide covers testing the dashboard after running the analysis pipeline.

## Pre-Conditions

Before testing, ensure you have generated fresh data:

```bash
# Activate virtual environment
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Generate news data
python main.py

# Generate AI analysis
python analysis.py
```

**Expected files created:**
- `outputs/latest_competitor_news.json`
- `outputs/daily_analysis.json`
- `outputs/daily_briefing.md`
- `data/news_history.csv`

## Launch Dashboard

```bash
streamlit run dashboard.py
```

The dashboard opens at `http://localhost:8501`.

## Tab 1: AI Briefing

### Executive Summary
- Blue info box appears at top with 2-3 paragraph summary
- Professional executive language suitable for C-level readers

### Metadata Metrics
- Three metric cards displayed side-by-side
- Shows: Competitor Articles | Internal Articles | Analysis Date
- Numbers match the actual article counts

### Market Pulse Section
- 4-5 expandable theme cards
- Each card has importance icon: 🔴 High | 🟡 Medium | 🟢 Low
- First theme expanded by default
- Each theme shows: Competitors Covering, Narrative, ICE/iGB Relevance

### Strategic Gaps Section
- 3 warning boxes with yellow background
- Each gap has commercial value badge: 🔴 HIGH | 🟡 MEDIUM | 🟢 LOW
- Two columns: Gap Details | Revenue Potential
- Content Opportunity shown with 💡 icon
- Each gap includes evidence article links (up to 5 clickable sources)

### Commercial Radar Section
- Two side-by-side sections: Sponsors | Speakers
- Interactive tables with company/name, reason, and value
- "View Full Details" expander shows complete information

### Download Buttons
- "Download JSON Data" button downloads valid JSON file
- "Download Markdown Report" button downloads markdown file

## Tab 2: News Feed

### Article Display
- All articles display with title, source, summary, date
- Search bar filters articles by keyword
- Category filter (All / Competitor / Internal) works
- Articles show clickable links to original sources

## Tab 3: Intelligence Battleground

### Chart A: Geographic Coverage
- Bar chart shows locations mentioned in articles
- Competitor vs. Internal comparison visible
- Top locations appear (e.g., North America, Europe, LatAm)

### Chart B: Most Mentioned Companies
- Bar chart shows company mentions
- Only shows entities extracted by spaCy NER
- Company names normalized (e.g., "DraftKings Inc" → "DraftKings")

### Chart C: Strategic Topics
- Bar chart shows topic distribution
- Competitor vs. Internal comparison
- Topics clustered by taxonomy (e.g., "Regulation & Compliance")
- Shows top 3 gaps where competitors lead
- Shows top 5 strengths where Clarion leads

### Chart D: Regional Breakdown
- Two pie charts: Competitor | Internal
- Shows distribution across: North America, Europe, LatAm, Asia Pacific, Middle East & Africa
- Percentages add to 100%

## Error Handling Tests

### Test: Missing Analysis File

```bash
# Rename the file temporarily
mv outputs/daily_analysis.json outputs/daily_analysis.json.backup

# Reload dashboard (Ctrl+C and restart)
streamlit run dashboard.py
```

**Expected:** Warning message appears: "No analysis found. Please run analysis.py"

```bash
# Restore file
mv outputs/daily_analysis.json.backup outputs/daily_analysis.json
```

### Test: Missing News File

```bash
# Rename the file temporarily
mv outputs/latest_competitor_news.json outputs/latest_competitor_news.json.backup

# Reload dashboard
streamlit run dashboard.py
```

**Expected:** Error message in News Feed and Intelligence Battleground tabs

```bash
# Restore file
mv outputs/latest_competitor_news.json.backup outputs/latest_competitor_news.json
```

## Common Issues

### "spaCy model not found"

**Symptom:** Warning in terminal when loading dashboard

**Solution:**
```bash
python -m spacy download en_core_web_sm
```

### Empty charts in Intelligence Battleground

**Cause:** No entities extracted or filtered by taxonomy

**Solution:** Check that articles contain recognizable company names and locations. Review `taxonomy.py` for normalization rules.

### Strategic gaps show "No supporting articles"

**Cause:** Keyword matching didn't find relevant articles

**Solution:** This is normal if gap topics are very specific. The AI still identified the gap based on aggregate patterns.

### Colors not displaying correctly

**Cause:** Importance values must match exactly: "High", "Medium", or "Low" (case-sensitive)

**Solution:** Gemini API usually returns correct values. If not, regenerate analysis with `python analysis.py`.

## Success Criteria

All of the following should pass:

- Executive summary displays in blue info box
- Market Pulse themes are expandable with color-coded importance
- Strategic Gaps show warning boxes with commercial value badges
- Evidence article links appear under each gap
- Commercial Radar tables display sponsors and speakers
- Download buttons produce valid JSON and Markdown files
- News Feed shows all articles with working search
- Intelligence Battleground shows 4 charts with data
- No Python errors in terminal
- No red error messages in dashboard

## Performance Expectations

- Dashboard loads in < 2 seconds
- Switching tabs is instant
- Search in News Feed responds immediately
- Charts render in < 1 second
- Expanders expand/collapse smoothly

## Next Steps

If all tests pass, the system is working correctly. To update data:

```bash
# Run pipeline
python main.py && python analysis.py

# Refresh dashboard (browser auto-refreshes)
```

To deploy, see [DEPLOYMENT.md](DEPLOYMENT.md).
