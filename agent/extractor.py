"""
Extractor Module - Fetch web pages and extract contact information

Reads page content and extracts:
- Phone numbers
- Email addresses
- WhatsApp numbers
- Contact form URLs
- Social media contact info
- Messenger links

Each extraction must include the source URL, page context, and raw evidence text.
"""

import re
import logging
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Request settings
REQUEST_TIMEOUT = 15
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Phone number patterns - comprehensive regex
PHONE_PATTERNS = [
    # US/Canada format: +1 (XXX) XXX-XXXX or 1-XXX-XXX-XXXX
    r'(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}',
    # International format: +XX XXX XXX XXXX
    r'\+\d{1,3}[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,9}',
    # Simple digits pattern: at least 7 consecutive digits (with possible separators)
    r'\b\d{3}[\s.-]\d{3}[\s.-]\d{4}\b',
    # Toll free: 1-800-XXX-XXXX variants
    r'1[\s.-]?8(?:00|88|77|66|55|44|33|22)[\s.-]?\d{3}[\s.-]?\d{4}',
]

# Email pattern
EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

# WhatsApp pattern
WHATSAPP_PATTERNS = [
    r'wa\.me/(\d+)',
    r'whatsapp\.com/send\?phone=(\d+)',
    r'whatsapp[:\s]+(?:\+?[\d\s-]+)',
]

# Messenger pattern
MESSENGER_PATTERN = r'm\.me/[a-zA-Z0-9._-]+'

# Contact form indicators
CONTACT_FORM_INDICATORS = [
    'contact-form', 'contact_form', 'form-contact',
    'id="contact"', 'name="contact"',
    'action.*contact', 'action.*send', 'action.*submit',
]


def fetch_page(url: str) -> Optional[Dict]:
    """
    Fetch a web page and return its content.
    Returns dict with html, text, status_code, or None on failure.
    """
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if response.status_code == 200:
            # Handle encoding
            if not response.encoding:
                response.encoding = 'utf-8'
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract visible text
            # Remove script and style elements but keep footer (often has contact info)
            for element in soup(['script', 'style', 'nav']):
                element.decompose()
            
            text = soup.get_text(separator='\n', strip=True)
            
            # Extract footer text separately (contact info often lives here)
            footer_text = ""
            for footer in soup.find_all(['footer']):
                footer_text += footer.get_text(separator=' ', strip=True) + "\n"
            
            # Also get specific sections that often contain contact info
            contact_sections = []
            for tag in soup.find_all(['div', 'section', 'article', 'p', 'span', 'li']):
                class_attr = tag.get('class', [])
                id_attr = tag.get('id', '')
                combined = ' '.join(class_attr) + ' ' + id_attr
                if any(kw in combined.lower() for kw in ['contact', 'about', 'team', 'footer', 'info', 'support', 'reach', 'staff']):
                    contact_sections.append(tag.get_text(separator=' ', strip=True))
            
            return {
                "url": url,
                "html": html,
                "text": text + "\n" + footer_text,
                "contact_sections": '\n'.join(contact_sections),
                "status_code": response.status_code,
                "final_url": response.url  # After redirects
            }
        else:
            logger.warning(f"Failed to fetch {url}: status {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Request error for {url}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error processing {url}: {e}")
        return None


def extract_phones(text: str, html: str) -> List[Dict]:
    """Extract phone numbers from text and HTML content."""
    phones = []
    seen_numbers = set()
    
    # Combined text to search
    search_text = text
    
    for pattern in PHONE_PATTERNS:
        matches = re.finditer(pattern, search_text)
        for match in matches:
            raw = match.group()
            # Normalize: remove formatting characters
            normalized = re.sub(r'[\s().\-]', '', raw)
            # Remove leading country code for comparison
            if normalized.startswith('1') and len(normalized) > 10:
                digits_only = normalized[1:]
            else:
                digits_only = normalized
            
            if len(digits_only) >= 7 and digits_only not in seen_numbers:
                seen_numbers.add(digits_only)
                
                # Get surrounding context (evidence)
                start = max(0, match.start() - 80)
                end = min(len(search_text), match.end() + 80)
                evidence = search_text[start:end].strip()
                
                # Check if there's a label near the phone
                label_context = search_text[max(0, match.start() - 150):match.start()].lower()
                phone_type = "phone"
                if any(kw in label_context for kw in ['fax', 'fax:']):
                    phone_type = "fax"
                elif any(kw in label_context for kw in ['mobile', 'cell', 'mobile:', 'cell:']):
                    phone_type = "mobile"
                elif any(kw in label_context for kw in ['toll', 'toll-free', '800', 'free call']):
                    phone_type = "toll_free"
                elif any(kw in label_context for kw in ['whatsapp', 'wa']):
                    phone_type = "whatsapp"
                
                phones.append({
                    "type": phone_type,
                    "raw_value": raw.strip(),
                    "normalized": normalized,
                    "digits_only": digits_only,
                    "evidence": evidence,
                    "evidence_length": len(evidence)
                })
    
    # Also check HTML for tel: links
    tel_matches = re.findall(r'href=["\']tel:([^"\']+)["\']', html)
    for tel in tel_matches:
        normalized = re.sub(r'[\s().\-+]', '', tel)
        if normalized.startswith('1') and len(normalized) > 10:
            digits_only = normalized[1:]
        else:
            digits_only = normalized
        if len(digits_only) >= 7 and digits_only not in seen_numbers:
            seen_numbers.add(digits_only)
            phones.append({
                "type": "phone",
                "raw_value": tel.strip(),
                "normalized": normalized,
                "digits_only": digits_only,
                "evidence": f"tel: link found: {tel}",
                "evidence_length": 20
            })
    
    return phones


def extract_emails(text: str, html: str) -> List[Dict]:
    """Extract email addresses from text and HTML content."""
    emails = []
    seen_emails = set()
    
    # Search in text
    matches = re.finditer(EMAIL_PATTERN, text)
    for match in matches:
        email = match.group().lower()
        if email not in seen_emails and not _is_noise_email(email):
            seen_emails.add(email)
            
            # Get surrounding context
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            evidence = text[start:end].strip()
            
            emails.append({
                "type": "email",
                "value": email,
                "domain": email.split('@')[1],
                "evidence": evidence,
                "evidence_length": len(evidence)
            })
    
    # Also check HTML for mailto: links
    mailto_matches = re.findall(r'href=["\']mailto:([^"\']+?)["\']', html)
    for mailto in mailto_matches:
        email = mailto.lower().split('?')[0]  # Remove query params
        if email not in seen_emails and not _is_noise_email(email):
            seen_emails.add(email)
            emails.append({
                "type": "email",
                "value": email,
                "domain": email.split('@')[1],
                "evidence": f"mailto link: {mailto}",
                "evidence_length": 20
            })
    
    return emails


def extract_whatsapp(text: str, html: str) -> List[Dict]:
    """Extract WhatsApp contact information."""
    whatsapp_contacts = []
    seen = set()
    
    # wa.me links
    for pattern in WHATSAPP_PATTERNS:
        matches = re.finditer(pattern, html + '\n' + text, re.IGNORECASE)
        for match in matches:
            value = match.group(1) if match.lastindex else match.group()
            normalized = re.sub(r'[\s.\-]', '', value)
            if normalized not in seen:
                seen.add(normalized)
                whatsapp_contacts.append({
                    "type": "whatsapp",
                    "value": value,
                    "normalized": normalized,
                    "evidence": match.group(),
                    "evidence_length": len(match.group())
                })
    
    return whatsapp_contacts


def extract_messenger(html: str) -> List[Dict]:
    """Extract Messenger contact links."""
    messenger_contacts = []
    seen = set()
    
    matches = re.finditer(MESSENGER_PATTERN, html)
    for match in matches:
        value = match.group()
        if value not in seen:
            seen.add(value)
            messenger_contacts.append({
                "type": "messenger",
                "value": value,
                "evidence": f"Messenger link: {value}",
                "evidence_length": 30
            })
    
    return messenger_contacts


def extract_contact_forms(url: str, html: str) -> List[Dict]:
    """Extract contact form URLs from the page."""
    forms = []
    soup = BeautifulSoup(html, 'html.parser')
    
    for form in soup.find_all('form'):
        action = form.get('action', '')
        method = form.get('method', 'get').lower()
        
        # Check if form is contact-related
        form_context = ""
        form_id = form.get('id', '')
        form_class = ' '.join(form.get('class', []))
        form_context = f"{form_id} {form_class}".lower()
        
        # Look for contact-related fields
        is_contact_form = False
        if any(kw in form_context for kw in ['contact', 'message', 'inquiry', 'feedback', 'support']):
            is_contact_form = True
        
        # Check for email/phone/message fields
        input_names = [inp.get('name', '').lower() for inp in form.find_all('input')]
        textarea_names = [ta.get('name', '').lower() for ta in form.find_all('textarea')]
        all_names = input_names + textarea_names
        
        if any(kw in n for kw in ['email', 'message', 'phone', 'subject', 'comment'] for n in all_names):
            is_contact_form = True
        
        if is_contact_form:
            form_url = urljoin(url, action) if action else url
            forms.append({
                "type": "contact_form",
                "value": form_url,
                "evidence": f"Contact form with fields: {', '.join(all_names[:5])}",
                "evidence_length": 50
            })
    
    return forms


def _is_noise_email(email: str) -> bool:
    """Filter out common noise/placeholder emails."""
    noise_domains = ['example.com', 'test.com', 'localhost', 'sentry.io', 'w3.org']
    noise_patterns = ['noreply', 'no-reply', 'unsubscribe', 'mailer', 'daemon', 'root@', 'admin@localhost']
    
    domain = email.split('@')[1]
    if domain in noise_domains:
        return True
    if any(pattern in email for pattern in noise_patterns):
        return True
    # Skip very generic info emails unless they match the company domain
    # (We'll handle this in the matcher)
    return False


def extract_all_contacts(url: str, page_data: Dict) -> List[Dict]:
    """
    Master extraction function: fetch a page and extract all contact information.
    
    Returns a list of contact items, each with:
    - type: phone/email/whatsapp/messenger/contact_form
    - value: the contact value
    - source_url: where it was found
    - evidence: raw text context
    """
    text = page_data.get("text", "")
    html = page_data.get("html", "")
    final_url = page_data.get("final_url", url)
    
    all_contacts = []
    
    # Extract phones
    phones = extract_phones(text, html)
    for phone in phones:
        all_contacts.append({
            "type": phone["type"],
            "value": phone["raw_value"],
            "normalized_value": phone["normalized"],
            "digits_only": phone.get("digits_only", phone["normalized"]),
            "source_url": final_url,
            "evidence": phone["evidence"],
        })
    
    # Extract emails
    emails = extract_emails(text, html)
    for email in emails:
        all_contacts.append({
            "type": "email",
            "value": email["value"],
            "normalized_value": email["value"],
            "domain": email["domain"],
            "source_url": final_url,
            "evidence": email["evidence"],
        })
    
    # Extract WhatsApp
    whatsapp = extract_whatsapp(text, html)
    for wa in whatsapp:
        all_contacts.append({
            "type": "whatsapp",
            "value": wa["value"],
            "normalized_value": wa.get("normalized", wa["value"]),
            "source_url": final_url,
            "evidence": wa["evidence"],
        })
    
    # Extract Messenger
    messenger = extract_messenger(html)
    for msg in messenger:
        all_contacts.append({
            "type": "messenger",
            "value": msg["value"],
            "normalized_value": msg["value"],
            "source_url": final_url,
            "evidence": msg["evidence"],
        })
    
    # Extract contact forms
    contact_forms = extract_contact_forms(url, html)
    for form in contact_forms:
        all_contacts.append({
            "type": "contact_form",
            "value": form["value"],
            "normalized_value": form["value"],
            "source_url": final_url,
            "evidence": form["evidence"],
        })
    
    # Also extract social media profile links that contain contact info
    social_contacts = _extract_social_contacts(html, text, final_url)
    all_contacts.extend(social_contacts)
    
    logger.info(f"Extracted {len(all_contacts)} contacts from {final_url}")
    return all_contacts


def _extract_social_contacts(html: str, text: str, source_url: str) -> List[Dict]:
    """
    Extract ALL social media profile links from the page.
    
    Unlike phone/email, social links are valuable on their own — they provide
    alternative channels to reach the customer. We capture every social link
    found on a matched page, not just those near contact keywords.
    """
    contacts = []
    seen = set()

    # Platform → regex pattern. Patterns are designed to capture profile paths
    # while excluding generic share/share.php tracking links.
    social_patterns = {
        "facebook": r'(?:https?://)?(?:www\.)?facebook\.com/(?!sharer|share\.php|dialog|tr\?|plugins|ajax|v[0-9])(?:people/[a-zA-Z0-9._-]+/[0-9]+|pg/[a-zA-Z0-9._-]+|[a-zA-Z0-9._-]+)',
        "instagram": r'(?:https?://)?(?:www\.)?instagram\.com/(?!p/|explore/|accounts/|rsrc\.|developer)[a-zA-Z0-9._-]+',
        "linkedin": r'(?:https?://)?(?:www\.)?linkedin\.com/(?:company|in)/[a-zA-Z0-9._-]+',
        "twitter": r'(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/(?!share|intent|home|search)[a-zA-Z0-9._-]+',
        "youtube": r'(?:https?://)?(?:www\.)?youtube\.com/(?:c/|channel/|user/|@)[a-zA-Z0-9._-]+',
        "tiktok": r'(?:https?://)?(?:www\.)?tiktok\.com/@[a-zA-Z0-9._-]+',
    }

    for platform, pattern in social_patterns.items():
        matches = re.finditer(pattern, html, re.IGNORECASE)
        for match in matches:
            raw_url = match.group()
            # Normalize: ensure full URL with https://
            if not raw_url.startswith('http'):
                url = 'https://' + raw_url
            else:
                url = raw_url
            # Strip trailing punctuation
            url = url.rstrip('/.,;')

            # Filter out noise paths (internal platform resources, not profiles)
            noise_paths = ['rsrc.php', 'sharer.php', 'share.php', 'dialog/', 'tr?', '/plugins/', '/v2/', '/ajax/']
            if any(noise in url.lower() for noise in noise_paths):
                continue
            # Filter out generic platform entry points with no profile name
            path_part = url.split(platform + '.com/')[-1].split(platform + '.com/')[-1] if platform + '.com/' in url else ''
            if path_part in ['', 'home', 'index', 'login', 'signup', 'about', 'help', 'privacy', 'terms']:
                continue

            if url.lower() not in seen:
                seen.add(url.lower())
                contacts.append({
                    "type": f"{platform}_profile",
                    "value": url,
                    "normalized_value": url,
                    "source_url": source_url,
                    "evidence": f"{platform.capitalize()} profile link found on page",
                })

    return contacts
