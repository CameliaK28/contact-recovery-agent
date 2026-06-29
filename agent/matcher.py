"""
Matcher Module - Entity matching logic

Determines whether a found contact belongs to the target customer.
Calculates confidence scores based on multiple matching factors:
- Company name match (weighted heavily)
- Location/address match (critical for disambiguation)
- Website domain match
- Name match
- Known contact association
- Country mismatch penalty (critical for international cases)
"""

import re
import logging
from typing import Dict, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Country indicators for mismatch detection
# IMPORTANT: Use raw strings (r"...") for regex patterns containing \b, \.
COUNTRY_INDICATORS = {
    "france": ["france", "franca", "paris", "lyon", "marseille", "toulouse",
                "nice", "nantes", "montpellier", "bordeaux", "lille", "rennes",
                "reims", "le havre", "saint-etienne", "toulon", "grenoble",
                "dijon", "annecy", "montanay", "rhone-alpes", "auvergne",
                r"\.fr\b", "pagesjaunes", r"societe\.com"],
    "united kingdom": ["united kingdom", "england", "london", "manchester",
                       "birmingham", "glasgow", "edinburgh", "liverpool",
                       r"\.co\.uk\b", r"yell\.com"],
    "united states": ["united states", "america", "new york", "california",
                      "texas", "florida", "chicago", "houston", "phoenix",
                      r"\.us\b", r"\.gov\b", r"yellowpages\.com", r"bbb\.org"],
    "germany": ["germany", "deutschland", "berlin", "munich", "hamburg",
                "cologne", "frankfurt", r"\.de\b", "gelbeseiten"],
    "spain": ["spain", "espana", "madrid", "barcelona", "valencia",
              r"\.es\b", "paginasamarillas"],
    "italy": ["italy", "italia", "rome", "milan", "naples", "turin",
              r"\.it\b", "paginebianche"],
    "australia": ["australia", "sydney", "melbourne", "brisbane", "perth",
                  "adelaide", "canberra", "gold coast", "hobart", "darwin",
                  "wollongong", "geelong", "townsville", "cairns",
                  "toowoomba", "millmerran",
                  r"\.com\.au\b", r"\.au\b",
                  "yellowpages.com.au", "truelocal.com.au",
                  "abr.business.gov.au", "whitepages.com.au"],
}


def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, remove extra spaces and punctuation."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def normalize_phone(phone: str) -> str:
    """Normalize phone number for comparison: keep only digits."""
    return re.sub(r'[\s().\-+]', '', phone)


def calculate_match_score(contact: Dict, customer_info: Dict, source_data: Dict = None) -> Dict:
    """
    Calculate a comprehensive match score for a found contact against the customer profile.
    
    Key insight: Location matching is critical for disambiguation when the same
    company name exists in different cities/countries.
    
    Returns a dict with:
    - confidence: percentage (0-100)
    - match_factors: list of matching evidence
    - mismatch_factors: list of mismatching evidence
    """
    score = 0
    max_score = 100
    match_factors = []
    mismatch_factors = []
    
    name = customer_info.get("name", "")
    company = customer_info.get("company", "")
    email = customer_info.get("email", "")
    phone = customer_info.get("phone", "")
    address = customer_info.get("address", "")
    
    contact_value = contact.get("value", "")
    source_url = contact.get("source_url", "")
    evidence = contact.get("evidence", "")
    contact_type = contact.get("type", "")

    # --- Social media profiles: special scoring ---
    # Social links are valuable channels on their own. If found on a page that
    # already matches the company (domain/name), they should get solid confidence
    # even without phone/email/location context.
    if contact_type.endswith("_profile"):
        return _score_social_profile(contact, customer_info)

    # Combine all searchable text
    evidence_norm = normalize_text(evidence)
    source_url_lower = source_url.lower()
    searchable = f"{evidence_norm} {source_url_lower}"
    
    # --- Factor 1: Company name match (30 points) ---
    if company:
        company_norm = normalize_text(company)
        company_words = [w for w in company_norm.split() if len(w) > 2]
        
        # Check for full company name match
        if company_norm in searchable:
            score += 30
            match_factors.append(f"✓ 公司名称完全匹配: {company}")
        else:
            # Partial match
            matched_words = sum(1 for w in company_words if w in searchable)
            if matched_words >= len(company_words) * 0.5 and matched_words > 0:
                partial_score = int(30 * (matched_words / len(company_words)))
                score += partial_score
                match_factors.append(f"✓ 公司名称部分匹配: {matched_words}/{len(company_words)} 关键词")
            else:
                mismatch_factors.append("✗ 公司名称未匹配")
                score += 0
    
    # --- Factor 2: Location match (25 points - critical for disambiguation) ---
    location_words = []
    if address:
        addr_norm = normalize_text(address)
        location_words = [w for w in addr_norm.split() if len(w) > 2]
    
    if location_words:
        matched_loc = sum(1 for w in location_words if w in searchable)
        if matched_loc >= 2:
            loc_score = int(25 * min(1.0, matched_loc / len(location_words)))
            score += loc_score
            match_factors.append(f"✓ 地址/位置匹配: {matched_loc}/{len(location_words)} 关键词")
        elif matched_loc >= 1:
            score += 8
            match_factors.append(f"✓ 位置部分匹配: {matched_loc}/{len(location_words)} 关键词")
        else:
            mismatch_factors.append("✗ 地址/位置未匹配")
    
    # --- Factor 3: Website domain match (20 points) ---
    if source_url:
        parsed = urlparse(source_url)
        domain = parsed.netloc.lower()
        company_norm = normalize_text(company) if company else ""
        company_concat = company_norm.replace(" ", "") if company_norm else ""
        company_words = [w for w in company_norm.split() if len(w) > 2] if company else []
        
        # Check if domain contains full company name (concatenated)
        domain_parts = re.split(r'[.\-]', domain)
        full_domain_match = company_concat and any(company_concat in dp for dp in domain_parts)
        # Also check email username in domain
        email_username = ""
        if email and "@" in email:
            email_username = email.split("@")[0].lower()
        username_in_domain = email_username and len(email_username) > 2 and email_username in domain
        
        if full_domain_match or username_in_domain:
            score += 20
            match_factors.append(f"✓ 网站域名关联: {domain}")
        elif email and "@" in email:
            email_domain = email.split("@")[1].lower()
            if domain == email_domain or domain.endswith(email_domain):
                score += 20
                match_factors.append(f"✓ 域名与已知邮箱域名一致: {domain}")
            else:
                # Partial domain match (only some company words in domain)
                partial_match = any(cw in dp for cw in company_words for dp in domain_parts)
                if partial_match:
                    score += 8  # Reduced from 20 to 8 for partial match
                    match_factors.append(f"✓ 域名部分匹配 (低可信度): {domain}")
                else:
                    mismatch_factors.append(f"✗ 域名与已知信息不一致")
        elif company:
            mismatch_factors.append(f"✗ 域名与公司名称不关联")
    
    # --- Factor 4: Name match (15 points, or 30 when no company) ---
    name_weight = 30 if not company else 15
    if name and name != company:  # Don't double-count if name == company
        name_norm = normalize_text(name)
        name_parts = [p for p in name_norm.split() if len(p) > 2]
        
        matched_name = sum(1 for p in name_parts if p in searchable)
        if matched_name >= len(name_parts) * 0.5 and matched_name > 0:
            name_score = int(name_weight * (matched_name / len(name_parts)))
            score += name_score
            match_factors.append(f"✓ 姓名匹配: {matched_name}/{len(name_parts)} 部分")
        else:
            mismatch_factors.append("✗ 姓名未匹配")
    
    # --- Factor 5: Known contact association (5 points) ---
    if phone and contact.get("type") in ["phone", "mobile", "whatsapp"]:
        known_digits = normalize_phone(phone)
        found_digits = normalize_phone(contact_value)
        if len(known_digits) >= 10 and len(found_digits) >= 10:
            if known_digits[:3] == found_digits[:3]:
                score += 5
                match_factors.append(f"✓ 电话区号关联: {found_digits[:3]}")
    
    if email and contact.get("type") == "email":
        known_domain = email.split("@")[1].lower()
        found_domain = contact.get("domain", contact_value.split("@")[1] if "@" in contact_value else "").lower()
        if known_domain == found_domain:
            score += 5
            match_factors.append(f"✓ 邮箱域名与已知一致: {known_domain}")
    
    # --- Factor 6: Source credibility (5 points) ---
    if source_url:
        if company and company.lower().replace(" ", "") in source_url_lower:
            score += 5
            match_factors.append("✓ 来源为企业官方相关网站")
        elif email and "@" in email:
            email_domain = email.split("@")[1].lower()
            if email_domain in source_url_lower:
                score += 5
                match_factors.append("✓ 来源与已知邮箱域名相关")
        elif any(d in source_url_lower for d in ["yellowpages", "bbb.org", "yelp", "manta", "opencorporates",
                                                    "pagesjaunes", "societe.com", "doctrine.fr",
                                                    "yell.com", "paginasamarillas"]):
            score += 3
            match_factors.append("✓ 来源为可信企业目录")

    # --- Factor 7: Country mismatch penalty (up to -30 points) ---
    # Critical for international cases: if the customer is in France but the
    # page content is clearly about a US company, penalize heavily.
    country_mismatch = _check_country_mismatch(evidence, source_url, address)
    if country_mismatch:
        score -= 30
        mismatch_factors.append(f"✗ 国家/地区不匹配: {country_mismatch}")
    
    # Calculate confidence
    confidence = min(99, int((score / max_score) * 100))
    
    # Minimum floor
    if confidence < 15 and len(match_factors) == 0:
        confidence = 10
    
    return {
        "confidence": confidence,
        "match_factors": match_factors,
        "mismatch_factors": mismatch_factors,
        "raw_score": score,
        "max_score": max_score,
        "category": _categorize_confidence(confidence)
    }


def _categorize_confidence(confidence: int) -> str:
    """Categorize confidence level."""
    if confidence >= 80:
        return "confirmed"
    elif confidence >= 50:
        return "potential"
    elif confidence >= 25:
        return "low_confidence"
    else:
        return "unlikely"


def _check_country_mismatch(evidence: str, source_url: str, customer_address: str) -> str:
    """
    Check if the page content's country indicators conflict with the customer's address country.

    Returns a description of the mismatch if found, empty string otherwise.
    """
    if not customer_address:
        return ""

    # Determine customer's country
    addr_lower = customer_address.lower()
    customer_country = None
    for country in COUNTRY_INDICATORS:
        if any(ind in addr_lower for ind in COUNTRY_INDICATORS[country]):
            customer_country = country
            break

    if not customer_country:
        return ""

    # Check page content for other country indicators
    combined = f"{evidence.lower()} {source_url.lower()}"

    for country, indicators in COUNTRY_INDICATORS.items():
        if country == customer_country:
            continue
        for ind in indicators:
            # Regex patterns (contain backslash)
            if '\\' in ind:
                try:
                    if re.search(ind, combined):
                        return f"页面内容指向{country}，与客户地址({customer_country})不符"
                except:
                    pass
            else:
                # Plain string match
                if ind in combined:
                    return f"页面内容指向{country}，与客户地址({customer_country})不符"

    return ""


def _score_social_profile(contact: Dict, customer_info: Dict) -> Dict:
    """
    Score a social media profile link.
    
    Social profiles get confidence based on WHERE they were found:
    - On the company's official website (full domain match) → high confidence
    - Email username matches social handle → high confidence
    - On a page with company name/location match → medium confidence
    - On a related business directory page → moderate confidence
    - Otherwise → low confidence (still listed, but flagged)
    
    Key improvement: Full company name match (concatenated) required for high score,
    not just individual word matches. This prevents "nawe" in nawe.us matching
    "NAWE AND CO".
    """
    score = 0
    match_factors = []
    mismatch_factors = []

    source_url = contact.get("source_url", "")
    company = customer_info.get("company", "")
    address = customer_info.get("address", "")
    name = customer_info.get("name", "")
    email = customer_info.get("email", "")

    source_url_lower = source_url.lower()
    parsed = urlparse(source_url)
    domain = parsed.netloc.lower()

    # Normalize company: remove spaces for domain comparison
    # "NAWE AND CO" -> "naweandco"
    company_norm = normalize_text(company) if company else ""
    company_concat = company_norm.replace(" ", "") if company_norm else ""

    # Email username (often the brand name on social media)
    email_username = ""
    if email and "@" in email:
        email_username = email.split("@")[0].lower()

    # Check if the source page is the company's official website
    # Use concatenated company name for stricter matching
    domain_parts = re.split(r'[.\-]', domain)
    full_domain_match = company_concat and any(company_concat in dp for dp in domain_parts)
    # Also check if email username is in the domain
    username_in_domain = email_username and len(email_username) > 2 and email_username in domain

    if full_domain_match:
        score += 50
        match_factors.append(f"✓ 社交链接来自企业官方网站: {domain}")
    elif username_in_domain:
        score += 50
        match_factors.append(f"✓ 域名包含邮箱用户名: {email_username}")
    elif email and "@" in email:
        email_domain = email.split("@")[1].lower()
        if domain == email_domain or domain.endswith(email_domain):
            score += 50
            match_factors.append(f"✓ 社交链接来自已知邮箱域名: {domain}")
        else:
            # Check if ANY company word is in domain, but give fewer points
            company_words = [w for w in company_norm.split() if len(w) > 2]
            partial_domain_match = any(cw in dp for cw in company_words for dp in domain_parts)
            if partial_domain_match:
                score += 20  # Reduced from 50 to 20 for partial match
                match_factors.append(f"✓ 域名部分匹配公司名 (低可信度): {domain}")
            else:
                score += 10
                match_factors.append("✓ 社交链接来自关联网页")
    else:
        score += 10
        match_factors.append("✓ 社交链接来自搜索结果页面")

    # Company name in source URL or evidence - use full match
    evidence = contact.get("evidence", "")
    searchable = f"{normalize_text(evidence)} {source_url_lower}"
    if company:
        company_words = [w for w in company_norm.split() if len(w) > 2]
        matched_words = sum(1 for w in company_words if w in searchable)
        if matched_words >= len(company_words):
            score += 25
            match_factors.append(f"✓ 公司名称完全匹配: {matched_words}/{len(company_words)} 关键词")
        elif matched_words >= 1:
            score += 10  # Reduced for partial match
            match_factors.append(f"✓ 公司名称部分匹配: {matched_words}/{len(company_words)} 关键词")

    # Person name match (important when no company, also useful as supplementary signal)
    # CRITICAL: For person-name searches, require MULTIPLE name parts in the profile URL
    # for high confidence. A single name part (e.g. "mundell") appearing in a URL is
    # a WEAK signal — there could be many unrelated people with that surname.
    # Distinguish 3 levels:
    #   - Strong: ALL name parts in profile URL (e.g. facebook.com/joshiel.mundell)
    #   - Medium: MOST name parts in profile URL (at least 2 for a 2-part name)
    #   - Weak: Only ONE name part in profile URL, or name only in evidence text
    # 
    # IMPORTANT: Name in search result title/evidence is a stronger signal than 
    # name in random page content. Search titles are curated and more likely to 
    # accurately describe the profile owner. Give extra weight to full name in
    # evidence when it's from a search result.
    if name:
        name_norm_val = normalize_text(name)
        name_parts = [p for p in name_norm_val.split() if len(p) > 2]
        profile_url_lower = contact.get("value", "").lower()
        
        # Strong: name parts in the profile URL itself
        name_in_url = sum(1 for p in name_parts if p in profile_url_lower)
        # Weak: name parts only in evidence/source text
        name_in_evidence = sum(1 for p in name_parts if p in searchable and p not in profile_url_lower)
        
        # Determine if name is in search result title (stronger than random page content)
        # Search result titles like "Joshiel Mundell Photography (@joshielmundellphotography)"
        # are curated descriptions that accurately identify the profile owner
        page_title = contact.get("page_title", "").lower()
        title_evidence = f"{page_title} {evidence.lower()}"
        name_in_title = sum(1 for p in name_parts if p in normalize_text(title_evidence))
        is_search_result_title = "search result" in evidence.lower() or page_title
        
        # Calculate name score based on how many parts match and where
        if name_in_url >= len(name_parts) and len(name_parts) >= 2:
            # ALL name parts in profile URL - very strong signal
            name_pts = 30 if not company else 15
            score += name_pts
            match_factors.append(f"✓ 姓名完全匹配(URL): {name_in_url}/{len(name_parts)} 部分")
        elif name_in_url >= max(2, len(name_parts) * 0.5) and len(name_parts) >= 2:
            # MOST name parts in profile URL (e.g. 2/2 or 2/3) - moderate signal
            name_pts = 20 if not company else 10
            score += name_pts
            match_factors.append(f"✓ 姓名多数匹配(URL): {name_in_url}/{len(name_parts)} 部分")
        elif name_in_url >= 1 and len(name_parts) >= 2:
            # Only ONE name part in URL (e.g. just surname) - WEAK signal
            # Many unrelated people share the same surname on social media
            name_pts = 8 if not company else 5
            score += name_pts
            match_factors.append(f"⚠ 姓名单一部分匹配(URL，低可信度): {name_in_url}/{len(name_parts)} 部分")
        elif name_in_evidence >= len(name_parts) and name_in_title >= len(name_parts):
            # Full name in search result title/evidence — STRONGER than random page content
            # Search titles are curated descriptions (e.g. "Joshiel Mundell Photography")
            name_pts = 20 if not company else 10
            score += name_pts
            match_factors.append(f"✓ 姓名完全匹配(搜索标题): {name_in_title}/{len(name_parts)} 部分")
        elif name_in_evidence >= len(name_parts):
            # Full name only in evidence text (weak signal - page mentions the person)
            name_pts = 10 if not company else 5
            score += name_pts
            match_factors.append(f"✓ 姓名匹配(页面内容): {name_in_evidence}/{len(name_parts)} 部分")
        elif name_in_evidence >= 1 and len(name_parts) >= 2:
            # Only one name part in evidence - very weak
            name_pts = 5 if not company else 3
            score += name_pts
            match_factors.append(f"⚠ 姓名单一部分匹配(页面内容): {name_in_evidence}/{len(name_parts)} 部分")

    # Brand/handle cross-verification bonus
    # When a social profile's evidence/title contains a brand name that matches
    # a social handle discovered in the search (e.g. "Joshiel Mundell Photography"
    # matches the IG handle "joshielmundellphotography"), this is a strong signal
    # that the profiles belong to the same person.
    profile_url = contact.get("value", "").lower()
    profile_handle = _extract_social_handle(contact.get("value", ""))
    profile_handle_norm = _normalize_handle(profile_handle)
    
    # Check if person name parts (concatenated) appear in the profile handle
    # "joshielmundell" in "joshielmundellphotography" → brand match bonus
    if name and not company and profile_handle:
        name_concat = normalize_text(name).replace(" ", "")
        if name_concat and name_concat in profile_handle_norm:
            # The profile handle contains the full person name → brand consistency
            score += 15
            match_factors.append(f"✓ Profile handle包含完整姓名(品牌一致性): {profile_handle}")
    
    # Also check if the evidence/title brand name matches the profile handle
    # "Joshiel Mundell Photography" in evidence → "joshielmundellphotography" handle
    if name and not company and profile_handle and evidence:
        # Extract brand-like words from evidence that could match the handle
        evidence_norm = normalize_text(evidence)
        name_words = [w for w in normalize_text(name).split() if len(w) > 2]
        # If most name words are in the evidence AND the handle contains them too
        name_in_both = sum(1 for w in name_words if w in evidence_norm and w in profile_handle_norm)
        if name_in_both >= len(name_words) and len(name_words) >= 2:
            score += 10
            match_factors.append(f"✓ 品牌名交叉匹配(标题+handle): {profile_handle}")

    # Email username match with social media handle (strong signal)
    # IMPORTANT: Only check the profile URL itself, NOT the evidence text
    # (evidence may mention the email username even on unrelated pages)
    if email_username and len(email_username) > 2:
        profile_url = contact.get("value", "").lower()
        if email_username in profile_url:
            score += 20
            match_factors.append(f"✓ 社交账号与邮箱用户名一致: {email_username}")

    # Location match
    if address:
        addr_norm = normalize_text(address)
        loc_words = [w for w in addr_norm.split() if len(w) > 2]
        matched_loc = sum(1 for w in loc_words if w in searchable)
        if matched_loc >= 2:
            score += 20
            match_factors.append(f"✓ 地址/位置匹配: {matched_loc}/{len(loc_words)} 关键词")
        elif matched_loc >= 1:
            score += 10
            match_factors.append(f"✓ 位置部分匹配")

    # Business directory bonus
    if any(d in source_url_lower for d in ["yellowpages", "bbb.org", "yelp", "manta",
                                              "pagesjaunes", "societe.com", "doctrine.fr",
                                              "yell.com", "paginasamarillas"]):
        score += 5
        match_factors.append("✓ 来源为可信企业目录")

    # Country mismatch penalty (same as regular contacts)
    country_mismatch = _check_country_mismatch(evidence, source_url, address)
    if country_mismatch:
        score -= 30
        mismatch_factors.append(f"✗ 国家/地区不匹配: {country_mismatch}")

    # Confidence cap for person-name-only profiles without strong signals
    # For person-only searches, the confidence cap depends on the quality of evidence:
    # - Full name in profile URL → cap at 65 (decent signal, but still person-only)
    # - Full name in search result title → cap at 55
    # - Single name part only → cap at 30 (very likely false positive)
    # These caps are RELAXED when cross-validation or strong corroborating signals exist
    has_strong_signal = any([
        company and score >= 25,  # Company name match contributes meaningfully
        email_username and len(email_username) > 2 and email_username in profile_url_lower,  # Email handle matches
        matched_loc >= 2,  # Strong location match
        score >= 50,  # Overall score already strong from multiple factors
        contact.get("cross_verified", False),  # Cross-platform verification
    ])
    
    if not has_strong_signal and not company:
        # For person-only searches without strong corroboration, cap confidence
        name_norm_val = normalize_text(name) if name else ""
        name_parts_count = len([p for p in name_norm_val.split() if len(p) > 2]) if name else 0
        
        if name_parts_count >= 2:
            # Check how many name parts are in the profile URL
            profile_url_val = contact.get("value", "").lower()
            name_in_url_count = sum(1 for p in [p for p in name_norm_val.split() if len(p) > 2] if p in profile_url_val)
            
            # Also check if name is in search result title (curated description)
            page_title = contact.get("page_title", "").lower()
            evidence_text = contact.get("evidence", "").lower()
            title_text = normalize_text(f"{page_title} {evidence_text}")
            name_in_title_count = sum(1 for p in [p for p in name_norm_val.split() if len(p) > 2] if p in title_text)
            
            if name_in_url_count >= name_parts_count:
                confidence_cap = 65  # Full name in URL — good signal for person-only search
            elif name_in_title_count >= name_parts_count:
                confidence_cap = 55  # Full name in search title — decent signal
            elif name_in_url_count >= max(2, name_parts_count * 0.5):
                confidence_cap = 40  # Most name parts in URL
            else:
                confidence_cap = 30  # Only one name part or name only in evidence — low confidence
        else:
            confidence_cap = 35  # Single-part name or very short name
        
        confidence = max(5, min(confidence_cap, score))
    else:
        confidence = max(5, min(95, score))

    return {
        "confidence": confidence,
        "match_factors": match_factors,
        "mismatch_factors": mismatch_factors,
        "raw_score": score,
        "max_score": 100,
        "category": _categorize_confidence(confidence)
    }


def _extract_social_handle(url: str) -> str:
    """
    Extract the username/handle from a social media profile URL.
    e.g. instagram.com/joshiel_mundell → "joshiel_mundell"
         facebook.com/joshiel.mundell → "joshiel.mundell"
         linkedin.com/in/joshiel-mundell → "joshiel-mundell"
    Returns empty string if handle cannot be extracted.
    """
    if not url:
        return ""
    # Remove protocol and www
    url_clean = re.sub(r'^https?://(www\.)?', '', url.lower())
    # Extract path after domain
    # Handle various URL formats
    patterns = [
        r'instagram\.com/([a-zA-Z0-9._-]+)',
        r'facebook\.com/(?:people/)?([a-zA-Z0-9._-]+)(?:/[0-9]+)?',
        r'linkedin\.com/in/([a-zA-Z0-9._-]+)',
        r'linkedin\.com/company/([a-zA-Z0-9._-]+)',
        r'(?:twitter\.com|x\.com)/([a-zA-Z0-9._-]+)',
        r'youtube\.com/(?:c/|channel/|user/|@)([a-zA-Z0-9._-]+)',
        r'tiktok\.com/@([a-zA-Z0-9._-]+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, url_clean)
        if m:
            handle = m.group(1)
            # Filter out system paths that aren't real handles
            if handle in ['', 'home', 'explore', 'search', 'login', 'signup',
                          'about', 'help', 'privacy', 'terms', 'share']:
                return ""
            return handle
    return ""


def _normalize_handle(handle: str) -> str:
    """
    Normalize a social media handle for cross-platform comparison.
    Remove common separators (. - _) and lowercase.
    e.g. "joshiel_mundell", "joshiel.mundell", "joshiel-mundell" all become "joshielmundell"
    """
    if not handle:
        return ""
    return re.sub(r'[._\-]', '', handle.lower())


def _apply_cross_validation(matched_contacts: List[Dict]) -> List[Dict]:
    """
    Apply cross-platform validation: if multiple social profiles share the same
    normalized handle, boost their confidence scores.
    
    This is a powerful signal: if instagram.com/joshiel_mundell and 
    facebook.com/joshiel.mundell both exist, they likely belong to the same person.
    The normalized handles "joshielmundell" match → cross-validation bonus.
    
    Also validates by brand name in evidence: if FB page title says
    "Joshiel Mundell Photography" and IG handle is "joshielmundellphotography",
    they share the same brand → cross-validation bonus.
    """
    # Group social profiles by normalized handle
    handle_groups = {}
    for contact in matched_contacts:
        if contact.get("type", "").endswith("_profile"):
            url = contact.get("value", "")
            handle = _extract_social_handle(url)
            norm_handle = _normalize_handle(handle)
            if norm_handle and len(norm_handle) > 3:
                if norm_handle not in handle_groups:
                    handle_groups[norm_handle] = []
                handle_groups[norm_handle].append(contact)
    
    # Also group by brand name found in evidence/title
    # Extract person name + brand keywords from evidence and create normalized brand keys
    brand_groups = {}
    for contact in matched_contacts:
        if contact.get("type", "").endswith("_profile"):
            evidence = contact.get("evidence", "")
            title = contact.get("page_title", "")
            combined = normalize_text(f"{title} {evidence}")
            
            # Look for brand-like patterns: "[Person Name] Photography", "[Person Name] Studio"
            # The brand name when normalized should match a handle
            brand_match = re.search(r'([a-zA-Z]{3,}(?:\s+[a-zA-Z]{3,})+)\s+(?:photography|studio|design|art|creative|media|music|fitness|coach|consulting|therapy)', combined)
            if brand_match:
                brand_name = brand_match.group(1)
                brand_norm = _normalize_handle(brand_name)
                # Also add the full brand (name + suffix)
                full_brand = brand_match.group(0)
                full_brand_norm = _normalize_handle(full_brand)
                
                if brand_norm and len(brand_norm) > 3:
                    # Use full brand as key (includes suffix like "photography")
                    key = full_brand_norm if len(full_brand_norm) > len(brand_norm) else brand_norm
                    if key not in brand_groups:
                        brand_groups[key] = []
                    brand_groups[key].append(contact)
    
    # For handles that appear on multiple platforms, boost confidence
    for norm_handle, group in handle_groups.items():
        if len(group) >= 2:
            # Cross-platform validation bonus
            platforms = set()
            for contact in group:
                ctype = contact.get("type", "")
                if "instagram" in ctype:
                    platforms.add("instagram")
                elif "facebook" in ctype:
                    platforms.add("facebook")
                elif "linkedin" in ctype:
                    platforms.add("linkedin")
                elif "twitter" in ctype:
                    platforms.add("twitter")
                elif "youtube" in ctype:
                    platforms.add("youtube")
                elif "tiktok" in ctype:
                    platforms.add("tiktok")
            
            platform_names = ", ".join(sorted(platforms))
            bonus = min(15 * (len(platforms) - 1), 30)  # 15 per additional platform, max 30
            
            for contact in group:
                old_conf = contact.get("confidence", 0)
                # Apply bonus but cap at 95
                new_conf = min(95, old_conf + bonus)
                contact["confidence"] = new_conf
                contact["cross_verified"] = True
                contact["cross_verified_platforms"] = list(platforms)
                existing_factors = contact.get("match_factors", [])
                existing_factors.append(f"✓ 交叉验证: 同一handle在{len(platforms)}个平台存在({platform_names})")
                contact["match_factors"] = existing_factors
                # Re-categorize
                contact["category"] = _categorize_confidence(new_conf)
    
    # For brand groups (title/evidence mentions same brand as a handle), boost confidence
    for brand_key, group in brand_groups.items():
        # Check if this brand key matches any handle group
        matching_handle_group = handle_groups.get(brand_key, [])
        all_related = group + matching_handle_group
        
        # Deduplicate contacts
        seen_ids = set()
        unique_related = []
        for c in all_related:
            cid = c.get("value", "").lower()
            if cid not in seen_ids:
                seen_ids.add(cid)
                unique_related.append(c)
        
        if len(unique_related) >= 2:
            # Brand cross-validation bonus (slightly less than handle match)
            platforms = set()
            for contact in unique_related:
                ctype = contact.get("type", "")
                if "instagram" in ctype:
                    platforms.add("instagram")
                elif "facebook" in ctype:
                    platforms.add("facebook")
                elif "linkedin" in ctype:
                    platforms.add("linkedin")
                elif "twitter" in ctype:
                    platforms.add("twitter")
                elif "youtube" in ctype:
                    platforms.add("youtube")
                elif "tiktok" in ctype:
                    platforms.add("tiktok")
            
            if len(platforms) >= 2:
                platform_names = ", ".join(sorted(platforms))
                bonus = min(12 * (len(platforms) - 1), 25)
                
                for contact in unique_related:
                    if not contact.get("cross_verified", False):
                        old_conf = contact.get("confidence", 0)
                        new_conf = min(90, old_conf + bonus)
                        contact["confidence"] = new_conf
                        contact["cross_verified"] = True
                        contact["cross_verified_platforms"] = list(platforms)
                        existing_factors = contact.get("match_factors", [])
                        existing_factors.append(f"✓ 品牌交叉验证: 同一品牌在{len(platforms)}个平台存在({platform_names})")
                        contact["match_factors"] = existing_factors
                        contact["category"] = _categorize_confidence(new_conf)
    
    return matched_contacts


def match_all_contacts(contacts: List[Dict], customer_info: Dict) -> List[Dict]:
    """
    Apply matching logic to all extracted contacts.
    
    Returns enriched contact list with confidence scores and match factors.
    Includes cross-platform validation bonus for social profiles.
    """
    matched_contacts = []
    
    for contact in contacts:
        match_result = calculate_match_score(contact, customer_info)
        enriched = {**contact, **match_result}
        matched_contacts.append(enriched)
    
    # Apply cross-platform validation (boost for matching handles across platforms)
    matched_contacts = _apply_cross_validation(matched_contacts)
    
    # Sort by confidence (highest first)
    matched_contacts.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    
    return matched_contacts
