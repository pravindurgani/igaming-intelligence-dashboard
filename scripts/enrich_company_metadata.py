#!/usr/bin/env python3
"""
Company Metadata Enrichment Script

Auto-fills company type and segment when missing using deterministic rules.
Updates data/company_metadata_auto.json with inferred metadata and confidence scores.
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from paths import COMPANY_METADATA_JSON, NEWS_HISTORY_CSV

# Curated domain mappings for deterministic classification
REGULATOR_DOMAINS = {
    'UK Gambling Commission', 'Malta Gaming Authority', 'MGA',
    'Nevada Gaming Control Board', 'Gambling Commission',
    'Swedish Gambling Authority', 'Spelinspektionen',
    'Danish Gambling Authority', 'Spillemyndigheden',
    'Curacao Gaming Control Board', 'eGaming'
}

MEDIA_DOMAINS = {
    'SBC News', 'iGaming Business', 'CalvinAyre',
    'GamblingCompliance', 'EGR', 'European Gaming',
    'ICE Gaming', 'G3 Newswire', 'CDC Gaming Reports',
    'Gaming Intelligence', 'iGB', 'iGaming Times'
}

# Context tokens for type inference (case-insensitive)
OPERATOR_TOKENS = {'casino', 'casinos', 'slot', 'slots', 'sportsbook', 'betting', 'wager', 'wagering', 'igaming'}
SUPPLIER_TOKENS = {'platform', 'b2b', 'supplier', 'provider', 'content', 'software', 'technology', 'solution'}


def load_company_metadata():
    """Load existing company metadata."""
    if COMPANY_METADATA_JSON.exists():
        with open(COMPANY_METADATA_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_company_metadata(metadata):
    """Save company metadata to JSON."""
    with open(COMPANY_METADATA_JSON, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"✓ Saved enriched metadata to {COMPANY_METADATA_JSON}")


def build_company_contexts(csv_path, days=180):
    """
    Build context dictionary for each company from recent articles.

    Returns:
        dict: {company_name: {'contexts': [text1, text2, ...], 'topics': [topic1, topic2, ...]}}
    """
    if not csv_path.exists():
        print(f"⚠️  History CSV not found at {csv_path}")
        return {}

    df = pd.read_csv(csv_path)

    # Filter to last N days
    if 'published_date' in df.columns:
        df['published_date'] = pd.to_datetime(df['published_date'], errors='coerce')
        cutoff_date = datetime.now() - timedelta(days=days)
        df = df[df['published_date'] >= cutoff_date]

    print(f"📊 Processing {len(df)} articles from last {days} days")

    company_data = defaultdict(lambda: {'contexts': [], 'topics': []})

    # Extract company mentions from article metadata if available
    if 'companies_list' in df.columns:
        for _, row in df.iterrows():
            # Build context text from title + summary
            context = f"{row.get('title', '')} {row.get('summary', '')}"

            # Get companies mentioned (assumes companies_list is JSON or list-like)
            companies_str = row.get('companies_list', '')
            if pd.notna(companies_str) and companies_str:
                # Handle different formats (string representation of list, JSON, etc.)
                if isinstance(companies_str, str):
                    # Simple parsing: extract company names from list-like string
                    # This is a simplified approach; actual implementation may need more robust parsing
                    companies_str = companies_str.strip('[]').replace("'", "")
                    companies = [c.strip() for c in companies_str.split(',') if c.strip()]
                else:
                    companies = []

                for company in companies:
                    if company:
                        company_data[company]['contexts'].append(context.lower())

    print(f"✓ Built contexts for {len(company_data)} companies")
    return dict(company_data)


def infer_company_type(company_name, contexts):
    """
    Infer company type using deterministic rules.

    Returns:
        tuple: (type, confidence_score)
    """
    # Rule 1: Check if it's a regulator
    if 'regulator' in company_name.lower() or 'gaming authority' in company_name.lower():
        return 'regulator', 1.0

    for regulator in REGULATOR_DOMAINS:
        if regulator.lower() in company_name.lower():
            return 'regulator', 0.95

    # Rule 2: Check if it's media
    for media in MEDIA_DOMAINS:
        if media.lower() in company_name.lower():
            return 'media', 0.95

    # Rule 3: Context-based inference for operator vs supplier
    if not contexts:
        return 'unknown', 0.0

    # Count operator and supplier token occurrences
    operator_count = 0
    supplier_count = 0

    for context in contexts:
        # Simple token matching (within 10 words heuristic simplified to presence in same context)
        context_lower = context.lower()

        # Check for operator tokens
        for token in OPERATOR_TOKENS:
            if token in context_lower:
                operator_count += 1
                break  # Count once per article

        # Check for supplier tokens
        for token in SUPPLIER_TOKENS:
            if token in context_lower:
                supplier_count += 1
                break  # Count once per article

    # Determine type based on occurrence counts
    if operator_count >= 2:
        confidence = min(0.9, 0.5 + (operator_count * 0.1))
        return 'operator', confidence
    elif supplier_count >= 2:
        confidence = min(0.9, 0.5 + (supplier_count * 0.1))
        return 'supplier', confidence
    elif operator_count > 0:
        return 'operator', 0.4
    elif supplier_count > 0:
        return 'supplier', 0.4

    return 'unknown', 0.0


def infer_segment(contexts):
    """
    Infer company segment from context topics.

    Returns:
        tuple: (segment, confidence_score)
    """
    if not contexts:
        return 'unknown', 0.0

    # Simple keyword-based segment detection
    segment_keywords = {
        'sports': ['sports', 'sportsbook', 'betting', 'football', 'soccer', 'odds'],
        'casino': ['casino', 'slot', 'slots', 'roulette', 'blackjack', 'table games'],
        'poker': ['poker', 'tournament', 'wsop'],
        'lottery': ['lottery', 'lotto', 'draw'],
        'esports': ['esports', 'esport', 'gaming', 'competitive'],
        'payments': ['payment', 'transaction', 'wallet', 'crypto', 'blockchain'],
        'regulation': ['regulation', 'compliance', 'license', 'authority', 'legal']
    }

    segment_scores = Counter()

    for context in contexts:
        context_lower = context.lower()
        for segment, keywords in segment_keywords.items():
            for keyword in keywords:
                if keyword in context_lower:
                    segment_scores[segment] += 1
                    break  # Count once per article per segment

    if segment_scores:
        top_segment, count = segment_scores.most_common(1)[0]
        confidence = min(0.9, 0.3 + (count * 0.1))
        return top_segment, confidence

    return 'unknown', 0.0


def enrich_metadata():
    """Main enrichment function."""
    print("=" * 70)
    print("COMPANY METADATA ENRICHMENT")
    print("=" * 70)
    print()

    # Load existing metadata
    metadata = load_company_metadata()
    print(f"📋 Loaded {len(metadata)} existing company records")

    # Build contexts from historical articles
    company_contexts = build_company_contexts(NEWS_HISTORY_CSV, days=180)

    if not company_contexts:
        print("⚠️  No company contexts available. Enrichment skipped.")
        return

    # Enrich metadata
    enriched_count = 0
    updated_companies = []

    for company_name, context_data in company_contexts.items():
        contexts = context_data['contexts']

        # Get or create company entry
        if company_name not in metadata:
            metadata[company_name] = {
                'type': 'unknown',
                'segment': 'unknown',
                'enriched': True,
                'last_updated': datetime.now().isoformat()
            }

        company_entry = metadata[company_name]

        # Only infer if type is unknown or marked as enriched (not manually set)
        should_update_type = (
            company_entry.get('type') == 'unknown' or
            company_entry.get('enriched', False)
        )

        if should_update_type:
            inferred_type, type_confidence = infer_company_type(company_name, contexts)

            if inferred_type != 'unknown' and type_confidence > 0.5:
                company_entry['type'] = inferred_type
                company_entry['type_confidence'] = round(type_confidence, 2)
                company_entry['enriched'] = True
                company_entry['last_updated'] = datetime.now().isoformat()
                enriched_count += 1
                updated_companies.append({
                    'name': company_name,
                    'type': inferred_type,
                    'confidence': type_confidence
                })

        # Infer segment if unknown
        should_update_segment = (
            company_entry.get('segment') == 'unknown' or
            company_entry.get('enriched', False)
        )

        if should_update_segment:
            inferred_segment, segment_confidence = infer_segment(contexts)

            if inferred_segment != 'unknown' and segment_confidence > 0.4:
                company_entry['segment'] = inferred_segment
                company_entry['segment_confidence'] = round(segment_confidence, 2)
                company_entry['enriched'] = True
                company_entry['last_updated'] = datetime.now().isoformat()

    # Save enriched metadata
    save_company_metadata(metadata)

    print()
    print("=" * 70)
    print("ENRICHMENT SUMMARY")
    print("=" * 70)
    print(f"✓ Enriched {enriched_count} companies with inferred types")
    print()

    if updated_companies:
        print("Updated companies (top 10):")
        for company in updated_companies[:10]:
            print(f"  • {company['name']}: {company['type']} (confidence: {company['confidence']:.2f})")

    print()
    print("=" * 70)


if __name__ == "__main__":
    enrich_metadata()
