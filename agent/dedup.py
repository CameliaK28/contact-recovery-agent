"""
Dedup Module - Deduplication logic

Removes contacts that are already known (same as input).
Removes duplicate contacts found across multiple sources.
"""

import re
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> str:
    """Normalize phone to digits only for comparison, removing leading country code 1."""
    digits = re.sub(r'[\s().\-+]', '', phone)
    # Remove leading US country code '1' if present (so +1-404 and (404) match)
    if digits.startswith('1') and len(digits) > 10:
        digits = digits[1:]
    return digits


def normalize_email(email: str) -> str:
    """Normalize email for comparison."""
    return email.lower().strip()


def deduplicate_against_known(contacts: List[Dict], customer_info: Dict) -> List[Dict]:
    """
    Remove contacts that match the customer's already-known information.
    
    We don't output what we already have - only NEW contacts.
    """
    known_phone = customer_info.get("phone", "")
    known_email = customer_info.get("email", "")
    
    known_phone_digits = normalize_phone(known_phone) if known_phone else ""
    known_email_norm = normalize_email(known_email) if known_email else ""
    
    filtered = []
    removed = []
    
    for contact in contacts:
        contact_type = contact.get("type", "")
        contact_value = contact.get("value", "")
        
        should_remove = False
        
        # Check phone duplicates
        if contact_type in ["phone", "mobile", "toll_free", "fax", "whatsapp"] and known_phone_digits:
            found_digits = normalize_phone(contact_value)
            if found_digits == known_phone_digits:
                should_remove = True
                removed.append({
                    "type": contact_type,
                    "value": contact_value,
                    "reason": "与已知电话号码一致"
                })
        
        # Check email duplicates
        if contact_type == "email" and known_email_norm:
            found_email_norm = normalize_email(contact_value)
            if found_email_norm == known_email_norm:
                should_remove = True
                removed.append({
                    "type": "email",
                    "value": contact_value,
                    "reason": "与已知邮箱一致"
                })
        
        if not should_remove:
            filtered.append(contact)
    
    logger.info(f"Dedup against known: removed {len(removed)} known contacts, kept {len(filtered)} new contacts")
    if removed:
        logger.debug(f"Removed: {removed}")
    
    return filtered


def deduplicate_cross_source(contacts: List[Dict]) -> List[Dict]:
    """
    Remove duplicate contacts found across multiple sources.
    Keep the one with highest confidence / best evidence.
    """
    # Group contacts by type and normalized value
    groups = {}
    
    for contact in contacts:
        contact_type = contact.get("type", "")
        contact_value = contact.get("value", "")
        
        # Create a normalized key for deduplication
        if contact_type in ["phone", "mobile", "toll_free", "fax", "whatsapp"]:
            norm_key = f"{contact_type}:{normalize_phone(contact_value)}"
        elif contact_type == "email":
            norm_key = f"email:{normalize_email(contact_value)}"
        elif contact_type == "contact_form":
            # For contact forms, deduplicate by URL
            norm_key = f"form:{contact_value.lower()}"
        else:
            # Social profiles, messenger, etc. - deduplicate by value
            norm_key = f"{contact_type}:{contact_value.lower()}"
        
        if norm_key not in groups:
            groups[norm_key] = []
        groups[norm_key].append(contact)
    
    deduped = []
    
    for key, group in groups.items():
        if len(group) == 1:
            deduped.append(group[0])
        else:
            # Keep the one with highest confidence
            best = max(group, key=lambda x: x.get("confidence", 0))
            
            # Merge source information from other duplicates
            other_sources = []
            for item in group:
                if item != best:
                    other_sources.append({
                        "url": item.get("source_url", ""),
                        "evidence": item.get("evidence", "")
                    })
            
            best["additional_sources"] = other_sources
            best["source_count"] = len(group)
            
            deduped.append(best)
    
    logger.info(f"Cross-source dedup: {len(contacts)} → {len(deduped)} unique contacts")
    return deduped


def filter_noise_contacts(contacts: List[Dict]) -> List[Dict]:
    """
    Filter out clearly irrelevant or noise contacts.
    """
    noise_emails = [
        "webmaster@", "admin@", "info@wordpress", "noreply@",
        "privacy@", "legal@", "support@wordpress", "donotreply@"
    ]
    
    noise_phone_area_codes = []  # Could add known spam area codes
    
    # Non-profile paths on social media sites (system pages, not user profiles)
    social_noise_paths = [
        "/events", "/event/", "/groups", "/group/", "/pages", "/page/",
        "/help", "/help/", "/about", "/about/", "/login", "/login/",
        "/signup", "/signup/", "/settings", "/privacy", "/terms",
        "/sharer", "/sharer.php", "/dialog/", "/plugins/", "/tr/",
        "/widget", "/widgets", "/widgets.js", "/sdk.js", "/api/",
        "/v/", "/search", "/search.php", "/hashtag/", "/explore/",
        "/directory/", "/policies/", "/legal/", "/ads/",
        "/home", "/home.php", "/bookmarks", "/notifications",
        "/messages", "/messages/", "/friends", "/friends/",
        "/photo.php", "/photo/", "/photo", "/media",
        "/watch", "/watch/", "/gaming", "/gaming/",
        "/marketplace", "/marketplace/",
        "/business/", "/developers/", "/developer/",
        "/careers/", "/jobs/", "/press/",
        "/intl/", "/l.php", "/l/",
        "/reel/", "/reels/", "/story/", "/stories/",
        "/video/", "/videos/", "/p/",
    ]
    
    filtered = []
    for contact in contacts:
        contact_type = contact.get("type", "")
        contact_value = contact.get("value", "")
        
        should_remove = False
        
        # Filter noise emails
        if contact_type == "email":
            for noise in noise_emails:
                if noise in contact_value.lower():
                    should_remove = True
                    break
        
        # Filter very short phone numbers (likely not real)
        if contact_type in ["phone", "mobile", "whatsapp"]:
            digits = normalize_phone(contact_value)
            if len(digits) < 7:
                should_remove = True
        
        # Filter invalid social profile URLs
        if contact_type.endswith("_profile"):
            url_lower = contact_value.lower()
            
            # Filter out JavaScript/widget URLs
            if url_lower.endswith(".js") or url_lower.endswith(".css"):
                should_remove = True
            
            # Filter out system pages
            for noise_path in social_noise_paths:
                if noise_path in url_lower:
                    should_remove = True
                    break
            
            # Filter out URLs with only numeric IDs shorter than 5 digits
            # (e.g., facebook.com/2008 is not a real profile)
            if not should_remove:
                path_match = re.search(r'/(?:[^/]+/)?(\d+)(?:[/?#]|$)', url_lower)
                if path_match and len(path_match.group(1)) < 5:
                    should_remove = True
            
            # Filter out empty or root paths (e.g., just "facebook.com/")
            if not should_remove:
                # Extract path after domain
                path = re.sub(r'^https?://[^/]+', '', url_lower)
                path = path.strip('/')
                if not path or len(path) < 2:
                    should_remove = True
        
        if not should_remove:
            filtered.append(contact)
    
    return filtered
