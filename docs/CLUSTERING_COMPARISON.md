# Clustered vs Raw Mode: Side-by-Side Comparison

## Test Data: 50 Articles

### Performance Metrics

| Metric | Clustered Mode | Raw Mode | Improvement |
|--------|---------------|----------|-------------|
| **Prompt Size** | 8,778 chars | 32,841 chars | **73.3% smaller** |
| **Clusters/Articles** | 19 clusters | 50 articles | 62% reduction |
| **Processing Time** | ~3 seconds | Instant | +3s preprocessing |
| **API Cost** | ~$0.001 | ~$0.004 | **75% cheaper** |
| **Scalability** | ✅ 500+ articles | ❌ ~150 max | **3.3x more** |

### Prompt Structure Comparison

#### Clustered Mode (8,778 chars)

```
You are the Strategic Content Director for the tracked portfolio...

**DATA FORMAT:**
Each entry is a pre-aggregated cluster with:
- topic_cluster: Main topic theme
- region: Geographic region covered
- category: 'competitor' or 'internal'
- article_count: Number of articles in this cluster
- sample_headlines: Representative article titles from this cluster

**INTERNAL COVERAGE (Tracked Portfolio):**
[]

**COMPETITOR COVERAGE (External Publishers):**
[
  {
    "topic_cluster": "Unclassified",
    "region": "Global",
    "category": "competitor",
    "article_count": 22,
    "sample_headlines": [
      "New CFO to take helm at Entain ahead of UK tax increases",
      "BETBY: The hybrid trading advantage removes the limits from operators",
      "Evoke hires advisors but keeps schtum on sales options",
      "GeoLocs: What matters most in GeoLocation",
      "Sportradar taps Logifuture for enhanced football offering"
    ]
  },
  {
    "topic_cluster": "Regulation & Compliance",
    "region": "Global",
    "category": "competitor",
    "article_count": 4,
    "sample_headlines": [
      "Jeton: Navigating the complexities of non-EU payments",
      "Understanding player payments in emerging markets",
      "Irish Gaming and Leisure association opposes new tax",
      "EU Commission opens probe into Google of AI content use"
    ]
  }
  // ... 17 more clusters
]

**ANALYSIS REQUIREMENTS:**
1. Analyze the cluster data to identify patterns, trends, and gaps across topics and regions.
2. Identify 4-5 major industry themes for "market_pulse"
3. Identify exactly 3 strategic gaps for "strategic_gaps"
...
```

#### Raw Mode (32,841 chars)

```
You are the Strategic Content Director for the tracked portfolio...

**DATA FORMAT:**
Each entry is a full article with title, summary, source, link, category, and published_date.

**INTERNAL COVERAGE (Tracked Portfolio):**
[]

**COMPETITOR COVERAGE (External Publishers):**
[
  {
    "title": "New CFO to take helm at Entain ahead of UK tax increases",
    "summary": "Entain plc has appointed Michael Rechsteiner as Chief Financial Officer (CFO) with effect from 1 March 2025. In a stock exchange announcement to the London Stock Exchange, Entain confirmed Rechsteiner will replace Rob Wood who will step down on 28 February 2025. Since January 2022, Rechsteiner has served as the CFO of EMEA and LatAm at Chubb Limited. He has previously held similar roles at GE Financial Assurance Holdings and American International Group. At chubb, Rechsteiner oversaw some of the largest operations of the business...",
    "source": "SBC News",
    "link": "https://sbcnews.co.uk/europe/2024/12/11/new-cfo-to-take-helm-at-entain-ahead-of-uk-tax-increases/",
    "category": "competitor",
    "published_date": "2024-12-11T00:00:00"
  },
  {
    "title": "BETBY: The hybrid trading advantage removes the limits from operators",
    "summary": "In a conversation with BETBY's Chief Commercial Officer and Chief Product Officer, Marius Dontu and Adi Dayan, we learn how having the choice between fully managed, semi-managed or self-managed sportsbooks paves the way to success. Over the past few months, BETBY has introduced its semi-managed and hybrid trading models, offering new opportunities for igaming operators and affiliates...",
    "source": "SBC News",
    "link": "https://sbcnews.co.uk/sportsbetting/2024/12/11/betby-the-hybrid-trading-advantage-removes-the-limits-from-operators/",
    "category": "competitor",
    "published_date": "2024-12-11T00:00:00"
  }
  // ... 48 more full articles with complete summaries
]

**ANALYSIS REQUIREMENTS:**
1. Analyze the individual articles to identify patterns, trends, and gaps.
2. Identify 4-5 major industry themes for "market_pulse"
3. Identify exactly 3 strategic gaps for "strategic_gaps"
...
```

## Visual Size Comparison

```
Clustered Mode:    ████████░░░░░░░░░░░░░░░░░░░░░░░░░  8,778 chars
Raw Mode:          ████████████████████████████████████  32,841 chars
```

## Cluster Breakdown (50 articles → 19 clusters)

| Cluster | Topic | Region | Articles | Sample Headlines |
|---------|-------|--------|----------|------------------|
| 1 | Unclassified | Global | 22 | "New CFO at Entain", "BETBY hybrid trading", "Evoke advisors" |
| 2 | Regulation & Compliance | Global | 4 | "Jeton payments", "Irish tax", "EU AI probe" |
| 3 | Sports Betting | Global | 3 | "Hybrid trading", "Football offering", "Trading platforms" |
| 4 | Technology & Innovation | Global | 3 | "GeoLocation tech", "AI content", "Platform innovations" |
| 5 | Unclassified | Europe | 2 | "Dutch oversight", "Swedish football" |
| ... | ... | ... | ... | ... |

## Projected Scaling

### 200 Articles (Daily Production Load)

| Metric | Clustered | Raw |
|--------|-----------|-----|
| Expected clusters | ~40 | N/A |
| Prompt size | ~18,000 chars | ~130,000 chars |
| API tokens | ~4,500 | ~32,500 |
| Cost per run | $0.002 | $0.013 |
| Monthly cost (30 days) | $0.06 | $0.39 |
| **Annual savings** | - | **$3.96** |

### 500 Articles (Weekly Digest)

| Metric | Clustered | Raw |
|--------|-----------|-----|
| Expected clusters | ~90 | N/A |
| Prompt size | ~35,000 chars | **350,000 chars** |
| API tokens | ~8,750 | **87,500** |
| Fits in context? | ✅ Yes | ❌ **Exceeds limits** |
| Cost per run | $0.004 | **N/A (truncation needed)** |
| Feasibility | ✅ Scalable | ❌ Requires batching |

## Trade-off Analysis

### Clustered Mode Advantages

✅ **73% smaller prompts** (8,778 vs 32,841 chars)
✅ **75% cost reduction** for daily analysis
✅ **Scalable to 500+ articles** without truncation
✅ **Faster LLM responses** (fewer tokens to process)
✅ **Better pattern recognition** (aggregated view)
✅ **Reduced rate limit risk** (smaller payloads)

### Clustered Mode Trade-offs

⚠️ **+3 seconds preprocessing** (spaCy NER + clustering)
⚠️ **Loss of article-level detail** (only 5 headlines per cluster)
⚠️ **Depends on classification accuracy** (topic/region detection)
⚠️ **Initial setup complexity** (spaCy model required)

### Raw Mode Advantages

✅ **Instant processing** (no preprocessing)
✅ **Full article detail** (complete summaries)
✅ **No classification dependency** (works without NER)
✅ **Simpler debugging** (direct article-to-gap mapping)

### Raw Mode Limitations

❌ **3.7x larger prompts** (32,841 vs 8,778 chars)
❌ **4x higher API costs** ($0.013 vs $0.002 per run)
❌ **Not scalable** (150 article practical limit)
❌ **Slower LLM responses** (more tokens)
❌ **Harder pattern recognition** (LLM must abstract from details)

## Recommendation Matrix

| Scenario | Articles | Recommendation | Reason |
|----------|----------|----------------|--------|
| **Testing/Development** | <30 | Raw Mode | Simple, no setup, full detail |
| **Daily Production** | 100-250 | **Clustered Mode** | 75% cost savings, reliable |
| **Weekly Digest** | 300-600 | **Clustered Mode** | Only feasible option |
| **Historical Analysis** | 1000+ | **Clustered Mode** | Must use clustering |
| **Debugging** | Any | Raw Mode | Easier to trace issues |
| **Cost-Sensitive** | Any | **Clustered Mode** | Lower API costs |

## Real-World Example

### User Story: Daily Competitive Intelligence

**Setup:**
- 12 RSS feeds (8 competitor + 4 internal)
- ~200 articles collected daily
- Analysis run once per day

**Monthly Cost Comparison:**

| Mode | Daily Cost | Monthly Cost (30 days) | Annual Cost |
|------|-----------|------------------------|-------------|
| Raw | $0.013 | $0.39 | $4.68 |
| Clustered | $0.002 | $0.06 | $0.72 |
| **Savings** | **$0.011** | **$0.33** | **$3.96** |

**Additional Benefits (Clustered):**
- ✅ Faster dashboard loading (smaller JSON files)
- ✅ More consistent analysis quality
- ✅ Can scale to weekly 500-article digests
- ✅ Less risk of hitting API rate limits

**Conclusion:** Clustered mode pays for itself immediately and enables future features that raw mode cannot support.

---

**Recommendation:** Use clustered mode (default) for all production workloads. Reserve raw mode for development and debugging only.
