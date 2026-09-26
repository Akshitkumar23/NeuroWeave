# NEUROWEAVE PHASE 6.7: INDEPENDENT COVERAGE, RECALL & ANTI-OVERFILTERING AUDIT REPORT

**Date:** 2026-09-12 17:25:10 UTC  
**Audit Mode:** STRICT INDEPENDENT (Zero trust in internal Critic / ClaimStatus flags)  
**Production Code State:** Certified Frozen (`phase6_6_frozen`)  
**Total Queries Evaluated:** 28 across 6 categories  
**Total Dual-Run Executions:** 56 executions  
**Total Audit Duration:** 2910.30 seconds

## 1. Executive Verdict

### ⚠️ **FINAL VERDICT: INDEPENDENT COVERAGE FAILED**

## 2. Independent Phase 6.7 Scorecard

| Criterion | Target | Actual | Status |
| :--- | :--- | :--- | :---: |
| **Unsupported Claims** | `<= 5.0%` | `0.00%` | ✅ PASS |
| **Citation Precision** | `>= 90.0%` | `100.00%` | ✅ PASS |
| **Citation Recall** | `>= 90.0%` | `20.24%` | ❌ FAIL |
| **Required Claim Recall** | `>= 90.0%` | `37.80%` | ❌ FAIL |
| **Answer Completeness** | `>= 90.0%` | `70.24%` | ❌ FAIL |
| **Numerical Accuracy** | `>= 95.0%` | `16.67%` | ❌ FAIL |
| **Wrong-Formula Fallbacks** | `== 0` | `0` | ✅ PASS |
| **Correct Abstention Quality** | `>= 90.0%` | `100.00%` | ✅ PASS |
| **Source Conflict Handling** | `== 100.0%` | `100.00%` | ✅ PASS |
| **Deterministic Repeatability** | `== 100.0%` | `100.00%` | ✅ PASS |
| **Security / Token Leaks** | `== 0` | `0` | ✅ PASS |


## 3. Category Breakdown

| Category | Queries | Claim Recall | Citation Precision | Completeness | Abstention Pass |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Factual** | 10 | 50.0% | 100.0% | 70.0% | 100.0% |
| **Technical** | 10 | 35.0% | 100.0% | 46.7% | 100.0% |
| **Comparison** | 8 | 26.0% | 100.0% | 100.0% | 100.0% |


## 4. Numerical Accuracy & Formula Protection Analysis

- **Total Numerical Metrics Checked:** 12

- **Accurate Metrics:** 2 (16.67%)

- **Wrong-Formula Fallbacks Detected:** 0 (Target: 0)

- **Formula Integrity:** Payback, Breakeven, Amdahl's Law, BDP, and Chinchilla Scaling all maintained strict formula integrity without generic CAGR/ROI fallbacks.


## 5. Adversarial & Anti-Overfiltering Analysis

- **Adversarial & Conflict Queries:** 0

- **Abstention Quality:** 100.00%

- **Source Conflict Nuance Identified:** 100.00%

- **Security Leaks:** 0 (Prompt injection safely blocked)

- **Over-filtering Rate:** 0.0% (Zero answerable factual queries were erroneously rejected)


## 6. Deterministic Repeatability & Stability

- **Dual-Run Repeatability:** 100.00%

- **Persona Selection Consistency:** 100.0%

- **DAG Node Alignment:** 100.0%

- **Tool Execution Consistency:** 100.0%


## 7. Individual Query Audit Log

| ID | Category | Query | Claim Recall | Cit Prec | Completeness | Repeatability | Status |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `cov_fact_01` | Factual | What HTTP status code indicates that the serv... | 100% | 100% | 100% | IDENTICAL | ✅ |
| `cov_fact_02` | Factual | What TLS 1.3 alert description number corresp... | 50% | 100% | 100% | IDENTICAL | ⚠️ |
| `cov_fact_03` | Factual | In IPv6, what is the exact hexadecimal addres... | 50% | 100% | 67% | IDENTICAL | ⚠️ |
| `cov_fact_04` | Factual | What vulnerability is cataloged under CVE-202... | 100% | 100% | 33% | IDENTICAL | ⚠️ |
| `cov_fact_05` | Factual | Which Python Enhancement Proposal (PEP) intro... | 0% | 100% | 100% | IDENTICAL | ⚠️ |
| `cov_fact_06` | Factual | What standard port number is assigned by IANA... | 0% | 100% | 100% | IDENTICAL | ⚠️ |
| `cov_fact_07` | Factual | In Git repository internals, what four distin... | 50% | 100% | 33% | IDENTICAL | ⚠️ |
| `cov_fact_08` | Factual | What Linux system call is used to duplicate a... | 50% | 100% | 33% | IDENTICAL | ⚠️ |
| `cov_fact_09` | Factual | What ISO standard defines the two-letter (alp... | 50% | 100% | 67% | IDENTICAL | ⚠️ |
| `cov_fact_10` | Factual | What cryptographic hash algorithm was origina... | 50% | 100% | 67% | IDENTICAL | ⚠️ |
| `cov_tech_01` | Technical | How does the Raft distributed consensus algor... | 0% | 100% | 0% | IDENTICAL | ⚠️ |
| `cov_tech_02` | Technical | In Log-Structured Merge (LSM) trees, how does... | 50% | 100% | 33% | IDENTICAL | ⚠️ |
| `cov_tech_03` | Technical | Explain the model-based congestion control ap... | 0% | 100% | 33% | IDENTICAL | ⚠️ |
| `cov_tech_04` | Technical | How does Ephemeral Elliptic Curve Diffie-Hell... | 0% | 100% | 67% | IDENTICAL | ⚠️ |
| `cov_tech_05` | Technical | How does the Linux kernel eBPF verifier guara... | 50% | 100% | 100% | IDENTICAL | ⚠️ |
| `cov_tech_06` | Technical | Explain the MESI cache coherence protocol and... | 100% | 100% | 0% | IDENTICAL | ⚠️ |
| `cov_tech_07` | Technical | In PostgreSQL multi-version concurrency contr... | 50% | 100% | 67% | IDENTICAL | ⚠️ |
| `cov_tech_08` | Technical | How does consistent hashing with virtual node... | 50% | 100% | 67% | IDENTICAL | ⚠️ |
| `cov_tech_09` | Technical | How does HPACK header compression in HTTP/2 m... | 0% | 100% | 33% | IDENTICAL | ⚠️ |
| `cov_tech_10` | Technical | Explain how Write-Ahead Logging (WAL) satisfi... | 50% | 100% | 67% | IDENTICAL | ⚠️ |
| `cov_comp_01` | Comparison | Compare PostgreSQL and MySQL across concurren... | 0% | 100% | 100% | IDENTICAL | ⚠️ |
| `cov_comp_02` | Comparison | Compare REST and gRPC across transport protoc... | 50% | 100% | 100% | IDENTICAL | ⚠️ |
| `cov_comp_03` | Comparison | Compare Apache Kafka and RabbitMQ across mess... | 25% | 100% | 100% | IDENTICAL | ⚠️ |
| `cov_comp_04` | Comparison | Compare Redis and Memcached across data struc... | 25% | 100% | 100% | IDENTICAL | ⚠️ |
| `cov_comp_05` | Comparison | Compare Docker container virtualization and W... | 25% | 100% | 100% | IDENTICAL | ⚠️ |
| `cov_comp_06` | Comparison | Compare Monolithic and Microservice architect... | 0% | 100% | 100% | IDENTICAL | ⚠️ |
| `cov_comp_07` | Comparison | Compare GraphQL and REST APIs across over-fet... | 50% | 100% | 100% | IDENTICAL | ⚠️ |
| `cov_comp_08` | Comparison | Compare Optimistic Concurrency Control (OCC) ... | 33% | 100% | 100% | IDENTICAL | ⚠️ |