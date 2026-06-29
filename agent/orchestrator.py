"""
Orchestrator Module - Coordinates the entire Customer Contact Recovery workflow

Step 1: Build customer identity profile → search keywords
Step 2: Execute multi-channel search
Step 3: Fetch pages and extract contact info
Step 4: Entity matching and verification
Step 5: Deduplication
Step 6: Format and return results
"""

import logging
import time
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from .search import build_search_queries, execute_searches, filter_relevant_urls, build_secondary_searches
from .extractor import fetch_page, extract_all_contacts
from .matcher import match_all_contacts, _extract_social_handle, _normalize_handle
from .dedup import deduplicate_against_known, deduplicate_cross_source, filter_noise_contacts

logger = logging.getLogger(__name__)


def run_recovery(customer_info: Dict, progress_callback=None) -> Dict:
    """
    Main orchestrator: run the full customer contact recovery process.
    
    Args:
        customer_info: Dict with name, company, email, phone, address
        progress_callback: Optional callable to report progress steps
    
    Returns:
        Dict with results, metadata, and formatted output
    """
    start_time = time.time()
    all_contacts = []
    all_sources = []
    errors = []
    
    def report_progress(step, message, data=None):
        if progress_callback:
            progress_callback(step, message, data)
        logger.info(f"[Step {step}] {message}")
    
    # ===== Step 1: Build search queries =====
    report_progress(1, "建立客户身份画像，构建搜索关键词...")
    queries = build_search_queries(customer_info)
    report_progress(1, f"生成 {len(queries)} 个搜索查询", {"queries": queries})
    
    # ===== Step 2: Execute searches =====
    report_progress(2, "执行多渠道搜索...")
    try:
        search_results = execute_searches(
            queries, max_results_per_query=5,
            address=customer_info.get("address", "")
        )
    except Exception as e:
        logger.error(f"Search execution failed: {e}")
        search_results = []
        errors.append(f"搜索执行出错: {str(e)}")
    
    report_progress(2, f"搜索完成，找到 {len(search_results)} 个结果")
    
    # Filter relevant URLs
    relevant_results = filter_relevant_urls(search_results, customer_info)
    report_progress(2, f"筛选后保留 {len(relevant_results)} 个相关URL")
    
    # ===== Step 3: Fetch pages and extract contacts =====
    report_progress(3, "读取网页内容，提取联系方式...")
    
    fetched_pages = {}
    
    # Fetch pages in parallel (up to 10 concurrent)
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_url = {
            executor.submit(fetch_page, result["url"]): result
            for result in relevant_results
        }
        
        for future in as_completed(future_to_url):
            result_info = future_to_url[future]
            try:
                page_data = future.result()
                if page_data:
                    url = page_data["url"]
                    fetched_pages[url] = page_data
                    
                    # Extract contacts from this page
                    contacts = extract_all_contacts(url, page_data)
                    
                    # Add source metadata
                    for contact in contacts:
                        contact["search_channel"] = result_info.get("channel", "")
                        contact["search_query"] = result_info.get("query", "")
                        contact["page_title"] = page_data.get("title", "")
                    
                    all_contacts.extend(contacts)
                    
                    # Track sources
                    all_sources.append({
                        "url": url,
                        "title": result_info.get("title", ""),
                        "channel": result_info.get("channel", ""),
                        "contacts_found": len(contacts),
                        "fetched": True
                    })
                    
                    report_progress(3, f"从 {url} 提取到 {len(contacts)} 个联系方式")
                else:
                    all_sources.append({
                        "url": result_info["url"],
                        "title": result_info.get("title", ""),
                        "channel": result_info.get("channel", ""),
                        "contacts_found": 0,
                        "fetched": False,
                        "error": "页面无法访问"
                    })
            except Exception as e:
                logger.warning(f"Error processing {result_info['url']}: {e}")
                errors.append(f"处理 {result_info['url']} 出错: {str(e)}")
    
    report_progress(3, f"页面读取完成，共提取 {len(all_contacts)} 个联系方式")
    
    # ===== Step 3b: Extract social profiles from search results directly =====
    # When we search "site:facebook.com \"Person Name\"" and get a result like
    # facebook.com/person.name/, that URL IS the finding — even if the page
    # can't be scraped (Facebook blocks scraping). We create social profile
    # contacts directly from these search result URLs.
    report_progress(3, "从搜索结果中提取直接匹配的社交媒体Profile...")
    
    social_platforms = {
        "facebook.com": "facebook_profile",
        "instagram.com": "instagram_profile",
        "linkedin.com": "linkedin_profile",
        "twitter.com": "twitter_profile",
        "x.com": "twitter_profile",
        "youtube.com": "youtube_profile",
        "tiktok.com": "tiktok_profile",
    }
    
    # Noise paths to exclude (system pages, not profiles)
    social_noise_paths = [
        "/events", "/event/", "/groups", "/group/", "/pages", "/page/",
        "/help", "/about", "/login", "/signup", "/settings", "/privacy",
        "/terms", "/sharer", "/dialog/", "/plugins/", "/tr/",
        "/widget", "/widgets", "/widgets.js", "/sdk.js", "/api/",
        "/search", "/hashtag/", "/explore/", "/directory/",
        "/policies/", "/legal/", "/ads/", "/home", "/bookmarks",
        "/notifications", "/messages", "/friends", "/photo.php", "/photo/",
        "/media", "/watch", "/gaming", "/marketplace", "/business/",
        "/developers/", "/developer/", "/careers/", "/jobs/", "/press/",
        "/intl/", "/l.php", "/l/", "/posts/", "/share",
        "/reel/", "/reels/", "/story/", "/stories/", "/video/", "/videos/",
        "/p/",  # Instagram post paths (not profiles)
    ]
    
    direct_social_profiles = []
    seen_profile_urls = set()
    
    # Also collect all profile URLs already found via page scraping
    # to avoid duplicates
    for c in all_contacts:
        if c.get("type", "").endswith("_profile"):
            seen_profile_urls.add(c.get("value", "").lower())
    
    for result in relevant_results:
        url = result.get("url", "")
        url_lower = url.lower()
        
        # Check if this URL is a social media profile
        profile_type = None
        for platform, ptype in social_platforms.items():
            if platform in url_lower:
                profile_type = ptype
                break
        
        if not profile_type:
            continue
        
        # Skip noise paths (system pages)
        if any(noise in url_lower for noise in social_noise_paths):
            continue
        
        # Skip .js/.css files
        if url_lower.endswith(".js") or url_lower.endswith(".css"):
            continue
        
        # Skip if already found via page scraping
        if url_lower in seen_profile_urls:
            continue
        
        # Skip pure numeric IDs < 5 digits
        import re as _re
        id_match = _re.search(r'/(?:[^/]+/)?(\d+)(?:[/?#]|$)', url_lower)
        if id_match and len(id_match.group(1)) < 5:
            continue
        
        # This is a direct social profile from search results
        direct_social_profiles.append({
            "type": profile_type,
            "value": url,
            "source_url": url,  # The profile URL itself is the source
            "evidence": f"Search result: {result.get('title', '')} - {result.get('description', '')[:100]}",
            "search_channel": result.get("channel", ""),
            "search_query": result.get("query", ""),
            "page_title": result.get("title", ""),
        })
        seen_profile_urls.add(url_lower)
    
    if direct_social_profiles:
        all_contacts.extend(direct_social_profiles)
        report_progress(3, f"从搜索结果中直接提取到 {len(direct_social_profiles)} 个社交媒体Profile")
    
    # Track unfetched social profile URLs as sources
    for profile in direct_social_profiles:
        url = profile["value"]
        if url not in fetched_pages:
            all_sources.append({
                "url": url,
                "title": profile.get("page_title", ""),
                "channel": profile.get("search_channel", ""),
                "contacts_found": 1,
                "fetched": False,
                "note": "直接从搜索结果提取（页面无法抓取）"
            })
    
    # ===== Step 4: Entity matching =====
    report_progress(4, "执行实体匹配和可信度评估...")
    matched_contacts = match_all_contacts(all_contacts, customer_info)
    report_progress(4, f"匹配完成，评估了 {len(matched_contacts)} 个联系方式的可信度")
    
    # ===== Step 4b: Cross-platform secondary search =====
    # If we found high-confidence social profiles (especially Instagram),
    # extract their handles and search for the same person on other platforms.
    # This dramatically improves accuracy: confirmed IG @joshiel_mundell →
    # search facebook.com/joshiel_mundell, linkedin.com/in/joshiel_mundell, etc.
    
    discovered_handles = []
    discovered_names = []
    
    # Find social profiles with decent confidence (>= 40 for person searches)
    # that could provide handles for cross-platform searches
    for contact in matched_contacts:
        ctype = contact.get("type", "")
        if ctype.endswith("_profile") and contact.get("confidence", 0) >= 40:
            url = contact.get("value", "")
            handle = _extract_social_handle(url)
            if handle and len(handle) > 3:
                norm_handle = _normalize_handle(handle)
                # Avoid duplicate handles
                if norm_handle not in [_normalize_handle(h) for h in discovered_handles]:
                    discovered_handles.append(handle)
                    report_progress(4, f"发现社交handle: {handle} (from {ctype}, confidence={contact.get('confidence', 0)}%)")
        
        # Also extract any alternative names found in evidence
        # (e.g., a page might reveal the person's nickname or full name variant)
        evidence = contact.get("evidence", "")
        if evidence and contact.get("confidence", 0) >= 50:
            # Look for name patterns in evidence that differ from the original
            import re as _re
            # Extract potential names from "Search result:" lines
            name_in_title = _re.search(r'(?:Joshiel|joshiel|Mundell|mundell|[\w]+ [\w]+)', evidence)
            if name_in_title:
                found_name = name_in_title.group()
                if found_name not in discovered_names and found_name.lower() != customer_info.get("name", "").lower():
                    discovered_names.append(found_name)
    
    if discovered_handles:
        report_progress(4, f"提取到 {len(discovered_handles)} 个社交handle，进行二次交叉搜索...")
        
        secondary_queries = build_secondary_searches(
            customer_info, discovered_handles, discovered_names
        )
        report_progress(4, f"生成 {len(secondary_queries)} 个二次搜索查询")
        
        # Execute secondary searches
        try:
            secondary_results = execute_searches(
                secondary_queries, max_results_per_query=5,
                address=customer_info.get("address", "")
            )
        except Exception as e:
            logger.warning(f"Secondary search failed: {e}")
            secondary_results = []
        
        # Filter relevant secondary results
        secondary_relevant = filter_relevant_urls(secondary_results, customer_info)
        report_progress(4, f"二次搜索找到 {len(secondary_relevant)} 个相关URL")
        
        # Fetch secondary pages and extract contacts
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {
                executor.submit(fetch_page, result["url"]): result
                for result in secondary_relevant
            }
            
            for future in as_completed(future_to_url):
                result_info = future_to_url[future]
                try:
                    page_data = future.result()
                    if page_data:
                        url = page_data["url"]
                        fetched_pages[url] = page_data
                        
                        contacts = extract_all_contacts(url, page_data)
                        for contact in contacts:
                            contact["search_channel"] = "cross_platform_search"
                            contact["search_query"] = result_info.get("query", "")
                            contact["page_title"] = page_data.get("title", "")
                            contact["secondary_search"] = True  # Flag for cross-validation
                        
                        all_contacts.extend(contacts)
                        
                        all_sources.append({
                            "url": url,
                            "title": result_info.get("title", ""),
                            "channel": "cross_platform_search",
                            "contacts_found": len(contacts),
                            "fetched": True,
                            "secondary_search": True
                        })
                except Exception as e:
                    logger.warning(f"Error in secondary search for {result_info['url']}: {e}")
        
        # Also extract direct social profiles from secondary search results
        social_platforms = {
            "facebook.com": "facebook_profile",
            "instagram.com": "instagram_profile",
            "linkedin.com": "linkedin_profile",
            "twitter.com": "twitter_profile",
            "x.com": "twitter_profile",
            "youtube.com": "youtube_profile",
            "tiktok.com": "tiktok_profile",
        }
        
        social_noise_paths = [
            "/events", "/event/", "/groups", "/group/", "/pages", "/page/",
            "/help", "/about", "/login", "/signup", "/settings", "/privacy",
            "/terms", "/sharer", "/dialog/", "/plugins/", "/tr/",
            "/widget", "/widgets", "/widgets.js", "/sdk.js", "/api/",
            "/search", "/hashtag/", "/explore/", "/directory/",
            "/policies/", "/legal/", "/ads/", "/home", "/bookmarks",
            "/notifications", "/messages", "/friends", "/photo.php", "/photo/",
            "/media", "/watch", "/gaming", "/marketplace", "/business/",
            "/developers/", "/developer/", "/careers/", "/jobs/", "/press/",
            "/intl/", "/l.php", "/l/", "/posts/", "/share",
        ]
        
        for result in secondary_relevant:
            url = result.get("url", "")
            url_lower = url.lower()
            
            profile_type = None
            for platform, ptype in social_platforms.items():
                if platform in url_lower:
                    profile_type = ptype
                    break
            
            if not profile_type:
                continue
            
            if any(noise in url_lower for noise in social_noise_paths):
                continue
            
            if url_lower.endswith(".js") or url_lower.endswith(".css"):
                continue
            
            import re as _re
            id_match = _re.search(r'/(?:[^/]+/)?(\d+)(?:[/?#]|$)', url_lower)
            if id_match and len(id_match.group(1)) < 5:
                continue
            
            # Check if this URL provides cross-validation with discovered handles
            handle = _extract_social_handle(url)
            norm_handle = _normalize_handle(handle)
            is_cross_validated = norm_handle in [_normalize_handle(h) for h in discovered_handles]
            
            # Create contact entry with cross-validation flag
            contact_entry = {
                "type": profile_type,
                "value": url,
                "source_url": url,
                "evidence": f"Cross-platform search: {result.get('title', '')} - {result.get('description', '')[:100]}",
                "search_channel": "cross_platform_search",
                "search_query": result.get("query", ""),
                "page_title": result.get("title", ""),
                "secondary_search": True,
                "cross_validated_handle": handle if is_cross_validated else "",
            }
            
            # Avoid duplicates with already-found contacts
            existing_urls = {c.get("value", "").lower() for c in all_contacts if c.get("type", "").endswith("_profile")}
            if url.lower() not in existing_urls:
                all_contacts.append(contact_entry)
                all_sources.append({
                    "url": url,
                    "title": result.get("title", ""),
                    "channel": "cross_platform_search",
                    "contacts_found": 1,
                    "fetched": False,
                    "note": "二次搜索直接提取（交叉验证）",
                    "secondary_search": True
                })
        
        # Re-run matching on all contacts (including secondary ones)
        report_progress(4, f"二次搜索新增 {len(all_contacts) - len(matched_contacts)} 个联系方式，重新执行匹配...")
        matched_contacts = match_all_contacts(all_contacts, customer_info)
        report_progress(4, f"二次匹配完成，共评估 {len(matched_contacts)} 个联系方式")
    
    # ===== Step 5: Deduplication =====
    report_progress(5, "执行去重处理...")
    
    # First: remove contacts that match known info
    new_contacts = deduplicate_against_known(matched_contacts, customer_info)
    
    # Second: remove cross-source duplicates
    deduped_contacts = deduplicate_cross_source(new_contacts)
    
    # Third: filter noise
    clean_contacts = filter_noise_contacts(deduped_contacts)
    
    report_progress(5, f"去重完成，保留 {len(clean_contacts)} 个新增联系方式")
    
    # ===== Step 6: Format results =====
    report_progress(6, "格式化输出结果...")
    
    elapsed_time = time.time() - start_time
    
    # Separate social media profiles from direct contacts
    social_profiles = [c for c in clean_contacts if c.get("type", "").endswith("_profile")]
    non_social_contacts = [c for c in clean_contacts if not c.get("type", "").endswith("_profile")]

    # Filter out low-confidence social profiles (noise from unrelated pages)
    social_profiles = [c for c in social_profiles if c.get("confidence", 0) >= 25]

    # Categorize non-social results
    confirmed_contacts = [c for c in non_social_contacts if c.get("category") == "confirmed"]
    potential_contacts = [c for c in non_social_contacts if c.get("category") == "potential"]
    low_confidence_contacts = [c for c in non_social_contacts if c.get("category") in ("low_confidence", "unlikely")]

    # Sort each category by confidence
    confirmed_contacts.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    potential_contacts.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    low_confidence_contacts.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    social_profiles.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    
    # Calculate overall customer match confidence
    overall_confidence = _calculate_overall_confidence(confirmed_contacts, potential_contacts, customer_info)
    
    result = {
        "customer": {
            "name": customer_info.get("name", ""),
            "company": customer_info.get("company", ""),
            "original_email": customer_info.get("email", ""),
            "original_phone": customer_info.get("phone", ""),
            "original_address": customer_info.get("address", ""),
        },
        "match_confidence": overall_confidence,
        "confirmed_contacts": confirmed_contacts,
        "potential_contacts": potential_contacts,
        "low_confidence_contacts": low_confidence_contacts,
        "social_media_profiles": social_profiles,
        "sources": all_sources,
        "metadata": {
            "queries_used": len(queries),
            "urls_searched": len(search_results),
            "urls_fetched": len(fetched_pages),
            "contacts_extracted": len(all_contacts),
            "contacts_after_dedup": len(clean_contacts),
            "elapsed_seconds": round(elapsed_time, 2),
            "errors": errors,
        }
    }
    
    report_progress(6, "搜索完成！", {"result_summary": {
        "confirmed": len(confirmed_contacts),
        "potential": len(potential_contacts),
        "low_confidence": len(low_confidence_contacts),
        "social_media": len(social_profiles),
        "time": round(elapsed_time, 2)
    }})
    
    return result


def _calculate_overall_confidence(confirmed: List, potential: List, customer_info: Dict) -> int:
    """
    Calculate overall customer match confidence.
    Based on whether we found confirmed contacts matching the customer.
    """
    if not confirmed and not potential:
        return 30  # Low confidence if nothing found
    
    # Base confidence from the highest-scoring confirmed contact
    if confirmed:
        max_conf = max(c.get("confidence", 0) for c in confirmed)
        return min(99, max_conf + 5)  # Boost slightly
    
    if potential:
        max_conf = max(c.get("confidence", 0) for c in potential)
        return min(90, max_conf)
    
    return 30
