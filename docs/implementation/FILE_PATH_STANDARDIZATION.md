# File Path Standardization

**Date:** 2025-12-11
**Status:** ✅ Complete

## Problem Identified

The repository had inconsistent file paths across different scripts, creating a risk of data sync issues between the pipeline components.

### Original Issue

**main.py** writes to:
```python
'outputs/latest_competitor_news.json'  # Canonical output path
```

**But other scripts read from:**
- `test_dedupe.py` → root-level `latest_competitor_news.json` (no fallback)
- Legacy docs referenced root-level paths

**Risk:** If you run `main.py`, it writes to `outputs/`. If you then run `test_dedupe.py` or other scripts, they would read a stale root-level file (or fail if it doesn't exist).

---

## Solution Implemented

### Standardized Path Hierarchy

**Primary paths (always try first):**
```
outputs/latest_competitor_news.json  ← PRIMARY
outputs/daily_analysis.json          ← PRIMARY
outputs/daily_briefing.md            ← PRIMARY
data/news_history.csv                ← PRIMARY
data/company_metadata_auto.json      ← PRIMARY
models/topic_classifier.joblib       ← PRIMARY
```

**Fallback paths (for backward compatibility):**
```
latest_competitor_news.json          ← FALLBACK (root level, legacy)
daily_analysis.json                  ← FALLBACK (root level, legacy)
daily_briefing.md                    ← FALLBACK (root level, legacy)
```

### Files Updated

#### 1. test_dedupe.py ✅ FIXED

**Before:**
```python
with open('latest_competitor_news.json', 'r') as f:
    articles = json.load(f)
```

**After:**
```python
# Standard path for latest news data
NEWS_PATH = Path('outputs/latest_competitor_news.json')
FALLBACK_NEWS_PATH = Path('latest_competitor_news.json')

def get_news_path():
    """Get the correct path to latest_competitor_news.json with fallback."""
    if NEWS_PATH.exists():
        return NEWS_PATH
    elif FALLBACK_NEWS_PATH.exists():
        print(f"⚠️ Using legacy path: {FALLBACK_NEWS_PATH}")
        return FALLBACK_NEWS_PATH
    else:
        raise FileNotFoundError(
            f"News data not found. Please run main.py first.\n"
            f"  Expected: {NEWS_PATH}\n"
            f"  Fallback: {FALLBACK_NEWS_PATH}"
        )

# All test functions now use:
with open(get_news_path(), 'r') as f:
    articles = json.load(f)
```

**Lines modified:** 10-26, 34, 57, 81, 153, 172

#### 2. enrich_companies.py ✅ ALREADY CORRECT

**Status:** Already had correct fallback logic:
```python
news_path = Path('outputs/latest_competitor_news.json')
if not news_path.exists():
    news_path = Path('latest_competitor_news.json')
```

#### 3. analysis.py ✅ ALREADY CORRECT

**Status:** Already had correct default with fallback:
```python
def load_news_data(self, filename: str = 'outputs/latest_competitor_news.json') -> list:
    # Try new path first
    file_path = Path(filename)
    if not file_path.exists():
        # Fallback to old root path
        old_path = Path(file_path.name)
        if old_path.exists():
            file_path = old_path
```

#### 4. dashboard.py ✅ ALREADY CORRECT

**Status:** Uses correct paths:
- Primary: `data/news_history.csv`
- Primary: `outputs/daily_analysis.json` with fallback to `daily_analysis.json`
- Primary: `outputs/daily_briefing.md` with fallback to `daily_briefing.md`

Does NOT read `latest_competitor_news.json` (uses history CSV instead).

#### 5. main.py ✅ ALREADY CORRECT

**Status:** Writes to correct paths:
```python
def save_to_json(self, filename: str = 'outputs/latest_competitor_news.json'):
    # ...
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Ensures outputs/ directory exists
```

---

## Current Data Flow (Verified)

### Primary Pipeline

```
┌─────────────┐
│   main.py   │
└──────┬──────┘
       │
       ├─→ outputs/latest_competitor_news.json  (deduplicated articles from current run)
       └─→ data/news_history.csv                (append-only log of all articles)

┌──────────────┐
│ analysis.py  │
└──────┬───────┘
       │
       ├─→ reads: outputs/latest_competitor_news.json
       ├─→ writes: outputs/daily_analysis.json
       └─→ writes: outputs/daily_briefing.md

┌──────────────┐
│ dashboard.py │
└──────┬───────┘
       │
       ├─→ reads: data/news_history.csv           (primary data source)
       ├─→ reads: outputs/daily_analysis.json     (AI briefing)
       └─→ reads: outputs/daily_briefing.md       (markdown report)
```

### Optional Scripts

```
┌────────────────────────┐
│ enrich_companies.py    │
└───────────┬────────────┘
            │
            ├─→ reads: outputs/latest_competitor_news.json (or fallback)
            └─→ writes: data/company_metadata_auto.json

┌────────────────────────┐
│ test_dedupe.py         │
└───────────┬────────────┘
            │
            ├─→ reads: outputs/latest_competitor_news.json (or fallback)
            └─→ reads: data/news_history.csv
```

---

## Path Constants by Script

### main.py
- ✅ `outputs/latest_competitor_news.json` (write)
- ✅ `data/news_history.csv` (write/append)

### analysis.py
- ✅ `outputs/latest_competitor_news.json` (read, fallback to root)
- ✅ `outputs/daily_analysis.json` (write)
- ✅ `outputs/daily_briefing.md` (write)

### dashboard.py
- ✅ `data/news_history.csv` (read)
- ✅ `data/company_metadata_auto.json` (read)
- ✅ `outputs/daily_analysis.json` (read, fallback to root)
- ✅ `outputs/daily_briefing.md` (read, fallback to root)
- ✅ `models/topic_classifier.joblib` (read)

### enrich_companies.py
- ✅ `outputs/latest_competitor_news.json` (read, fallback to root)
- ✅ `data/company_metadata_auto.json` (write)

### test_dedupe.py (FIXED)
- ✅ `outputs/latest_competitor_news.json` (read, fallback to root)
- ✅ `data/news_history.csv` (read)

### scripts/build_company_contexts.py
- ✅ `data/news_history.csv` (read)
- ✅ `data/company_contexts_for_enrichment.json` (write)

### scripts/enrich_company_metadata_llm.py
- ✅ `data/company_contexts_for_enrichment.json` (read)
- ✅ `data/company_metadata_auto.json` (write)

### ml/train_topic_classifier.py
- ✅ `data/news_history.csv` (read)
- ✅ `models/topic_classifier.joblib` (write)

---

## Verification Tests

### Test 1: Run Full Pipeline

```bash
# 1. Collect news
python main.py
# ✅ Writes to: outputs/latest_competitor_news.json
# ✅ Writes to: data/news_history.csv

# 2. Run AI analysis
python analysis.py
# ✅ Reads from: outputs/latest_competitor_news.json
# ✅ Writes to: outputs/daily_analysis.json, outputs/daily_briefing.md

# 3. Launch dashboard
streamlit run dashboard.py
# ✅ Reads from: data/news_history.csv
# ✅ Reads from: outputs/daily_analysis.json
```

**Expected:** All scripts use data from the same source (no stale data)

### Test 2: Run Tests

```bash
python test_dedupe.py
# ✅ Reads from: outputs/latest_competitor_news.json (with fallback)
# ✅ Reads from: data/news_history.csv
```

**Expected:** Tests pass using current data

### Test 3: Backward Compatibility

```bash
# Simulate legacy setup (root-level file only)
rm outputs/latest_competitor_news.json
cp data/backup.json latest_competitor_news.json

python analysis.py
# ✅ Falls back to: latest_competitor_news.json (with warning)

python test_dedupe.py
# ✅ Falls back to: latest_competitor_news.json (with warning)
```

**Expected:** Scripts work with legacy path, display fallback warning

---

## Benefits

### 1. Data Consistency
✅ All scripts now reference the same canonical data source
✅ No risk of stale data causing sync issues
✅ Clear primary vs. fallback paths

### 2. Backward Compatibility
✅ Legacy root-level files still work (with warnings)
✅ Gradual migration path for existing users
✅ No breaking changes

### 3. Better Organization
✅ All outputs in `outputs/` folder
✅ All data in `data/` folder
✅ All models in `models/` folder
✅ Clean root directory

### 4. Clear Error Messages
✅ `get_news_path()` shows both expected and fallback paths in error
✅ Warnings when using legacy paths
✅ Easy troubleshooting

---

## Migration Guide

### For Existing Users

If you have a root-level `latest_competitor_news.json`:

**Option 1: Move to outputs/ (recommended)**
```bash
mkdir -p outputs
mv latest_competitor_news.json outputs/
```

**Option 2: Keep using root-level (deprecated)**
```bash
# Scripts will continue to work but show warnings:
# ⚠️ Using legacy path: latest_competitor_news.json
```

### For New Users

Just run the pipeline normally:
```bash
python main.py      # Creates outputs/latest_competitor_news.json
python analysis.py  # Reads from outputs/
streamlit run dashboard.py  # Reads from data/news_history.csv
```

---

## Future Improvements

### Phase 1: Centralized Path Constants (Optional)

Create `paths.py`:
```python
from pathlib import Path

# Outputs
LATEST_NEWS = Path('outputs/latest_competitor_news.json')
DAILY_ANALYSIS = Path('outputs/daily_analysis.json')
DAILY_BRIEFING = Path('outputs/daily_briefing.md')

# Data
NEWS_HISTORY = Path('data/news_history.csv')
COMPANY_METADATA = Path('data/company_metadata_auto.json')
COMPANY_CONTEXTS = Path('data/company_contexts_for_enrichment.json')

# Models
TOPIC_CLASSIFIER = Path('models/topic_classifier.joblib')

# Legacy fallbacks
LEGACY_LATEST_NEWS = Path('latest_competitor_news.json')
LEGACY_DAILY_ANALYSIS = Path('daily_analysis.json')
LEGACY_DAILY_BRIEFING = Path('daily_briefing.md')
```

Then import in all scripts:
```python
from paths import LATEST_NEWS, NEWS_HISTORY
```

**Benefit:** Single source of truth for all paths

### Phase 2: Remove Fallbacks (Breaking Change)

After sufficient time, remove root-level fallbacks:
```python
# Remove this:
elif FALLBACK_NEWS_PATH.exists():
    print(f"⚠️ Using legacy path: {FALLBACK_NEWS_PATH}")
    return FALLBACK_NEWS_PATH
```

**Benefit:** Simpler code, enforced standards

---

## Rollback Instructions

If you need to revert the changes to `test_dedupe.py`:

```bash
git checkout HEAD~1 -- test_dedupe.py
```

**Note:** Not recommended - the fix ensures data consistency

---

## Summary

| Aspect | Before | After |
|--------|--------|-------|
| **test_dedupe.py** | ❌ Root-level only | ✅ outputs/ with fallback |
| **enrich_companies.py** | ✅ Already correct | ✅ No change |
| **analysis.py** | ✅ Already correct | ✅ No change |
| **dashboard.py** | ✅ Already correct | ✅ No change |
| **main.py** | ✅ Already correct | ✅ No change |
| **Data consistency** | ⚠️ At risk | ✅ Guaranteed |
| **Backward compat** | N/A | ✅ Maintained |

**Result:** ✅ **All scripts now use consistent, standardized paths with backward compatibility**

---

**Completion Date:** 2025-12-11
**Verified By:** Claude Code Assistant
**Status:** ✅ **Production Ready**
