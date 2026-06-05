#!/usr/bin/env python3
"""
Taxonomy and Mapping System for iGaming Intelligence
Cleans up messy NER data by normalizing company names, regions, and topics.
"""

# Company name normalization - maps variations to canonical names
COMPANY_ALIASES = {
    # Flutter Entertainment
    'flutter entertainment': 'Flutter',
    'flutter plc': 'Flutter',
    'flutter entertainment plc': 'Flutter',

    # DraftKings
    'draftkings inc': 'DraftKings',
    'draftkings inc.': 'DraftKings',
    'draft kings': 'DraftKings',

    # FanDuel
    'fanduel group': 'FanDuel',
    'fan duel': 'FanDuel',

    # Entain
    'entain plc': 'Entain',
    'gvc holdings': 'Entain',

    # Evolution Gaming
    'evolution gaming': 'Evolution',
    'evolution gaming group': 'Evolution',

    # BetMGM
    'betmgm llc': 'BetMGM',
    'bet mgm': 'BetMGM',

    # Caesars
    'caesars entertainment': 'Caesars',
    'caesars entertainment inc': 'Caesars',

    # Penn Entertainment
    'penn entertainment': 'Penn Entertainment',
    'penn national gaming': 'Penn Entertainment',
    'penn interactive': 'Penn Entertainment',

    # Boyd Gaming
    'boyd gaming corporation': 'Boyd Gaming',

    # MGM
    'mgm resorts': 'MGM',
    'mgm resorts international': 'MGM',

    # Kambi
    'kambi group': 'Kambi',
    'kambi group plc': 'Kambi',

    # Playtech
    'playtech plc': 'Playtech',

    # IGT
    'international game technology': 'IGT',
    'igt plc': 'IGT',

    # Aristocrat
    'aristocrat leisure': 'Aristocrat',
    'aristocrat leisure limited': 'Aristocrat',

    # Light & Wonder
    'light & wonder': 'Light & Wonder',
    'light and wonder': 'Light & Wonder',
    'scientific games': 'Light & Wonder',

    # Sportradar
    'sportradar group': 'Sportradar',
    'sportradar ag': 'Sportradar',

    # Genius Sports
    'genius sports group': 'Genius Sports',
    'genius sports limited': 'Genius Sports',

    # GeoComply
    'geocomply solutions': 'GeoComply',

    # Fanatics
    'fanatics betting': 'Fanatics',
    'fanatics gaming': 'Fanatics',

    # Betsson
    'betsson group': 'Betsson',
    'betsson ab': 'Betsson',

    # Kindred
    'kindred group': 'Kindred',
    'kindred group plc': 'Kindred',

    # 888
    '888 holdings': '888',
    '888 holdings plc': '888',

    # Wynn
    'wynn resorts': 'Wynn',
    'wynn interactive': 'Wynn',

    # Las Vegas Sands
    'las vegas sands corp': 'Las Vegas Sands',
    'lvs': 'Las Vegas Sands',

    # Tabcorp
    'tabcorp holdings': 'Tabcorp',

    # BetMakers
    'betmakers technology': 'BetMakers',
    'betmakers technology group': 'BetMakers',

    # OpenBet
    'openbet (igt)': 'OpenBet',

    # SBTech
    'sbtech (draftkings)': 'SBTech',

    # Evoke
    'evoke plc': 'Evoke',
    '888 (evoke)': 'Evoke',

    # Inspired
    'inspired entertainment': 'Inspired',

    # Novomatic
    'novomatic ag': 'Novomatic',

    # Konami
    'konami gaming': 'Konami',
    'konami holdings': 'Konami',

    # PMU (French horse racing operator)
    'pmu': 'PMU',
    'pari mutuel urbain': 'PMU',
    'pari mutuel urbain (pmu)': 'PMU',
    'pari mutuel urbain (pmu': 'PMU',  # Truncated variant from NER
}

# Region mapping - maps locations to broader geographic regions
REGION_MAPPING = {
    # North America
    'united states': 'North America',
    'usa': 'North America',
    'us': 'North America',
    'america': 'North America',
    'canada': 'North America',

    # US States (all 50 states + DC + territories for comprehensive coverage)
    'alabama': 'North America',
    'alaska': 'North America',
    'arizona': 'North America',
    'arkansas': 'North America',
    'california': 'North America',
    'colorado': 'North America',
    'connecticut': 'North America',
    'delaware': 'North America',
    'florida': 'North America',
    'georgia': 'North America',
    'hawaii': 'North America',
    'idaho': 'North America',
    'illinois': 'North America',
    'indiana': 'North America',
    'iowa': 'North America',
    'kansas': 'North America',
    'kentucky': 'North America',
    'louisiana': 'North America',
    'maine': 'North America',
    'maryland': 'North America',
    'massachusetts': 'North America',
    'michigan': 'North America',
    'minnesota': 'North America',
    'mississippi': 'North America',
    'missouri': 'North America',
    'montana': 'North America',
    'nebraska': 'North America',
    'nevada': 'North America',
    'new hampshire': 'North America',
    'new jersey': 'North America',
    'new mexico': 'North America',
    'new york': 'North America',
    'north carolina': 'North America',
    'north dakota': 'North America',
    'ohio': 'North America',
    'oklahoma': 'North America',
    'oregon': 'North America',
    'pennsylvania': 'North America',
    'rhode island': 'North America',
    'south carolina': 'North America',
    'south dakota': 'North America',
    'tennessee': 'North America',
    'texas': 'North America',
    'utah': 'North America',
    'vermont': 'North America',
    'virginia': 'North America',
    'washington': 'North America',
    'washington state': 'North America',
    'west virginia': 'North America',
    'wisconsin': 'North America',
    'wyoming': 'North America',
    'washington d.c.': 'North America',
    'washington dc': 'North America',
    'dc': 'North America',

    # US Gaming Cities
    'las vegas': 'North America',
    'vegas': 'North America',
    'atlantic city': 'North America',
    'reno': 'North America',

    # Canada
    'ontario': 'North America',

    # Europe
    'united kingdom': 'Europe',
    'uk': 'Europe',
    'britain': 'Europe',
    'great britain': 'Europe',
    'england': 'Europe',
    'scotland': 'Europe',
    'wales': 'Europe',
    'ireland': 'Europe',
    'germany': 'Europe',
    'france': 'Europe',
    'spain': 'Europe',
    'italy': 'Europe',
    'netherlands': 'Europe',
    'sweden': 'Europe',
    'denmark': 'Europe',
    'norway': 'Europe',
    'finland': 'Europe',
    'switzerland': 'Europe',
    'austria': 'Europe',
    'belgium': 'Europe',
    'portugal': 'Europe',
    'greece': 'Europe',
    'czech republic': 'Europe',
    'poland': 'Europe',
    'malta': 'Europe',
    'gibraltar': 'Europe',
    'cyprus': 'Europe',

    # Latin America (LatAm) - comprehensive coverage
    'brazil': 'LatAm',
    'brasil': 'LatAm',
    'argentina': 'LatAm',
    'colombia': 'LatAm',
    'peru': 'LatAm',
    'chile': 'LatAm',
    'uruguay': 'LatAm',
    'paraguay': 'LatAm',
    'venezuela': 'LatAm',
    'ecuador': 'LatAm',
    'bolivia': 'LatAm',
    'panama': 'LatAm',
    'costa rica': 'LatAm',
    'mexico': 'LatAm',
    'guatemala': 'LatAm',
    'honduras': 'LatAm',
    'el salvador': 'LatAm',
    'nicaragua': 'LatAm',
    'belize': 'LatAm',
    'cuba': 'LatAm',
    'dominican republic': 'LatAm',
    'haiti': 'LatAm',
    'jamaica': 'LatAm',
    'trinidad and tobago': 'LatAm',
    'trinidad': 'LatAm',
    'tobago': 'LatAm',
    'barbados': 'LatAm',
    'bahamas': 'LatAm',
    'aruba': 'LatAm',
    'curacao': 'LatAm',
    'curaçao': 'LatAm',
    'bonaire': 'LatAm',
    'sint maarten': 'LatAm',
    'saint martin': 'LatAm',
    'anguilla': 'LatAm',
    'antigua': 'LatAm',
    'barbuda': 'LatAm',
    'antigua and barbuda': 'LatAm',
    'dominica': 'LatAm',
    'grenada': 'LatAm',
    'saint lucia': 'LatAm',
    'saint vincent': 'LatAm',
    'grenadines': 'LatAm',
    'saint kitts': 'LatAm',
    'nevis': 'LatAm',
    'montserrat': 'LatAm',
    'cayman islands': 'LatAm',
    'turks and caicos': 'LatAm',
    'british virgin islands': 'LatAm',
    'us virgin islands': 'LatAm',
    'puerto rico': 'LatAm',
    'guyana': 'LatAm',
    'suriname': 'LatAm',
    'french guiana': 'LatAm',
    'guadeloupe': 'LatAm',
    'martinique': 'LatAm',
    'saba': 'LatAm',
    'sint eustatius': 'LatAm',
    'buenos aires': 'LatAm',
    'sao paulo': 'LatAm',
    'são paulo': 'LatAm',
    'rio de janeiro': 'LatAm',
    'caribbean': 'LatAm',
    'latin america': 'LatAm',
    'latin-america': 'LatAm',
    'latam': 'LatAm',

    # Asia Pacific
    'australia': 'Asia Pacific',
    'new zealand': 'Asia Pacific',
    'japan': 'Asia Pacific',
    'south korea': 'Asia Pacific',
    'singapore': 'Asia Pacific',
    'hong kong': 'Asia Pacific',
    'macau': 'Asia Pacific',
    'philippines': 'Asia Pacific',
    'thailand': 'Asia Pacific',
    'vietnam': 'Asia Pacific',
    'india': 'Asia Pacific',
    'china': 'Asia Pacific',
    'taiwan': 'Asia Pacific',
    'malaysia': 'Asia Pacific',
    'indonesia': 'Asia Pacific',

    # Middle East & Africa
    'united arab emirates': 'Middle East & Africa',
    'uae': 'Middle East & Africa',
    'dubai': 'Middle East & Africa',
    'south africa': 'Middle East & Africa',
    'kenya': 'Middle East & Africa',
    'nigeria': 'Middle East & Africa',
    'egypt': 'Middle East & Africa',
    'morocco': 'Middle East & Africa',
    'israel': 'Middle East & Africa',
    'saudi arabia': 'Middle East & Africa',
    'mena': 'Middle East & Africa',
    'gcc': 'Middle East & Africa',
    'middle east': 'Middle East & Africa',
    'mea': 'Middle East & Africa',
    'africa': 'Middle East & Africa',
}

# Topic clustering - groups related keywords into strategic themes
TOPIC_CLUSTERS = {
    # Regulation & Compliance
    'regulation': 'Regulation & Compliance',
    'regulatory': 'Regulation & Compliance',
    'compliance': 'Regulation & Compliance',
    'license': 'Regulation & Compliance',
    'licensing': 'Regulation & Compliance',
    'legal': 'Regulation & Compliance',
    'law': 'Regulation & Compliance',
    'legislation': 'Regulation & Compliance',
    'tax': 'Regulation & Compliance',
    'taxation': 'Regulation & Compliance',
    'ban': 'Regulation & Compliance',
    'banned': 'Regulation & Compliance',
    'prohibition': 'Regulation & Compliance',
    'fine': 'Regulation & Compliance',
    'penalty': 'Regulation & Compliance',
    'sanction': 'Regulation & Compliance',
    'regulator': 'Regulation & Compliance',
    'gambling commission': 'Regulation & Compliance',

    # M&A and Corporate
    'merger': 'M&A & Partnerships',
    'acquisition': 'M&A & Partnerships',
    'deal': 'M&A & Partnerships',
    'partnership': 'M&A & Partnerships',
    'joint venture': 'M&A & Partnerships',
    'investment': 'M&A & Partnerships',
    'funding': 'M&A & Partnerships',
    'takeover': 'M&A & Partnerships',
    'buyout': 'M&A & Partnerships',

    # Technology & Innovation
    'technology': 'Technology & Innovation',
    'innovation': 'Technology & Innovation',
    'ai': 'Technology & Innovation',
    'artificial intelligence': 'Technology & Innovation',
    'blockchain': 'Technology & Innovation',
    'cryptocurrency': 'Technology & Innovation',
    'crypto': 'Technology & Innovation',
    'bitcoin': 'Technology & Innovation',
    'nft': 'Technology & Innovation',
    'web3': 'Technology & Innovation',
    'platform': 'Technology & Innovation',
    'mobile': 'Technology & Innovation',
    'app': 'Technology & Innovation',
    'digital': 'Technology & Innovation',

    # Sports Betting - expanded for better detection
    'sports betting': 'Sports Betting',
    'sportsbook': 'Sports Betting',
    'sports book': 'Sports Betting',
    'sports wagering': 'Sports Betting',
    'betting odds': 'Sports Betting',
    'odds': 'Sports Betting',
    'in-play': 'Sports Betting',
    'live betting': 'Sports Betting',
    'parlay': 'Sports Betting',
    'point spread': 'Sports Betting',
    'moneyline': 'Sports Betting',
    'over/under': 'Sports Betting',
    'over under': 'Sports Betting',
    'sports handle': 'Sports Betting',
    'betting handle': 'Sports Betting',
    'betting revenue': 'Sports Betting',
    'nfl betting': 'Sports Betting',
    'nba betting': 'Sports Betting',
    'mlb betting': 'Sports Betting',
    'nhl betting': 'Sports Betting',
    'horse racing': 'Sports Betting',
    'race betting': 'Sports Betting',
    'prop bet': 'Sports Betting',
    'prop bets': 'Sports Betting',
    'futures bet': 'Sports Betting',

    # Responsible Gaming
    'responsible gaming': 'Responsible Gaming',
    'responsible gambling': 'Responsible Gaming',
    'problem gambling': 'Responsible Gaming',
    'addiction': 'Responsible Gaming',
    'self-exclusion': 'Responsible Gaming',
    'safer gambling': 'Responsible Gaming',

    # Esports & New Verticals
    'esports': 'Esports & Emerging',
    'e-sports': 'Esports & Emerging',
    'daily fantasy': 'Esports & Emerging',
    'dfs': 'Esports & Emerging',
    'prediction market': 'Esports & Emerging',
    'prediction markets': 'Esports & Emerging',
    'social casino': 'Esports & Emerging',

    # Market Expansion
    'expansion': 'Market Expansion',
    'launch': 'Market Expansion',
    'enter': 'Market Expansion',
    'debut': 'Market Expansion',
    'growth': 'Market Expansion',
}

# Entities to strictly ignore (generic/noise words)
IGNORE_ENTITIES = {
    # Generic industry terms
    'Gaming', 'Casino', 'Casinos', 'iGaming', 'Betting', 'Sports',
    'Online', 'Digital', 'Market', 'Markets', 'Industry', 'Business',
    'Company', 'Companies', 'Operator', 'Operators', 'Platform', 'Platforms',

    # Generic words
    'Report', 'Reports', 'News', 'Article', 'Articles', 'Story', 'Stories',
    'Year', 'Month', 'Week', 'Day', 'Time', 'Today', 'Yesterday',
    'How', 'What', 'Why', 'When', 'Where', 'New', 'Latest', 'First',
    'Last', 'Next', 'Top', 'Best', 'Big', 'Major', 'Key', 'Main',

    # Known competitors (already in KNOWN_COMPETITORS in dashboard.py)
    'SBC News', 'SBC', 'iGaming Future', 'Next.io', 'SiGMA World',
    'SiGMA', 'EGR Global', 'EGR', 'CDC Gaming', 'CDC', 'Global Gaming Insider',
    'iGaming Today',

    # Internal brands (already in INTERNAL_BRANDS in dashboard.py)
    'iGaming Business', 'iGB', 'iGB Affiliate', 'GGB Magazine', 'GGB',
    'ICE Gaming', 'ICE', 'Clarion', 'Clarion Events',

    # Common false positives
    'Group', 'Holdings', 'International', 'Global', 'World', 'Entertainment',
    'Interactive', 'Solutions', 'Services', 'Technologies',

    # Generic organizational terms
    'Board', 'Board Member', 'Council', 'Committee',
}

# Precompute lowercased ignore set for case-insensitive matching
IGNORE_ENTITIES_LOWER = {e.strip().lower() for e in IGNORE_ENTITIES}

# Job titles and executive role terms (separate from generic ignore list)
ROLE_TERMS = {
    # C-suite abbreviations
    'CEO', 'CFO', 'COO', 'CTO', 'CMO', 'CIO', 'CRO', 'CPO', 'CHRO', 'CSO', 'CDO',

    # Full C-suite titles
    'Chief Executive Officer',
    'Chief Financial Officer',
    'Chief Operating Officer',
    'Chief Technology Officer',
    'Chief Marketing Officer',
    'Chief Information Officer',
    'Chief Revenue Officer',
    'Chief Product Officer',
    'Chief Human Resources Officer',
    'Chief Strategy Officer',
    'Chief Data Officer',
    'Chief Commercial Officer',
    'Chief Legal Officer',
    'Chief Compliance Officer',
    'Chief Risk Officer',
    'Chief Security Officer',

    # Other executive positions
    'Chairman', 'Chairwoman', 'Chairperson', 'Chair',
    'President', 'Vice President', 'VP', 'EVP', 'SVP', 'AVP',
    'Director', 'Managing Director', 'Executive Director',
    'General Manager', 'Manager',
    'Commissioner', 'Minister', 'Secretary', 'Ambassador',
    'Head', 'Chief', 'Officer',
    'Founder', 'Co-Founder', 'Owner', 'Partner',
}

# Precompute lowercased role terms for case-insensitive matching
ROLE_TERMS_LOWER = {r.strip().lower() for r in ROLE_TERMS}

# Platform and publisher domains to exclude from company detection
# These are non-gambling tech companies that shouldn't appear in sponsor lists
DOMAIN_STOPLIST = {
    'google.com',
    'youtube.com',
    'x.com',
    'twitter.com',
    'linkedin.com',
    'instagram.com',
    'facebook.com',
    'meta.com',
    'apple.com',
    'amazon.com',
    'microsoft.com',
    'tiktok.com',
    'whatsapp.com'
}


def is_platform_domain(host: str) -> bool:
    """
    Check if a domain is a generic platform/publisher that should be excluded.

    Args:
        host: Domain name to check (e.g., 'www.google.com' or 'google.com')

    Returns:
        True if the domain is in the platform stoplist
    """
    h = host.lower()
    if h.startswith('www.'):
        h = h[4:]
    return any(h == d or h.endswith('.' + d) for d in DOMAIN_STOPLIST)


def normalize_company(entity_name: str) -> str:
    """
    Normalize company name to canonical form.

    Args:
        entity_name: Raw entity name from NER

    Returns:
        Canonical company name, or original if no mapping exists
    """
    # Convert to lowercase for lookup
    lookup_key = entity_name.lower().strip()

    # Check if it's in the alias mapping
    if lookup_key in COMPANY_ALIASES:
        return COMPANY_ALIASES[lookup_key]

    # Return original if no mapping found
    return entity_name


def normalize_region(entity_name: str) -> str | None:
    """
    Map location to broader geographic region.

    Args:
        entity_name: Raw location name from NER

    Returns:
        Regional grouping (e.g., 'LatAm', 'North America'), or None if not recognized as a location
    """
    if not entity_name:
        return None

    # Convert to lowercase for lookup
    lookup_key = entity_name.lower().strip()

    # Check if it's in the region mapping
    if lookup_key in REGION_MAPPING:
        return REGION_MAPPING[lookup_key]

    # Unknown or noisy entity - treat as non-geographic
    return None


def classify_topic(text: str) -> list:
    """
    Classify text into topic clusters based on keyword matching.

    Args:
        text: Article title or summary text

    Returns:
        List of topic cluster names found in the text
    """
    text_lower = text.lower()
    topics_found = set()

    for keyword, cluster in TOPIC_CLUSTERS.items():
        if keyword in text_lower:
            topics_found.add(cluster)

    return list(topics_found)


def should_ignore(entity_name: str) -> bool:
    """
    Check if an entity should be filtered out as noise.

    Now truly case-insensitive and filters common role titles like CEO, CFO, etc.

    Args:
        entity_name: Entity name to check

    Returns:
        True if entity should be ignored, False otherwise

    Examples:
        >>> should_ignore("CEO")
        True
        >>> should_ignore("cfo")
        True
        >>> should_ignore("Chief Financial Officer")
        True
        >>> should_ignore("Gaming")
        True
        >>> should_ignore("DraftKings")
        False
    """
    if not entity_name:
        return True

    # Normalize: strip whitespace and lowercase once
    name = entity_name.strip().lower()

    # Check if empty after stripping
    if not name:
        return True

    # Check if too short or just numbers
    if len(name) < 3 or name.isdigit():
        return True

    # Check against generic ignore list (case-insensitive)
    if name in IGNORE_ENTITIES_LOWER:
        return True

    # Check against role terms (case-insensitive)
    if name in ROLE_TERMS_LOWER:
        return True

    # Pattern matching for role-like strings
    # e.g., "chief technology officer", "vice president of marketing"
    if name.startswith("chief ") and " officer" in name:
        return True

    if name.endswith(" officer") and len(name.split()) <= 4:
        # Catches things like "compliance officer", "risk officer"
        return True

    return False


def get_region_stats():
    """
    Get statistics about region mappings.

    Returns:
        Dictionary with region counts
    """
    region_counts = {}
    for location, region in REGION_MAPPING.items():
        region_counts[region] = region_counts.get(region, 0) + 1

    return region_counts


def get_company_count():
    """
    Get count of unique canonical companies.

    Returns:
        Number of unique companies
    """
    return len(set(COMPANY_ALIASES.values()))


def get_topic_count():
    """
    Get count of unique topic clusters.

    Returns:
        Number of unique topics
    """
    return len(set(TOPIC_CLUSTERS.values()))


if __name__ == "__main__":
    # Test the taxonomy functions
    print("=== Taxonomy System Test ===\n")

    print("Company Normalization:")
    print(f"  'flutter entertainment' → {normalize_company('flutter entertainment')}")
    print(f"  'DraftKings Inc' → {normalize_company('DraftKings Inc')}")
    print(f"  'Unknown Corp' → {normalize_company('Unknown Corp')}\n")

    print("Region Mapping:")
    print(f"  'Brazil' → {normalize_region('Brazil')}")
    print(f"  'Sao Paulo' → {normalize_region('Sao Paulo')}")
    print(f"  'Nevada' → {normalize_region('Nevada')}")
    print(f"  'Unknown Country' → {normalize_region('Unknown Country')}\n")

    print("Topic Classification:")
    test_text = "New tax regulations for sports betting operators in Brazil"
    print(f"  Text: '{test_text}'")
    print(f"  Topics: {classify_topic(test_text)}\n")

    print("Ignore Filter:")
    print(f"  'Gaming' → Ignore: {should_ignore('Gaming')}")
    print(f"  'DraftKings' → Ignore: {should_ignore('DraftKings')}\n")

    print("Statistics:")
    print(f"  Unique companies: {get_company_count()}")
    print(f"  Unique topics: {get_topic_count()}")
    print("  Region mapping:")
    for region, count in get_region_stats().items():
        print(f"    {region}: {count} locations")
