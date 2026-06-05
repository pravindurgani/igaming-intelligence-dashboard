# iGaming Dashboard - Analysis & Cursor Prompts (Dec 18, 2025)

## Test Suite Status: ✅ ALL PASS
```
460 passed, 1 skipped, 30 warnings in 13.23s
```

---

## PART 1: Issues Analysis

### Current State Summary

| Metric | Value |
|--------|-------|
| Total Articles | 902 |
| Internal | 219 |
| Competitor | 683 |
| Articles since Jan 2025 | 721 |
| Test Coverage | 460 tests |
| Dashboard Lines | 2,572 |

### Issue #1: GGB Magazine Data Quality (UPSTREAM - Cannot Fix in Code)

**Status:** Known limitation - Google News RSS proxy issue

| Source | Short Summaries (<50 chars) | Total | % |
|--------|---------------------------|-------|---|
| GGB Magazine | 66 | 79 | 83.5% |
| iGB Affiliate | 34 | 70 | 48.6% |
| SiGMA World | 38 | 106 | 35.8% |

**Root Cause:** Google News RSS returns title echoes instead of proper article summaries for many sources.

**Impact:** NER and region detection rely on summary text; short summaries = missed entities.

**Mitigation Already Applied:** Expanded phrase fallbacks for regions (lines 653-696 and 769-812 in dashboard.py).

**Recommendation:** Consider future integration with article scraping (newspaper3k) to get full content.

---

### Issue #2: Deprecated `datetime.utcnow()` Warning

**Location:** `scripts/main.py:276`

```python
# Current (deprecated)
self.run_timestamp = datetime.utcnow().isoformat()

# Fix
from datetime import datetime, timezone
self.run_timestamp = datetime.now(timezone.utc).isoformat()
```

**Severity:** Low (warning only, not breaking)

---

### Issue #3: Deprecated Function in Dashboard

**Location:** `app/dashboard.py:900-921`

```python
def calculate_percentage_coverage(entities_list, total_articles):
    """
    DEPRECATED: Use calculate_entity_article_coverage instead.
    ...
    """
```

**Status:** Already marked deprecated, kept for backward compatibility.

**Recommendation:** Verify no callers exist, then remove in future cleanup.

---

### Issue #4: Multiple Module Versions Creating Confusion

**reader_advantages - 3 versions:**
| File | Purpose | Used By |
|------|---------|---------|
| `scripts/reader_advantages.py` | Pipeline script | `scripts/analysis.py` |
| `src/reader_advantages.py` | Decision briefs | Tests |
| `src/reader_advantages_v2.py` | Pattern detection | Dashboard, tests |

**differentiators - 2 versions:**
| File | Purpose | Used By |
|------|---------|---------|
| `src/differentiators.py` | Original | `scripts/analysis.py` |
| `src/differentiators_v2.py` | Enhanced | Dashboard, `scripts/analysis.py` |

**Recommendation:** Document clearly which module to use for what purpose, or consolidate.

---

### Issue #5: 60 Timestamped Output Files in data/outputs/

Files like `audience_edge_20251216_010815.csv` accumulate over time.

**Recommendation:** 
1. Keep only `*_latest.csv` files
2. Add cleanup to Makefile
3. Or configure .gitignore to exclude timestamped files

---

### Issue #6: Documentation Fragmentation

- 6 markdown files in root
- 34 markdown files in docs/ subfolders
- Some overlap and historical context mixed with current guides

**Recommendation:** Consolidate into a clear structure with README pointing to key docs.

---

## PART 2: PROMPT FOR ADDRESSING ISSUES

Copy this prompt into Cursor/Claude:

---

### CURSOR PROMPT: Fix Remaining Issues

```
You are working on the iGaming Dashboard project. Please address the following issues:

## Task 1: Fix Deprecated datetime.utcnow() Warning

File: scripts/main.py
Line: 276

Change from:
```python
self.run_timestamp = datetime.utcnow().isoformat()
```

To:
```python
from datetime import datetime, timezone
# ... later in code:
self.run_timestamp = datetime.now(timezone.utc).isoformat()
```

Make sure to:
1. Add the timezone import at the top of the file if not present
2. Update any other utcnow() calls in the same file

## Task 2: Clean Up Deprecated Function

File: app/dashboard.py
Function: calculate_percentage_coverage (lines 900-921)

Steps:
1. Search the entire codebase for any calls to `calculate_percentage_coverage`
2. If no callers exist (other than tests), remove the function
3. If callers exist, update them to use `calculate_entity_article_coverage` instead

## Task 3: Add Output File Cleanup to Makefile

Add a new target to Makefile:

```makefile
clean-outputs:
	@echo "Removing timestamped output files..."
	find data/outputs/ -name "*_2025*.csv" ! -name "*_latest.csv" -delete
	@echo "Done. Keeping only *_latest.csv files."
```

## Verification Steps:

After making changes, run:
```bash
python -m pytest tests/ -v --tb=short
```

All 460 tests should still pass.
```

---

## PART 3: PROMPT FOR REPO CLEANUP & ORGANIZATION

Copy this prompt into Cursor/Claude:

---

### CURSOR PROMPT: Clean & Organize Repository

```
You are cleaning up and organizing the iGaming Dashboard repository. The goal is to improve maintainability without breaking any functionality.

## CRITICAL SAFETY RULES:
1. Run `python -m pytest tests/ -v` after EVERY change
2. Do NOT delete or rename files that are imported by other modules
3. Keep all backward-compatible imports working
4. Create backups before any destructive operations

## Task 1: Consolidate Root-Level Documentation

Current state:
- README.md (keep)
- CHANGELOG.md (keep)
- CURSOR_PROMPT_COMPREHENSIVE_FIXES.md (archive to docs/)
- QUICK_EXECUTION_CHECKLIST.md (archive to docs/)
- REPO_CLEANUP_SUMMARY.md (archive to docs/)
- PR_THREE_CRITICAL_FIXES.md (archive to docs/)

Steps:
1. Move non-essential markdown files to `docs/archive/`:
   ```bash
   mkdir -p docs/archive
   mv CURSOR_PROMPT_COMPREHENSIVE_FIXES.md docs/archive/
   mv QUICK_EXECUTION_CHECKLIST.md docs/archive/
   mv REPO_CLEANUP_SUMMARY.md docs/archive/
   mv PR_THREE_CRITICAL_FIXES.md docs/archive/
   ```

2. Keep only README.md and CHANGELOG.md in root

## Task 2: Clean Up data/outputs/ Directory

The data/outputs/ folder has 60 timestamped files. Keep only the latest versions.

Steps:
1. Create a cleanup script:
   ```python
   # scripts/cleanup_old_outputs.py
   from pathlib import Path
   import re
   
   def cleanup_outputs():
       outputs_dir = Path('data/outputs')
       timestamped_pattern = re.compile(r'.*_\d{8}_\d{6}\.csv$')
       
       for f in outputs_dir.glob('*.csv'):
           if timestamped_pattern.match(f.name) and '_latest' not in f.name:
               print(f"Removing: {f.name}")
               f.unlink()
       
       print("Cleanup complete. Kept *_latest.csv files.")
   
   if __name__ == "__main__":
       cleanup_outputs()
   ```

2. Run the cleanup:
   ```bash
   python scripts/cleanup_old_outputs.py
   ```

3. Add to Makefile:
   ```makefile
   clean-outputs:
   	python scripts/cleanup_old_outputs.py
   ```

## Task 3: Document Module Purpose in README

Add a section to README.md explaining the module structure:

```markdown
## Module Structure

### Core Modules (src/)
- `search.py` - Unified search engine (use this for all search operations)
- `taxonomy.py` - Topic classification and entity filtering
- `textnorm.py` - Text normalization utilities
- `fulltext_search.py` - Backward-compatible redirect to search.py

### Analysis Modules (src/)
- `differentiators.py` - Original differentiator extraction
- `differentiators_v2.py` - Enhanced differentiators with content briefs (preferred)
- `reader_advantages.py` - Decision-oriented reader briefs
- `reader_advantages_v2.py` - Pattern-based advantage detection (used by dashboard)
- `analysis_differentiators.py` - Analysis integration layer

### Pipeline Scripts (scripts/)
- `main.py` - News aggregation pipeline
- `analysis.py` - Daily analysis generation
- `reader_advantages.py` - Reader advantages calculation
- `backfill_2025.py` - Historical data backfill

### Dashboard (app/)
- `dashboard.py` - Streamlit dashboard application
```

## Task 4: Add .gitignore Entries

Ensure .gitignore includes:
```
# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/

# Output files (keep only *_latest.csv)
data/outputs/*_20??????_??????.csv

# macOS
__MACOSX/
.DS_Store

# Environment
.env
.venv/
venv/

# IDE
.idea/
.vscode/
*.swp
```

## Task 5: Remove Deprecated Script

File: scripts/clean_history_remove_ice.py

This script is marked as deprecated and was a one-time cleanup.

Steps:
1. Verify it's not imported anywhere:
   ```bash
   grep -r "clean_history_remove_ice" --include="*.py"
   ```
2. If no imports, delete the file:
   ```bash
   rm scripts/clean_history_remove_ice.py
   ```

## Verification Checklist:

After all changes:
1. [ ] Run full test suite: `python -m pytest tests/ -v`
2. [ ] Start dashboard: `streamlit run app/dashboard.py` (verify no import errors)
3. [ ] Check all imports: `python -c "from scripts.main import NewsAggregator; from src.search import search_articles; print('OK')"`
4. [ ] Verify data files: `ls data/news_history.csv data/daily_analysis.json`

All 460 tests must still pass after cleanup.
```

---

## PART 4: Quick Reference Commands

```bash
# Run all tests
python -m pytest tests/ -v --tb=short

# Run specific test file
python -m pytest tests/test_search.py -v

# Start dashboard
streamlit run app/dashboard.py

# Check article counts
python -c "import pandas as pd; df=pd.read_csv('data/news_history.csv'); print(f'Total: {len(df)}, Internal: {len(df[df.category==\"internal\"])}, Competitor: {len(df[df.category==\"competitor\"])}')"

# Check for deprecated datetime usage
grep -rn "datetime.utcnow" --include="*.py"

# Verify all key imports
python -c "
from scripts.main import NewsAggregator
from src.search import search_articles, search_all_time
from src.taxonomy import classify_topic, TOPIC_CLUSTERS
from src.differentiators_v2 import generate_content_brief
from src.reader_advantages_v2 import detect_all_advantages
print('All imports OK')
"
```

---

## Summary of Changes Needed

| Priority | Issue | Effort | Risk |
|----------|-------|--------|------|
| Low | Fix utcnow deprecation | 5 min | None |
| Low | Clean output files | 10 min | None |
| Low | Archive root docs | 5 min | None |
| Low | Remove deprecated script | 5 min | None |
| Medium | Document module purposes | 15 min | None |
| Future | Consider module consolidation | 2-4 hrs | Medium |

**Total Estimated Effort:** ~40 minutes for all low-priority items

**Tests After Cleanup:** All 460 should still pass
