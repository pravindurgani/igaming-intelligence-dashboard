# Taxonomy Guide

The taxonomy system normalizes messy Named Entity Recognition (NER) data to produce clean, accurate charts in the dashboard.

## What It Does

The taxonomy performs three transformations:

1. **Company Normalization:** Maps variations to canonical names
2. **Region Mapping:** Groups locations into geographic regions
3. **Topic Clustering:** Categorizes content into strategic themes

All transformations are defined in [taxonomy.py](../taxonomy.py).

## Company Normalization

**Problem:** NER extracts multiple variations of the same company.

**Example:**
```
Raw NER output:
- "DraftKings"
- "DraftKings Inc"
- "Draft Kings"
```

**Solution:** All variations map to `DraftKings`.

**Configuration:**
```python
COMPANY_ALIASES = {
    'draftkings inc': 'DraftKings',
    'draft kings': 'DraftKings',
}
```

**Impact on Chart B (Most Mentioned Companies):**
- Before: 3 separate entries (10 + 5 + 2 = 17 mentions split)
- After: 1 consolidated entry (17 mentions combined)

## Region Mapping

**Problem:** Cities and countries treated as separate locations.

**Example:**
```
Raw NER output:
- "Brazil" (15 mentions)
- "Sao Paulo" (5 mentions)
- "Rio de Janeiro" (3 mentions)
```

**Solution:** All map to `LatAm` (23 total mentions).

**Configuration:**
```python
REGION_MAPPING = {
    'brazil': 'LatAm',
    'sao paulo': 'LatAm',
    'rio de janeiro': 'LatAm',
    'nevada': 'North America',
    'uk': 'Europe',
}
```

**Five Regions:**
- **North America** (27 locations mapped)
- **Europe** (27 locations)
- **LatAm** (17 locations)
- **Asia Pacific** (15 locations)
- **Middle East & Africa** (10 locations)

**Impact on Chart A (Geographic Coverage) and Chart D (Regional Breakdown):**
- Before: 96 separate city/country entries
- After: 5 consolidated regions with percentage comparisons

## Topic Clustering

**Problem:** Individual keywords don't show strategic themes.

**Example:**
```
Raw keywords in articles:
- "tax" (12 mentions)
- "fine" (8 mentions)
- "regulation" (15 mentions)
```

**Solution:** All cluster into `Regulation & Compliance` (35 total mentions).

**Configuration:**
```python
TOPIC_CLUSTERS = {
    'tax': 'Regulation & Compliance',
    'fine': 'Regulation & Compliance',
    'regulation': 'Regulation & Compliance',
    'merger': 'M&A & Partnerships',
}
```

**Seven Strategic Topics:**
1. Regulation & Compliance
2. M&A & Partnerships
3. Technology & Innovation
4. Sports Betting
5. Responsible Gaming
6. Esports & Emerging
7. Market Expansion

**Impact on Chart C (Strategic Topics):**
- Before: 50+ scattered keywords
- After: 7 strategic themes with competitor vs. portfolio comparison

## Noise Filtering

**Problem:** Generic terms like "Gaming" and "Casino" clutter charts.

**Solution:** Ignore list filters out 40+ generic terms.

**Configuration:**
```python
IGNORE_ENTITIES = {
    'Gaming', 'Casino', 'How', 'New', 'Market', 'Report',
    # Plus competitor/internal brand names
}
```

**Impact on Chart B:**
- Before: "Gaming" (25 mentions), "How" (15 mentions) appear as top entities
- After: Only relevant companies shown

## How It Works in the Dashboard

The `process_articles_with_nlp()` function in dashboard.py applies taxonomy automatically:

```python
# Extract location → normalize to region
if ent.label_ == "GPE":
    normalized_region = normalize_region(ent.text)  # Brazil → LatAm

# Extract company → normalize name, filter noise
elif ent.label_ == "ORG":
    if not should_ignore(ent.text):
        normalized_company = normalize_company(ent.text)  # DraftKings Inc → DraftKings

# Classify topics → cluster into themes
article_topics = classify_topic(text)  # "tax increase" → Regulation & Compliance
```

## Extending the Taxonomy

### Add a New Company

Edit `COMPANY_ALIASES` in taxonomy.py:

```python
COMPANY_ALIASES = {
    # Existing entries
    'draftkings inc': 'DraftKings',

    # New company
    'flutter entertainment plc': 'Flutter',
    'flutter ent': 'Flutter',
}
```

### Add a New Location

Edit `REGION_MAPPING` in taxonomy.py:

```python
REGION_MAPPING = {
    # Existing entries
    'brazil': 'LatAm',

    # New location
    'tokyo': 'Asia Pacific',
    'osaka': 'Asia Pacific',
}
```

### Add a New Topic Keyword

Edit `TOPIC_CLUSTERS` in taxonomy.py:

```python
TOPIC_CLUSTERS = {
    # Existing entries
    'merger': 'M&A & Partnerships',

    # New keyword
    'blockchain': 'Technology & Innovation',
    'nft': 'Technology & Innovation',
}
```

### Add to Ignore List

Edit `IGNORE_ENTITIES` in taxonomy.py:

```python
IGNORE_ENTITIES = {
    # Existing entries
    'Gaming',

    # New noise term
    'Industry',
}
```

## Testing Changes

After modifying taxonomy.py, test it:

```bash
python taxonomy.py
```

**Expected output:**
```
=== Taxonomy System Test ===

Company Normalization:
  'draftkings inc' → DraftKings

Region Mapping:
  'Brazil' → LatAm
  'Nevada' → North America

Topic Classification:
  Topics: ['Sports Betting', 'Regulation & Compliance']

Ignore Filter:
  'Gaming' → Ignore: True
  'DraftKings' → Ignore: False
```

## Maintenance

Review and update the taxonomy:
- **Weekly:** Add new company variations appearing in charts
- **Monthly:** Review ignore list for false positives
- **Quarterly:** Evaluate topic clusters for relevance

## Troubleshooting

**Company still appears as duplicate:**
- Check spelling in `COMPANY_ALIASES` (must be exact match, lowercase)

**Region not being mapped:**
- Verify location name in `REGION_MAPPING` (case-insensitive match required)

**Topic not being detected:**
- Keyword must appear in article title or summary text
- Check `TOPIC_CLUSTERS` for exact keyword spelling

**Valid entity being filtered:**
- Check if accidentally added to `IGNORE_ENTITIES`
