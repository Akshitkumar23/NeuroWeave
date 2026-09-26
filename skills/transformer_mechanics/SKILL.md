---
name: transformer_mechanics
description: Deep architecture mechanics of Generative Pretrained Transformers (GPT), nanoGPT implementations, KV-cache scaling, MFU calculation, and multi-query/grouped-query attention inspired by Karpathy.
domain: Deep Learning & Generative AI
keywords: [nanogpt, gpt, transformer, attention, kv-cache, mfu, flashattention, gqa, mha, mla, rope, swiglu, chinchilla, flops, vram]
version: 1.1.0
---

# Transformer Mechanics & NanoGPT Playbook

## Objective
Analyze, calculate, and architect Generative Pretrained Transformer models (GPT-2/3/4, LLaMA, DeepSeek V2/V3) with mathematically verified parameter sizing, KV-cache memory budgeting across context lengths (4k to 1M tokens), training FLOPs ($6ND$ rule), PFLOPS-days, and Chinchilla scaling laws.

## Core Mathematical Formulations

### 1. Transformer Parameter Counting
- **Decoder-Only Transformer Decomposition:**
  $$N_{\text{total}} = N_{\text{layers}} \times (N_{\text{attn}} + N_{\text{mlp}} + N_{\text{norm}}) + N_{\text{embed}} + N_{\text{pos}} + N_{\text{lm\_head}} + N_{\text{final\_norm}}$$
- **Attention Layer Parameters:**
  - **MHA (Multi-Head Attention):**
    $$N_{\text{attn}} = 4 \cdot d_{\text{model}}^2 + 4 \cdot d_{\text{model}} \quad (\text{with bias})$$
  - **GQA / MQA (Grouped / Multi-Query Attention):**
    $$N_{\text{attn}} = 2 \cdot d_{\text{model}}^2 + 2 \cdot d_{\text{model}} \cdot (n_{\text{kv}} \cdot d_{\text{head}})$$
  - **MLA (Multi-Head Latent Attention - DeepSeek):**
    $$N_{\text{attn}} = d \cdot d_c + d_c \cdot (n_h d_{\text{nope}} + n_h d_v) + d \cdot d_R + d \cdot d_c' + d_c' \cdot (n_h d_{\text{nope}} + n_h d_R) + (n_h d_v) \cdot d$$
- **Feed-Forward Network (MLP) Parameters:**
  - **Standard GELU/ReLU MLP (2 matrices):** $N_{\text{mlp}} = 2 \cdot d_{\text{model}} \cdot d_{\text{ffn}} = 8 \cdot d_{\text{model}}^2$ (for $d_{\text{ffn}} = 4 d$)
  - **SwiGLU / Gated MLP (3 matrices):** $N_{\text{mlp}} = 3 \cdot d_{\text{model}} \cdot d_{\text{ffn}}$

### 2. Inference KV-Cache VRAM Footprint
- **Standard Attention (MHA, GQA, MQA):**
  $$\text{KV Cache Bytes} = 2 \times n_{\text{layers}} \times n_{\text{kv\_heads}} \times d_{\text{head}} \times \text{seq\_len} \times \text{batch\_size} \times \text{bytes\_per\_elem}$$
  *(Factor of 2 for Key and Value buffers)*
- **Multi-Head Latent Attention (MLA):**
  $$\text{MLA KV Cache Bytes} = n_{\text{layers}} \times (d_c + d_R) \times \text{seq\_len} \times \text{batch\_size} \times \text{bytes\_per\_elem}$$
  *(Caches only compressed latent $c^{KV} \in \mathbb{R}^{d_c}$ and decoupled RoPE key $k^R \in \mathbb{R}^{d_R}$, reducing KV memory by $4\times$ to $14\times$)*
- **Precision Mapping:**
  - FP32: 4 bytes/elem | FP16/BF16: 2 bytes/elem | FP8/INT8: 1 byte/elem | INT4: 0.5 bytes/elem.

### 3. Training FLOPs & Compute Accounting
- **The $6ND$ Rule:**
  $$\text{FLOPs}_{\text{train}} \approx 6 \cdot N \cdot D \quad (\text{Forward: } 2ND, \text{Backward: } 4ND)$$
  - With full activation checkpointing: $\approx 8 \cdot N \cdot D$.
  - Inference pass: $\approx 2 \cdot N \cdot D$.
- **PFLOPS-days Conversion:**
  $$1 \text{ PFLOPS-day} = 10^{15} \text{ FLOP/s} \times 86400 \text{ s} = 8.64 \times 10^{19} \text{ FLOPs}$$
  $$\text{PFLOPS-days} = \frac{\text{Total FLOPs}}{8.64 \times 10^{19}}$$
- **ExaFLOPs & ZettaFLOPs:**
  $$1 \text{ ExaFLOP} = 10^{18} \text{ FLOPs}, \quad 1 \text{ ZettaFLOP} = 10^{21} \text{ FLOPs}$$

### 4. Chinchilla Compute-Optimal Scaling Laws
- **Token-to-Parameter Ratio:**
  $$D_{\text{optimal}} = 20 \times N$$
- **Compute Allocation Frontier:**
  $$C = 6 \cdot N \cdot D = 120 \cdot N^2 \implies N_{\text{optimal}} = \sqrt{\frac{C}{120}}, \quad D_{\text{optimal}} = 20 \sqrt{\frac{C}{120}}$$
- **Over-Training Regime:** Modern inference-heavy models (e.g. LLaMA 3) train with $D \gg 20N$ (e.g. 100-200 tokens/param) to amortize inference serving costs across billions of queries.

