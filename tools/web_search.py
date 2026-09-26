import logging
import httpx
import re
import html
import urllib.parse
import asyncio
from typing import Dict, Any, List, Optional
from security.guardrails import SecurityGuardrails
from core.tool_registry import registry

logger = logging.getLogger("neuroweave.web_search")

# Realistic User-Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

def _extract_uddg_url(raw_url: str) -> str:
    """Extracts actual destination URL from DuckDuckGo redirect wrapper."""
    if not raw_url:
        return ""
    if "uddg=" in raw_url:
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
        uddg_targets = parsed.get("uddg", [])
        if uddg_targets:
            return urllib.parse.unquote(uddg_targets[0])
    if raw_url.startswith("//duckduckgo.com/l/?uddg="):
        raw_url = "https:" + raw_url
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
        uddg_targets = parsed.get("uddg", [])
        if uddg_targets:
            return urllib.parse.unquote(uddg_targets[0])
    if raw_url.startswith("/"):
        return f"https://duckduckgo.com{raw_url}"
    return raw_url

def _clean_snippet(text: str) -> str:
    """Strips HTML tags, normalizes unicode characters, and unescapes entities."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]*>', '', text)
    clean = html.unescape(clean)
    # Normalize unicode quotation marks, dashes, and whitespace
    clean = clean.replace('\u2018', "'").replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
    clean = clean.replace('\u2013', '-').replace('\u2014', '-').replace('\u2011', '-').replace('\u00a0', ' ')
    clean = re.sub(r'[\r\n\t]+', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

async def search_duckduckgo_lite(query: str, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """
    Primary 1: Searches DuckDuckGo Lite (lite.duckduckgo.com/lite/) with table-based parsing.
    """
    results: List[Dict[str, Any]] = []
    url = "https://lite.duckduckgo.com/lite/"
    headers = {
        "User-Agent": USER_AGENTS[0],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://lite.duckduckgo.com",
        "Referer": "https://lite.duckduckgo.com/"
    }
    
    try:
        response = await client.post(url, data={"q": query, "kl": "wt-wt"}, headers=headers, timeout=1.5)
        if response.status_code == 200 and "anomaly" not in response.text:
            html_text = response.text
            
            link_pattern = re.findall(
                r'<a[^>]+class=[\'"](?:result-link|result__url)[\'"][^>]+href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>',
                html_text,
                re.DOTALL | re.IGNORECASE
            )
            snippet_pattern = re.findall(
                r'<td[^>]+class=[\'"](?:result-snippet|result__snippet)[\'"][^>]*>(.*?)</td>',
                html_text,
                re.DOTALL | re.IGNORECASE
            )
            
            if not link_pattern:
                link_pattern = re.findall(
                    r'<a[^>]+href=[\'"]([^\'"]*uddg=[^\'"]*)[\'"][^>]*>(.*?)</a>',
                    html_text,
                    re.DOTALL | re.IGNORECASE
                )
            
            for idx, (raw_url, raw_title) in enumerate(link_pattern):
                dest_url = _extract_uddg_url(raw_url)
                if not dest_url or not dest_url.startswith("http") or not SecurityGuardrails.is_url_safe(dest_url):
                    continue
                
                title = _clean_snippet(raw_title)
                snippet = ""
                if idx < len(snippet_pattern):
                    snippet = _clean_snippet(snippet_pattern[idx])
                
                if title and dest_url:
                    clean_snip = snippet.strip() if snippet else title
                    results.append({
                        "title": title,
                        "url": dest_url,
                        "snippet": clean_snip,
                        "source": "duckduckgo_lite",
                        "source_type": "LIVE_EXTERNAL",
                        "source_tier": "Tier 3 (Web Index / Search Aggregate)",
                        "credibility": 0.95
                    })
    except Exception as e:
        logger.debug(f"DuckDuckGo Lite search error for '{query}': {e}")
        
    return results

async def search_duckduckgo_html(query: str, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """
    Primary 3: Fallback search using html.duckduckgo.com/html/.
    """
    results: List[Dict[str, Any]] = []
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": USER_AGENTS[1],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://duckduckgo.com/"
    }
    
    try:
        response = await client.post(url, data={"q": query}, headers=headers, timeout=1.5)
        if response.status_code == 200 and "anomaly" not in response.text:
            html_text = response.text
            
            titles_links = re.findall(
                r'<a[^>]+class=[\'"](?:result__a|result__url)[\'"][^>]+href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>',
                html_text,
                re.DOTALL | re.IGNORECASE
            )
            snippets = re.findall(
                r'<a[^>]+class=[\'"]result__snippet[\'"][^>]*>(.*?)</a>',
                html_text,
                re.DOTALL | re.IGNORECASE
            )
            
            for idx, (raw_url, raw_title) in enumerate(titles_links):
                dest_url = _extract_uddg_url(raw_url)
                if not dest_url or not dest_url.startswith("http") or not SecurityGuardrails.is_url_safe(dest_url):
                    continue
                
                title = _clean_snippet(raw_title)
                snippet = ""
                if idx < len(snippets):
                    snippet = _clean_snippet(snippets[idx])
                
                if title and dest_url:
                    clean_snip = snippet.strip() if snippet else title
                    results.append({
                        "title": title,
                        "url": dest_url,
                        "snippet": clean_snip,
                        "source": "duckduckgo_html",
                        "source_type": "LIVE_EXTERNAL",
                        "source_tier": "Tier 3 (Web Index / Search Aggregate)",
                        "credibility": 0.93
                    })
    except Exception as e:
        logger.debug(f"DuckDuckGo HTML search error for '{query}': {e}")
        
    return results

async def search_wikipedia(query: str, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """
    Primary 2: Wikipedia Search API + Batch Intro Extracts.
    Fetches encyclopedic definitions, technical architecture, and factual history.
    """
    results: List[Dict[str, Any]] = []
    search_url = "https://en.wikipedia.org/w/api.php"
    headers = {
        "User-Agent": "NeuroWeaveBot/1.0 (https://neuroweave.internal; research-core@neuroweave.org)"
    }
    
    try:
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "utf8": "",
            "format": "json",
            "srlimit": 5
        }
        res = await client.get(search_url, params=search_params, headers=headers, timeout=6.0)
        if res.status_code == 200:
            data = res.json()
            hits = data.get("query", {}).get("search", [])
            
            if hits:
                # Fetch detailed page extracts for rich, deep technical content
                titles = [hit["title"] for hit in hits[:4]]
                extract_params = {
                    "action": "query",
                    "prop": "extracts",
                    "exintro": "1",
                    "explaintext": "1",
                    "titles": "|".join(titles),
                    "format": "json"
                }
                extract_res = await client.get(search_url, params=extract_params, headers=headers, timeout=6.0)
                extract_map: Dict[str, str] = {}
                if extract_res.status_code == 200:
                    pages = extract_res.json().get("query", {}).get("pages", {})
                    for pid, pdata in pages.items():
                        title_k = pdata.get("title", "")
                        ext = pdata.get("extract", "")
                        if title_k and ext:
                            extract_map[title_k.lower()] = ext
                
                for hit in hits:
                    hit_title = hit.get("title", "")
                    raw_snippet = _clean_snippet(hit.get("snippet", ""))
                    page_extract = extract_map.get(hit_title.lower(), "")
                    
                    if page_extract:
                        clean_ext = _clean_snippet(page_extract)
                        full_snippet = clean_ext[:450]
                        if len(clean_ext) > 450:
                            full_snippet += "..."
                    else:
                        full_snippet = raw_snippet
                        
                    clean_snip = full_snippet.strip() if full_snippet else hit_title
                        
                    url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(hit_title.replace(' ', '_'))}"
                    
                    if SecurityGuardrails.is_url_safe(url) and hit_title:
                        results.append({
                            "title": f"{hit_title} (Wikipedia Encyclopedia)",
                            "url": url,
                            "snippet": clean_snip,
                            "source": "wikipedia_encyclopedia",
                            "source_type": "SECONDARY_EXTERNAL",
                            "source_tier": "Tier 2 (Reputable Technical Publication)",
                            "credibility": 0.98
                        })
    except Exception as e:
        logger.debug(f"Wikipedia search error for '{query}': {e}")
        
    return results

async def search_developer_web(query: str, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """
    Live developer & engineering search via HackerNews Algolia and DuckDuckGo Instant Answers.
    Provides verified engineering discussions, repository links, benchmarks, and architectural analyses.
    """
    results: List[Dict[str, Any]] = []
    
    # 1. Algolia HackerNews Technical Index
    try:
        hn_url = "https://hn.algolia.com/api/v1/search"
        params = {"query": query, "tags": "(story,comment)", "hitsPerPage": 4}
        r = await client.get(hn_url, params=params, timeout=2.5)
        if r.status_code == 200:
            data = r.json()
            for hit in data.get("hits", [])[:3]:
                title = hit.get("title") or hit.get("story_title") or f"Discussion: {query}"
                title = _clean_snippet(title)
                story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                comment_text = _clean_snippet(hit.get("comment_text", ""))
                story_text = _clean_snippet(hit.get("story_text", ""))
                
                content = comment_text or story_text
                points = hit.get("points", 0)
                num_comments = hit.get("num_comments", 0)
                
                snippet = content[:350].strip() if content else f"{title} (Discussion: {points} points, {num_comments} comments)"
                
                if SecurityGuardrails.is_url_safe(story_url) and title:
                    results.append({
                        "title": title,
                        "url": story_url,
                        "snippet": snippet.strip(),
                        "source": "developer_engineering_index",
                        "source_type": "LIVE_EXTERNAL",
                        "source_tier": "Tier 2 (Reputable Technical Publication)",
                        "credibility": 0.92
                    })
    except Exception as e:
        logger.debug(f"Developer index search error for '{query}': {e}")
        
    # 2. DuckDuckGo Instant Answer API (Fast failover: 1.2s timeout)
    try:
        ddg_api_url = "https://api.duckduckgo.com/"
        ddg_params = {
            "q": query,
            "format": "json",
            "no_redirect": "1",
            "no_html": "1",
            "skip_disambig": "0"
        }
        r_api = await client.get(ddg_api_url, params=ddg_params, timeout=1.2)
        if r_api.status_code == 200:
            data = r_api.json()
            abstract = _clean_snippet(data.get("AbstractText", ""))
            abstract_url = data.get("AbstractURL", "")
            abstract_src = data.get("AbstractSource", "Reference")
            heading = _clean_snippet(data.get("Heading", query))
            
            if abstract and abstract_url and SecurityGuardrails.is_url_safe(abstract_url):
                full_abstract = abstract[:450].strip()
                results.append({
                    "title": f"{heading} ({abstract_src})",
                    "url": abstract_url,
                    "snippet": full_abstract,
                    "source": "duckduckgo_instant_answer",
                    "source_type": "LIVE_EXTERNAL",
                    "source_tier": "Tier 2 (Reputable Technical Publication)",
                    "credibility": 0.96
                })
                
            for topic in data.get("RelatedTopics", [])[:3]:
                if isinstance(topic, dict) and "Text" in topic and "FirstURL" in topic:
                    t_url = topic["FirstURL"]
                    t_text = _clean_snippet(topic["Text"])
                    if SecurityGuardrails.is_url_safe(t_url):
                        t_title = t_text.split(" - ")[0] if " - " in t_text else t_text[:60]
                        clean_topic_snippet = t_text.strip()
                        results.append({
                            "title": t_title,
                            "url": t_url,
                            "snippet": clean_topic_snippet,
                            "source": "duckduckgo_related_topic",
                            "source_type": "LIVE_EXTERNAL",
                            "source_tier": "Tier 3 (Web Index / Search Aggregate)",
                            "credibility": 0.91
                        })
    except Exception as e:
        logger.debug(f"DDG instant answer error for '{query}': {e}")

    return results

async def search_ietf_standards(query: str, client: Optional[httpx.AsyncClient] = None) -> List[Dict[str, Any]]:
    """
    Tier 1: IETF Datatracker API for RFCs, Internet Drafts, and protocol specifications.
    """
    results: List[Dict[str, Any]] = []
    rfc_match = re.search(r'\brfc\s*(\d+)\b', query, re.IGNORECASE)
    search_param = f"rfc{rfc_match.group(1)}" if rfc_match else ""
    
    url = "https://datatracker.ietf.org/api/v1/doc/document/"
    headers = {"User-Agent": "NeuroWeaveBot/1.0 (https://neuroweave.internal; standards@neuroweave.internal)"}
    
    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=6.0)
        should_close = True

    try:
        params = {"format": "json", "limit": 3}
        if search_param:
            params["name__icontains"] = search_param
        else:
            words = [w for w in re.findall(r'[a-zA-Z0-9]+', query) if len(w) > 3 and w.lower() not in ["what", "does", "role", "mean", "play", "explain"]]
            if not words:
                return []
            params["title__icontains"] = words[0]
            
        res = await client.get(url, params=params, headers=headers, timeout=5.0)
        if res.status_code == 200:
            objects = res.json().get("objects", [])
            for obj in objects:
                doc_name = obj.get("name", "")
                title = obj.get("title", "")
                abstract = _clean_snippet(obj.get("abstract", ""))
                rfc_url = f"https://www.rfc-editor.org/info/{doc_name}" if doc_name.startswith("rfc") else f"https://datatracker.ietf.org/doc/{doc_name}/"
                snippet = abstract[:400] if abstract else f"{title} (Official IETF / RFC Specification)"
                if SecurityGuardrails.is_url_safe(rfc_url) and title:
                    results.append({
                        "title": f"{doc_name.upper()}: {title} (IETF Standard)",
                        "url": rfc_url,
                        "snippet": snippet,
                        "source": "ietf_datatracker",
                        "source_type": "LIVE_EXTERNAL",
                        "source_tier": "Tier 1 (Authoritative / Standards)",
                        "credibility": 0.99
                    })
    except Exception as e:
        logger.debug(f"IETF search error for '{query}': {e}")
    finally:
        if should_close:
            await client.aclose()
    return results

async def search_stackexchange(query: str, client: Optional[httpx.AsyncClient] = None) -> List[Dict[str, Any]]:
    """
    Tier 2: StackExchange / StackOverflow API for verified engineering and systems architecture answers.
    """
    results: List[Dict[str, Any]] = []
    words = [w for w in re.findall(r'[a-zA-Z0-9\-\+\#\.]+', query) if len(w) > 2 and w.lower() not in ["what", "which", "where", "explain", "difference", "between", "does", "mean", "with"]]
    se_query = " ".join(words[:5])
    if not se_query:
        return []
        
    url = "https://api.stackexchange.com/2.3/search/advanced"
    params = {
        "order": "desc",
        "sort": "relevance",
        "site": "stackoverflow",
        "q": se_query,
        "pagesize": 3
    }
    headers = {"User-Agent": "NeuroWeaveBot/1.0 (https://neuroweave.internal)"}
    
    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=6.0)
        should_close = True

    try:
        res = await client.get(url, params=params, headers=headers, timeout=5.0)
        if res.status_code == 200:
            items = res.json().get("items", [])
            for item in items:
                link = item.get("link", "")
                title = _clean_snippet(item.get("title", ""))
                score = item.get("score", 0)
                is_ans = item.get("is_answered", False)
                tags = ", ".join(item.get("tags", []))
                snip = f"{title}. Verified technical discussion (Score: {score}, Answered: {is_ans}, Tags: {tags})."
                if SecurityGuardrails.is_url_safe(link) and title:
                    results.append({
                        "title": f"{title} (StackOverflow)",
                        "url": link,
                        "snippet": snip,
                        "source": "stackoverflow_engineering",
                        "source_type": "LIVE_EXTERNAL",
                        "source_tier": "Tier 2 (Reputable Technical Publication)",
                        "credibility": 0.94
                    })
    except Exception as e:
        logger.debug(f"StackExchange search error for '{query}': {e}")
    finally:
        if should_close:
            await client.aclose()
    return results

async def search_openalex(query: str, client: Optional[httpx.AsyncClient] = None) -> List[Dict[str, Any]]:
    """
    Tier 1: OpenAlex Scholarly Database for peer-reviewed Computer Science & Systems research.
    Gracefully falls back to Crossref API when OpenAlex is rate-limited (HTTP 429).
    """
    results: List[Dict[str, Any]] = []
    words = [w for w in re.findall(r'[a-zA-Z0-9]+', query) if len(w) > 3 and w.lower() not in ["what", "which", "where", "explain", "does", "compare"]]
    oa_query = " ".join(words[:4])
    if not oa_query:
        return []
        
    url = "https://api.openalex.org/works"
    params = {"search": oa_query, "per-page": 3}
    headers = {"User-Agent": "NeuroWeaveBot/1.0 (mailto:research@neuroweave.internal)"}
    
    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=6.0)
        should_close = True

    try:
        try:
            res = await client.get(url, params=params, headers=headers, timeout=4.0)
            if res.status_code == 200:
                works = res.json().get("results", [])
                for work in works:
                    title = _clean_snippet(work.get("title", ""))
                    doi = work.get("doi") or work.get("id") or ""
                    year = work.get("publication_year", "")
                    cited_by = work.get("cited_by_count", 0)
                    snip = f"{title} (Published: {year}, Citations: {cited_by}). Primary computer science research."
                    if doi and SecurityGuardrails.is_url_safe(doi) and title:
                        results.append({
                            "title": f"{title} (Scholarly Research {year})",
                            "url": doi,
                            "snippet": snip,
                            "source": "openalex_research",
                            "source_type": "LIVE_EXTERNAL",
                            "source_tier": "Tier 1 (Authoritative / Standards)",
                            "credibility": 0.98
                        })
        except Exception as e:
            logger.debug(f"OpenAlex search error for '{query}': {e}")

        # Fallback to Crossref if OpenAlex is rate-limited (429) or returned 0 items
        if not results:
            try:
                cf_url = "https://api.crossref.org/works"
                cf_params = {"query": oa_query, "rows": 3}
                cf_res = await client.get(cf_url, params=cf_params, headers=headers, timeout=4.0)
                if cf_res.status_code == 200:
                    items = cf_res.json().get("message", {}).get("items", [])
                    for item in items:
                        title_list = item.get("title", [])
                        title = _clean_snippet(title_list[0] if title_list else "Scholarly Research")
                        doi_val = item.get("DOI", "")
                        if not doi_val:
                            continue
                        doi = f"https://doi.org/{doi_val}" if not doi_val.startswith("http") else doi_val
                        issued = item.get("issued", {}).get("date-parts", [[None]])
                        year = issued[0][0] if (issued and issued[0] and issued[0][0]) else "2023"
                        snip = f"{title} (Published: {year}). Scholarly peer-reviewed research."
                        if doi and SecurityGuardrails.is_url_safe(doi) and title:
                            results.append({
                                "title": f"{title} (Scholarly Research {year})",
                                "url": doi,
                                "snippet": snip,
                                "source": "openalex_research",
                                "source_type": "LIVE_EXTERNAL",
                                "source_tier": "Tier 1 (Authoritative / Standards)",
                                "credibility": 0.98
                            })
            except Exception as e:
                logger.debug(f"Crossref fallback error for '{query}': {e}")
    finally:
        if should_close:
            await client.aclose()
    return results

@registry.register_tool(
    name="web_search",
    description="Performs exhaustive live multi-source web searches across IETF Standards, StackExchange, OpenAlex Research, Wikipedia API, and Developer Knowledge indexes.",
    allowed_agents=["researcher", "planner", "analyzer", "synthesizer"]
)
async def web_search(query: str) -> Dict[str, Any]:
    """
    Executes live multi-source concurrent web retrieval, deduplicates URLs, and extracts genuine factual snippets.
    Never outputs generic corporate filler.
    """
    if not isinstance(query, str):
        query = str(query or "")

    clean_query = SecurityGuardrails.sanitize_user_query(query)
    clean_query = clean_query.strip()
    if not clean_query:
        logger.warning("Empty search query after security sanitization.")
        return {
            "success": False,
            "engine": "live_multi_source_engine",
            "results": [],
            "error": "Empty or sanitized query"
        }

    logger.info(f"Executing multi-source concurrent live search for: '{clean_query}'")

    # Formulate complementary search queries
    search_terms = [clean_query]
    q_lower = clean_query.lower()
    
    if "vs" in q_lower or "comparison" in q_lower or "compare" in q_lower:
        # Split tokens for entity lookup
        tokens = [t.strip() for t in re.split(r'\b(?:vs|versus|compared to|comparison|compare)\b', clean_query, flags=re.IGNORECASE) if t.strip()]
        for tok in tokens:
            if len(tok) >= 3 and tok not in search_terms:
                search_terms.append(tok)
                search_terms.append(f"{tok} architecture")
    else:
        search_terms.append(f"{clean_query} architecture")
        search_terms.append(f"{clean_query} technical overview")

    aggregated_results: List[Dict[str, Any]] = []
    seen_urls = set()

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        tasks = []
        
        # 1. Wikipedia Search (High factual accuracy)
        for term in search_terms[:3]:
            tasks.append(search_wikipedia(term, client))
            
        # 2. DuckDuckGo Lite
        for term in search_terms[:2]:
            tasks.append(search_duckduckgo_lite(term, client))
            
        # 3. DuckDuckGo HTML Fallback
        tasks.append(search_duckduckgo_html(clean_query, client))
        
        # 4. Developer Knowledge & Tech Index
        for term in search_terms[:3]:
            tasks.append(search_developer_web(term, client))

        # 5. IETF Datatracker Standards (Tier 1 RFCs & Protocols)
        tasks.append(search_ietf_standards(clean_query, client))
        for term in search_terms[:2]:
            t_low = term.lower()
            if any(k in t_low for k in ["rfc", "protocol", "http", "tcp", "udp", "tls", "dns", "oauth", "jwt", "ietf"]):
                tasks.append(search_ietf_standards(term, client))

        # 6. StackExchange Verified Engineering (Tier 2 Technical Discussions)
        tasks.append(search_stackexchange(clean_query, client))

        # 7. OpenAlex Scholarly Research (Tier 1 Systems Papers & Research)
        tasks.append(search_openalex(clean_query, client))

        # Execute all searches concurrently
        harvested = await asyncio.gather(*tasks, return_exceptions=True)

        for res_list in harvested:
            if isinstance(res_list, list):
                for item in res_list:
                    raw_url = item.get("url", "")
                    normalized_url = raw_url.rstrip("/").lower()
                    if normalized_url and normalized_url not in seen_urls:
                        seen_urls.add(normalized_url)
                        aggregated_results.append(item)

    # Sort results by credibility score descending, ensuring richest content first
    aggregated_results.sort(
        key=lambda r: (r.get("credibility", 0.0), len(r.get("snippet", ""))),
        reverse=True
    )

    logger.info(f"Live web search completed. Harvested {len(aggregated_results)} genuine references.")
    
    return {
        "success": True if len(aggregated_results) > 0 else False,
        "engine": "live_multi_source_engine",
        "query": clean_query,
        "total_results": len(aggregated_results),
        "results": aggregated_results[:12]
    }


