"""
Build script to filter and parse the public-apis repository into a lean,
project-specific, high-performance offline database for NeuroWeave agents.

Filters out non-relevant categories (memes, pets, anime, games, comics, horoscopes, etc.)
and retains ONLY the essential APIs needed for:
  - Technical & Developer Research (Development, Programming, Open Source, ML)
  - Quantitative & Financial Analysis (Finance, Currency Exchange, Business, Patent)
  - Scientific & Fact-Checking Research (Science & Math, Open Data, Dictionaries, Text Analysis)
  - Security & System Auditing (Security, Anti-Malware)
  - Government & Geopolitical Verification (Government, Geocoding)
  - Testing & Sandbox Validation (Data Validation, Test Data)
"""
import os
import re
import json
from collections import Counter, defaultdict
from typing import Dict, Any, List

PROJECT_RELEVANT_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "Development": {
        "agents": ["researcher", "analyzer", "synthesizer"],
        "purpose": "Developer tooling, package registries, version control, CI/CD, and system APIs"
    },
    "Programming": {
        "agents": ["researcher", "analyzer"],
        "purpose": "Code snippets, programming challenges, and developer documentation"
    },
    "Open Source Projects": {
        "agents": ["researcher", "synthesizer"],
        "purpose": "Open source repository tracking, licensing, and community projects"
    },
    "Machine Learning": {
        "agents": ["researcher", "analyzer", "synthesizer"],
        "purpose": "Machine learning models, datasets, inference runtimes, and AI benchmarks"
    },
    "Finance": {
        "agents": ["analyzer", "planner", "synthesizer"],
        "purpose": "Macroeconomics, financial indicators, stock market metrics, and treasury data"
    },
    "Currency Exchange": {
        "agents": ["analyzer", "planner", "synthesizer"],
        "purpose": "Foreign exchange (Forex) rates, currency conversions, and historical FX data"
    },
    "Business": {
        "agents": ["planner", "synthesizer", "researcher"],
        "purpose": "Corporate filings, company registries, commerce benchmarks, and business data"
    },
    "Patent": {
        "agents": ["researcher", "synthesizer"],
        "purpose": "Patent searches, intellectual property filings, and innovation metrics"
    },
    "Science & Math": {
        "agents": ["researcher", "analyzer", "synthesizer"],
        "purpose": "Academic research, arXiv papers, mathematics rendering, astronomy, and physics"
    },
    "Open Data": {
        "agents": ["researcher", "analyzer", "synthesizer"],
        "purpose": "Public open datasets, census, global records, and archives"
    },
    "Dictionaries": {
        "agents": ["researcher", "synthesizer"],
        "purpose": "Lexical definitions, phonetics, etymology, synonyms, and linguistics"
    },
    "Text Analysis": {
        "agents": ["researcher", "analyzer"],
        "purpose": "Natural language processing, sentiment analysis, entity extraction, and translation"
    },
    "Security": {
        "agents": ["critic", "researcher", "analyzer"],
        "purpose": "CVE vulnerabilities, cryptography, hash lookups, certificates, and security auditing"
    },
    "Anti-Malware": {
        "agents": ["critic", "researcher"],
        "purpose": "Threat intelligence, malware signatures, and URL threat scanning"
    },
    "Government": {
        "agents": ["researcher", "analyzer", "synthesizer"],
        "purpose": "Official government open data, regulatory filings, and public sector statistics"
    },
    "Geocoding": {
        "agents": ["researcher", "analyzer", "planner"],
        "purpose": "Geographic coordinates, addresses, reverse geocoding, and administrative boundaries"
    },
    "Data Validation": {
        "agents": ["analyzer", "critic"],
        "purpose": "Data schema validation, format checkers, and HTTP echo endpoints"
    },
    "Test Data": {
        "agents": ["analyzer", "planner"],
        "purpose": "Mock datasets, fake JSON schemas, and test fixtures for deterministic testing"
    }
}


def parse_and_filter_readme(readme_path: str) -> Dict[str, Any]:
    with open(readme_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_cat = None
    link_re = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')

    entries: List[Dict[str, Any]] = []
    category_counts: Dict[str, int] = Counter()

    for line in lines:
        line = line.strip()
        if line.startswith('### '):
            current_cat = line[4:].strip()
            continue

        # Skip categories not required by NeuroWeave
        if current_cat not in PROJECT_RELEVANT_CATEGORIES:
            continue

        if line.startswith('|') and not line.startswith('|---') and not line.startswith('| API') and not line.startswith('|:---'):
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 5:
                m = link_re.match(parts[0])
                if m:
                    title = m.group(1).strip()
                    url = m.group(2).strip()
                    desc = parts[1].strip()
                    auth_raw = parts[2].replace('`', '').strip()
                    auth = "None" if auth_raw.lower() in ("no", "none", "") else auth_raw
                    https = parts[3].strip().lower() == "yes"
                    cors = parts[4].strip()

                    # Require HTTPS for security
                    if not https:
                        continue

                    cat_meta = PROJECT_RELEVANT_CATEGORIES[current_cat]
                    entry_id = f"{current_cat.lower().replace(' ', '_').replace('&', 'and')}_{len(entries)+1}"

                    entry = {
                        "id": entry_id,
                        "name": title,
                        "url": url,
                        "description": desc,
                        "category": current_cat,
                        "auth": auth,
                        "zero_auth": auth == "None",
                        "https": True,
                        "cors": cors,
                        "relevant_agents": cat_meta["agents"],
                        "purpose": cat_meta["purpose"]
                    }
                    entries.append(entry)
                    category_counts[current_cat] += 1

    # Inverted index for fast keyword lookup
    inverted_index = defaultdict(list)
    stop_words = {"a", "an", "the", "and", "or", "in", "on", "at", "for", "to", "of", "with", "is", "api", "apis"}

    for idx, entry in enumerate(entries):
        text = f"{entry['name']} {entry['description']} {entry['category']}".lower()
        tokens = set(re.findall(r'[a-z0-9]{2,}', text))
        for token in tokens:
            if token not in stop_words:
                inverted_index[token].append(idx)

    index_dict = {k: v for k, v in inverted_index.items() if len(v) <= 200}

    database = {
        "metadata": {
            "source": "https://github.com/public-apis/public-apis",
            "scope": "NeuroWeave Targeted Public APIs Catalog (Zero-API Architecture)",
            "total_curated_apis": len(entries),
            "total_categories": len(category_counts),
            "zero_auth_apis": sum(1 for e in entries if e["zero_auth"]),
            "categories": sorted(list(category_counts.keys()))
        },
        "category_purposes": {cat: meta["purpose"] for cat, meta in PROJECT_RELEVANT_CATEGORIES.items() if cat in category_counts},
        "category_counts": dict(category_counts),
        "apis": entries,
        "inverted_index": index_dict
    }

    return database


def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    readme_path = os.path.join(root_dir, 'scratch', 'public-apis', 'README.md')
    out_path = os.path.join(root_dir, 'data', 'public_apis.json')

    if not os.path.exists(readme_path):
        print(f"Error: {readme_path} not found.")
        return

    print(f"Parsing and filtering {readme_path} for NeuroWeave needs...")
    db = parse_and_filter_readme(readme_path)
    print(f"Retained {db['metadata']['total_curated_apis']} project-relevant APIs across {db['metadata']['total_categories']} categories.")
    print(f"Zero-Auth (keyless) APIs: {db['metadata']['zero_auth_apis']}")

    print(f"Writing to {out_path}...")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    print(f"Successfully generated {out_path} ({os.path.getsize(out_path)} bytes).")


if __name__ == '__main__':
    main()
