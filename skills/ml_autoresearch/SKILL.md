---
name: ml_autoresearch
description: Autonomous machine learning experiment loops, neural network architecture optimization, hyperparameter tuning, and keep/discard validation benchmarking inspired by Karpathy AutoResearch.
domain: Machine Learning & Deep Learning
keywords: [autoresearch, karpathy, training loop, val_bpb, loss, transformer, muon, adamw, gpt, mlx, cuda, vram, hyperparameter, benchmark, experiment, pytorch]
version: 1.1.0
---

# ML AutoResearch & Experimentation Loop Playbook

## Objective
Structure and execute autonomous machine learning research loops. Formulate architectural hypotheses (e.g. attention patterns, optimizer configurations, learning rate schedules, normalization placement), execute fixed-budget training benchmarks, and evaluate validation metrics (`val_bpb`, MFU %, tokens/sec) using an empirical **Keep/Discard** decision matrix.

## Methodology: The Karpathy Propose-Train-Evaluate Loop
1. **Hypothesis Formulation:** Propose targeted architectural or algorithmic modifications (e.g. SwiGLU vs GeLU, Muon vs AdamW momentum, Rotary Embeddings, LayerNorm scaling).
2. **Fixed Budget Execution:** Run experiments under a strict compute budget (e.g. 5-minute wall-clock training iterations) to ensure fair comparison across parameter scales.
3. **Primary Evaluation Metrics:**
   - **Validation Bits Per Byte (`val_bpb`):**
     $$\text{val\_bpb} = \frac{\text{Validation Cross-Entropy Loss}}{\ln(2) \times \text{bytes\_per\_token}}$$
     Independent of vocabulary size, providing absolute compression benchmarks.
   - **Peak VRAM (GB):** Peak GPU memory allocated during forward + backward + optimizer step.
   - **Model FLOPs Utilization (MFU %):**
     $$\text{MFU} = \frac{6 \times N \times \text{tokens\_per\_step}}{\text{step\_time\_sec} \times \text{num\_gpus} \times \text{peak\_flops\_per\_gpu}} \times 100\%$$
   - **Hardware FLOPs Utilization (HFU %):** Measures operational FLOPs including activation recomputation.

4. **Muon (Momentum Orthogonalized by Newton-Schulz) Optimizer:**
   - Replaces AdamW on 2D weight matrices (hidden layers).
   - Solves polar decomposition $U = \text{polar}(G)$ via quintic Newton-Schulz iterations:
     $$X_0 = \frac{G}{\|G\|_F + \epsilon}$$
     $$X_{k+1} = X_k (3.4445 I - 4.7750 X_k^T X_k + 2.0315 (X_k^T X_k)^2)$$
   - **Memory Advantage:** Stores only momentum buffer ($m$) in BF16/FP32 (4 bytes/param), eliminating the second-moment variance buffer ($v$). Yields a **66.7% optimizer memory reduction** compared to AdamW (12 bytes/param $\to$ 4 bytes/param).

5. **Keep / Discard Decision Matrix:**
   - **KEEP:** If $\Delta \text{val\_bpb} \le -0.005$ strictly decreases and memory remains within the hardware envelope without step throughput regressions.
   - **DISCARD:** If `val_bpb` degrades, remains flat, or introduces disproportionate latency/complexity.
   - **CRASH:** Out of Memory (OOM) or gradient instability ($\text{NaN} / \text{Inf}$).

6. **Immutable TSV Experiment Ledger:**
   Maintain an append-only ledger tracking `commit`, `val_bpb`, `memory_gb`, `mfu_percent`, `status`, and `description`.

## Output Format Rules
- Include an **AutoResearch Experiment Ledger** table with trial steps, `val_bpb`, memory, MFU %, and status (`KEEP` / `DISCARD`).
- Render a **Validation Loss / BPB Convergence Curve** via a Chart.js JSON block (line chart).
- Provide explicit actionable recommendations for production scaling and hardware allocation.
