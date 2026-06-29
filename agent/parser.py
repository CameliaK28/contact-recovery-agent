"""
Intelligent text parser for free-form customer information.

Parses pasted text like:
    Thomas Cater III
    Muse Studios
    museatlantastaff@gmail.com
    +1 404-795-7907
    1522 Dekalb Ave NE
    Atlanta GA 30307
    United States

Into structured fields: name, company, email, phone, address.
"""

import re
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

PHONE_RE = re.compile(
    r'(?:\+?\d{1,3}[\s.\-]?)?'
    r'(?:\(?\d{1,4}\)?[\s.\-]?)?'
    r'\d{1,4}[\s.\-]?\d{1,4}[\s.\-]?\d{1,9}'
)

# US ZIP code pattern
ZIP_RE = re.compile(r'\b\d{5}(?:[-\s]\d{4})?\b')

# UK postcode pattern (e.g. WA5 8WX, SW1A 1AA, M1 1AE, B33 8TH)
UK_ZIP_RE = re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s\d[A-Z]{1,2}\b', re.IGNORECASE)

# Canadian postal code pattern (e.g. K1A 0B1)
CA_ZIP_RE = re.compile(r'\b[A-Z]\d[A-Z]\s\d[A-Z]\d\b', re.IGNORECASE)

# Australian postcode pattern (4 digits, e.g. 4357, 2000, 0800)
AU_ZIP_RE = re.compile(r'\b\d{4}\b')

# Australian state abbreviations and full names
AU_STATES_ABBR = {'NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'ACT'}
AU_STATES_FULL = {
    'new south wales', 'victoria', 'queensland',
    'south australia', 'western australia', 'tasmania',
    'northern territory', 'australian capital territory',
}

STREET_SUFFIXES = {
    'ave', 'avenue', 'blvd', 'boulevard', 'st', 'street', 'rd', 'road',
    'dr', 'drive', 'ln', 'lane', 'ct', 'court', 'pl', 'place', 'cir',
    'circle', 'way', 'pkwy', 'parkway', 'hwy', 'highway', 'loop', 'sq',
    'square', 'ter', 'terrace', 'trail', 'trl', 'ne', 'nw', 'se', 'sw',
    'east', 'west', 'north', 'south',
    # UK-specific suffixes
    'close', 'crescent', 'croft', 'mews', 'row', 'garth', 'gate',
    'haven', 'hill', 'wharf', 'quay', 'meadow', 'orchard', 'grove',
    'walk', 'ride', 'vale', 'view', 'green', 'promenade', 'circus',
    'parade', 'embankment', 'bank', 'ford', 'cross', 'end', 'fold',
    'ham', 'heath', 'holm', 'moor', 'nook', 'port', 'stock', 'marsh',
    'beck', 'burn', 'dene', 'gill', 'lea', 'ing', 'ness', 'wold',
    'yard', 'flats', 'estate',
}

# PO BOX / Postal box patterns (address component, not company)
PO_BOX_KEYWORDS = {'po', 'p.o.', 'postal', 'box', 'pobox', 'gpo'}

US_STATES_ABBR = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
}
US_STATES_FULL = {
    'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
    'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho',
    'illinois', 'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana',
    'maine', 'maryland', 'massachusetts', 'michigan', 'minnesota',
    'mississippi', 'missouri', 'montana', 'nebraska', 'nevada',
    'new hampshire', 'new jersey', 'new mexico', 'new york', 'north carolina',
    'north dakota', 'ohio', 'oklahoma', 'oregon', 'pennsylvania',
    'rhode island', 'south carolina', 'south dakota', 'tennessee', 'texas',
    'utah', 'vermont', 'virginia', 'washington', 'west virginia', 'wisconsin',
    'wyoming', 'district of columbia',
}
# Australian state abbreviations and full names
AU_STATES_ABBR = {'NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'ACT'}
AU_STATES_FULL = {
    'new south wales', 'victoria', 'queensland',
    'south australia', 'western australia', 'tasmania',
    'northern territory', 'australian capital territory',
}
COUNTRIES = {
    'united states', 'usa', 'us', 'united states of america',
    'canada', 'mexico', 'united kingdom', 'uk', 'australia',
    'germany', 'france', 'spain', 'italy', 'japan', 'china', 'india',
    'brazil', 'netherlands', 'switzerland', 'singapore',
    'ireland', 'new zealand', 'south korea', 'korea', 'taiwan', 'hong kong',
}

COMPANY_KEYWORDS = {
    'inc', 'llc', 'ltd', 'corp', 'corporation', 'company', 'co', 'group',
    'studio', 'studios', 'agency', 'consulting', 'solutions', 'services',
    'technologies', 'technology', 'systems', 'enterprises', 'associates',
    'partners', 'holding', 'holdings', 'capital', 'ventures', 'media',
    'design', 'marketing', 'law', 'clinic', 'university', 'college',
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_customer_text(raw_text: str) -> Dict:
    """
    Parse free-form pasted text into structured customer fields.
    Returns dict with keys: name, company, email, phone, address, confidence, warnings.
    """
    raw_text = raw_text.strip()
    if not raw_text:
        return _empty_result()

    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    warnings: List[str] = []
    used: set = set()

    # 1. Email
    email, eidx = _find_email(lines)
    if email:
        used.add(eidx)
    else:
        warnings.append("No email found")

    # 2. Phone
    phone, pidx = _find_phone(lines)
    if phone:
        used.add(pidx)
    else:
        warnings.append("No phone number found")

    # 3. Address block
    address, aidx = _find_address_block(lines)
    used.update(aidx)
    if not address:
        warnings.append("No address detected")

    # 4. Name / Company from remaining lines
    remaining = [lines[i] for i in range(len(lines)) if i not in used]
    name, company = _infer_name_company(remaining, email)

    confidence = _score_confidence(name, company, email, phone, address)

    return {
        "name": name,
        "company": company,
        "email": email,
        "phone": phone,
        "address": address,
        "confidence": confidence,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def _find_email(lines: List[str]) -> Tuple[str, int]:
    for i, line in enumerate(lines):
        m = EMAIL_RE.search(line)
        if m:
            return m.group(), i
    return "", -1


def _find_phone(lines: List[str]) -> Tuple[str, int]:
    best = ""
    best_idx = -1
    best_score = 0
    for i, line in enumerate(lines):
        for m in PHONE_RE.finditer(line):
            raw = m.group()
            score = _phone_quality(raw)
            if score > best_score:
                best_score = score
                best = re.sub(r'\s+', ' ', raw).strip()
                best_idx = i
    return best, best_idx


def _phone_quality(s: str) -> int:
    digits = re.sub(r'\D', '', s)
    if len(digits) < 7 or len(digits) > 15:
        return 0
    score = min(len(digits), 12)
    if '+' in s:
        score += 2
    if re.search(r'[a-zA-Z]', s):
        score -= 10
    return max(score, 0)


# ---------------------------------------------------------------------------
# Address extraction — simple top-down approach
# ---------------------------------------------------------------------------

def _line_is_address(line: str) -> bool:
    """
    Return True if line looks like part of an address.
    Address signals are checked first to avoid misclassifying
    address lines that happen to start with a number.
    IMPORTANT: Exclusion checks (email, phone) must come BEFORE
    _starts_with_street_number, otherwise a phone number starting
    with digits gets misclassified as a street number.
    """
    if not line:
        return False
    lower = line.lower().strip()

    # --- Definitely NOT address (check FIRST, before street-number check) ---
    # A line containing an email is NOT an address line
    if '@' in line or EMAIL_RE.search(line):
        return False
    # A line that is primarily a phone number is NOT an address line
    if _looks_like_phone_line(line):
        return False

    # --- Definitely address ---
    if ZIP_RE.search(line):
        return True
    if UK_ZIP_RE.search(line):
        return True
    if CA_ZIP_RE.search(line):
        return True
    # Australian postcode: "4357", "QLD 4357", "MILLMERRAN QLD 4357"
    # Only match 4-digit patterns that look like Australian postcodes
    # (not US 5-digit, not random 4-digit numbers in text)
    if _is_au_postcode_line(line):
        return True
    if _starts_with_street_number(line):
        return True
    # PO BOX lines are address components
    if _is_po_box_line(lower):
        return True
    words = set(re.findall(r'[a-zA-Z]+', lower))
    if words & STREET_SUFFIXES:
        return True
    if lower in COUNTRIES or lower in US_STATES_FULL or lower in AU_STATES_FULL:
        return True
    if _is_us_state(lower):
        return True
    if _is_au_state(lower):
        return True

    return False


def _looks_like_phone_line(line: str) -> bool:
    """
    Return True only if the line is primarily a phone number.
    Avoid matching street numbers like '1522 Main St'.
    """
    m = PHONE_RE.search(line)
    if not m:
        return False
    digits = re.sub(r'\D', '', m.group())
    # Legitimate phone numbers have at least 7 digits
    if len(digits) < 7:
        return False
    # The matched portion should be a substantial part of the line
    if len(m.group()) / max(len(line.strip()), 1) > 0.4:
        return True
    return False


def _starts_with_street_number(line: str) -> bool:
    return bool(re.match(r'^\d+\s', line.strip()))


def _is_us_state(lower: str) -> bool:
    bare = lower.strip().rstrip(',').strip()
    return bare in US_STATES_ABBR or bare in US_STATES_FULL


def _is_au_state(lower: str) -> bool:
    """Check if line is or contains an Australian state abbreviation."""
    bare = lower.strip().rstrip(',').strip()
    return bare in AU_STATES_ABBR or bare in AU_STATES_FULL


def _is_au_postcode_line(line: str) -> bool:
    """
    Check if line contains an Australian postcode pattern.
    Australian postcodes are 4 digits, but we need to distinguish them
    from random 4-digit numbers. Valid patterns:
    - Standalone: "4357" (only if no other content)
    - With state: "QLD 4357", "NSW 2000"
    - City+state+postcode: "MILLMERRAN QLD 4357"
    NOT matched: random 4-digit numbers embedded in longer text (e.g. phone parts)
    """
    stripped = line.strip()
    # Pattern: CITY STATE POSTCODE (e.g. "MILLMERRAN QLD 4357")
    if re.match(r'^[A-Z\s]+\s+(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s+\d{4}$', stripped, re.IGNORECASE):
        return True
    # Pattern: STATE POSTCODE (e.g. "QLD 4357")
    if re.match(r'^\s*(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s+\d{4}\s*$', stripped, re.IGNORECASE):
        return True
    # Pattern: standalone 4-digit postcode (only if short line)
    if re.match(r'^\d{4}\s*$', stripped):
        return True
    return False


def _is_po_box_line(lower: str) -> bool:
    """Check if line contains PO BOX pattern."""
    # Patterns: "PO BOX 475", "P.O. Box 475", "Postal Box 475", "GPO Box 475"
    if re.match(r'^\s*(po|p\.o\.|postal|gpo)\s+box\b', lower):
        return True
    return False


def _find_address_block(lines: List[str]) -> Tuple[str, List[int]]:
    """
    Find the contiguous block of address lines.
    Enhanced: allows gaps of up to 2 non-address lines between address lines.
    This handles multi-line addresses like:
        47 Vermont close   (address)
        Warrington         (city - not tagged as address by _line_is_address)
        WA5 8WX            (postcode - address)
        United Kingdom     (country - address)
    Without gap tolerance, the "Warrington" gap would split the address into fragments.
    """
    tags = [_line_is_address(line) for line in lines]

    best_start = -1
    best_end = -1  # exclusive

    # Strategy: find "anchor" address lines and merge them with nearby lines
    # An anchor is a True-tagged line. We allow gaps of up to 2 False lines
    # between anchors, as they're likely city/state lines.

    i = 0
    while i < len(tags):
        if not tags[i]:
            i += 1
            continue
        # Found start of an address block
        start = i
        gap_count = 0
        while i < len(tags):
            if tags[i]:
                # Address line — reset gap counter
                gap_count = 0
                i += 1
            else:
                # Non-address line within the block
                gap_count += 1
                if gap_count > 2:
                    # Too many non-address lines — block ends here
                    break
                # But check: is this gap line a plausible address continuation?
                # Single-word lines or short lines between address lines are likely
                # city/state names that _line_is_address didn't recognize
                gap_line = lines[i].strip()
                gap_lower = gap_line.lower()
                # Don't include lines that are clearly not address (name, email, company)
                if '@' in gap_line or EMAIL_RE.search(gap_line):
                    break
                if _looks_like_phone_line(gap_line):
                    break
                # Single-word or two-word lines are likely city/state names
                # Longer lines (3+ words) might be company names — skip them
                # unless they contain location keywords
                gap_words = gap_line.split()
                if len(gap_words) <= 2:
                    i += 1  # Include short gap lines (likely city/state)
                elif len(gap_words) <= 4 and any(
                    w.lower() in {'county', 'province', 'region', 'district',
                                   'borough', 'town', 'city', 'village', 'area'}
                    for w in gap_words
                ):
                    i += 1  # Include lines with location keywords
                else:
                    break  # Longer gap lines — likely company/name, end block

        end = i
        # Also check if next line after block is a country name
        if i < len(lines) and lines[i].strip().lower() in COUNTRIES:
            end = i + 1
            i += 1

        # Update best block
        if end - start > best_end - best_start:
            best_start, best_end = start, end

    if best_start < 0:
        return "", []

    indices = list(range(best_start, best_end))
    return ", ".join(lines[k] for k in indices), indices


def _line_looks_like_continuation(line: str) -> bool:
    """Return True if line could be a continuation of an address (e.g. 'Suite 100')."""
    lower = line.lower().strip()
    if not lower:
        return False
    # Suite/unit on its own line
    if re.match(r'^(suite|ste|unit|apt|room|floor|fl|building|bldg)\b', lower):
        return True
    # Country name
    if lower in COUNTRIES:
        return True
    return False


# ---------------------------------------------------------------------------
# Name / Company inference
# ---------------------------------------------------------------------------

def _infer_name_company(remaining: List[str], email: str) -> Tuple[str, str]:
    if not remaining:
        return "", ""

    # First, filter remaining lines to exclude lines that look like
    # postal codes, country names, or other address fragments (not company/name)
    filtered = []
    for line in remaining:
        lower = line.lower().strip()
        # Skip postal codes (UK, US, Canadian, Australian)
        if UK_ZIP_RE.search(line) or ZIP_RE.search(line) or CA_ZIP_RE.search(line):
            continue
        # Skip Australian postcode patterns (e.g. "4357", "QLD 4357", "MILLMERRAN QLD 4357")
        if _is_au_postcode_line(line):
            continue
        # Skip country names
        if lower in COUNTRIES or lower in US_STATES_FULL or lower in US_STATES_ABBR:
            continue
        # Skip Australian state abbreviations and full names
        if lower in AU_STATES_ABBR or lower in AU_STATES_FULL:
            continue
        # Skip lines that are primarily digits or alphanumeric postal areas
        if re.match(r'^[\d\s]+$', line) and len(line.strip()) <= 10:
            continue
        # Skip very short uppercase lines (likely postal areas, state codes)
        # but NOT if they contain company keywords (like "CO", "LTD")
        if line == line.upper() and len(line.strip()) <= 8 and len(line.strip()) >= 2:
            lower_words = set(lower.split())
            if not (lower_words & COMPANY_KEYWORDS):
                continue
        filtered.append(line)

    if not filtered:
        # Everything was address fragments — try to infer company from email domain
        company_from_email = _infer_company_from_email(email)
        return "", company_from_email

    # Build scoring for each filtered line
    domain_hint = ""
    email_domain_full = ""
    if email and '@' in email:
        try:
            email_domain_full = email.split('@')[1].lower()
            # For .com.au, .co.uk, etc., the company name is in the subdomain part
            # e.g. eepaktransport.com.au -> "eepaktransport"
            domain_hint = email_domain_full.split('.')[0].lower()
        except Exception:
            pass

    # Also try to infer company from full email domain (handles .com.au, .co.uk)
    company_from_email = _infer_company_from_email(email)

    # Email username hint (often matches name or social handle)
    email_username = ""
    if email and '@' in email:
        email_username = email.split('@')[0].lower()

    scored = []
    for line in filtered:
        score = 0
        lower = line.lower()
        # Company keyword
        for kw in COMPANY_KEYWORDS:
            if kw in lower:
                score += 10
        # Domain hint (first part of email domain)
        if domain_hint and domain_hint in lower.replace(' ', '').lower():
            score += 15
        # Full email domain match (eepaktransport.com.au matches "eepaktransport" in company)
        if email_domain_full:
            domain_no_tld = email_domain_full.split('.')[0].lower()
            if domain_no_tld in lower.replace(' ', '').lower():
                score += 15
        # All caps (only for longer lines — short caps are likely postal codes, already filtered)
        if line == line.upper() and len(line) > 8:
            score += 5
        # Legal suffix
        if re.search(r'\b(inc|llc|ltd|corp|gmbh|co\.?|ltd\.?)\b', lower):
            score += 20
        # Email username match (person might use similar name in company)
        if email_username and email_username in lower.replace(' ', '').lower():
            score += 5
        scored.append((score, line))

    scored.sort(key=lambda x: -x[0])

    company = ""
    name = ""
    if scored and scored[0][0] > 0:
        company = scored[0][1]
        # Name = first remaining line that isn't company
        for s, line in scored[1:]:
            if line != company:
                name = line
                break
    else:
        # No company signal from text lines — try email domain inference
        name = filtered[0] if filtered else ""
        company = company_from_email  # May be "" if email is personal/ISP

    # If we found a name but no company, and email suggests a company, use it
    if name and not company and company_from_email:
        company = company_from_email

    return name.strip(), company.strip()


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def _infer_company_from_email(email: str) -> str:
    """
    Infer company name from email domain.
    Handles multi-part TLDs like .com.au, .co.uk, .com.br.
    e.g. patricia@eepaktransport.com.au -> "Eepak Transport"
         info@naweandco.gmail.com -> "" (ISP/personal)
    """
    if not email or '@' not in email:
        return ""

    domain = email.split('@')[1].lower()

    # ISP/personal email domains — can't infer company
    isp_domains = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "icloud.com", "live.com", "aol.com", "protonmail.com",
        "gmx.com", "mail.com", "zoho.com", "yandex.com",
        "btinternet.com", "virginmedia.com", "sky.com",
        "talktalk.net", "orange.fr", "free.fr", "sfr.fr",
        "wanadoo.fr", "laposte.net", "163.com", "126.com",
        "qq.com", "sina.com",
    }
    if domain in isp_domains:
        return ""

    # Extract the company name part from domain
    # eepaktransport.com.au -> "eepaktransport"
    # naweandco.co.uk -> "naweandco"
    # musestudios.com -> "musestudios"
    parts = domain.split('.')
    company_part = parts[0]  # First part before any TLD

    if not company_part:
        return ""

    # Try to split compound names into words
    # "eepaktransport" -> ["eepak", "transport"]
    # "naweandco" -> ["nawe", "and", "co"]  (but keep as brand name)
    # Strategy: split at common word boundaries
    words = _split_domain_to_words(company_part)

    if words:
        # Capitalize each word and join with space
        company_name = " ".join(w.capitalize() for w in words)
    else:
        # Can't split — just capitalize the whole string
        company_name = company_part.capitalize()

    return company_name


def _split_domain_to_words(domain_part: str) -> List[str]:
    """
    Split a domain name part into likely words.
    e.g. "eepaktransport" -> ["eepak", "transport"]
         "naweandco" -> ["nawe", "and", "co"]  (brand names kept as-is)
         "musestudios" -> ["muse", "studios"]
    Uses known company suffixes as split points and common word patterns.
    """
    # Known suffixes that indicate company type
    suffix_words = {
        'transport', 'logistics', 'shipping', 'freight', 'courier',
        'consulting', 'solutions', 'services', 'technologies', 'technology',
        'systems', 'engineering', 'construction', 'building', 'design',
        'marketing', 'media', 'group', 'holdings', 'capital', 'ventures',
        'studio', 'studios', 'agency', 'company', 'co', 'inc', 'llc',
        'ltd', 'corp', 'partners', 'associates', 'enterprises',
        'plumbing', 'electrical', 'mechanical', 'automotive', 'medical',
        'legal', 'financial', 'insurance', 'realty', 'property',
        'cleaning', 'maintenance', 'repair', 'manufacturing', 'trading',
        'imports', 'exports', 'wholesale', 'retail', 'distribution',
        'farming', 'agriculture', 'mining', 'forestry', 'fishing',
        'food', 'restaurant', 'cafe', 'bakery', 'hotel', 'resort',
        'fitness', 'health', 'beauty', 'salon', 'spa', 'gym',
        'education', 'training', 'academy', 'school', 'college',
        'church', 'charity', 'foundation', 'community', 'council',
        'and', 'of', 'the', 'for', 'in', 'on', 'at',
    }

    lower = domain_part.lower()
    words = []

    # Try to find suffix words at the end and split
    # Iterate through suffix words, longest first to avoid partial matches
    sorted_suffixes = sorted(suffix_words, key=len, reverse=True)

    remaining = lower
    found_suffix = False

    for suffix in sorted_suffixes:
        if remaining.endswith(suffix) and len(remaining) > len(suffix):
            # Split: prefix + suffix
            prefix = remaining[:-len(suffix)]
            # Check if prefix is meaningful (not just a single letter)
            if len(prefix) >= 2:
                words.append(prefix)
                words.append(suffix)
                remaining = ""
                found_suffix = True
                break

    if not found_suffix:
        # No suffix found — try camelCase-like splitting
        # Look for transitions from lowercase to uppercase in original domain
        # e.g. "eepakTransport" -> ["eepak", "Transport"]
        # But domains are usually lowercase, so try common word boundaries
        
        # For purely lowercase compound names, try all possible splits
        # and pick the one where the second part is a known suffix
        best_split = None
        for i in range(2, len(lower)):
            first = lower[:i]
            second = lower[i:]
            if second in suffix_words:
                best_split = (first, second)
                break

        if best_split:
            words = list(best_split)
        else:
            # Can't split meaningfully — return the whole thing
            words = [lower]

    return words


def _score_confidence(name: str, company: str, email: str, phone: str, address: str) -> int:
    score = 0
    if name:
        score += 25
    if company:
        score += 15
    if email and '@' in email:
        score += 30
    if phone:
        digits = re.sub(r'\D', '', phone)
        if len(digits) >= 10:
            score += 20
        elif digits:
            score += 10
    if address:
        # Check for any postal code format (US, UK, Canadian, Australian)
        if ZIP_RE.search(address) or UK_ZIP_RE.search(address) or CA_ZIP_RE.search(address):
            score += 15
        elif AU_ZIP_RE.search(address):
            score += 15
        elif any(kw in address.lower() for kw in STREET_SUFFIXES):
            score += 10
        else:
            score += 5
    return min(score, 100)


def _empty_result() -> Dict:
    return {
        "name": "", "company": "", "email": "", "phone": "", "address": "",
        "confidence": 0, "warnings": ["No input provided"],
    }
