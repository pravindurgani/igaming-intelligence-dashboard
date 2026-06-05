"""
Topic classifier for strategic gap evidence mapping.

Classifies gaps and articles into topic categories to ensure coherent
evidence linking in the AI briefing.

Topics:
- executive: Executive appointments, leadership changes
- product: Product launches, new features, announcements
- regulation: Regulatory, compliance, legal, licensing
- market: Market expansion, geography, new markets
- partnership: Partnerships, acquisitions, M&A, deals
- general: Default fallback
"""

import re
from typing import Any

import pandas as pd


def classify_gap_topic(gap_title: str, gap_desc: str) -> str:
    """
    Classify a strategic gap into a topic category for evidence filtering.

    Args:
        gap_title: The gap title text
        gap_desc: The gap description text

    Returns:
        One of: 'executive', 'product', 'regulation', 'market', 'partnership', 'general'
    """
    text = f"{gap_title} {gap_desc}".lower()

    # Executive / leadership patterns (check first - most specific)
    exec_patterns = [
        'executive', 'ceo', 'cfo', 'cto', 'coo', 'chief', 'director',
        'appointment', 'appointed', 'hire', 'hiring', 'leadership',
        'promotion', 'promoted', 'joins', 'joined', 'names', 'named',
        'head of', 'vp ', 'vice president', 'president', 'officer',
        'talent', 'personnel', 'management', 'board', 'chairman'
    ]
    if any(pat in text for pat in exec_patterns):
        return 'executive'

    # Partnership / M&A patterns (check BEFORE product to avoid 'announce' conflicts)
    partnership_patterns = [
        'partner', 'partnership', 'acquisition', 'acquire', 'acquired',
        'merger', 'deal', 'agreement', 'collaboration', 'alliance',
        'joint venture', 'investment', 'investor', 'stake', 'm&a'
    ]
    if any(pat in text for pat in partnership_patterns):
        return 'partnership'

    # Regulation / compliance patterns
    regulation_patterns = [
        'regulat', 'compliance', 'license', 'licensing', 'legal',
        'legislation', 'law', 'government', 'authority', 'commission',
        'approval', 'approved', 'permit', 'certification', 'certified',
        'responsible gambling', 'safer gambling', 'player protection'
    ]
    if any(pat in text for pat in regulation_patterns):
        return 'regulation'

    # Market expansion patterns
    market_patterns = [
        'market', 'expansion', 'expand', 'geography', 'region', 'country',
        'enter', 'entering', 'entry', 'latam', 'brazil', 'africa', 'asia',
        'europe', 'americas', 'growth', 'opportunity'
    ]
    if any(pat in text for pat in market_patterns):
        return 'market'

    # Product / launch patterns (check last - most generic)
    product_patterns = [
        'launch', 'launches', 'launched', 'unveil', 'unveiled', 'introduce',
        'introduces', 'introduced', 'release', 'released', 'new product',
        'new feature', 'platform', 'solution', 'technology', 'innovation',
        'upgrade', 'rollout', 'debut', 'announce', 'announcement'
    ]
    if any(pat in text for pat in product_patterns):
        return 'product'

    return 'general'


def article_matches_topic(row: pd.Series, topic: str) -> bool:
    """
    Check if an article matches the evidence criteria for a given topic.

    Args:
        row: Article DataFrame row with title, summary, content columns
        topic: One of 'executive', 'product', 'regulation', 'market', 'partnership', 'general'

    Returns:
        True if article is relevant evidence for this topic
    """
    title = str(row.get('title', '')).lower()
    summary = str(row.get('summary', '')).lower()
    content = str(row.get('content', '')).lower()[:500]  # First 500 chars
    combined = f"{title} {summary} {content}"

    if topic == 'executive':
        # Must have executive role keywords AND appointment verbs
        role_keywords = [
            'ceo', 'cfo', 'cto', 'coo', 'chief', 'director', 'vp',
            'vice president', 'president', 'officer', 'head of',
            'managing director', 'chairman', 'board member'
        ]
        action_keywords = [
            'appoint', 'appointed', 'hire', 'hired', 'hiring',
            'promote', 'promoted', 'join', 'joins', 'joined',
            'name', 'names', 'named', 'welcome', 'welcomes'
        ]
        has_role = any(kw in combined for kw in role_keywords)
        has_action = any(kw in combined for kw in action_keywords)
        return has_role and has_action

    elif topic == 'product':
        # Product launch keywords
        launch_keywords = [
            'launch', 'launches', 'launched', 'unveil', 'unveiled',
            'introduce', 'introduces', 'introduced', 'release', 'released',
            'debut', 'debuts', 'debuted', 'rollout', 'roll out', 'rolls out',
            'new platform', 'new product', 'new solution', 'new feature',
            'announces', 'announced', 'live with', 'goes live'
        ]
        return any(kw in combined for kw in launch_keywords)

    elif topic == 'regulation':
        # Regulatory and compliance keywords
        reg_keywords = [
            'regulat', 'compliance', 'license', 'licensing', 'licensed',
            'legal', 'legislation', 'law', 'government', 'authority',
            'commission', 'approval', 'approved', 'permit', 'certified',
            'certification', 'responsible gambling', 'safer gambling',
            'player protection', 'aml', 'kyc'
        ]
        return any(kw in combined for kw in reg_keywords)

    elif topic == 'market':
        # Market expansion and geography keywords
        market_keywords = [
            'expansion', 'expand', 'expands', 'expanded', 'enter', 'enters',
            'entered', 'entry', 'market', 'region', 'latam', 'brazil',
            'africa', 'asia', 'europe', 'americas', 'north america',
            'debut in', 'launches in', 'live in', 'available in'
        ]
        return any(kw in combined for kw in market_keywords)

    elif topic == 'partnership':
        # Partnership and M&A keywords
        partner_keywords = [
            'partner', 'partnership', 'partners with', 'acquisition',
            'acquire', 'acquires', 'acquired', 'merger', 'merges',
            'deal', 'agreement', 'collaboration', 'alliance',
            'joint venture', 'investment', 'stake', 'signs with'
        ]
        return any(kw in combined for kw in partner_keywords)

    else:  # 'general' - fall back to match anything
        return True


def article_matches_topic_dict(article: dict[str, Any], topic: str) -> bool:
    """
    Check if an article dict matches the evidence criteria for a given topic.

    Args:
        article: Article dict with title, summary, content keys
        topic: One of 'executive', 'product', 'regulation', 'market', 'partnership', 'general'

    Returns:
        True if article is relevant evidence for this topic
    """
    # Convert dict to Series-like object for the main function
    row = pd.Series(article)
    return article_matches_topic(row, topic)


def extract_gap_keywords(gap_title: str, gap_desc: str) -> list:
    """
    Extract specific keywords from gap that MUST appear in evidence articles.

    Returns list of keywords (at least one must match for relevant evidence).
    This ensures evidence articles are actually about the gap topic,
    not just generically matching the topic category.

    Fully dynamic - no hardcoded industry terms, works for any future topic.
    """
    text = f"{gap_title} {gap_desc}"
    keywords = []

    # 1. Brand/company names (acronyms, CamelCase) - DYNAMIC
    brands = re.findall(r'\b[A-Z][a-z]*[A-Z]+[a-z]*\b|\b[A-Z]{2,}\b', text)
    brands += [m.replace("'s", "") for m in re.findall(r"\b[A-Z][a-z]*'s\b", text)]
    keywords.extend([b for b in brands if len(b) >= 2 and b not in ['US', 'UK', 'EU', 'THE', 'AND', 'FOR', 'BUT', 'NOT']])

    # 2. Multi-word phrases (likely specific topics) - DYNAMIC
    # Extract 2-3 word capitalized phrases
    phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b', text)
    keywords.extend(phrases)

    # 3. Hyphenated terms (often industry-specific) - DYNAMIC
    hyphenated = re.findall(r'\b\w+-\w+(?:-\w+)?\b', text)
    keywords.extend(hyphenated)

    # 4. Words in quotes (explicitly important) - DYNAMIC
    quoted = re.findall(r'"([^"]+)"', text)
    keywords.extend(quoted)

    # 5. Fallback: Extract distinctive nouns from title (not generic words)
    generic_words = {
        'analysis', 'coverage', 'development', 'entry', 'impact', 'opportunity',
        'detailed', 'strategic', 'market', 'industry', 'specific', 'new',
        'into', 'with', 'from', 'about', 'this', 'that', 'their', 'these',
        'potential', 'emerging', 'growing', 'expanding', 'increasing'
    }
    words = re.findall(r'\b[A-Z][a-z]{3,}\b', gap_title)  # Capitalized words 4+ chars
    keywords.extend([w for w in words if w.lower() not in generic_words])

    # Deduplicate and return
    return list(set(keywords))


# Topic descriptions for display
TOPIC_DESCRIPTIONS = {
    'executive': 'Executive appointments and leadership changes',
    'product': 'Product launches and feature announcements',
    'regulation': 'Regulatory, compliance, and licensing news',
    'market': 'Market expansion and geographic growth',
    'partnership': 'Partnerships, acquisitions, and M&A',
    'general': 'General industry news'
}
