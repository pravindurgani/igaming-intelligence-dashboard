"""
Text normalization utilities for unified search across the dashboard.

Ensures consistent matching between News Feed and Context Explorer:
- Normalizes case and accents
- Handles camelCase and compound terms (iGaming -> i gaming -> gaming)
- Normalizes industry-specific terms (eCricket -> cricket, eSports -> esports)
"""

import re
import unicodedata

import pandas as pd


def normalize_text(text: str) -> str:
    """
    Normalize text for consistent searching.

    Transformations applied:
    1. NFKD unicode normalization + remove accents
    2. Insert spaces at camelCase boundaries (iGaming -> i Gaming)
    3. Insert spaces at letter-digit boundaries (B2B -> B 2 B)
    4. Convert to lowercase
    5. Replace punctuation with spaces
    6. Normalize industry terms:
       - 'i gaming' -> 'igaming gaming'
       - 'e cricket' -> 'ecricket cricket'
       - 'e sports' / 'e-sports' -> 'esports'
    7. Collapse whitespace

    Args:
        text: Input text to normalize

    Returns:
        Normalized text string
    """
    if not isinstance(text, str):
        return ""

    if not text.strip():
        return ""

    # 1. NFKD normalization - decompose unicode characters
    text = unicodedata.normalize('NFKD', text)

    # Remove combining characters (accents)
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')

    # 2. Insert space at camelCase boundaries BEFORE lowercasing
    # iGaming -> i Gaming, eCricket -> e Cricket
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    # Handle sequences like "iGB" -> "i G B" -> later normalized
    text = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', text)

    # 3. Insert spaces at letter-digit boundaries
    # B2B -> B 2 B, G2G -> G 2 G
    text = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', text)
    text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', text)

    # 4. NOW convert to lowercase (after camelCase splitting)
    text = text.lower()

    # 5. Replace punctuation with spaces (keep alphanumeric)
    text = re.sub(r'[^\w\s]', ' ', text)

    # 6. Normalize industry-specific terms
    # Note: Apply these AFTER punctuation removal so 'e-sports' becomes 'e sports' first

    # 'i gaming' -> keep both 'igaming' and 'gaming' for matching
    text = re.sub(r'\bi\s+gaming\b', 'igaming gaming', text)

    # 'e cricket' -> keep both 'ecricket' and 'cricket'
    text = re.sub(r'\be\s+cricket\b', 'ecricket cricket', text)

    # 'e sports' -> 'esports'
    text = re.sub(r'\be\s+sports?\b', 'esports', text)

    # Also handle 'esport' singular
    text = re.sub(r'\besport\b', 'esports', text)

    # 7. Collapse whitespace
    text = ' '.join(text.split())

    return text


def build_search_field(row: pd.Series) -> str:
    """
    Build a combined, normalized search field from an article row.

    Concatenates title, summary, and content (if present) and normalizes.

    Args:
        row: DataFrame row with article data

    Returns:
        Normalized combined text for searching
    """
    parts = []

    # Get title
    title = row.get('title')
    if title and isinstance(title, str) and title.strip():
        parts.append(title)

    # Get summary
    summary = row.get('summary')
    if summary and isinstance(summary, str) and summary.strip():
        parts.append(summary)

    # Get content
    content = row.get('content')
    if content and isinstance(content, str) and content.strip():
        parts.append(content)

    combined = ' '.join(parts)
    return normalize_text(combined)


def has_content(row: pd.Series) -> bool:
    """
    Check if a row has article content (body text).

    Args:
        row: DataFrame row with article data

    Returns:
        True if content field is non-empty
    """
    content = row.get('content')
    return bool(content and isinstance(content, str) and content.strip())
