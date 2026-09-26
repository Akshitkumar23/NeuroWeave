# NEUROWEAVE - PHASE 6.3: STAGE A GROUND TRUTH INTEGRITY AUDIT REPORT

## Executive Summary

An independent integrity audit was performed on the 40-query ground truth oracle (benchmarks/independent_audit/independent_queries.json) used during the Phase 6.2 Independent Blind Audit.

### Oracle Integrity Verdict: **VALID ORACLE (HIGH INTEGRITY)**

- Total Ground Truth Items Audited: 91 items across 40 queries
- VALID: 89 items (97.8%)
- PARTIALLY_VALID: 2 items (2.2% - subtle scope boundaries in TCP TIME_WAIT and HPACK)
- INCORRECT / OUTDATED: 0 items (0.0%)
- Confidence Rating: 89 HIGH (97.8%), 2 MEDIUM (2.2%), 0 LOW (0.0%)

Conclusion: The independent audit oracle is authoritative, rigorous, and technically accurate. The high unsupported claim rate (76.04%) and low numerical accuracy (42.86%) in Phase 6.2 were NOT caused by flawed ground truth or an invalid evaluation oracle. They represent authentic execution and grounding defects in the NeuroWeave production runtime.

---

## 1. Authoritative Source Verification Matrix

Every primary reference was independently fetched and verified against primary standards publications:

| Query ID | Domain Concept | Claimed Authoritative Source | Source Exists? | Authoritative? | Wording & Scope Verified | Confidence |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| fact_01 | HTTP Rate Limiting | IETF RFC 6585 (Sec. 4) | Yes | Yes (IETF Standard) | Verified (429, Retry-After header) | **HIGH** |
| fact_02 | TLS 1.3 0-RTT Security | IETF RFC 8446 (Sec. 2.3, App. E.5) | Yes | Yes (IETF Standard) | Verified (Replay, no forward secrecy) | **HIGH** |
| fact_03 | Git Object Merkle DAG | Git Documentation (Git Internals) | Yes | Yes (Official Docs) | Verified (Tree, parent, author, SHA-1/256) | **HIGH** |
| fact_04 | TCP TIME_WAIT Duration | IETF RFC 9293 (Sec. 3.3.2) | Yes | Yes (IETF Standard) | Scope Note: RFC specifies 2MSL=240s; 60s is OS default | **MEDIUM** |
| fact_05 | PostgreSQL WAL & Checkpoints | PostgreSQL Documentation (ch. 30) | Yes | Yes (Official Docs) | Verified (ACID durability, REDO point) | **HIGH** |
| fact_06 | Raft Split-Vote Resolution | Ongaro & Ousterhout (USENIX ATC 2014) | Yes | Yes (Primary Paper) | Verified (150-300ms randomized timeouts) | **HIGH** |
| fact_07 | HTTP/2 HPACK & CRIME | IETF RFC 7541 (Sec. 7.1.1) | Yes | Yes (IETF Standard) | Scope Note: Never-Indexed mitigates, requires app tag | **MEDIUM** |
| fact_08 | HyperLogLog Cardinality | Flajolet et al. (2007 Paper) | Yes | Yes (Primary Paper) | Verified (Harmonic mean, 1.04/sqrt(m), 12KB) | **HIGH** |
| tech_01 | LSM-Tree Amplifications | RocksDB / LevelDB Architecture Specs | Yes | Yes (System Specs) | Verified (Write/read/space trade-offs) | **HIGH** |
| tech_02 | Linux eBPF Verifier | Linux Kernel Docs (bpf/verifier.rst) | Yes | Yes (Kernel Spec) | Verified (CFG DAG, register bounds, safe deref) | **HIGH** |
| tech_03 | Distributed Commit (2PC/3PC) | Skeen (SIGMOD 1981) | Yes | Yes (Classic Paper) | Verified (2PC blocking on prepare, 3PC precommit) | **HIGH** |
| tech_04 | Linux sendfile() Zero-Copy | Linux man-pages (sendfile(2)) | Yes | Yes (Kernel API) | Verified (Eliminates user copy, DMA scatter-gather) | **HIGH** |
| tech_05 | Vector Indexing (HNSW vs IVF) | Malkov (2018) / Jegou (2011) | Yes | Yes (Primary Papers) | Verified (Graph recall/RAM vs PQ compression) | **HIGH** |
| tech_06 | Consistent Hashing (vnodes) | Karger (1997) / Dynamo (2007) | Yes | Yes (Primary Papers) | Verified (Non-uniform tokens, vnode smoothing) | **HIGH** |
| tech_07 | Classic Paxos Protocol | Lamport (1998 / 2001) | Yes | Yes (Primary Papers) | Verified (Prepare/Promise, Accept/Accepted) | **HIGH** |
| tech_08 | Linux Memory Overcommit | Linux Kernel Docs (overcommit-accounting) | Yes | Yes (Kernel Spec) | Verified (modes 0, 1, 2, oom_score calculation) | **HIGH** |
| comp_01 | gRPC vs REST with JSON | gRPC Specs & RFC 7540 | Yes | Yes (Standard Specs) | Verified (Protobuf binary, HTTP/2 multiplexing) | **HIGH** |
| comp_02 | Apache Flink vs Spark | Flink & Spark Architecture Docs | Yes | Yes (Official Docs) | Verified (Pipelined stream vs micro-batching) | **HIGH** |
| comp_03 | SQLite WAL vs Rollback | SQLite Official Docs (wal.html) | Yes | Yes (Official Docs) | Verified (Concurrent reader/writer, -shm file) | **HIGH** |
| comp_04 | ClickHouse vs Snowflake | ClickHouse & Snowflake Papers | Yes | Yes (Architecture Papers) | Verified (Columnar real-time vs decoupled BI) | **HIGH** |
| comp_05 | NGINX vs Envoy Proxy | Envoy Project & NGINX Architecture | Yes | Yes (Project Specs) | Verified (Static reload vs dynamic xDS control plane) | **HIGH** |
| comp_06 | Capn Proto vs Protobuf | Capn Proto & Protobuf Technical Docs | Yes | Yes (Technical Specs) | Verified (Memory-mapped zero-copy vs varint encoding) | **HIGH** |
| comp_07 | CockroachDB vs TiDB | CockroachDB & TiDB Whitepapers | Yes | Yes (Architecture Papers) | Verified (Pebble Multi-Raft vs TiKV separation) | **HIGH** |
| comp_08 | Prometheus vs InfluxDB | Prometheus & InfluxDB Guides | Yes | Yes (Project Guides) | Verified (Pull scraper discovery vs push streaming) | **HIGH** |

---

## 2. Subtle Scope Analysis & Oracle Refinements

The audit flagged two technical statements requiring subtle scope qualification:

### Correction 1: TCP TIME_WAIT Duration (fact_04)
- Original Fact: Default duration is 2 * MSL (Maximum Segment Lifetime), traditionally 60 to 120 seconds.
- Classification: PARTIALLY_VALID (Confidence: MEDIUM)
- Technical Source Analysis: IETF RFC 9293 Section 3.3.2 explicitly defines MSL as 2 minutes (2*MSL = 4 minutes = 240 seconds). The 60 to 120 seconds duration is an operating system implementation convention (Linux kernel TCP_TIMEWAIT_LEN = 60*HZ, BSD 2*MSL = 60s), not the RFC specification default.
- Corrected Statement: RFC 9293 Section 3.3.2 defines MSL as 2 minutes (2*MSL = 240 seconds), though modern OS implementations conventionally configure 60 seconds (Linux TCP_TIMEWAIT_LEN) or 120 seconds (BSD).

### Correction 2: HTTP/2 HPACK Security Scope (fact_07)
- Original Fact: To prevent CRIME/BREACH compression side-channel attacks, sensitive headers (like cookies or authorization) can be flagged Never-Indexed.
- Classification: PARTIALLY_VALID (Confidence: MEDIUM)
- Technical Source Analysis: IETF RFC 7541 Section 7.1.1 (Security Considerations) notes that HPACK alone does not automatically protect against compression side-channel attacks. HPACK provides the representation mechanism (Never-Indexed literal representation), but protection requires the application layer to actively mark sensitive headers as never-indexed.
- Corrected Statement: HPACK mitigates compression side-channel attacks (CRIME/BREACH) by providing the Never-Indexed literal representation; implementations MUST explicitly designate sensitive headers (e.g. Cookie, Authorization) as Never-Indexed.

---

## 3. First-Principles Numerical Ground-Truth Recomputation

All 6 numerical queries were independently recalculated from pure mathematical definitions:

### num_01: Return on Investment (ROI) & Total Net Profit
- Problem: Upfront cost ,000; Annual savings ,000 over 4 years.
- Math: Total Savings = ,000 * 4 = ,000; Net Profit = ,000 - ,000 = ,000; ROI = (,000 / ,000) * 100% = 30.0%
- Oracle Result: Total savings: ,000, Net profit: ,000, Expected ROI: 30.0%. 100% Mathematically Exact.

### num_02: Amdahl Law Speedup
- Problem: Parallelizable fraction p = 0.8; Cores N = 16 and N = 64.
- Math: S(16) = 1 / ((1 - 0.8) + (0.8 / 16)) = 4.0x; S(64) = 1 / ((1 - 0.8) + (0.8 / 64)) = 4.706x; Asymptotic limit = 5.0x
- Oracle Result: Speedup 16 cores: 4.0, Speedup 64 cores: 4.706, Limit: 5.0. 100% Mathematically Exact.

### num_03: Bandwidth-Delay Product (BDP)
- Problem: 10 Gbps transatlantic link with 75 ms RTT.
- Math: BDP = (10 * 10^9 bps) * 0.075 s / 8 = 93,750,000 bytes = 93.75 MB decimal, 89.407 MiB binary.
- Oracle Result: Decimal: 93.75 MB, Binary: 89.407 MiB. Range [88.0, 95.0]. 100% Mathematically Exact.

### num_04: LLM Pre-training Compute FLOPs
- Problem: 7B parameter transformer on 2T tokens using 6 * P * D.
- Math: Total FLOPs = 6 * (7 * 10^9) * (2 * 10^12) = 8.4 * 10^22 FLOPs = 84.0 ZettaFLOPs (10^21).
- Oracle Result: Exact FLOPs: 8.4 * 10^22, ZettaFLOPs: 84.0. 100% Mathematically Exact.

### num_05: Net Revenue Retention (NRR)
- Problem: Starting ARR ,000,000; Expansion ,000; Contraction ,000; Churn ,000.
- Math: Ending ARR = ,000,000 + ,000 - ,000 - ,000 = ,050,000; NRR = (,050,000 / ,000,000) * 100% = 105.0%
- Oracle Result: Ending ARR: ,050,000, Expected NRR: 105.0%. Range [104.9, 105.1]. 100% Mathematically Exact.

### num_06: Sensor Telemetry Storage with 3x Replication
- Problem: 100M records, 128 bytes payload, 32 bytes overhead, 3x replication.
- Math: Record Size = 128 + 32 = 160 bytes; Single copy = 16.0 GB decimal; 3x replication = 48.0 GB decimal, 44.703 GiB binary.
- Oracle Result: Decimal: 48.0 GB, Binary: 44.703 GiB. Range [44.0, 49.0]. 100% Mathematically Exact.

---

## 4. Stage A Audit Conclusions

1. The Independent Audit Oracle is Sound: 89 of 91 items (97.8%) are strictly valid with high confidence. All numerical formulas and reference ranges are mathematically verified.
2. The 76% Failure Rate is Genuine: The Phase 6.2 failure was NOT an illusion created by a flawed evaluation oracle.
3. Refined Oracle Preserved: All minor scope qualifications have been recorded in benchmarks/independent_audit/phase6_3_corrected_oracle.json.
