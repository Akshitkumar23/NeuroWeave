"""
Public API Catalog Tool for NeuroWeave.
Provides fast, deterministic, offline discovery and recommendation of curated public APIs,
open datasets, and zero-auth endpoints specifically needed for NeuroWeave multi-agent workflows.
"""
import os
import re
import json
import logging
from typing import Dict, Any, List, Optional
from core.tool_registry import registry

logger = logging.getLogger("neuroweave.public_api_catalog")

_PUBLIC_APIS_DATA: Optional[Dict[str, Any]] = None

def _load_database() -> Dict[str, Any]:
    global _PUBLIC_APIS_DATA
    if _PUBLIC_APIS_DATA is not None:
        return _PUBLIC_APIS_DATA

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(base_dir, "data", "public_apis.json")

    if not os.path.exists(data_path):
        logger.warning(f"public_apis.json not found at {data_path}. Initializing empty catalog.")
        _PUBLIC_APIS_DATA = {
            "metadata": {"total_curated_apis": 0, "categories": []},
            "category_purposes": {},
            "category_counts": {},
            "apis": [],
            "inverted_index": {}
        }
        return _PUBLIC_APIS_DATA

    try:
        with open(data_path, "r", encoding="utf-8") as f:
            _PUBLIC_APIS_DATA = json.load(f)
            logger.info(f"Loaded curated public API catalog: {_PUBLIC_APIS_DATA.get('metadata', {}).get('total_curated_apis', 0)} APIs.")
    except Exception as e:
        logger.error(f"Failed to load public API catalog from {data_path}: {e}")
        _PUBLIC_APIS_DATA = {
            "metadata": {"total_curated_apis": 0, "categories": []},
            "category_purposes": {},
            "category_counts": {},
            "apis": [],
            "inverted_index": {}
        }

    return _PUBLIC_APIS_DATA


def list_categories() -> List[Dict[str, Any]]:
    """Returns all project-relevant API categories with counts and intended purposes."""
    db = _load_database()
    counts = db.get("category_counts", {})
    purposes = db.get("category_purposes", {})
    return [
        {
            "category": cat,
            "count": count,
            "purpose": purposes.get(cat, "Domain research and data verification")
        }
        for cat, count in sorted(counts.items(), key=lambda x: x[0])
    ]


def get_catalog_statistics() -> Dict[str, Any]:
    """Returns summary statistics for the public API catalog."""
    db = _load_database()
    return db.get("metadata", {})


def get_recommended_apis_for_intent(intent: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Returns curated, zero-auth API recommendations based on query intent.
    Used by Planner, Researcher, and Synthesizer to provide grounded API suggestions.
    """
    intent_norm = (intent or "").lower()
    cat_map = {
        "quantitative": ["Finance", "Currency Exchange"],
        "comparison": ["Development", "Open Source Projects", "Machine Learning"],
        "research": ["Science & Math", "Open Data", "Government"],
        "security": ["Security", "Anti-Malware"],
        "conceptual": ["Development", "Dictionaries"],
    }
    
    selected_cats = []
    for k, v in cat_map.items():
        if k in intent_norm:
            selected_cats.extend(v)
            
    if not selected_cats:
        selected_cats = ["Development", "Open Data"]
        
    db = _load_database()
    apis = db.get("apis", [])
    
    results = []
    for entry in apis:
        if entry.get("category") in selected_cats and entry.get("zero_auth", False):
            results.append({
                "name": entry["name"],
                "category": entry["category"],
                "description": entry["description"],
                "url": entry["url"],
                "auth": "None",
                "purpose": entry.get("purpose", "")
            })
            if len(results) >= limit:
                break
                
    return results


def search_apis(
    query: str = "",
    category: Optional[str] = None,
    for_agent: Optional[str] = None,
    zero_auth_only: bool = False,
    https_only: bool = True,
    cors_only: bool = False,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Searches the curated public API catalog using token relevance scoring and multi-attribute filters.
    """
    db = _load_database()
    apis = db.get("apis", [])
    if not apis:
        return {
            "success": False,
            "error": "Public API database is empty or unavailable.",
            "results": []
        }

    query_norm = (query or "").strip().lower()
    query_tokens = [t for t in re.findall(r'[a-z0-9]+', query_norm) if len(t) >= 2]
    cat_filter = category.strip().lower() if category else None
    agent_filter = for_agent.strip().lower() if for_agent else None

    scored_entries = []

    for entry in apis:
        # Category filter check
        if cat_filter:
            entry_cat_lower = entry["category"].lower()
            if cat_filter != entry_cat_lower and cat_filter not in entry_cat_lower:
                continue

        # Agent relevance check
        if agent_filter:
            rel_agents = [a.lower() for a in entry.get("relevant_agents", [])]
            if agent_filter not in rel_agents:
                continue

        # Zero-auth check
        if zero_auth_only and not entry.get("zero_auth", False):
            continue

        # HTTPS check
        if https_only and not entry.get("https", False):
            continue

        # CORS check
        if cors_only and str(entry.get("cors", "")).lower() != "yes":
            continue

        # If query is empty, allow browsing with active filters
        if not query_tokens:
            scored_entries.append((1.0, entry))
            continue

        name_lower = entry["name"].lower()
        desc_lower = entry["description"].lower()
        cat_lower = entry["category"].lower()
        url_lower = entry["url"].lower()

        score = 0.0

        # Exact name match
        if query_norm == name_lower:
            score += 60.0
        elif query_norm in name_lower:
            score += 30.0

        # Category match
        if query_norm in cat_lower:
            score += 20.0

        # Token scoring
        for token in query_tokens:
            if token == name_lower:
                score += 25.0
            elif token in name_lower:
                score += 15.0

            if token in desc_lower:
                score += 6.0

            if token in cat_lower:
                score += 8.0

            if token in url_lower:
                score += 3.0

        # Preference bonus for zero_auth
        if entry.get("zero_auth", False):
            score += 2.0

        if score > 0.0:
            scored_entries.append((score, entry))

    scored_entries.sort(key=lambda x: x[0], reverse=True)
    top_entries = [e for _, e in scored_entries[:max(1, min(limit, 50))]]

    results = []
    for entry in top_entries:
        results.append({
            "name": entry["name"],
            "category": entry["category"],
            "description": entry["description"],
            "url": entry["url"],
            "auth": entry["auth"],
            "zero_auth": entry.get("zero_auth", False),
            "https": entry.get("https", True),
            "cors": entry.get("cors", "Unknown"),
            "relevant_agents": entry.get("relevant_agents", []),
            "purpose": entry.get("purpose", "")
        })

    summary_text = (
        f"Found {len(scored_entries)} matching curated APIs for NeuroWeave. "
        f"Displaying top {len(results)} authoritative endpoints."
    )

    return {
        "success": True,
        "query": query,
        "category_filter": category,
        "for_agent": for_agent,
        "zero_auth_only": zero_auth_only,
        "https_only": https_only,
        "cors_only": cors_only,
        "total_matches": len(scored_entries),
        "results": results,
        "summary": summary_text
    }


@registry.register_tool(
    name="public_api_catalog",
    description=(
        "Searches an authoritative, curated offline registry of 740+ verified public APIs and 350+ zero-auth "
        "endpoints specifically required for NeuroWeave research (Development, Finance, Currency, "
        "Science & Math, Open Data, Security, Government, and Test Data). Supports filtering by query, category, "
        "agent role, and zero-auth status."
    ),
    allowed_agents=["researcher", "planner", "analyzer", "synthesizer"]
)
def public_api_catalog(
    query: str = "",
    category: Optional[str] = None,
    for_agent: Optional[str] = None,
    zero_auth_only: bool = False,
    https_only: bool = True,
    cors_only: bool = False,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Tool entrypoint registered with NeuroWeave ToolRegistry.
    """
    logger.info(f"Executing public_api_catalog: query='{query}', cat='{category}', agent='{for_agent}', zero_auth={zero_auth_only}")
    return search_apis(
        query=query,
        category=category,
        for_agent=for_agent,
        zero_auth_only=zero_auth_only,
        https_only=https_only,
        cors_only=cors_only,
        limit=limit
    )
