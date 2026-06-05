# Company Metadata Enrichment Guide

## Overview

The `enrich_company_metadata_llm.py` script uses Google Gemini AI to automatically classify companies based on context snippets extracted from news articles. It produces structured metadata including company type, business segment, and confidence scores.

## Purpose

This script transforms raw company mentions into actionable intelligence by:
1. **Classifying company type:** Operator, supplier, regulator, media, etc.
2. **Identifying business segment:** Sports betting, online casino, payments, etc.
3. **Detecting special categories:** Regulators, media outlets
4. **Providing confidence scores:** How certain the classification is
5. **Generating rationales:** Explaining the classification logic

## Workflow

```
data/company_contexts_for_enrichment.json  →  [LLM Classification]  →  data/company_metadata_auto.json
```

**Input:** Company contexts with mention counts and text snippets
**Process:** LLM analyzes context and classifies each company
**Output:** Enriched metadata with type, segment, confidence, rationale

## Usage

### Running the Script

```bash
# From project root
python -m scripts.enrich_company_metadata_llm
```

### Prerequisites

1. **Input file:** `data/company_contexts_for_enrichment.json` (from `build_company_contexts.py`)
2. **API Key:** `GEMINI_API_KEY` in `.env` file
3. **Dependencies:** `google-generativeai`, `python-dotenv`

### Expected Output

```
======================================================================
ENRICHING COMPANY METADATA WITH LLM CLASSIFICATION
======================================================================

Loading company contexts from data/company_contexts_for_enrichment.json...
✓ Loaded 4 companies

Initializing LLM client (Gemini)...
✓ LLM client initialized

Processing top 4 companies by mention count

[1/4] Classifying: Leovegas (4 mentions)
  ✓ Type: operator, Segment: sports betting and online casino, Confidence: 0.95

[2/4] Classifying: Evoke (3 mentions)
  ✓ Type: operator, Segment: online casino, Confidence: 0.90

[3/4] Classifying: Easywin (3 mentions)
  ✓ Type: other, Segment: generic, Confidence: 0.60

[4/4] Classifying: Fanduel (3 mentions)
  ✓ Type: operator, Segment: sports betting, Confidence: 0.90

✓ Saved enriched metadata to data/company_metadata_auto.json

======================================================================
STATISTICS
======================================================================

Total companies processed: 4
Successful classifications: 4
Failed classifications: 0

Breakdown by type:
  operator          3 companies
  other             1 companies

High-confidence classifications (≥0.8): 3
  Leovegas                  operator     sports betting and online casino (0.95)
  Evoke                     operator     online casino        (0.90)
  Fanduel                   operator     sports betting       (0.90)

======================================================================
✅ Company metadata enrichment complete!
======================================================================
```

## Output Schema

### JSON Structure

```json
{
  "Leovegas": {
    "canonical_name": "Leovegas",
    "raw_variants": ["LeoVegas"],
    "mention_count": 4,
    "type": "operator",
    "primary_segment": "sports betting and online casino",
    "is_regulator": false,
    "is_media": false,
    "confidence": 0.95,
    "rationale": "LeoVegas is launching sports betting in Germany. The CFO was interviewed, indicating it's a public company involved in operations."
  }
}
```

### Field Definitions

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `canonical_name` | string | - | Normalized company name |
| `raw_variants` | array | - | All name variations seen in articles |
| `mention_count` | integer | ≥3 | Total mentions across articles |
| `type` | string | operator, supplier, regulator, media, association, tech, other | Company classification |
| `primary_segment` | string | sports betting, online casino, payments, etc. | Main business area |
| `is_regulator` | boolean | true/false | Whether company is a regulatory body |
| `is_media` | boolean | true/false | Whether company is a media outlet |
| `confidence` | float | 0.0-1.0 | Classification confidence score |
| `rationale` | string | - | LLM's reasoning for classification |

### Company Types

| Type | Description | Examples |
|------|-------------|----------|
| **operator** | Gambling operator (casino, sportsbook, lottery) | DraftKings, Flutter, Betsson |
| **supplier** | Technology/content supplier | Evolution Gaming, Kambi, Playtech |
| **regulator** | Regulatory body or compliance authority | UKGC, MGA, KSA |
| **media** | News outlet, publication, conference | SBC News, Next.io, ICE Events |
| **association** | Industry association or advocacy group | AGA, EGBA |
| **tech** | Technology company (payments, security) | PayPal, Stripe, GeoComply |
| **other** | Unclear or doesn't fit above categories | Startups, emerging companies |

### Primary Segments

Common segment values:
- `sports betting`
- `online casino`
- `lottery`
- `payments`
- `platform` (B2B platform provider)
- `compliance` (regulatory/compliance tech)
- `media` (news/events)
- `marketing` (affiliate/marketing tech)
- `generic` (unclear or mixed)

## How It Works

### 1. Load Company Contexts

Reads `data/company_contexts_for_enrichment.json` containing:
- Canonical company names
- Context snippets from articles
- Mention counts

### 2. Sort and Limit

- Sorts companies by mention count (most mentioned first)
- Limits to top N companies (default: 100, configurable)
- Processes high-value companies first

### 3. LLM Classification

For each company:

**a) Build Prompt:**
```python
# Include up to 5 context snippets, truncated to 200 chars each
context_bullets = "\n".join([
    f"  - {snippet[:200]}..."
    for snippet in context_snippets[:5]
])

prompt = f"""
Company: {canonical_name}
Context snippets:
{context_bullets}

Classify into JSON schema...
"""
```

**b) Call Gemini API:**
```python
response = model.generate_content(prompt)
```

**c) Parse JSON Response:**
```python
metadata = json.loads(response_text)
# Validate fields, apply defaults, ensure types
```

### 4. Merge and Save

- Merges LLM metadata with original context data
- Validates all fields
- Saves to `data/company_metadata_auto.json`

## LLM Prompt Design

### System Instructions

```
You are classifying companies in the global gambling and iGaming industry.

You will receive:
- A company name
- Several short context snippets from news articles

From this, infer structured metadata.

**CRITICAL:** Respond with ONLY valid JSON, no markdown formatting.
```

### JSON Schema Specification

```json
{
  "canonical_name": "string",
  "type": "operator|supplier|regulator|media|association|tech|other",
  "primary_segment": "string",
  "is_regulator": boolean,
  "is_media": boolean,
  "confidence": 0.0-1.0,
  "rationale": "string"
}
```

### Type Definitions Provided to LLM

- **operator:** Gambling operator (casino, sportsbook, lottery operator)
- **supplier:** Technology/content supplier (platform, games, odds, data)
- **regulator:** Regulatory body or compliance authority
- **media:** News outlet, publication, conference organizer
- **association:** Industry association or advocacy group
- **tech:** Technology company (payments, security, etc.)
- **other:** Unclear or doesn't fit above categories

### Example Prompt

```
Company: Leovegas

Context snippets:
  - ☕️ LeoVegas CFO Stefan Nelson talks competition on the public markets and the padel court - NEXT.
  - LeoVegas launches online sports betting in Germany - igamingbusiness.

Classify into JSON schema...
```

### Example Response

```json
{
  "canonical_name": "Leovegas",
  "type": "operator",
  "primary_segment": "sports betting and online casino",
  "is_regulator": false,
  "is_media": false,
  "confidence": 0.95,
  "rationale": "LeoVegas is launching sports betting in Germany. The CFO was interviewed, indicating it's a public company involved in operations."
}
```

## Configuration

### Top N Companies Limit

**Default:** Process top 100 companies by mention count

**To change:**
```python
# In enrich_company_metadata_llm.py, line 16
TOP_N_COMPANIES = 100  # Set to None for all companies
```

**Why limit?**
- Reduces API costs
- Faster processing for testing
- Focuses on high-value companies

### Context Snippet Limits

**Max snippets per prompt:** 5 (default)
**Max snippet length:** 200 characters (default)

**To change:**
```python
# In enrich_company_metadata_llm.py, lines 17-18
MAX_SNIPPETS_PER_PROMPT = 5
MAX_SNIPPET_LENGTH = 200
```

### LLM Model

**Default:** `gemini-2.0-flash-exp`

**To change:**
```python
# In LLMClient.__init__(), line 27
def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash-exp"):
```

**Alternative models:**
- `gemini-2.0-flash-exp` - Fast, cost-effective (recommended)
- `gemini-1.5-pro` - More capable but slower/costlier
- Can swap to Claude/OpenAI by modifying `LLMClient` class

## Error Handling

### JSON Parsing Fallback

If LLM returns invalid JSON:
```python
# Fallback metadata applied
{
  "type": "other",
  "primary_segment": "unknown",
  "confidence": 0.0,
  "rationale": "Classification failed - unable to determine from context"
}
```

### Missing Fields

If LLM omits required fields:
```python
# Default values applied
defaults = {
    'type': 'other',
    'primary_segment': 'unknown',
    'is_regulator': False,
    'is_media': False,
    'confidence': 0.3,
    'rationale': 'Classification uncertain due to missing data'
}
```

### Type Validation

If LLM returns invalid type:
```python
# Automatically corrected to 'other'
valid_types = ['operator', 'supplier', 'regulator', 'media', 'association', 'tech', 'other']
if metadata['type'] not in valid_types:
    metadata['type'] = 'other'
```

### Confidence Bounds

Confidence scores are clamped to [0.0, 1.0]:
```python
metadata['confidence'] = max(0.0, min(1.0, metadata['confidence']))
```

## Use Cases

### 1. Sponsor Targeting

**Query:** Find high-value operators for sponsorship outreach
```python
import json

with open('data/company_metadata_auto.json', 'r') as f:
    companies = json.load(f)

# Find operators with high mention count
operators = [
    (name, data)
    for name, data in companies.items()
    if data['type'] == 'operator' and data['mention_count'] >= 5
]

# Sort by mention count (proxy for relevance)
operators.sort(key=lambda x: x[1]['mention_count'], reverse=True)
```

### 2. Supplier Database

**Query:** Build a supplier directory
```python
suppliers = [
    (name, data['primary_segment'])
    for name, data in companies.items()
    if data['type'] == 'supplier' and data['confidence'] >= 0.7
]
```

### 3. Content Gap Analysis

**Query:** Compare operator coverage across sources
```python
# Operators mentioned in competitor articles
competitor_operators = [
    name for name, data in companies.items()
    if data['type'] == 'operator'
]

# TODO: Cross-reference with Clarion coverage
```

### 4. Regulatory Intelligence

**Query:** Track regulatory bodies
```python
regulators = [
    (name, data)
    for name, data in companies.items()
    if data['is_regulator']
]
```

## Performance

**Typical benchmarks:**
- LLM calls: ~1-2 seconds per company
- Total runtime (4 companies): ~10 seconds
- Total runtime (100 companies): ~3-5 minutes

**API Costs (Gemini 2.0 Flash):**
- ~200 tokens per classification
- 4 companies ≈ 800 tokens ≈ $0.001
- 100 companies ≈ 20K tokens ≈ $0.02

## Integration with Dashboard

### Current State

Company metadata is generated offline, stored in JSON.

### Future Integration

1. **Enhanced Company Insights Tab:**
   ```python
   # Load metadata
   with open('data/company_metadata_auto.json', 'r') as f:
       metadata = json.load(f)

   # Filter by type
   operators = [
       name for name, data in metadata.items()
       if data['type'] == 'operator'
   ]

   # Display in dashboard
   st.dataframe(pd.DataFrame(metadata).T)
   ```

2. **Sponsor Recommendations:**
   - Filter operators with high mention counts
   - Show business segments
   - Display confidence scores

3. **Company Deep Dive:**
   - Click company name to see full metadata
   - View context snippets
   - See rationale for classification

## Troubleshooting

### Issue: "GEMINI_API_KEY not found"

**Solution:**
```bash
# Add to .env file
echo "GEMINI_API_KEY=your-key-here" >> .env
```

### Issue: Low Confidence Scores

**Causes:**
- Insufficient context snippets
- Ambiguous company mentions
- Emerging/unknown companies

**Solutions:**
1. Increase `MAX_SNIPPETS_PER_PROMPT`
2. Increase `MAX_SNIPPET_LENGTH`
3. Lower minimum mention threshold in `build_company_contexts.py`

### Issue: Incorrect Classifications

**Causes:**
- LLM misinterpreting context
- Ambiguous snippets

**Solutions:**
1. Review rationales to understand LLM logic
2. Manually correct in post-processing
3. Improve context extraction in `build_company_contexts.py`

### Issue: Rate Limiting

**Cause:** Too many API calls in short time

**Solution:**
```python
# Add rate limiting
import time

for company in companies:
    classify(company)
    time.sleep(0.5)  # 500ms delay between calls
```

## Future Enhancements

Potential improvements:

1. **Multi-Model Ensemble:**
   - Call multiple LLMs (Gemini + Claude)
   - Compare results, use highest confidence
   - Voting mechanism for disagreements

2. **Human Review Interface:**
   - Dashboard tab for reviewing classifications
   - Accept/reject classifications
   - Manual corrections feed back into training

3. **Confidence Thresholds:**
   - Auto-approve high confidence (≥0.8)
   - Flag low confidence (<0.6) for review
   - Batch processing for manual review

4. **Additional Metadata:**
   - Company size (enterprise, mid-market, startup)
   - Geographic focus (North America, Europe, etc.)
   - Public/private status
   - Founded year

5. **Historical Tracking:**
   - Track classification changes over time
   - Detect company pivots (e.g., supplier → operator)
   - Trend analysis

6. **External Data Enrichment:**
   - Call external APIs (Clearbit, Crunchbase)
   - Fetch company logos, websites, social links
   - Revenue/funding data

## Modular LLM Client Design

The `LLMClient` class is designed to be swappable:

```python
class LLMClient:
    """Abstract interface for LLM providers."""

    def __init__(self, api_key: str, model_name: str):
        # Initialize provider-specific client
        pass

    def classify_company(self, canonical_name: str, context_snippets: List[str]) -> Dict:
        # Call LLM, return structured metadata
        pass
```

### Swapping to Claude

```python
import anthropic

class ClaudeLLMClient(LLMClient):
    def __init__(self, api_key: str, model_name: str = "claude-3-5-sonnet-20241022"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model_name = model_name

    def classify_company(self, canonical_name: str, context_snippets: List[str]) -> Dict:
        prompt = self._build_classification_prompt(canonical_name, context_snippets)

        response = self.client.messages.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}]
        )

        return self._parse_response(response.content[0].text, canonical_name)
```

### Swapping to OpenAI

```python
from openai import OpenAI

class OpenAILLMClient(LLMClient):
    def __init__(self, api_key: str, model_name: str = "gpt-4"):
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name

    def classify_company(self, canonical_name: str, context_snippets: List[str]) -> Dict:
        prompt = self._build_classification_prompt(canonical_name, context_snippets)

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}]
        )

        return self._parse_response(response.choices[0].message.content, canonical_name)
```

---

**Last Updated:** December 2025
**Version:** 1.0
**Status:** Production Ready
