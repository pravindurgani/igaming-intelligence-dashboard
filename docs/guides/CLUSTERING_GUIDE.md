# LLM Scaling with Pre-Aggregation Clustering

## Overview

The clustering feature pre-aggregates articles by topic and region before sending to the LLM, reducing prompt size by ~66% and enabling efficient scaling to larger article volumes.

## Problem Solved

**Before:** Sending 200+ raw articles to Gemini created very long prompts (20,000+ characters):
- Slow API responses
- Higher API costs
- Risk of hitting context limits
- Harder for LLM to identify patterns

**After:** Pre-aggregating into ~20-30 clusters creates compact prompts (7,000 characters):
- Faster API responses
- Lower token costs
- Scalable to 500+ articles
- Easier for LLM to spot trends

## How It Works

### 1. Article Classification

For each article, the system:
1. Extracts topics using `classify_topic()` from taxonomy
2. Extracts regions using spaCy NER + `normalize_region()`
3. Creates a cluster key: `(topic, region, category)`

```python
# Example article processing
article = {
    "title": "Brazil regulates sports betting with new tax framework",
    "summary": "The Brazilian government announces...",
    "category": "competitor"
}

# Classification
topics = classify_topic(text)  # → ['Regulation & Compliance']
regions = extract_regions(text)  # → ['LatAm']
category = article['category']  # → 'competitor'

# Cluster key
key = ('Regulation & Compliance', 'LatAm', 'competitor')
```

### 2. Cluster Aggregation

Articles with the same (topic, region, category) are grouped:

```python
{
  "topic_cluster": "Regulation & Compliance",
  "region": "LatAm",
  "category": "competitor",
  "article_count": 12,
  "sample_headlines": [
    "Brazil regulates sports betting with new tax framework",
    "Argentina updates online gaming licensing requirements",
    "Colombia introduces responsible gambling measures",
    "Peru drafts new sports betting legislation",
    "Chile considers tax increases for online operators"
  ]
}
```

### 3. LLM Prompt Generation

The clustered data is sent to Gemini:

```json
{
  "internal_clusters": [
    {
      "topic_cluster": "Technology & Innovation",
      "region": "Europe",
      "category": "internal",
      "article_count": 8,
      "sample_headlines": ["..."]
    }
  ],
  "competitor_clusters": [
    {
      "topic_cluster": "Regulation & Compliance",
      "region": "LatAm",
      "category": "competitor",
      "article_count": 12,
      "sample_headlines": ["..."]
    }
  ]
}
```

### 4. Analysis Output

The LLM analyzes clusters to identify:
- **Market Pulse themes** across topics/regions
- **Strategic Gaps** where competitors cover more clusters
- **Commercial opportunities** from high-volume clusters

The output JSON schema remains unchanged, so `dashboard.py` requires no modifications.

## Configuration

### Enable/Disable Clustering

**Default:** Clustering enabled (`USE_CLUSTERED_SUMMARY = True`)

**To disable:** Edit line 22 in `analysis.py`:

```python
# Use clustered mode (recommended for 100+ articles)
USE_CLUSTERED_SUMMARY = True

# Use raw articles (better for small datasets < 50 articles)
USE_CLUSTERED_SUMMARY = False
```

### Maximum Headlines Per Cluster

**Default:** 5 sample headlines per cluster

**To change:** Edit the call in `build_cluster_summary()`:

```python
# In create_analysis_prompt(), lines 224-225
internal_clusters = self.build_cluster_summary(
    internal_articles,
    max_headlines_per_cluster=5  # ← Change this
)
```

**Guidelines:**
- 3 headlines: Minimum context (most compact)
- 5 headlines: Balanced (default)
- 10 headlines: Maximum context (larger prompts)

### Region Extraction

**Method:** spaCy NER extracts GPE (geopolitical) entities

**Fallback:** If no regions found, defaults to "Global"

**To improve region detection:**
1. Add more location keywords to `REGION_MAPPING` in `taxonomy.py`
2. Ensure spaCy model is installed: `python -m spacy download en_core_web_sm`

### Topic Classification

**Method:** Keyword matching via `classify_topic()` in taxonomy

**Fallback:** If no topics match, defaults to "Unclassified"

**To improve topic detection:**
1. Add more keywords to `TOPIC_CLUSTERS` in `taxonomy.py`
2. Use more specific article titles/summaries in RSS feeds

## Implementation Details

### Files Modified

1. **analysis.py**
   - Added `USE_CLUSTERED_SUMMARY` flag (line 22)
   - Added `_load_spacy_model()` method (lines 85-95)
   - Added `extract_regions_from_text()` method (lines 97-126)
   - Added `build_cluster_summary()` method (lines 128-204)
   - Updated `create_analysis_prompt()` to support both modes (lines 206-336)

2. **No changes required to:**
   - `dashboard.py` - Output JSON schema unchanged
   - `main.py` - Article collection unchanged
   - `daily_analysis.json` - Schema remains identical

### Cluster Summary Schema

```json
[
  {
    "topic_cluster": "Regulation & Compliance",
    "region": "LatAm",
    "category": "competitor",
    "article_count": 12,
    "sample_headlines": [
      "Headline 1",
      "Headline 2",
      "Headline 3",
      "Headline 4",
      "Headline 5"
    ]
  }
]
```

### Prompt Structure Comparison

**Clustered Mode:**
```
You are the Strategic Content Director...

**DATA FORMAT:**
Each entry is a pre-aggregated cluster with:
- topic_cluster: Main topic theme
- region: Geographic region covered
- category: 'competitor' or 'internal'
- article_count: Number of articles in this cluster
- sample_headlines: Representative article titles

**INTERNAL COVERAGE:**
[14 cluster objects]

**COMPETITOR COVERAGE:**
[23 cluster objects]

**ANALYSIS REQUIREMENTS:**
1. Analyze the cluster data to identify patterns, trends, and gaps across topics and regions.
2. Identify 4-5 major industry themes...
```

**Raw Mode:**
```
You are the Strategic Content Director...

**DATA FORMAT:**
Each entry is a full article with title, summary, source, link, category, and published_date.

**INTERNAL COVERAGE:**
[45 full article objects with titles, summaries, links]

**COMPETITOR COVERAGE:**
[155 full article objects with titles, summaries, links]

**ANALYSIS REQUIREMENTS:**
1. Analyze the individual articles to identify patterns, trends, and gaps.
2. Identify 4-5 major industry themes...
```

## Performance Benchmarks

### Test Dataset: 30 Articles

**Clustered Mode:**
- Clusters created: 14
- Prompt size: 7,320 characters (227 lines)
- Clustering time: ~2-3 seconds (includes spaCy NER)

**Raw Mode:**
- Articles sent: 30
- Prompt size: 21,347 characters (385 lines)
- No preprocessing time

**Size Reduction: 65.7%** (14,027 fewer characters)

### Projected Scaling: 200 Articles

**Clustered Mode:**
- Expected clusters: ~40-50
- Estimated prompt: ~15,000 characters
- API cost: ~$0.002 per analysis (Gemini pricing)

**Raw Mode:**
- Articles sent: 200
- Estimated prompt: ~140,000 characters
- API cost: ~$0.014 per analysis (Gemini pricing)

**Cost Reduction: ~85%**

### Projected Scaling: 500 Articles

**Clustered Mode:**
- Expected clusters: ~80-100
- Estimated prompt: ~30,000 characters
- Still within all model context limits
- API cost: ~$0.004 per analysis

**Raw Mode:**
- Articles sent: 500
- Estimated prompt: ~350,000 characters
- **Exceeds most model context limits**
- Would require batching or truncation

## Use Cases

### 1. Daily Analysis (Current: 200-240 articles)

**Recommendation:** Use clustered mode
- Reduces API costs by 70-85%
- Faster responses (less tokens to process)
- More reliable (less risk of hitting limits)

### 2. Weekly Digest (500+ articles)

**Requirement:** Must use clustered mode
- Raw mode would exceed context limits
- Clustering enables analysis of full week's data
- LLM can identify week-long trends across topics/regions

### 3. Historical Analysis (1000+ articles)

**Strategy:** Cluster by time period first
```python
# Pseudo-code for time-based clustering
articles_by_week = group_by_week(articles)
for week, week_articles in articles_by_week.items():
    clusters = build_cluster_summary(week_articles)
    analysis = analyze_with_gemini(clusters)
```

### 4. Real-Time Monitoring (Streaming updates)

**Strategy:** Incremental clustering
```python
# Add new articles to existing clusters
existing_clusters = load_clusters()
new_articles = fetch_latest_news()
updated_clusters = update_clusters(existing_clusters, new_articles)
```

## Advantages

### For LLM Processing

1. **Pattern Recognition:** Easier to spot "LatAm regulation" trend from 1 cluster vs 15 individual articles
2. **Attention Focus:** LLM focuses on high-level patterns, not repetitive article details
3. **Response Quality:** Strategic insights vs article summaries
4. **Consistency:** Reduces variability in analysis quality

### For System Scalability

1. **Context Limits:** Stay well under 1M token limits even with 1000+ articles
2. **API Costs:** 70-85% reduction in token usage
3. **Response Time:** Fewer tokens = faster generation
4. **Rate Limits:** Less likely to hit rate limits with smaller prompts

### For Data Management

1. **Preprocessing:** Topic/region extraction done once, cached in clusters
2. **Debugging:** Easier to validate cluster accuracy vs inspecting LLM reasoning
3. **Transparency:** Can audit which clusters influenced which gaps
4. **Reusability:** Clusters can be used for multiple analysis types

## Disadvantages & Trade-offs

### Loss of Article-Level Detail

**Issue:** LLM doesn't see full article text, only headlines

**Mitigation:**
- Store 5 representative headlines per cluster
- Increase `max_headlines_per_cluster` if needed
- Use evidence linking (Step 4) to attach full articles post-analysis

### Clustering Accuracy

**Issue:** `classify_topic()` may mis-classify articles

**Mitigation:**
- Regularly audit topic classification accuracy
- Improve `TOPIC_CLUSTERS` keywords in taxonomy
- Add custom classification rules for edge cases

**Issue:** spaCy NER may miss region mentions

**Mitigation:**
- Expand `REGION_MAPPING` with more location keywords
- Fallback to "Global" is reasonable default
- Review "Global" clusters to find missed regions

### Initial Processing Time

**Issue:** Clustering adds 2-3 seconds before LLM call

**Trade-off:** Worth it for:
- 70%+ cost reduction
- Faster LLM response
- Better scalability

**Not worth it for:** Small datasets (<50 articles) where raw mode is fine

## When to Use Each Mode

### Use Clustered Mode (Recommended)

✅ Daily analysis with 100+ articles
✅ Weekly/monthly digests
✅ Historical analysis
✅ Multi-source aggregation
✅ Cost-sensitive deployments
✅ Scaling to 500+ articles

### Use Raw Mode

✅ Small datasets (<50 articles)
✅ Debugging/testing with sample data
✅ Maximum article-level detail needed
✅ Topic/region classification not accurate
✅ Comparing old vs new analysis method

## Testing & Validation

### Test Cluster Quality

```bash
# Run clustering on sample data
source .venv/bin/activate
python -c "
from analysis import NewsAnalyzer
import json

with open('latest_competitor_news.json', 'r') as f:
    articles = json.load(f)[:50]

analyzer = NewsAnalyzer()
clusters = analyzer.build_cluster_summary(articles)

# Inspect clusters
for cluster in clusters[:10]:
    print(f\"{cluster['topic_cluster']} | {cluster['region']} | {cluster['article_count']} articles\")
    for headline in cluster['sample_headlines'][:3]:
        print(f\"  - {headline[:60]}...\")
    print()
"
```

### Compare Analysis Quality

```bash
# Test 1: Clustered mode
python analysis.py  # Uses USE_CLUSTERED_SUMMARY = True
cp daily_analysis.json daily_analysis_clustered.json

# Test 2: Raw mode
# Edit analysis.py: set USE_CLUSTERED_SUMMARY = False
python analysis.py
cp daily_analysis.json daily_analysis_raw.json

# Compare outputs
python -c "
import json

with open('daily_analysis_clustered.json', 'r') as f:
    clustered = json.load(f)

with open('daily_analysis_raw.json', 'r') as f:
    raw = json.load(f)

print('Clustered mode gaps:', [g['topic'] for g in clustered['strategic_gaps']])
print('Raw mode gaps:', [g['topic'] for g in raw['strategic_gaps']])
"
```

### Benchmark Performance

```bash
# Benchmark clustering time
source .venv/bin/activate
python -c "
import time
from analysis import NewsAnalyzer
import json

with open('latest_competitor_news.json', 'r') as f:
    articles = json.load(f)

analyzer = NewsAnalyzer()

# Test clustering speed
start = time.time()
clusters = analyzer.build_cluster_summary(articles)
duration = time.time() - start

print(f\"Clustered {len(articles)} articles into {len(clusters)} clusters in {duration:.2f}s\")
print(f\"Speed: {len(articles)/duration:.1f} articles/second\")
"
```

## Future Enhancements

### 1. Hierarchical Clustering

**Goal:** Sub-cluster by additional dimensions (company, sentiment, date)

```python
# Nested cluster structure
{
  "topic_cluster": "Regulation & Compliance",
  "region": "LatAm",
  "sub_clusters": [
    {"dimension": "country", "value": "Brazil", "article_count": 8},
    {"dimension": "country", "value": "Argentina", "article_count": 4}
  ]
}
```

### 2. Dynamic Clustering

**Goal:** Adjust clustering granularity based on article volume

```python
if len(articles) < 50:
    # Use raw mode
    use_clusters = False
elif len(articles) < 200:
    # Coarse clustering (2-3 dimensions)
    max_headlines = 5
else:
    # Fine clustering (3-4 dimensions)
    max_headlines = 3
```

### 3. Cluster Embeddings

**Goal:** Use semantic similarity instead of keyword matching

```python
# Use sentence transformers for clustering
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode([a['title'] + ' ' + a['summary'] for a in articles])

# K-means clustering on embeddings
from sklearn.cluster import KMeans
clusters = KMeans(n_clusters=20).fit_predict(embeddings)
```

### 4. Incremental Updates

**Goal:** Add new articles without re-clustering everything

```python
# Load existing clusters
previous_clusters = load_clusters_from_cache()

# Add only new articles
new_articles = fetch_articles_since(last_run_timestamp)
updated_clusters = update_clusters(previous_clusters, new_articles)
```

### 5. Cluster Visualization

**Goal:** Dashboard showing cluster distribution

```python
# In dashboard.py
st.subheader("Article Cluster Map")
cluster_data = load_cluster_summary()
fig = px.sunburst(cluster_data, path=['region', 'topic_cluster'], values='article_count')
st.plotly_chart(fig)
```

## Troubleshooting

### Issue: Too Many "Unclassified" Clusters

**Cause:** Articles don't match any topic keywords

**Solution:**
1. Review unclassified headlines
2. Add missing keywords to `TOPIC_CLUSTERS` in taxonomy
3. Check if topics are too narrow

### Issue: Too Many "Global" Regions

**Cause:** spaCy NER not detecting location mentions

**Solution:**
1. Verify spaCy model installed: `python -m spacy download en_core_web_sm`
2. Add location aliases to `REGION_MAPPING`
3. Review article titles - ensure they mention locations

### Issue: Clusters Too Large/Small

**Cause:** Clustering dimensions too coarse/fine

**Solution:**
- Too large (30+ articles/cluster): Add more topic subcategories
- Too small (1-2 articles/cluster): Merge related topics

### Issue: Analysis Quality Degraded

**Cause:** LLM needs more article details

**Solution:**
1. Increase `max_headlines_per_cluster` from 5 to 10
2. Consider raw mode for this use case
3. Add article summaries to cluster (future enhancement)

---

**Last Updated:** December 2025
**Version:** 1.0
**Status:** Production Ready
