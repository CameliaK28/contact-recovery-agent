"""
Search Module - Multi-channel search for customer contact information

Constructs search queries and performs web searches across multiple channels:
1. Company official website
2. Google Business / Maps
3. Social media public pages
4. Business directories

Key improvements:
- Quoted company name search to avoid word-level matching
- Smart location extraction (city name from postal-code lines)
- Email username search (often the brand name on social media)
- Site-specific social media searches (site:instagram.com, etc.)
- Region-aware directory terms (pagesjaunes.fr for France, etc.)
- Direct website guess from email domain
- DDGS region parameter based on customer address country
"""

import re
import logging
from typing import List, Dict, Optional
from ddgs import DDGS
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Country -> DDGS region code mapping
COUNTRY_REGION_MAP = {
    "france": "fr", "fr": "fr", "franca": "fr",
    "germany": "de", "deutschland": "de", "de": "de",
    "spain": "es", "espana": "es", "es": "es",
    "italy": "it", "italia": "it", "it": "it",
    "united kingdom": "uk", "uk": "uk", "england": "uk", "scotland": "uk",
    "netherlands": "nl", "nl": "nl",
    "belgium": "be", "be": "be",
    "switzerland": "ch", "ch": "ch",
    "united states": "us", "usa": "us", "us": "us",
    "canada": "ca", "ca": "ca",
    "australia": "au", "au": "au",
    "japan": "jp", "jp": "jp",
    "china": "cn", "cn": "cn",
    "portugal": "pt", "pt": "pt",
    "poland": "pl", "pl": "pl",
    "sweden": "se", "se": "se",
    "norway": "no", "no": "no",
    "denmark": "dk", "dk": "dk",
    "finland": "fi", "fi": "fi",
    "ireland": "ie", "ie": "ie",
    "austria": "at", "at": "at",
}

# Country -> local directory sites for search and boost
COUNTRY_DIRECTORIES = {
    "france": ["pagesjaunes.fr", "societe.com", "doctrine.fr", "annuaire.com"],
    "germany": ["das-oertliche.de", "gelbeseiten.de", "handelsregister.de"],
    "spain": ["paginasamarillas.es", "axesor.es"],
    "italy": ["paginebianche.it", "paginegialle.it"],
    "united kingdom": ["yell.com", "companieshouse.gov.uk", "thomsonlocal.com"],
    "netherlands": ["detelefoongids.nl", "kvk.nl"],
    "united states": ["yellowpages.com", "bbb.org", "yelp.com", "manta.com"],
    "canada": ["yellowpages.ca", "canada411.ca"],
    "australia": ["yellowpages.com.au", "truelocal.com.au", "abr.business.gov.au", "whitepages.com.au"],
}

# Generic directory sites that work internationally
INTERNATIONAL_DIRECTORIES = ["opencorporates.com", "linkedin.com", "facebook.com"]


def _extract_country(address: str) -> str:
    """Extract country name from address text."""
    if not address:
        return ""
    addr_lower = address.lower().strip()
    # Split address into words for word-level matching
    # This prevents short codes like "it" matching inside "united" or "fr" inside "france"
    parts = re.split(r'[,\n]', addr_lower)

    # Check each comma-separated part for country names
    # Long names first (to match "united kingdom" before "uk", etc.)
    sorted_countries = sorted(COUNTRY_REGION_MAP.keys(), key=len, reverse=True)

    for country in sorted_countries:
        # For short codes (<=3 chars), require word-level match
        if len(country) <= 3:
            # Match as standalone word or comma-separated part
            if any(part.strip() == country for part in parts):
                return country
            # Also match as word in longer parts
            if re.search(r'\b' + re.escape(country) + r'\b', addr_lower):
                return country
        else:
            # Longer names can use substring matching (they won't false-match)
            if country in addr_lower:
                return country

    return parts[-1].strip() if parts else ""


def _get_region(address: str) -> str:
    """Get DDGS region code from address."""
    country = _extract_country(address)
    return COUNTRY_REGION_MAP.get(country, "")


def _extract_city(address: str) -> str:
    """
    Extract city name from address, handling postal-code prefixed lines.
    e.g. "69250 Montanay" -> "Montanay"
         "Atlanta GA 30307" -> "Atlanta"
         "Warrington, WA5 8WX" -> "Warrington" (WA5 8WX is a UK postcode, filtered)
         "MILLMERRAN QLD 4357" -> "MILLMERRAN" (Australian CITY STATE POSTCODE)
    Prefers shorter parts (city names) over street addresses.
    Filters out standalone postal codes (US, UK, Canadian, Australian formats).
    """
    if not address:
        return ""
    parts = re.split(r'[,\n]', address)
    cities = []
    # Street type words to exclude
    street_types = {'allée', 'allee', 'avenue', 'ave', 'street', 'st', 'road', 'rd',
                    'boulevard', 'blvd', 'drive', 'dr', 'lane', 'ln', 'way',
                    'rue', 'place', 'pl', 'court', 'ct', 'square', 'sq',
                    'close', 'crescent', 'croft', 'mews', 'row', 'gate',
                    'haven', 'hill', 'wharf', 'quay', 'grove', 'walk',
                    'view', 'green', 'promenade', 'parade', 'embankment'}

    # Postal code regex patterns (for standalone postal code detection)
    uk_zip = re.compile(r'^[A-Z]{1,2}\d[A-Z\d]?\s\d[A-Z]{1,2}$', re.IGNORECASE)
    us_zip = re.compile(r'^\d{5}(?:[-\s]\d{4})?$')
    ca_zip = re.compile(r'^[A-Z]\d[A-Z]\s\d[A-Z]\d$', re.IGNORECASE)

    # Australian state abbreviations for CITY STATE POSTCODE pattern
    au_states = {'NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'ACT'}

    # PO BOX keywords to exclude
    po_box_words = {'po', 'box', 'p.o.', 'postal', 'gpo'}

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # If line starts with digits (postal code prefix), extract the text after
        m = re.match(r'^\d+\s+(.+)', part)
        if m:
            city = m.group(1).strip()
            # For US addresses like "Atlanta GA 30307", extract just the city
            city_cleaned = re.sub(r'\s+[A-Z]{2}\s+\d+', '', city)
            city_cleaned = city_cleaned.strip()
            if city_cleaned:
                words = set(city_cleaned.lower().split())
                # Skip if it looks like a street address (contains street type words)
                if not (words & street_types):
                    cities.append(city_cleaned)
            continue

        # Australian CITY STATE POSTCODE pattern: "MILLMERRAN QLD 4357"
        au_match = re.match(r'^(.+?)\s+(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s+\d{4}\s*$', part, re.IGNORECASE)
        if au_match:
            city_name = au_match.group(1).strip()
            words = set(city_name.lower().split())
            if not (words & street_types) and not (words & po_box_words):
                cities.append(city_name)
            continue

        # Skip standalone postal codes (pure postal code parts with no city name)
        if uk_zip.match(part) or us_zip.match(part) or ca_zip.match(part):
            continue
        # Skip standalone Australian postcodes (4 digits only)
        if re.match(r'^\d{4}\s*$', part):
            continue
        # Skip AU state+postcode like "QLD 4357"
        if re.match(r'^\s*(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s+\d{4}\s*$', part, re.IGNORECASE):
            continue

        # Skip pure numbers
        if re.match(r'^\d+$', part):
            continue

        # Skip PO BOX lines
        po_words = set(part.lower().split())
        if po_words & po_box_words:
            continue

        # Non-numeric line, could be city or country
        words = set(part.lower().split())
        if part.lower() not in COUNTRY_REGION_MAP and not (words & street_types):
            # Clean up: remove US state abbreviations and ZIP codes from city names
            # e.g. "Atlanta GA 30307" -> "Atlanta"
            cleaned = re.sub(r'\s+[A-Z]{2}\s+\d{5}(?:[-\s]\d{4})?\s*$', '', part)
            cleaned = re.sub(r'\s+\d{5}(?:[-\s]\d{4})?\s*$', '', cleaned)  # Remove trailing ZIP
            cleaned = re.sub(r'\s+[A-Z]{2}\s*$', '', cleaned)  # Remove trailing state abbr
            # Also remove Australian state+postcode: "MILLMERRAN QLD 4357" -> "MILLMERRAN"
            cleaned = re.sub(r'\s+(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s+\d{4}\s*$', '', cleaned, flags=re.IGNORECASE)
            # Also remove standalone Australian state abbreviation
            cleaned = re.sub(r'\s+(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s*$', '', cleaned, flags=re.IGNORECASE)
            cleaned = cleaned.strip()
            if cleaned and cleaned.lower() not in COUNTRY_REGION_MAP:
                cities.append(cleaned)

    return cities[-1] if cities else ""


def _extract_location_parts(address: str) -> List[str]:
    """
    Extract all meaningful location words from address.
    Includes city, country, and street area names.
    Filters out street addresses (which contain street type words)
    and postal codes (US, UK, Canadian, Australian formats).
    Also filters PO BOX lines.
    """
    parts = []
    if not address:
        return parts

    # Street type words to exclude
    street_types = {'allée', 'allee', 'avenue', 'ave', 'street', 'st', 'road', 'rd',
                    'boulevard', 'blvd', 'drive', 'dr', 'lane', 'ln', 'way',
                    'rue', 'place', 'pl', 'court', 'ct', 'square', 'sq',
                    'close', 'crescent', 'croft', 'mews', 'row', 'gate',
                    'haven', 'hill', 'wharf', 'quay', 'grove', 'walk',
                    'view', 'green', 'promenade', 'parade', 'embankment'}

    # Postal code regex patterns
    uk_zip = re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s\d[A-Z]{1,2}\b', re.IGNORECASE)
    us_zip = re.compile(r'\b\d{5}(?:[-\s]\d{4})?\b')
    ca_zip = re.compile(r'\b[A-Z]\d[A-Z]\s\d[A-Z]\d\b', re.IGNORECASE)

    # Australian state abbreviations
    au_states_re = re.compile(r'\b(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\b', re.IGNORECASE)
    au_postcode_re = re.compile(r'\b\d{4}\b')

    # PO BOX keywords to exclude
    po_box_words = {'po', 'box', 'p.o.', 'postal', 'gpo'}

    city = _extract_city(address)
    if city:
        parts.append(city)

    country = _extract_country(address)
    if country:
        parts.append(country)

    # Also extract any other meaningful parts
    for raw_part in re.split(r'[,\n]', address):
        raw_part = raw_part.strip()
        if not raw_part:
            continue
        # Skip PO BOX lines
        po_words = set(raw_part.lower().split())
        if po_words & po_box_words:
            continue
        # Skip postal codes (UK, US, Canadian)
        if uk_zip.search(raw_part) or us_zip.search(raw_part) or ca_zip.search(raw_part):
            continue
        # Skip Australian state+postcode patterns like "QLD 4357" or standalone 4-digit postcodes
        if re.match(r'^\s*(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s+\d{4}\s*$', raw_part, re.IGNORECASE):
            continue
        if re.match(r'^\d{4}\s*$', raw_part):
            continue
        # Skip pure numbers or postal codes
        if re.match(r'^\d+(\s+[A-Z]{2})?$', raw_part):
            continue
        # Check for street type words
        words = set(raw_part.lower().split())
        if words & street_types:
            continue  # Skip street addresses
        # Extract text after postal code
        m = re.match(r'^\d+\s+(.+)', raw_part)
        if m:
            text = m.group(1).strip()
            # Remove state abbreviations
            text = re.sub(r'\s+[A-Z]{2}\s*$', '', text)
            if text and text.lower() not in [p.lower() for p in parts]:
                # Also skip if it's a postal code
                if not (uk_zip.search(text) or us_zip.search(text) or ca_zip.search(text)):
                    parts.append(text)
        elif raw_part.lower() not in [p.lower() for p in parts]:
            # Don't add if it's a country (already added)
            if raw_part.lower() not in COUNTRY_REGION_MAP:
                # Clean up Australian CITY STATE POSTCODE pattern
                au_match = re.match(r'^(.+?)\s+(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s+\d{4}\s*$', raw_part, re.IGNORECASE)
                if au_match:
                    city_name = au_match.group(1).strip()
                    if city_name.lower() not in [p.lower() for p in parts]:
                        parts.append(city_name)
                else:
                    parts.append(raw_part)

    return parts


def build_search_queries(customer_info: Dict) -> List[Dict]:
    """
    Step 1: Build customer identity profile and form search keywords.

    Returns a list of search query configurations, each targeting a specific channel.
    Strategy:
    - Use quoted company name for exact phrase matching
    - Include city name for disambiguation
    - Search email username (often brand name on social media)
    - Site-specific social media searches
    - Region-appropriate directory terms
    - Direct website guess from email domain
    """
    name = customer_info.get("name", "")
    company = customer_info.get("company", "")
    email = customer_info.get("email", "")
    phone = customer_info.get("phone", "")
    address = customer_info.get("address", "")

    # Extract location info
    city = _extract_city(address)
    country = _extract_country(address)
    location_parts = _extract_location_parts(address)
    location = " ".join(location_parts[:2]) if location_parts else ""

    # Quoted company name for exact phrase matching
    quoted_company = f'"{company}"' if company else ""

    # Extract email username (often the brand name on social media)
    email_username = ""
    email_domain = ""
    if email and "@" in email:
        email_parts = email.split("@")
        email_username = email_parts[0]
        email_domain = email_parts[1]

    # Get region-appropriate directory terms
    country_directories = COUNTRY_DIRECTORIES.get(country, [])
    if not country_directories:
        # Fallback: use international directories
        country_directories = INTERNATIONAL_DIRECTORIES

    queries = []

    # === Query 1: Quoted company + city (most targeted) ===
    if company:
        if city:
            queries.append({
                "channel": "official_website",
                "query": f'{quoted_company} {city}',
                "priority": 1
            })
        if location:
            queries.append({
                "channel": "official_website",
                "query": f'{quoted_company} {location} contact',
                "priority": 1
            })
        queries.append({
            "channel": "official_website",
            "query": f'{quoted_company} official website',
            "priority": 1
        })

    # === Query 2: Email username search (brand name on social media) ===
    if email_username and len(email_username) > 2:
        queries.append({
            "channel": "email_username",
            "query": email_username,
            "priority": 1
        })

    # === Query 3: Direct website guess from email domain ===
    # ISP/personal email domains are excluded — they're not company websites
    isp_domains = ["gmail.com", "yahoo.com", "hotmail.com",
                   "outlook.com", "icloud.com", "live.com",
                   "aol.com", "protonmail.com", "gmx.com",
                   "btinternet.com", "virginmedia.com", "sky.com",
                   "talktalk.net", "tiscali.co.uk", "orange.fr",
                   "free.fr", "sfr.fr", "wanadoo.fr", "laposte.net",
                   "mail.ru", "yandex.ru", "163.com", "126.com",
                   "qq.com", "sina.com", "wo.cn", "189.cn"]
    if email_domain and email_domain.lower() not in isp_domains:
        queries.append({
            "channel": "email_domain",
            "query": f'site:{email_domain}',
            "priority": 1
        })

    # === Query 4: Social media site-specific searches ===
    if company:
        for site in ["instagram.com", "facebook.com"]:
            queries.append({
                "channel": "social_media",
                "query": f'site:{site} {quoted_company}',
                "priority": 2
            })
        # Also search with email username on social media
        if email_username and len(email_username) > 2:
            queries.append({
                "channel": "social_media",
                "query": f'site:instagram.com {email_username}',
                "priority": 2
            })

    # === Query 5: LinkedIn search ===
    if company:
        queries.append({
            "channel": "social_media",
            "query": f'site:linkedin.com {quoted_company}',
            "priority": 2
        })

    # === Query 6: Phone number search ===
    if phone and company:
        queries.append({
            "channel": "phone_search",
            "query": f'"{phone}" {quoted_company}',
            "priority": 2
        })

    # === Query 7: Maps / local business ===
    if company and city:
        queries.append({
            "channel": "google_maps",
            "query": f'{quoted_company} {city} phone number',
            "priority": 2
        })

    # === Query 8: Business directories (region-appropriate) ===
    if company:
        # Use first 2 local directory sites
        dir_str = " ".join(country_directories[:2])
        queries.append({
            "channel": "business_directory",
            "query": f'{quoted_company} {city or country} {dir_str}',
            "priority": 3
        })

    # === Query 9: Person search (with company) ===
    if name and company:
        queries.append({
            "channel": "person_search",
            "query": f'"{name}" {quoted_company}',
            "priority": 2
        })

    # === Query 10: Person-name-based search (no company required) ===
    # When company is missing, search by person name on social media + location
    if name and not company:
        quoted_name = f'"{name}"'

        # Social media site-specific searches by name
        for site in ["facebook.com", "instagram.com", "linkedin.com"]:
            queries.append({
                "channel": "social_media",
                "query": f'site:{site} {quoted_name}',
                "priority": 1
            })

        # Name + location for disambiguation
        if city:
            queries.append({
                "channel": "person_search",
                "query": f'{quoted_name} {city}',
                "priority": 1
            })
        elif location:
            queries.append({
                "channel": "person_search",
                "query": f'{quoted_name} {location}',
                "priority": 1
            })

        # Name + phone
        if phone:
            queries.append({
                "channel": "person_search",
                "query": f'{quoted_name} "{phone}"',
                "priority": 2
            })

        # Name + email username (they might use same handle on social media)
        if email_username and len(email_username) > 2:
            queries.append({
                "channel": "person_search",
                "query": f'{quoted_name} {email_username}',
                "priority": 2
            })
            # Also search the email username directly on social media
            # (email handle IS often the social handle)
            for site in ["instagram.com", "facebook.com", "twitter.com"]:
                queries.append({
                    "channel": "social_media",
                    "query": f'site:{site} {email_username}',
                    "priority": 2
                })

        # General name search (use country if city already has a query above)
        general_loc = country if city else (city or country)
        if general_loc:
            queries.append({
                "channel": "person_search",
                "query": f'{quoted_name} {general_loc}',
                "priority": 2
            })

    return queries


def build_secondary_searches(customer_info: Dict, discovered_handles: List[str],
                              discovered_names: List[str] = None) -> List[Dict]:
    """
    Step 1b: Build secondary search queries using information discovered
    during the initial search round.
    
    When we find a confirmed Instagram profile like @joshiel_mundell,
    we can search for the same handle on Facebook, LinkedIn, Twitter, etc.
    This cross-platform search dramatically improves accuracy for person searches.
    
    Args:
        customer_info: Original customer information dict
        discovered_handles: List of social media handles/username extracted
            from confirmed/potential social profiles found in first round
        discovered_names: Optional list of additional name variants found
            (e.g., nicknames, alternate spellings from social profiles)
    
    Returns:
        List of secondary search query configurations
    """
    queries = []
    address = customer_info.get("address", "")
    name = customer_info.get("name", "")
    
    # Get region for search
    region = _get_region(address)
    
    for handle in discovered_handles:
        if not handle or len(handle) < 3:
            continue
        
        # Search this handle on other social platforms
        # This is the key improvement: confirmed IG handle → search FB/LinkedIn/Twitter
        for site in ["facebook.com", "linkedin.com", "twitter.com", "x.com"]:
            queries.append({
                "channel": "cross_platform_search",
                "query": f'site:{site} {handle}',
                "priority": 1  # High priority - this is targeted verification
            })
        
        # Also search handle + name for disambiguation
        if name:
            quoted_name = f'"{name}"'
            queries.append({
                "channel": "cross_platform_search",
                "query": f'{handle} {quoted_name}',
                "priority": 1
            })
        
        # Search handle + location for further disambiguation
        city = _extract_city(address)
        if city:
            queries.append({
                "channel": "cross_platform_search",
                "query": f'{handle} {city}',
                "priority": 2
            })
    
    # If discovered alternative names, search those too
    if discovered_names:
        for alt_name in discovered_names:
            if not alt_name or len(alt_name) < 3:
                continue
            alt_name_words = alt_name.split()
            # Only search if it's a meaningful name (not just a single very short word)
            if len(alt_name_words) >= 2 or (len(alt_name_words) == 1 and len(alt_name_words[0]) > 3):
                quoted_alt = f'"{alt_name}"'
                for site in ["facebook.com", "instagram.com", "linkedin.com"]:
                    queries.append({
                        "channel": "cross_platform_search",
                        "query": f'site:{site} {quoted_alt}',
                        "priority": 2
                    })
    
    return queries


def execute_searches(queries: List[Dict], max_results_per_query: int = 5,
                     address: str = "") -> List[Dict]:
    """
    Step 2: Execute multi-channel searches.

    Returns a list of search results with URL, title, description, and channel info.
    Uses region parameter based on customer's address country.
    """
    all_results = []
    seen_urls = set()

    # Determine region from address
    region = _get_region(address) if address else ""

    with DDGS() as ddgs:
        for query_config in queries:
            query = query_config["query"]
            channel = query_config["channel"]
            priority = query_config["priority"]

            logger.info(f"Searching [{channel}]: {query}")

            try:
                # Use region parameter if available
                kwargs = {"max_results": max_results_per_query}
                if region:
                    kwargs["region"] = region

                results = ddgs.text(
    query,
    **kwargs,
    backend="duckduckgo"
)
                for r in results:
                    url = r.get("href", "")
                    title = r.get("title", "")
                    desc = r.get("body", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append({
                            "url": url,
                            "title": title,
                            "description": desc,
                            "channel": channel,
                            "priority": priority,
                            "query": query
                        })
            except Exception as e:
                logger.warning(f"Search failed for query '{query}': {e}")
                results = fallback_search(query, max_results_per_query)
                # Retry without region if region caused issues
                if region:
                    try:
                        results = ddgs.text(
    query,
    max_results=max_results_per_query,
    backend="duckduckgo"
)
                        for r in results:
                            url = r.get("href", "")
                            title = r.get("title", "")
                            desc = r.get("body", "")
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                all_results.append({
                                    "url": url,
                                    "title": title,
                                    "description": desc,
                                    "channel": channel,
                                    "priority": priority,
                                    "query": query
                                })
                    except Exception as e2:
                        logger.warning(f"Retry without region also failed for '{query}': {e2}")
                        continue

    # Sort by priority (lower = higher priority)
    all_results.sort(key=lambda x: x["priority"])

    # Limit total results
    max_total = 30
    if len(all_results) > max_total:
        all_results = all_results[:max_total]

    logger.info(f"Total unique URLs found: {len(all_results)}")
    return all_results


def filter_relevant_urls(search_results: List[Dict], customer_info: Dict) -> List[Dict]:
    """
    Filter search results to prioritize URLs likely to contain contact information.
    Region-aware: uses local directory sites based on customer's country.
    """
    company = customer_info.get("company", "").lower()
    name = customer_info.get("name", "").lower()
    address = customer_info.get("address", "")

    # Extract location words
    location_parts = _extract_location_parts(address)
    location_words = []
    for part in location_parts:
        for w in part.lower().split():
            if len(w) > 2:
                location_words.append(w)

    # Get country-appropriate directory sites
    country = _extract_country(address)
    country_dir_sites = COUNTRY_DIRECTORIES.get(country, [])
    if not country_dir_sites:
        country_dir_sites = INTERNATIONAL_DIRECTORIES

    # Contact info keywords
    contact_keywords = [
        "contact", "about", "team", "staff", "reach", "touch",
        "support", "customer service", "phone", "email",
        "directory", "listing", "profile", "business"
    ]

    # Strong exclusion keywords
    exclude_keywords = [
        "job", "career", "hiring", "employment", "salary",
        "review", "rating", "complaint", "lawsuit",
        "wikihow", "tutorial", "how to", "opinion"
    ]

    # Sites that are almost always irrelevant for contact recovery
    irrelevant_sites = [
        "wikihow.com", "wikipedia.org", "reddit.com", "quora.com",
        "medium.com", "pinterest.com", "tiktok.com/discover",
        "youtube.com/watch", "booking.com", "tripadvisor.com",
        "glassdoor.com", "indeed.com", "zillow.com",
        "businessinsider.com/reference", "w3schools.com"
    ]

    # Email username (for relevance scoring)
    email = customer_info.get("email", "")
    email_username = ""
    if email and "@" in email:
        email_username = email.split("@")[0].lower()

    filtered = []
    for result in search_results:
        url = result["url"].lower()
        title = result["title"].lower()
        desc = result.get("description", "").lower()
        combined = f"{url} {title} {desc}"

        # Hard exclude: irrelevant sites
        if any(site in url for site in irrelevant_sites):
            continue

        # Hard exclude: very obvious non-contact content
        if any(kw in combined for kw in ["how to contact instagram", "how to contact facebook",
                                          "gmail login", "how to contact google"]):
            continue

        score = 0

        # Company name match (strong signal) - check both quoted and unquoted
        if company:
            company_clean = company.replace('"', '')
            company_words = [w for w in company_clean.split() if len(w) > 2]
            matched = sum(1 for w in company_words if w in combined)
            if matched >= len(company_words):
                score += 5  # Full match
            elif matched >= len(company_words) * 0.5:
                score += 3  # Partial match
        else:
            # No company: use person name as primary signal
            if name:
                name_words = [w for w in name.split() if len(w) > 2]
                name_matched = sum(1 for w in name_words if w in combined)
                if name_matched >= len(name_words):
                    score += 5  # Full name match
                elif name_matched >= len(name_words) * 0.5:
                    score += 3  # Partial name match

        # Email username match (very strong signal - it's often the brand name)
        if email_username and len(email_username) > 2:
            if email_username in combined:
                score += 5

        # Location match (strong signal for disambiguation)
        loc_matched = sum(1 for w in location_words if w in combined)
        if loc_matched >= 2:
            score += 4  # Strong location match
        elif loc_matched >= 1:
            score += 2

        # Contact keywords
        contact_count = sum(1 for kw in contact_keywords if kw in combined)
        score += min(contact_count, 3)

        # Exclusion penalty
        if any(kw in combined for kw in exclude_keywords):
            score -= 3

        # URL path boosts
        if any(kw in url for kw in ["contact", "about", "team", "support"]):
            score += 4

        # Region-appropriate directory site boost
        for dir_site in country_dir_sites:
            if dir_site in url:
                score += 3
                break

        # International directory boost
        if any(site in url for site in INTERNATIONAL_DIRECTORIES):
            score += 2

        # Social media site boost
        social_sites = ["facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
                        "youtube.com", "tiktok.com"]
        if any(site in url for site in social_sites):
            score += 2

        # Direct domain match boost (email domain == URL domain)
        if email and "@" in email:
            email_domain = email.split("@")[1].lower()
            if email_domain in url:
                score += 5

        result["relevance_score"] = score

        # Only keep results with positive relevance
        if score >= 1:
            filtered.append(result)

    # Sort by relevance score
    filtered.sort(key=lambda x: x["relevance_score"], reverse=True)

    # Limit to most relevant
    max_filtered = 18
    if len(filtered) > max_filtered:
        filtered = filtered[:max_filtered]

    logger.info(f"Filtered to {len(filtered)} relevant URLs (from {len(search_results)})")
    return filtered


def fallback_search(query, max_results=5):
    url = "https://html.duckduckgo.com/html/"
    try:
        r = requests.post(
            url,
            data={"q": query},
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        soup = BeautifulSoup(r.text, "html.parser")

        results = []

        for a in soup.select(".result__a")[:max_results]:
            results.append({
                "url": a.get("href", ""),
                "title": a.get_text(),
                "description": ""
            })

        return results

    except Exception:
        return []