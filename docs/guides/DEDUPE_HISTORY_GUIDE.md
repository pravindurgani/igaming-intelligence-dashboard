# Deduplication & History Layer Guide

## Overview

The news aggregation system now includes deduplication and historical tracking capabilities. Every article is assigned a unique ID, duplicates are removed within each run, and all articles are logged to an append-only history file.

## Implementation Details

### Article ID Generation

Each article receives a unique `article_id` generated from a SHA256 hash of `source|link`, shortened to 16 hex characters:

```python
article_id = hashlib.sha256(f"{source}|{link}".encode("utf-8")).hexdigest()[:16]
```

**Example:**
- Source: `SBC News`
- Link: `https://sbcnews.co.uk/europe/2025/12/11/ksa-dutch-control-databases/`
- Article ID: `d43a1f1cb90f0b5e`

### Run Timestamp

Each article includes a `run_timestamp` (UTC ISO format) representing when the aggregation script ran:

```python
run_timestamp: "2025-12-11T12:35:06.350100"
```

All articles in a single run share the same timestamp.

### Article Schema

Every article now has these fields:

```json
{
  "article_id": "d43a1f1cb90f0b5e",
  "source": "SBC News",
  "title": "Article Title",
  "link": "https://...",
  "published_date": "2025-12-11 12:00",
  "summary": "Article summary text...",
  "category": "competitor",
  "run_timestamp": "2025-12-11T12:35:06.350100"
}
```

## Processing Flow

### 1. Fetch Articles

Articles are fetched from all sources (12 sources total):
- Direct RSS: SBC News, iGaming Future
- Google News Proxy: Next.io, SiGMA World, EGR Global, CDC Gaming, Global Gaming Insider, iGaming Today
- Portfolio Brands: iGaming Business, iGB Affiliate, GGB Magazine, ICE Gaming

**Expected:** ~200-240 articles (20 per source × 12 sources)

### 2. Deduplicate Within Run

After all articles are fetched, duplicates within the current run are removed:

```python
deduped = {}
for article in all_articles:
    article_id = article["article_id"]
    if article_id not in deduped:
        deduped[article_id] = article
    else:
        # Keep article with latest published_date
        if article["published_date"] > deduped[article_id]["published_date"]:
            deduped[article_id] = article
```

**Expected:** ~100-220 unique articles (duplicates removed)

### 3. Save to latest_competitor_news.json

The deduplicated articles are saved to `latest_competitor_news.json`:

```bash
✓ Successfully saved 220 articles to latest_competitor_news.json
```

This file is **overwritten** on each run with the latest articles.

### 4. Append to History Log

New articles are appended to `data/news_history.csv`:

```python
# Only append articles not already in history
existing_ids = set(df_existing["article_id"])
df_new = df_run[~df_run["article_id"].isin(existing_ids)]
df_new.to_csv(HISTORY_PATH, mode="a", header=False, index=False)
```

**Expected on first run:**
```
✓ Created history file with 220 articles
```

**Expected on subsequent runs:**
```
✓ Added 16 new articles to history (skipped 204 duplicates)
```

## File Outputs

### latest_competitor_news.json

- **Purpose:** Latest news for dashboard/analysis
- **Format:** JSON array of articles
- **Update behavior:** Overwritten on each run
- **Typical size:** 100-220 articles (~130KB)

### data/news_history.csv

- **Purpose:** Append-only historical log
- **Format:** CSV with header row
- **Update behavior:** Appends only new articles (by article_id)
- **Columns:** `article_id, source, title, link, published_date, summary, category, run_timestamp`
- **Growth:** Increases over time as new articles are published

**CSV Structure:**
```csv
article_id,source,title,link,published_date,summary,category,run_timestamp
d43a1f1cb90f0b5e,SBC News,KSA: Dutch gambling oversight...,https://...,2025-12-11 12:00,Kansspelautoriteit...,competitor,2025-12-11T12:35:06.350100
081494e4d19a22ae,SBC News,Swedish sports fraud expert...,https://...,2025-12-11 11:10,A representative...,competitor,2025-12-11T12:35:06.350100
```

## Usage Examples

### Running the Aggregator

```bash
# Activate virtual environment
source .venv/bin/activate

# Run aggregation
python main.py
```

**Terminal Output:**
```
======================================================================
DEDUPLICATION
======================================================================
✓ Deduplicated: 220 → 220 articles
  (Removed 0 duplicates within this run)

======================================================================
SAVING TO HISTORY
======================================================================
✓ Created history file with 220 articles

✅ Aggregation complete!
   📄 Latest articles: latest_competitor_news.json (220 articles)
   📚 History log: data/news_history.csv (append-only)

💡 Normal run stats:
   - Fetched: ~200-240 articles (20 per source × 12 sources)
   - After deduplication: ~100-200 articles (saved to JSON)
   - New articles added to history: varies (depends on overlap with existing)
```

### Analyzing History Data

```python
import pandas as pd

# Load history
df = pd.read_csv('data/news_history.csv')

# Count total articles
print(f"Total articles in history: {len(df)}")

# Count unique articles
print(f"Unique articles: {df['article_id'].nunique()}")

# Articles by source
print(df['source'].value_counts())

# Articles by date
df['published_date'] = pd.to_datetime(df['published_date'])
print(df.groupby(df['published_date'].dt.date).size())

# Most recent run
latest_run = df['run_timestamp'].max()
latest_articles = df[df['run_timestamp'] == latest_run]
print(f"Articles in latest run: {len(latest_articles)}")
```

### Querying Specific Articles

```python
import pandas as pd

df = pd.read_csv('data/news_history.csv')

# Find articles mentioning specific topics
regulation_articles = df[df['summary'].str.contains('regulation|license', case=False, na=False)]

# Filter by source
sbc_articles = df[df['source'] == 'SBC News']

# Filter by date range
recent = df[df['published_date'] >= '2025-12-01']
```

## Backward Compatibility

The public interface of `NewsAggregator.aggregate_all_news()` remains unchanged:

- **Still returns:** List of article dictionaries
- **New fields:** `article_id` and `run_timestamp` added to each article
- **Existing consumers:** `dashboard.py` and `analysis.py` continue to work without changes

They simply ignore the new fields or can optionally use them for enhanced functionality.

## Testing

### Test 1: First Run

```bash
python main.py
```

**Expected:**
- Creates `data/news_history.csv` with ~220 articles
- Creates `latest_competitor_news.json` with ~220 articles
- All articles have unique `article_id` and `run_timestamp`

### Test 2: Second Run (Duplicate Detection)

```bash
python main.py
```

**Expected:**
- Detects duplicates from first run
- Only appends new articles to history (~10-20 new articles)
- Message: `✓ Added X new articles to history (skipped Y duplicates)`

### Test 3: Verify JSON Structure

```bash
python -c "import json; data = json.load(open('latest_competitor_news.json')); print(list(data[0].keys()))"
```

**Expected output:**
```
['article_id', 'source', 'title', 'link', 'published_date', 'summary', 'category', 'run_timestamp']
```

### Test 4: Verify CSV Structure

```bash
head -1 data/news_history.csv
```

**Expected output:**
```
article_id,source,title,link,published_date,summary,category,run_timestamp
```

## Statistics

### Normal Run Statistics

| Metric | Value |
|--------|-------|
| Sources fetched | 12 |
| Articles per source | ~20 (varies by RSS feed) |
| Total fetched | ~200-240 |
| After deduplication | ~100-220 |
| Typical duplicates within run | 0-20 |
| New articles per run (after 1st) | ~10-30 |

### File Growth

**First run:**
- `latest_competitor_news.json`: ~130KB (220 articles)
- `data/news_history.csv`: ~97KB (220 articles + header)

**After 10 runs (assuming 20 new articles per run):**
- `latest_competitor_news.json`: ~130KB (stable, overwritten each run)
- `data/news_history.csv`: ~150KB (220 + 9×20 = 400 articles)

**Growth rate:** ~6KB per run (~50KB per month with daily runs)

## Troubleshooting

### Issue: Duplicate articles in history

**Cause:** Manual editing of history file or article_id collision

**Solution:**
```python
import pandas as pd
df = pd.read_csv('data/news_history.csv')
df_clean = df.drop_duplicates(subset=['article_id'], keep='first')
df_clean.to_csv('data/news_history.csv', index=False)
```

### Issue: Missing article_id field

**Cause:** Old articles from before dedupe layer implementation

**Solution:** Delete old JSON file and re-run aggregation:
```bash
rm latest_competitor_news.json
python main.py
```

### Issue: History file grows too large

**Solution:** Archive old history and start fresh:
```bash
mkdir -p data/archive
mv data/news_history.csv data/archive/news_history_$(date +%Y%m%d).csv
python main.py  # Creates new history file
```

## Future Enhancements

Potential improvements:

1. **Time-based filtering:** Only keep articles from last N days in JSON
2. **Historical analysis:** Track trending topics over time from history
3. **Source health monitoring:** Track which sources are active/inactive
4. **Duplicate article detection across sources:** Find same story from different outlets
5. **Article versioning:** Track updates to existing articles

---

**Last Updated:** December 2025
**Version:** 1.0 (Dedupe & History Layer)
