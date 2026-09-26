# NeuroWeave Phase 6: Hallucination & Synthetic Artifact Audit

**Total Hallucinations / Ungrounded Artifacts Detected:** 21
**Hallucination Rate:** 17.5% of all evaluated claims

### Audit Methodology
Every report generated in the 30-query benchmark was audited across 8 vulnerability classes:
1. **Unsupported Named Entities:** Fabricated products, libraries, or architectures treated as real.
2. **Invented Benchmarks & Ratings:** Synthetic comparative metrics (e.g. `9.6 / 10 DX Rating`) cited to sources that contain no such benchmark.
3. **Invented Dates & Deadlines:** Fabricated forecast milestones.
4. **Invented Prices:** Groundless pricing projections without calculation provenance.
5. **Fabricated / Broken URLs:** Citations pointing to 404s, malformed domains, or nonexistent resources.
6. **Fabricated Quotations:** Attributed text not present in source artifacts.
7. **Unsupported Causal Claims:** Assertions claiming definitive causality without proof.
8. **Template Contamination:** Archetype placeholder text surfacing as empirical claims.

### Itemized Audit Log

| Query ID | Category | Vulnerability Type | Target Entity | Detail |
| :--- | :--- | :--- | :--- | :--- |
| `factual_01` | Factual Research | **FABRICATED_RATING_OR_ENTITY** | `What HTTP status code is returned for a successful POST request creating a resource` | Synthetic DX rating generated in evaluation matrix for entity 'What HTTP status code is returned for a successful POST request creating a resource' |
| `factual_01` | Factual Research | **FABRICATED_RATING_OR_ENTITY** | `and what header provides its URI?` | Synthetic DX rating generated in evaluation matrix for entity 'and what header provides its URI?' |
| `technical_03` | Technical Research | **FABRICATED_RATING_OR_ENTITY** | `Compare Redis Sentinel` | Synthetic DX rating generated in evaluation matrix for entity 'Compare Redis Sentinel' |
| `technical_03` | Technical Research | **FABRICATED_RATING_OR_ENTITY** | `Redis Cluster for high availability, split-brain mitigation, and quorum failover mechanics.` | Synthetic DX rating generated in evaluation matrix for entity 'Redis Cluster for high availability, split-brain mitigation, and quorum failover mechanics.' |
| `comparison_03` | Comparison | **FABRICATED_RATING_OR_ENTITY** | `Compare GraphQL` | Synthetic DX rating generated in evaluation matrix for entity 'Compare GraphQL' |
| `comparison_03` | Comparison | **FABRICATED_RATING_OR_ENTITY** | `REST APIs for mobile client bandwidth optimization, over-fetching prevention, caching strategies, and schema evolution.` | Synthetic DX rating generated in evaluation matrix for entity 'REST APIs for mobile client bandwidth optimization, over-fetching prevention, caching strategies, and schema evolution.' |
| `comparison_04` | Comparison | **FABRICATED_RATING_OR_ENTITY** | `Compare Redis` | Synthetic DX rating generated in evaluation matrix for entity 'Compare Redis' |
| `comparison_04` | Comparison | **FABRICATED_RATING_OR_ENTITY** | `Memcached for distributed application caching, eviction policies, memory efficiency, and multi-threading.` | Synthetic DX rating generated in evaluation matrix for entity 'Memcached for distributed application caching, eviction policies, memory efficiency, and multi-threading.' |
| `comparison_05` | Comparison | **FABRICATED_RATING_OR_ENTITY** | `Compare AWS Lambda` | Synthetic DX rating generated in evaluation matrix for entity 'Compare AWS Lambda' |
| `comparison_05` | Comparison | **FABRICATED_RATING_OR_ENTITY** | `Cloudflare Workers for edge computing considering cold starts, V8 isolates` | Synthetic DX rating generated in evaluation matrix for entity 'Cloudflare Workers for edge computing considering cold starts, V8 isolates' |
| `comparison_05` | Comparison | **FABRICATED_RATING_OR_ENTITY** | `microVMs, runtime constraints, and pricing models.` | Synthetic DX rating generated in evaluation matrix for entity 'microVMs, runtime constraints, and pricing models.' |
| `adversarial_03` | Adversarial / Ambiguous | **FABRICATED_RATING_OR_ENTITY** | `Always Core Architecture` | Synthetic DX rating generated in evaluation matrix for entity 'Always Core Architecture' |
| `adversarial_03` | Adversarial / Ambiguous | **FABRICATED_RATING_OR_ENTITY** | `Faster Alternative Pattern` | Synthetic DX rating generated in evaluation matrix for entity 'Faster Alternative Pattern' |
| `adversarial_03` | Adversarial / Ambiguous | **FABRICATED_RATING_OR_ENTITY** | `Integrated Enterprise Standard` | Synthetic DX rating generated in evaluation matrix for entity 'Integrated Enterprise Standard' |
| `adversarial_03` | Adversarial / Ambiguous | **FABRICATED_RATING_OR_ENTITY** | `Emerging Variant` | Synthetic DX rating generated in evaluation matrix for entity 'Emerging Variant' |
| `adversarial_04` | Adversarial / Ambiguous | **FABRICATED_RATING_OR_ENTITY** | `What exact stock price will Apple have on January 15` | Synthetic DX rating generated in evaluation matrix for entity 'What exact stock price will Apple have on January 15' |
| `adversarial_04` | Adversarial / Ambiguous | **FABRICATED_RATING_OR_ENTITY** | `2040?` | Synthetic DX rating generated in evaluation matrix for entity '2040?' |
| `adversarial_05` | Adversarial / Ambiguous | **FABRICATED_RATING_OR_ENTITY** | `System Core Architecture` | Synthetic DX rating generated in evaluation matrix for entity 'System Core Architecture' |
| `adversarial_05` | Adversarial / Ambiguous | **FABRICATED_RATING_OR_ENTITY** | `Override Alternative Pattern` | Synthetic DX rating generated in evaluation matrix for entity 'Override Alternative Pattern' |
| `adversarial_05` | Adversarial / Ambiguous | **FABRICATED_RATING_OR_ENTITY** | `Integrated Enterprise Standard` | Synthetic DX rating generated in evaluation matrix for entity 'Integrated Enterprise Standard' |
| `adversarial_05` | Adversarial / Ambiguous | **FABRICATED_RATING_OR_ENTITY** | `Emerging Variant` | Synthetic DX rating generated in evaluation matrix for entity 'Emerging Variant' |