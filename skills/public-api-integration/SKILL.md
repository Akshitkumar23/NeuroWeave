---
name: public-api-integration
description: "Autonomous discovery, zero-credential data sourcing, and integration of public APIs across 50+ categories including Science, Finance, Geocoding, Weather, Government, and Developer Tools."
domain: "Public APIs & Open Data Integration"
keywords: [public_apis, open_data, rest_api, zero_auth, api_discovery, endpoints, dataset_integration, public_api_catalog]
version: "1.0.0"
risk: safe
source_type: builtin
date_added: "2026-09-09"
---

# Public API Integration & Open Data Playbook

## When to Use
- User asks for recommendations of free, open, or public APIs for any domain (finance, weather, science, geocoding, sports, entertainment, etc.).
- The agent requires external live or offline reference datasets without incurring API costs or requiring credential configuration (`Auth: None`).
- Building prototypes, webhooks, data pipelines, or frontend integrations needing public mock/live endpoints with CORS support.

## Integration Architecture

```
User Query / Requirement
      │
      ▼
Intent Analysis (intent: api_recommendation / dataset_lookup)
      │
      ▼
Tool: public_api_catalog
  - Parameters: query, category, zero_auth_only, https_only, cors_only
  - Search Mode: Token BM25 scoring across Name, Category, Description
      │
      ▼
Candidate Evaluation
  ├── Auth Verification: Zero-Auth (no key required) vs API Key vs OAuth
  ├── Transport Security: HTTPS enforced
  ├── Cross-Origin: CORS enabled for client-side / browser applications
  └── Redundancy: Primary + Fallback endpoint selection
      │
      ▼
Agent Response / Synthesis
  - Clear endpoint specification (API name, official URL)
  - Authentication requirements
  - Integration example or payload structure
```

## Key Evaluation Criteria
1. **Authentication Friction**:
   - `Auth: None`: Immediate zero-config integration. Ideal for agent autonomous queries and quick prototyping.
   - `Auth: apiKey`: Requires developer registration and credential management.
   - `Auth: OAuth`: Enterprise workflows with identity verification.
2. **CORS Support**:
   - Critical if the consumer is browser-based frontend code.
3. **Transport Security**:
   - Always enforce HTTPS (`https_only=True`) to prevent man-in-the-middle tampering.
