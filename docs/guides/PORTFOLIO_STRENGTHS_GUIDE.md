# Portfolio Strengths Feature Guide

## Overview

The Intelligence Battleground dashboard now shows not only where competitors lead (gaps), but also where the **tracked portfolio leads** competitors in topic coverage. This balanced view helps identify both opportunities to improve and existing strengths to leverage.

## What Changed

### New Helper Function: `get_portfolio_strengths()`

**Location:** [dashboard.py:215-249](dashboard.py)

**Purpose:** Identifies topics where the portfolio's coverage percentage exceeds competitor coverage.

**Signature:**

```python
def get_portfolio_strengths(competitor_pct, portfolio_pct, top_n=10):
    """
    Identify topics where the portfolio's coverage exceeds competitor coverage.
    Returns top N entities sorted by percentage point lead.

    Args:
        competitor_pct: Dict mapping entity to competitor percentage
        portfolio_pct: Dict mapping entity to portfolio percentage
        top_n: Number of top strengths to return

    Returns:
        List of dicts with entity, portfolio_pct, competitor_pct, and gap_pct
    """
```

**Algorithm:**

1. Iterates through all unique entities from both competitor and portfolio data
2. Calculates the gap: `gap = portfolio_pct - competitor_pct`
3. Filters to only entities where the portfolio has coverage AND leads (`port > 0 and gap > 0`)
4. Sorts by gap (largest lead first)
5. Returns top N results

### New Dashboard Section: "Portfolio Strengths"

**Location:** Chart C (Strategic Topics) section

**Position:** Appears directly after "Top 3 Topic Gaps"

**Format:**

```
✅ Portfolio Strengths - Topics where we lead:
- Technology & Innovation - Portfolio 16.25% vs competitors 12.00% (lead of 4.25 pp)
- Mobile Gaming - Portfolio 14.50% vs competitors 8.75% (lead of 5.75 pp)
- Responsible Gaming - Portfolio 11.00% vs competitors 6.50% (lead of 4.50 pp)
```

**Display Logic:**

- Shows up to 5 strengths
- Only displays if at least one strength exists
- Uses percentage points (pp) for gap measurement

## Example Use Cases

### Use Case 1: Content Strategy

**Scenario:** Editorial team planning next quarter's content calendar

**Before:**

- Only saw gaps: "We need to cover more about regulation and tax"

**After:**

- **Gaps:** "We need to cover more about regulation and tax"
- **Strengths:** "We're leading in mobile gaming and responsible gaming - let's maintain this advantage"

**Action:** Allocate resources to both fill gaps AND reinforce strengths

### Use Case 2: Sales Positioning

**Scenario:** Sales team preparing sponsor pitch decks

**Before:**

- Could only demonstrate market awareness through gap analysis

**After:**

- **Gaps:** Shows we understand what competitors are doing
- **Strengths:** Proves we have unique, differentiated coverage areas

**Action:** Use strengths as proof points: "We lead the industry in mobile gaming coverage with 14.5% vs competitors' 8.75%"

### Use Case 3: Editorial Review

**Scenario:** Monthly performance review

**Before:**

- "We're behind on X topics" (demotivating)

**After:**

- "We're behind on X topics" (areas to improve)
- "We're leading on Y topics" (areas of excellence)

**Action:** Balanced feedback: celebrate wins, plan improvements

## Implementation Details

### Integration with Existing Code

The new feature integrates seamlessly with the existing Chart C section:

**Before:**

```python
# Chart C displays
if topic_comparison:
    # ... render chart ...

    # Find topic gaps
    topic_gaps = [...]

    if topic_gaps[:3]:
        st.markdown("**🎯 Top 3 Topic Gaps:**")
        # Display gaps
```

**After:**

```python
# Chart C displays
if topic_comparison:
    # ... render chart ...

    # Find topic gaps
    topic_gaps = [...]

    if topic_gaps[:3]:
        st.markdown("**🎯 Top 3 Topic Gaps:**")
        # Display gaps

    # NEW: Find portfolio strengths
    topic_pct_competitor = {item['entity']: item['competitor_pct'] for item in topic_comparison}
    topic_pct_portfolio = {item['entity']: item['internal_pct'] for item in topic_comparison}

    strengths = get_portfolio_strengths(topic_pct_competitor, topic_pct_portfolio, top_n=5)
    if strengths:
        st.markdown("**✅ Portfolio Strengths - Topics where we lead:**")
        for row in strengths:
            st.markdown(f"- **{row['entity']}** - Portfolio {row['portfolio_pct']:.2f}% vs competitors {row['competitor_pct']:.2f}% (lead of {row['gap_pct']:.2f} pp)")
```

### Data Flow

1. **Chart C** processes topic comparison data
2. Creates two dictionaries:
   - `topic_pct_competitor`: Maps topics to competitor coverage %
   - `topic_pct_portfolio`: Maps topics to portfolio coverage %
3. Calls `get_portfolio_strengths()` with these dictionaries
4. Renders strengths section if results exist

### Display Conditions

The strengths section only appears when:

1. Topic comparison data exists (`if topic_comparison`)
2. At least one strength is found (`if strengths`)

If neither condition is met, the section is skipped silently.

## Testing

### Manual Test

1. Run the dashboard:

   ```bash
   streamlit run dashboard.py
   ```
2. Navigate to **Tab 3: Intelligence Battleground**
3. Scroll to **Chart C: Strategic Topics**
4. Verify sections appear in order:

   - Chart (bar chart)
   - **🎯 Top 3 Topic Gaps** (if gaps exist)
   - **✅ Portfolio Strengths - Topics where we lead** (if strengths exist)

### Unit Test

```python
from dashboard import get_portfolio_strengths

# Test data
competitor_pct = {
    'regulation': 15.0,
    'sports betting': 20.0,
    'tax': 10.0,
    'mobile': 5.0,
}

portfolio_pct = {
    'regulation': 12.0,        # Competitor leads
    'sports betting': 25.0,    # Portfolio leads by 5pp
    'tax': 8.0,                # Competitor leads
    'mobile': 12.0,            # Portfolio leads by 7pp
    'innovation': 10.0,        # Portfolio only (leads by 10pp)
}

strengths = get_portfolio_strengths(competitor_pct, portfolio_pct, top_n=5)

# Expected results (sorted by gap):
# 1. innovation - Portfolio 10.00%, Competitor 0.00%, Gap 10.00pp
# 2. mobile - Portfolio 12.00%, Competitor 5.00%, Gap 7.00pp
# 3. sports betting - Portfolio 25.00%, Competitor 20.00%, Gap 5.00pp

assert len(strengths) == 3
assert strengths[0]['entity'] == 'innovation'
assert strengths[0]['gap_pct'] == 10.0
```

## Sample Output

### Dashboard Display

```
Chart C: Strategic Topics - Key Phrases
[Bar chart showing topic comparison]

🎯 Top 3 Topic Gaps (by % difference):
1. Regulation & Compliance: Competitors (18.5%) vs. Portfolio (12.3%) - Gap of 6.2%
2. Tax Policy: Competitors (14.2%) vs. Portfolio (9.8%) - Gap of 4.4%
3. M&A Activity: Competitors (11.7%) vs. Portfolio (8.5%) - Gap of 3.2%

✅ Portfolio Strengths - Topics where we lead:
- Mobile Gaming - Portfolio 14.50% vs competitors 8.75% (lead of 5.75 pp)
- Responsible Gaming - Portfolio 11.00% vs competitors 6.50% (lead of 4.50 pp)
- Technology & Innovation - Portfolio 16.25% vs competitors 12.00% (lead of 4.25 pp)
- Esports - Portfolio 9.75% vs competitors 5.50% (lead of 4.25 pp)
- Virtual Reality - Portfolio 7.50% vs competitors 4.25% (lead of 3.25 pp)
```

## Configuration

### Adjusting Number of Strengths Displayed

**Default:** Top 5 strengths

**To change:** Modify the `top_n` parameter in the function call:

```python
# dashboard.py, line 764
strengths = get_portfolio_strengths(topic_pct_competitor, topic_pct_portfolio, top_n=10)  # Show top 10
```

### Filtering Criteria

**Current filter:** `if port > 0 and gap > 0`

**To add minimum threshold:**

```python
# In get_portfolio_strengths(), line 239
if port > 0 and gap > 2.0:  # Only show leads of 2pp or more
```

## Future Enhancements

Potential improvements:

1. **Visual Indicators:**

   - Green highlighting for strengths
   - Color-coded by gap size
2. **Strength Categories:**

   - "Strong Lead" (>5pp)
   - "Moderate Lead" (2-5pp)
   - "Slight Lead" (<2pp)
3. **Trend Analysis:**

   - "↑ Increasing lead" vs "↓ Declining lead"
   - Requires historical data
4. **Export to Reports:**

   - Include strengths in AI briefing
   - Add to executive summary
5. **Competitor Breakdown:**

   - Show which specific competitors we lead
   - Identify gaps vs specific competitors

## Benefits

### Strategic Value

1. **Balanced View:** Shows both gaps AND strengths
2. **Resource Allocation:** Helps prioritize content investments
3. **Competitive Positioning:** Identifies unique differentiation
4. **Team Morale:** Celebrates editorial wins

### Operational Value

1. **No Breaking Changes:** Adds to existing functionality
2. **Minimal Code:** ~35 lines of new code
3. **Reusable Pattern:** Can apply to other charts (locations, companies)
4. **Performance:** Fast dictionary lookups, no API calls

## Related Features

- **Chart A:** Geographic coverage comparison
- **Chart B:** Company mentions comparison
- **Chart C:** Strategic topics comparison (includes strengths)
- **Chart D:** Regional distribution

This feature could be extended to Charts A and B in the future.

---

**Last Updated:** December 2025
**Version:** 1.0
**Status:** Production Ready
