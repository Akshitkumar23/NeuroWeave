"""
nano_engine.py
Inspired directly by Andrej Karpathy's nanoGPT & AutoResearch.
Provides mathematically verified, pure-Python calculation utilities for:
1. Transformer parameter sizing (MHA, GQA, MQA, MLA, SwiGLU, RoPE, tied/untied embeddings).
2. Training FLOPs calculation (6ND rule, attention quadratic terms, PFLOPS-days, ExaFLOPs).
3. Model FLOPs Utilization (MFU) & Hardware FLOPs Utilization (HFU).
4. KV-cache VRAM footprint across context lengths (4k to 1M tokens) with FP16/BF16/FP8/INT4.
5. Muon polar decomposition vs AdamW memory footprint reduction & pure Newton-Schulz solver.
6. Chinchilla compute-optimal scaling laws (D = 20 * N, compute frontier inverse solving).
"""

import math
from typing import Dict, Any, List, Optional, Union, Tuple


# =====================================================================
# 1. TRANSFORMER PARAMETER COUNTING
# =====================================================================

def calculate_transformer_params(
    n_layer: int = 12,
    n_embd: int = 768,
    n_head: int = 12,
    n_kv_head: Optional[int] = None,
    vocab_size: int = 50257,
    mlp_ratio: float = 4.0,
    mlp_type: str = 'standard',
    mlp_hidden: Optional[int] = None,
    attn_type: str = 'MHA',
    head_dim: Optional[int] = None,
    pos_emb_type: str = 'learned',
    max_seq_len: int = 1024,
    tie_embeddings: bool = True,
    bias: bool = True,
    norm_type: str = 'layernorm',
    # MLA specific parameters (DeepSeek V2/V3 style)
    q_lora_rank: Optional[int] = 1536,
    kv_lora_rank: Optional[int] = 512,
    qk_rope_head_dim: Optional[int] = 64,
    qk_nope_head_dim: Optional[int] = 128,
    v_head_dim: Optional[int] = 128,
) -> Dict[str, Any]:
    """
    Computes exact parameter counts for modern Transformer architectures:
    - Standard GPT (MHA, standard GELU MLP, learned pos emb, tied weights)
    - Modern LLaMA / Mistral (GQA/MQA, SwiGLU MLP, RoPE, untied weights, RMSNorm)
    - DeepSeek V2/V3 (Multi-Head Latent Attention - MLA, SwiGLU / MoE)

    Supports edge cases: batch_size=0, zero layers, custom head dims, untied embeddings.
    """
    if n_layer < 0 or n_embd < 0 or n_head < 0 or vocab_size < 0 or max_seq_len < 0:
        raise ValueError("Model dimensions, layers, vocab_size, and max_seq_len must be non-negative.")

    if n_layer == 0 or n_embd == 0:
        return {
            'total_parameters': 0,
            'total_parameters_millions': 0.0,
            'total_parameters_billions': 0.0,
            'non_embedding_parameters': 0,
            'non_embedding_parameters_millions': 0.0,
            'non_embedding_parameters_billions': 0.0,
            'per_layer_parameters': 0,
            'attention_parameters_per_layer': 0,
            'mlp_parameters_per_layer': 0,
            'norm_parameters_per_layer': 0,
            'embedding_parameters': 0,
            'pos_embedding_parameters': 0,
            'lm_head_parameters': 0,
            'final_norm_parameters': 0,
            'layers': n_layer,
            'hidden_dimension': n_embd,
            'attention_heads': n_head,
            'kv_heads': n_kv_head if n_kv_head is not None else n_head,
            'head_dimension': head_dim if head_dim is not None else 0,
            'attn_type': attn_type.upper(),
            'mlp_type': mlp_type.lower(),
            'tie_embeddings': tie_embeddings,
            'bias': bias
        }

    attn_type_upper = attn_type.upper()
    mlp_type_lower = mlp_type.lower()
    norm_type_lower = norm_type.lower()
    pos_emb_type_lower = pos_emb_type.lower()

    # Determine head dimension
    if head_dim is None:
        if n_head > 0:
            if n_embd % n_head != 0:
                raise ValueError(f"n_embd ({n_embd}) must be divisible by n_head ({n_head}) when head_dim is None.")
            head_dim = n_embd // n_head
        else:
            head_dim = 0

    # Determine KV heads
    if attn_type_upper == 'MHA':
        effective_n_kv_head = n_head
    elif attn_type_upper == 'MQA':
        effective_n_kv_head = 1
    elif attn_type_upper == 'GQA':
        effective_n_kv_head = n_kv_head if n_kv_head is not None else max(1, n_head // 4)
    elif attn_type_upper == 'MLA':
        effective_n_kv_head = n_head
    else:
        raise ValueError(f"Unsupported attn_type: {attn_type}. Use 'MHA', 'GQA', 'MQA', or 'MLA'.")

    # 1. Embedding parameters
    token_emb_params = vocab_size * n_embd

    if pos_emb_type_lower in ('learned', 'absolute'):
        pos_emb_params = max_seq_len * n_embd
    elif pos_emb_type_lower in ('rope', 'rotary', 'alibi', 'none', 'nope'):
        pos_emb_params = 0
    else:
        raise ValueError(f"Unsupported pos_emb_type: {pos_emb_type}. Use 'learned', 'rope', 'alibi', or 'none'.")

    # Output head parameters
    if tie_embeddings:
        lm_head_params = 0
    else:
        lm_head_params = vocab_size * n_embd

    # 2. Attention parameters per layer
    if attn_type_upper == 'MLA':
        # DeepSeek Multi-Head Latent Attention (MLA)
        # q_lora_rank (d_c'), kv_lora_rank (d_c), qk_rope_head_dim (d_R), qk_nope_head_dim (d_nope), v_head_dim (d_v)
        d_c_prime = q_lora_rank if q_lora_rank is not None else n_embd
        d_c = kv_lora_rank if kv_lora_rank is not None else (n_embd // 2)
        d_r = qk_rope_head_dim if qk_rope_head_dim is not None else 64
        d_nope = qk_nope_head_dim if qk_nope_head_dim is not None else head_dim
        d_v = v_head_dim if v_head_dim is not None else head_dim

        # Down-projection for KV
        w_dkv = n_embd * d_c
        # Up-projection for K (nope) & V
        w_uk = d_c * (n_head * d_nope)
        w_uv = d_c * (n_head * d_v)
        # Decoupled RoPE Key
        w_kr = n_embd * d_r

        # Query compression & RoPE
        if q_lora_rank is not None and q_lora_rank > 0:
            w_dq = n_embd * d_c_prime
            w_uq = d_c_prime * (n_head * d_nope)
            w_qr = d_c_prime * (n_head * d_r)
        else:
            w_dq = 0
            w_uq = n_embd * (n_head * d_nope)
            w_qr = n_embd * (n_head * d_r)

        # Output projection
        w_o = (n_head * d_v) * n_embd

        attn_params = w_dkv + w_uk + w_uv + w_kr + w_dq + w_uq + w_qr + w_o
        if bias:
            attn_params += (d_c + n_head * d_nope + n_head * d_v + d_r + (d_c_prime if q_lora_rank else 0) + n_head * d_nope + n_head * d_r + n_embd)

    elif attn_type_upper in ('MHA', 'GQA', 'MQA'):
        q_dim = n_head * head_dim
        kv_dim = effective_n_kv_head * head_dim
        w_q = n_embd * q_dim
        w_k = n_embd * kv_dim
        w_v = n_embd * kv_dim
        w_o = q_dim * n_embd
        attn_params = w_q + w_k + w_v + w_o
        if bias:
            attn_params += (q_dim + kv_dim + kv_dim + n_embd)

    # 3. MLP parameters per layer
    if mlp_hidden is not None:
        d_ffn = mlp_hidden
    else:
        d_ffn = int(n_embd * mlp_ratio)

    if mlp_type_lower in ('standard', 'gelu', 'relu'):
        # 2 matrices: W_fc1 (n_embd -> d_ffn) and W_fc2 (d_ffn -> n_embd)
        w_fc1 = n_embd * d_ffn
        w_fc2 = d_ffn * n_embd
        mlp_params = w_fc1 + w_fc2
        if bias:
            mlp_params += (d_ffn + n_embd)
    elif mlp_type_lower in ('swiglu', 'glu', 'geglu', 'gated'):
        # 3 matrices: W_gate (n_embd -> d_ffn), W_up (n_embd -> d_ffn), W_down (d_ffn -> n_embd)
        w_gate = n_embd * d_ffn
        w_up = n_embd * d_ffn
        w_down = d_ffn * n_embd
        mlp_params = w_gate + w_up + w_down
        if bias:
            mlp_params += (d_ffn + d_ffn + n_embd)
    else:
        raise ValueError(f"Unsupported mlp_type: {mlp_type}. Use 'standard' or 'swiglu'.")

    # 4. Normalization parameters per layer & final norm
    if norm_type_lower in ('layernorm', 'ln'):
        # 2 LayerNorms per block (weight + bias = 2 * n_embd each)
        norm_params_per_layer = 2 * (2 * n_embd) if bias else 2 * n_embd
        final_norm = 2 * n_embd if bias else n_embd
    elif norm_type_lower in ('rmsnorm', 'rms'):
        # RMSNorm has scale weight only (1 * n_embd), no bias
        norm_params_per_layer = 2 * n_embd
        final_norm = n_embd
    else:
        raise ValueError(f"Unsupported norm_type: {norm_type}. Use 'layernorm' or 'rmsnorm'.")

    per_layer_params = attn_params + mlp_params + norm_params_per_layer
    total_layer_params = n_layer * per_layer_params

    total_params = total_layer_params + token_emb_params + pos_emb_params + lm_head_params + final_norm
    non_embedding_params = total_layer_params + final_norm + (lm_head_params if not tie_embeddings else 0)

    return {
        'total_parameters': total_params,
        'total_parameters_millions': round(total_params / 1e6, 2),
        'total_parameters_billions': round(total_params / 1e9, 3),
        'non_embedding_parameters': non_embedding_params,
        'non_embedding_parameters_millions': round(non_embedding_params / 1e6, 2),
        'non_embedding_parameters_billions': round(non_embedding_params / 1e9, 3),
        'per_layer_parameters': per_layer_params,
        'attention_parameters_per_layer': attn_params,
        'mlp_parameters_per_layer': mlp_params,
        'norm_parameters_per_layer': norm_params_per_layer,
        'embedding_parameters': token_emb_params,
        'pos_embedding_parameters': pos_emb_params,
        'lm_head_parameters': lm_head_params,
        'final_norm_parameters': final_norm,
        'layers': n_layer,
        'hidden_dimension': n_embd,
        'attention_heads': n_head,
        'kv_heads': effective_n_kv_head,
        'head_dimension': head_dim,
        'attn_type': attn_type_upper,
        'mlp_type': mlp_type_lower,
        'tie_embeddings': tie_embeddings,
        'bias': bias
    }


# =====================================================================
# 2. KV-CACHE VRAM FOOTPRINT ACROSS CONTEXT LENGTHS & PRECISIONS
# =====================================================================

PRECISION_BYTES_MAP: Dict[str, float] = {
    'fp32': 4.0,
    'float32': 4.0,
    'tf32': 4.0,
    'fp16': 2.0,
    'float16': 2.0,
    'bf16': 2.0,
    'bfloat16': 2.0,
    'fp8': 1.0,
    'fp8_e4m3': 1.0,
    'fp8_e5m2': 1.0,
    'int8': 1.0,
    'int4': 0.5,
    'uint4': 0.5
}

def calculate_kv_cache_memory(
    n_layer: int = 32,
    n_kv_head: int = 8,
    head_dim: int = 128,
    seq_len: int = 4096,
    batch_size: int = 16,
    precision: str = 'fp16',
    attn_type: str = 'standard',
    # MLA specific parameters
    kv_lora_rank: int = 512,
    qk_rope_head_dim: int = 64
) -> Dict[str, Any]:
    """
    Computes precise KV-cache memory consumption in bytes, MB, and GB.
    Supports:
    - Standard MHA/GQA/MQA: 2 * n_layer * n_kv_head * head_dim * seq_len * batch_size * bytes_per_elem
    - MLA (Multi-Head Latent Attention): n_layer * (kv_lora_rank + qk_rope_head_dim) * seq_len * batch_size * bytes_per_elem
    - Precisions: FP32 (4B), FP16/BF16 (2B), FP8/INT8 (1B), INT4 (0.5B).
    - Edge cases: batch_size=0, seq_len=0, n_layer=0.
    """
    if n_layer < 0 or n_kv_head < 0 or head_dim < 0 or seq_len < 0 or batch_size < 0:
        raise ValueError("Layer count, heads, head_dim, seq_len, and batch_size must be non-negative.")

    prec_lower = precision.lower()
    if prec_lower not in PRECISION_BYTES_MAP:
        raise ValueError(f"Unsupported precision: {precision}. Supported: {list(PRECISION_BYTES_MAP.keys())}")

    bytes_per_elem = PRECISION_BYTES_MAP[prec_lower]
    total_tokens = seq_len * batch_size
    attn_type_upper = attn_type.upper()

    if total_tokens == 0 or n_layer == 0:
        return {
            'kv_cache_bytes': 0,
            'kv_cache_mb': 0.0,
            'kv_cache_gb': 0.0,
            'tokens_cached': 0,
            'per_token_bytes': 0.0,
            'per_token_per_layer_bytes': 0.0,
            'precision': prec_lower,
            'bytes_per_elem': bytes_per_elem,
            'attn_type': attn_type_upper
        }

    if attn_type_upper == 'MLA':
        # In MLA, we cache only the compressed latent vector c^{KV} (kv_lora_rank) and decoupled RoPE key k^R (qk_rope_head_dim)
        per_token_per_layer_elements = kv_lora_rank + qk_rope_head_dim
        per_token_per_layer_bytes = per_token_per_layer_elements * bytes_per_elem
        per_token_bytes = n_layer * per_token_per_layer_bytes
        total_bytes = int(per_token_bytes * total_tokens)
    else:
        # Standard MHA/GQA/MQA: factor of 2 for Key and Value
        per_token_per_layer_elements = 2 * n_kv_head * head_dim
        per_token_per_layer_bytes = per_token_per_layer_elements * bytes_per_elem
        per_token_bytes = n_layer * per_token_per_layer_bytes
        total_bytes = int(per_token_bytes * total_tokens)

    total_mb = total_bytes / (1024**2)
    total_gb = total_bytes / (1024**3)

    return {
        'kv_cache_bytes': total_bytes,
        'kv_cache_mb': round(total_mb, 2),
        'kv_cache_gb': round(total_gb, 4),
        'tokens_cached': total_tokens,
        'per_token_bytes': round(per_token_bytes, 2),
        'per_token_per_layer_bytes': round(per_token_per_layer_bytes, 2),
        'precision': prec_lower,
        'bytes_per_elem': bytes_per_elem,
        'attn_type': attn_type_upper
    }

# Alias for backward compatibility
calculate_kv_cache_vram = calculate_kv_cache_memory


def generate_kv_cache_context_table(
    n_layer: int = 32,
    n_head: int = 32,
    n_kv_head: int = 8,
    head_dim: int = 128,
    batch_size: int = 1,
    context_lengths: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """
    Generates a comparative KV-cache VRAM scaling table across context lengths (4k up to 1M tokens)
    and precisions (FP16, FP8, INT4) comparing Standard GQA vs DeepSeek MLA.
    """
    if context_lengths is None:
        context_lengths = [4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576]

    table = []
    for ctx in context_lengths:
        mha_fp16 = calculate_kv_cache_memory(n_layer, n_head, head_dim, ctx, batch_size, 'fp16', 'standard')['kv_cache_gb']
        gqa_fp16 = calculate_kv_cache_memory(n_layer, n_kv_head, head_dim, ctx, batch_size, 'fp16', 'standard')['kv_cache_gb']
        gqa_fp8 = calculate_kv_cache_memory(n_layer, n_kv_head, head_dim, ctx, batch_size, 'fp8', 'standard')['kv_cache_gb']
        gqa_int4 = calculate_kv_cache_memory(n_layer, n_kv_head, head_dim, ctx, batch_size, 'int4', 'standard')['kv_cache_gb']
        mla_fp16 = calculate_kv_cache_memory(n_layer, n_kv_head, head_dim, ctx, batch_size, 'fp16', 'mla', kv_lora_rank=512, qk_rope_head_dim=64)['kv_cache_gb']
        mla_fp8 = calculate_kv_cache_memory(n_layer, n_kv_head, head_dim, ctx, batch_size, 'fp8', 'mla', kv_lora_rank=512, qk_rope_head_dim=64)['kv_cache_gb']

        table.append({
            'context_length': ctx,
            'context_k': f"{ctx // 1024}k" if ctx >= 1024 else str(ctx),
            'mha_fp16_gb': mha_fp16,
            'gqa_fp16_gb': gqa_fp16,
            'gqa_fp8_gb': gqa_fp8,
            'gqa_int4_gb': gqa_int4,
            'mla_fp16_gb': mla_fp16,
            'mla_fp8_gb': mla_fp8,
            'gqa_vs_mha_compression': round(mha_fp16 / gqa_fp16, 2) if gqa_fp16 > 0 else 1.0,
            'mla_vs_gqa_compression': round(gqa_fp16 / mla_fp16, 2) if mla_fp16 > 0 else 1.0
        })

    return table


# =====================================================================
# 3. TRAINING & INFERENCE FLOPS CALCULATION & MFU
# =====================================================================

def calculate_training_flops(
    params_b: float,
    tokens_b: float,
    forward_only: bool = False,
    activation_checkpointing: bool = False,
    seq_len: Optional[int] = None,
    n_layer: Optional[int] = None,
    n_embd: Optional[int] = None
) -> Dict[str, Any]:
    """
    Computes exact training or inference FLOPs.
    Formulation:
    - Standard forward pass: 2 * N * D FLOPs
    - Standard backward pass: 4 * N * D FLOPs (2 FLOPs for d_act, 2 FLOPs for d_weight)
    - Full training loop: 6 * N * D FLOPs
    - With full activation checkpointing / recomputation: 8 * N * D FLOPs
    - Optional attention quadratic term: 12 * L * s * d * D FLOPs for self-attention matmuls.

    Conversions:
    - 1 PFLOPS-day = 1e15 * 86400 = 8.64e19 FLOPs.
    - 1 ExaFLOP = 1e18 FLOPs.
    - 1 ZettaFLOP = 1e21 FLOPs.
    """
    if params_b < 0 or tokens_b < 0:
        raise ValueError("params_b and tokens_b must be non-negative.")

    n_params = params_b * 1e9
    n_tokens = tokens_b * 1e9

    if forward_only:
        multiplier = 2.0
    elif activation_checkpointing:
        multiplier = 8.0
    else:
        multiplier = 6.0

    dense_flops = multiplier * n_params * n_tokens

    # Optional attention quadratic FLOPs calculation
    attn_quadratic_flops = 0.0
    if seq_len is not None and n_layer is not None and n_embd is not None and seq_len > 0:
        # Per token per layer forward matmul FLOPs for QK^T and AV: 4 * seq_len * n_embd
        attn_mult = 4.0 if forward_only else (16.0 if activation_checkpointing else 12.0)
        attn_quadratic_flops = attn_mult * n_layer * seq_len * n_embd * n_tokens

    total_flops = dense_flops + attn_quadratic_flops
    petaflops_days = total_flops / (1e15 * 86400)
    exaflops = total_flops / 1e18
    zettaflops = total_flops / 1e21

    return {
        'total_flops': total_flops,
        'total_flops_scientific': f"{total_flops:.3e}",
        'dense_flops': dense_flops,
        'attn_quadratic_flops': attn_quadratic_flops,
        'exaflops': round(exaflops, 6),
        'zettaflops': round(zettaflops, 6),
        'petaflops_days': round(petaflops_days, 4),
        'tokens_billion': tokens_b,
        'params_billion': params_b,
        'multiplier_used': multiplier,
        'mode': 'inference' if forward_only else ('training_recompute' if activation_checkpointing else 'training_standard')
    }


def calculate_mfu(
    params_b: float,
    tokens_per_step: int,
    step_time_sec: float,
    num_gpus: int = 1,
    gpu_peak_tflops: float = 312.0,
    activation_checkpointing: bool = False
) -> Dict[str, Any]:
    """
    Computes Model FLOPs Utilization (MFU) and Hardware FLOPs Utilization (HFU)
    following Andrej Karpathy's nanoGPT standard formula.

    MFU = (6 * N * tokens_per_step) / (step_time_sec * num_gpus * peak_flops_per_gpu)
    """
    if step_time_sec <= 0 or num_gpus <= 0 or gpu_peak_tflops <= 0:
        raise ValueError("step_time_sec, num_gpus, and gpu_peak_tflops must be positive.")

    n_params = params_b * 1e9
    flops_per_token_theoretical = 6.0 * n_params
    flops_per_step_theoretical = flops_per_token_theoretical * tokens_per_step

    # Operational flops (HFU accounts for recomputation if present)
    op_multiplier = 8.0 if activation_checkpointing else 6.0
    flops_per_step_operational = op_multiplier * n_params * tokens_per_step

    achieved_flops_per_sec = flops_per_step_theoretical / step_time_sec
    achieved_tflops = achieved_flops_per_sec / 1e12

    total_peak_tflops = num_gpus * gpu_peak_tflops
    mfu_percent = (achieved_tflops / total_peak_tflops) * 100.0

    achieved_op_tflops = (flops_per_step_operational / step_time_sec) / 1e12
    hfu_percent = (achieved_op_tflops / total_peak_tflops) * 100.0

    tokens_per_sec = tokens_per_step / step_time_sec

    return {
        'mfu_percent': round(mfu_percent, 2),
        'hfu_percent': round(hfu_percent, 2),
        'achieved_tflops': round(achieved_tflops, 2),
        'total_peak_tflops': round(total_peak_tflops, 2),
        'tokens_per_sec': round(tokens_per_sec, 2),
        'step_time_sec': step_time_sec,
        'tokens_per_step': tokens_per_step,
        'params_billion': params_b,
        'num_gpus': num_gpus
    }


# =====================================================================
# 4. TRAINING VRAM ESTIMATION & OPTIMIZER COMPARISON (ADAMW VS MUON)
# =====================================================================

def estimate_training_vram(
    params_b: float,
    batch_size: int = 4,
    seq_len: int = 2048,
    precision: str = 'bf16',
    optimizer: str = 'adamw',
    activation_checkpointing: bool = True,
    zero_stage: int = 0,
    num_gpus: int = 1
) -> Dict[str, Any]:
    """
    Estimates total GPU training memory breakdown:
    - Model weights
    - Gradients
    - Optimizer states (AdamW vs Muon vs SGD vs 8-bit Adam)
    - Activations (with or without selective/full activation checkpointing)
    - ZeRO stage 0, 1, 2, 3 partitioning support.
    """
    if params_b < 0 or batch_size < 0 or seq_len < 0:
        raise ValueError("params_b, batch_size, and seq_len must be non-negative.")

    if params_b == 0 or (batch_size == 0 and seq_len == 0):
        return {
            'total_vram_gb': 0.0,
            'weights_vram_gb': 0.0,
            'gradients_vram_gb': 0.0,
            'optimizer_vram_gb': 0.0,
            'activations_vram_gb': 0.0,
            'suggested_gpu': 'None required',
            'optimizer': optimizer.lower()
        }

    prec_lower = precision.lower()
    bytes_per_param = PRECISION_BYTES_MAP.get(prec_lower, 2.0)
    total_params = params_b * 1e9

    # Weights and Gradients
    weights_bytes = total_params * bytes_per_param
    grads_bytes = total_params * bytes_per_param

    # Optimizer state bytes per parameter
    opt_lower = optimizer.lower()
    if opt_lower in ('adamw', 'adam'):
        # AdamW mixed precision: fp32 master weight (4B) + fp32 momentum (4B) + fp32 variance (4B) = 12B/param
        opt_bytes_per_param = 12.0 if bytes_per_param <= 2.0 else 8.0
    elif opt_lower in ('muon', 'polar'):
        # Muon: Applied to 2D matrices (stores momentum only in bf16/fp32, no 2nd moment variance).
        # Momentum buffer (4B fp32 or 2B bf16) + minimal master weight / scratch = 4B to 6B/param
        opt_bytes_per_param = 4.0
    elif opt_lower in ('8bit_adam', '8bit_adamw', 'bnb_adam'):
        # 8-bit AdamW: 1B momentum + 1B variance + 4B master = 6B/param
        opt_bytes_per_param = 6.0
    elif opt_lower in ('sgd', 'sgd_momentum'):
        # SGD with momentum: 4B momentum
        opt_bytes_per_param = 4.0
    else:
        raise ValueError(f"Unsupported optimizer: {optimizer}. Supported: 'adamw', 'muon', '8bit_adam', 'sgd'")

    opt_bytes = total_params * opt_bytes_per_param

    # ZeRO Stage Sharding
    effective_gpus = max(1, num_gpus)
    if zero_stage == 1:
        # ZeRO-1: Shards optimizer state across data-parallel GPUs
        opt_bytes /= effective_gpus
    elif zero_stage == 2:
        # ZeRO-2: Shards optimizer state + gradients
        opt_bytes /= effective_gpus
        grads_bytes /= effective_gpus
    elif zero_stage >= 3:
        # ZeRO-3: Shards optimizer + gradients + model weights
        opt_bytes /= effective_gpus
        grads_bytes /= effective_gpus
        weights_bytes /= effective_gpus

    # Activations calculation
    # For a transformer layer with hidden dimension d ≈ sqrt(params / (12 * n_layers))
    # Standard activation memory per token per layer ≈ 34 * d bytes (no recompute)
    # With activation checkpointing: ≈ 2 * d bytes per layer (stores layer input checkpoints)
    hidden_dim_est = math.sqrt(max(1.0, total_params / 144.0)) # heuristic estimation
    if activation_checkpointing:
        # Checkpointing stores input to each layer
        act_factor = 2.0
    else:
        # Uncheckpointed stores all intermediate QK, AV, MLP projections
        act_factor = 16.0

    act_bytes = batch_size * seq_len * hidden_dim_est * act_factor * bytes_per_param

    weights_gb = weights_bytes / (1024**3)
    gradients_gb = grads_bytes / (1024**3)
    optimizer_gb = opt_bytes / (1024**3)
    activations_gb = act_bytes / (1024**3)

    total_gb = weights_gb + gradients_gb + optimizer_gb + activations_gb

    # Suggested GPU hardware
    if total_gb > 80:
        suggested_gpu = f"{math.ceil(total_gb / 80)}x H100 80GB (Distributed / FSDP / DeepSpeed)"
    elif total_gb > 40:
        suggested_gpu = "H100 / A100 80GB"
    elif total_gb > 24:
        suggested_gpu = "A6000 48GB / A100 40GB"
    elif total_gb > 16:
        suggested_gpu = "RTX 4090 / RTX 3090 24GB"
    elif total_gb > 8:
        suggested_gpu = "RTX 4080 16GB / V100 16GB"
    else:
        suggested_gpu = "RTX 4070 / RTX 3080 10-12GB"

    return {
        'total_vram_gb': round(total_gb, 2),
        'weights_vram_gb': round(weights_gb, 2),
        'gradients_vram_gb': round(gradients_gb, 2),
        'optimizer_vram_gb': round(optimizer_gb, 2),
        'activations_vram_gb': round(activations_gb, 2),
        'suggested_gpu': suggested_gpu,
        'optimizer': opt_lower,
        'zero_stage': zero_stage,
        'activation_checkpointing': activation_checkpointing
    }


def compare_optimizer_footprint(params_b: float, precision: str = 'bf16') -> Dict[str, Any]:
    """
    Compares exact memory footprint of AdamW vs Muon (Polar Newton-Schulz) vs SGD vs 8-Bit AdamW.
    Highlights why Muon reduces optimizer state by ~66.7% compared to AdamW.
    """
    total_params = params_b * 1e9
    bytes_per_param = PRECISION_BYTES_MAP.get(precision.lower(), 2.0)
    model_weight_gb = (total_params * bytes_per_param) / (1024**3)
    grad_gb = (total_params * bytes_per_param) / (1024**3)

    # AdamW: 12 bytes/param (4B master + 4B m + 4B v)
    adamw_opt_gb = (total_params * 12.0) / (1024**3)
    adamw_total_gb = model_weight_gb + grad_gb + adamw_opt_gb

    # Muon: 4 bytes/param (4B momentum m only, NO second moment v)
    muon_opt_gb = (total_params * 4.0) / (1024**3)
    muon_total_gb = model_weight_gb + grad_gb + muon_opt_gb

    # 8-bit AdamW: 6 bytes/param (4B master + 1B m + 1B v)
    bnb_opt_gb = (total_params * 6.0) / (1024**3)
    bnb_total_gb = model_weight_gb + grad_gb + bnb_opt_gb

    # SGD with momentum: 4 bytes/param
    sgd_opt_gb = (total_params * 4.0) / (1024**3)
    sgd_total_gb = model_weight_gb + grad_gb + sgd_opt_gb

    opt_reduction_muon_vs_adamw = ((adamw_opt_gb - muon_opt_gb) / adamw_opt_gb) * 100.0 if adamw_opt_gb > 0 else 0.0
    total_reduction_muon_vs_adamw = ((adamw_total_gb - muon_total_gb) / adamw_total_gb) * 100.0 if adamw_total_gb > 0 else 0.0

    return {
        'params_billion': params_b,
        'precision': precision,
        'model_weights_gb': round(model_weight_gb, 2),
        'gradients_gb': round(grad_gb, 2),
        'adamw': {
            'optimizer_gb': round(adamw_opt_gb, 2),
            'total_static_gb': round(adamw_total_gb, 2),
            'bytes_per_param': 12.0
        },
        'muon': {
            'optimizer_gb': round(muon_opt_gb, 2),
            'total_static_gb': round(muon_total_gb, 2),
            'bytes_per_param': 4.0
        },
        'bnb_8bit_adamw': {
            'optimizer_gb': round(bnb_opt_gb, 2),
            'total_static_gb': round(bnb_total_gb, 2),
            'bytes_per_param': 6.0
        },
        'sgd_momentum': {
            'optimizer_gb': round(sgd_opt_gb, 2),
            'total_static_gb': round(sgd_total_gb, 2),
            'bytes_per_param': 4.0
        },
        'muon_optimizer_memory_savings_percent': round(opt_reduction_muon_vs_adamw, 2),
        'muon_total_static_memory_savings_percent': round(total_reduction_muon_vs_adamw, 2),
        'muon_mechanism': 'Orthogonalizes 2D weight gradients via quintic Newton-Schulz iterations, eliminating the second-moment variance buffer (v_t).'
    }


# =====================================================================
# 5. NEWTON-SCHULZ POLAR DECOMPOSITION SOLVER (MUON OPTIMIZER CORE)
# =====================================================================

def newton_schulz_polar(
    matrix: List[List[float]],
    steps: int = 5,
    eps: float = 1e-7,
    mode: str = 'muon_quintic',
    coefficients: Tuple[float, float, float] = (3.4445, -4.7750, 2.0315)
) -> Tuple[List[List[float]], Dict[str, Any]]:
    """
    Pure-Python reference implementation of Newton-Schulz polar decomposition
    for matrix orthogonalization (Andrej Karpathy & Keller Jordan modded-nanogpt Muon optimizer).

    Modes:
    - 'muon_quintic': Fast 5-step quintic polynomial (a=3.4445, b=-4.7750, c=2.0315) used in Muon.
    - 'classical_cubic': Exact analytical polar decomposition X_{k+1} = 0.5 * X_k * (3*I - X_k^T * X_k)
      converging to machine-precision orthonormal matrix (||X^T X - I||_F < 1e-7).
    """
    rows = len(matrix)
    if rows == 0:
        return [], {'steps': 0, 'frobenius_norm': 0.0, 'orthogonality_error': 0.0, 'is_orthogonal': True}
    cols = len(matrix[0])

    mode_lower = mode.lower()

    # Helper: matrix multiplication
    def matmul(A: List[List[float]], B: List[List[float]]) -> List[List[float]]:
        r_A, c_A = len(A), len(A[0])
        r_B, c_B = len(B), len(B[0])
        out = [[0.0 for _ in range(c_B)] for _ in range(r_A)]
        for i in range(r_A):
            for k in range(c_A):
                a_ik = A[i][k]
                for j in range(c_B):
                    out[i][j] += a_ik * B[k][j]
        return out

    # Helper: transpose
    def transpose(A: List[List[float]]) -> List[List[float]]:
        return [[A[r][c] for r in range(len(A))] for c in range(len(A[0]))]

    # Helper: Frobenius norm
    frob_sq = sum(matrix[r][c] ** 2 for r in range(rows) for c in range(cols))
    frob_norm = math.sqrt(frob_sq)

    # Initial normalization: X = matrix / (||matrix||_F + eps)
    scale = 1.0 / (frob_norm + eps)
    X = [[matrix[r][c] * scale for c in range(cols)] for r in range(rows)]

    if mode_lower in ('classical', 'classical_cubic', 'cubic', 'exact'):
        for _ in range(steps):
            XT = transpose(X)
            XTX = matmul(XT, X) # cols x cols
            poly = [[(3.0 if i == j else 0.0) - XTX[i][j] for j in range(cols)] for i in range(cols)]
            X_next = matmul(X, poly)
            X = [[0.5 * X_next[i][j] for j in range(cols)] for i in range(rows)]
    else:
        # Muon quintic iteration (Keller Jordan / Andrej Karpathy modded-nanogpt)
        transposed = False
        if rows > cols:
            X = transpose(X)
            rows, cols = cols, rows
            transposed = True

        a, b, c = coefficients
        for _ in range(steps):
            XT = transpose(X)
            A = matmul(X, XT) # rows x rows
            A2 = matmul(A, A)
            B = [[b * A[i][j] + c * A2[i][j] for j in range(rows)] for i in range(rows)]
            BX = matmul(B, X)
            X = [[a * X[i][j] + BX[i][j] for j in range(cols)] for i in range(rows)]

        if transposed:
            X = transpose(X)
            rows, cols = cols, rows

    # Compute orthogonality error: ||X^T * X - I||_F
    XT_final = transpose(X)
    XTX = matmul(XT_final, X)
    diff_frob_sq = 0.0
    max_off_diag = 0.0
    for i in range(len(XTX)):
        for j in range(len(XTX[0])):
            expected = 1.0 if i == j else 0.0
            diff = abs(XTX[i][j] - expected)
            diff_frob_sq += diff ** 2
            if i != j:
                max_off_diag = max(max_off_diag, abs(XTX[i][j]))
    ortho_error = math.sqrt(diff_frob_sq)
    threshold = 0.01 if mode_lower.startswith(('classical', 'cubic', 'exact')) else 0.20
    return X, {
        'steps': steps,
        'mode': mode_lower,
        'initial_frobenius_norm': round(frob_norm, 6),
        'orthogonality_error': round(ortho_error, 8),
        'max_off_diagonal_error': round(max_off_diag, 8),
        'is_orthogonal': (ortho_error < threshold) or (max_off_diag < threshold)
    }


# =====================================================================
# 6. CHINCHILLA COMPUTE-OPTIMAL SCALING LAWS
# =====================================================================

def chinchilla_optimal_tokens(params_b: float) -> Dict[str, Any]:
    """
    Calculates Chinchilla compute-optimal training token count (D = 20 * N).
    Given parameter count N, computes optimal tokens D and required compute C = 6ND = 120 N^2.
    """
    if params_b < 0:
        raise ValueError("params_b must be non-negative.")

    optimal_tokens_b = params_b * 20.0
    flops_info = calculate_training_flops(params_b, optimal_tokens_b)

    return {
        'params_billion': params_b,
        'compute_optimal_tokens_billion': optimal_tokens_b,
        'optimal_training_flops': flops_info['total_flops'],
        'optimal_training_flops_scientific': flops_info['total_flops_scientific'],
        'exaflops': flops_info['exaflops'],
        'petaflops_days': flops_info['petaflops_days'],
        'tokens_per_param_ratio': 20.0
    }


def chinchilla_optimal_model_from_compute(
    compute_flops: Optional[float] = None,
    exaflops: Optional[float] = None,
    petaflops_days: Optional[float] = None
) -> Dict[str, Any]:
    """
    Inverse Chinchilla solver: Given a target compute budget (FLOPs, ExaFLOPs, or PFLOPS-days),
    determines the compute-optimal parameter count N and token count D.

    Formulas:
    C = 6 * N * D = 6 * N * (20 * N) = 120 * N^2
    => N_optimal = sqrt(C / 120)
    => D_optimal = 20 * N_optimal
    """
    if compute_flops is not None:
        c = compute_flops
    elif exaflops is not None:
        c = exaflops * 1e18
    elif petaflops_days is not None:
        c = petaflops_days * (1e15 * 86400)
    else:
        raise ValueError("Provide either compute_flops, exaflops, or petaflops_days.")

    if c < 0:
        raise ValueError("Compute budget must be non-negative.")
    if c == 0:
        return {
            'compute_flops': 0.0,
            'optimal_params_billion': 0.0,
            'optimal_tokens_billion': 0.0,
            'exaflops': 0.0,
            'petaflops_days': 0.0
        }

    n_optimal = math.sqrt(c / 120.0)
    d_optimal = 20.0 * n_optimal

    params_b = n_optimal / 1e9
    tokens_b = d_optimal / 1e9

    return {
        'compute_flops': c,
        'compute_flops_scientific': f"{c:.3e}",
        'optimal_params_billion': round(params_b, 4),
        'optimal_params_millions': round(params_b * 1000, 2),
        'optimal_tokens_billion': round(tokens_b, 4),
        'optimal_tokens_trillion': round(tokens_b / 1000, 4),
        'exaflops': round(c / 1e18, 4),
        'petaflops_days': round(c / (1e15 * 86400), 2)
    }


def chinchilla_compute_tradeoff(
    params_b: float,
    tokens_b: float
) -> Dict[str, Any]:
    """
    Evaluates where a given training run sits relative to the Chinchilla compute-optimal frontier:
    - Under-trained (tokens < 20 * params)
    - Compute-optimal (tokens ≈ 20 * params)
    - Over-trained / Inference-optimal (tokens > 20 * params, e.g. LLaMA-3 style for ultra-efficient deployment).
    """
    if params_b <= 0 or tokens_b <= 0:
        raise ValueError("params_b and tokens_b must be positive.")

    ratio = tokens_b / params_b
    flops_info = calculate_training_flops(params_b, tokens_b)
    actual_flops = flops_info['total_flops']

    # For the same compute budget, what would be the optimal split?
    optimal_allocation = chinchilla_optimal_model_from_compute(compute_flops=actual_flops)

    if ratio < 18.0:
        regime = "Under-trained (Under-utilizing model capacity for given compute)"
    elif 18.0 <= ratio <= 22.0:
        regime = "Compute-Optimal (Strict Chinchilla Pareto Frontier)"
    else:
        regime = f"Inference-Optimal / Over-trained ({ratio:.1f}x tokens per param; lower serving latency)"

    return {
        'actual_params_billion': params_b,
        'actual_tokens_billion': tokens_b,
        'tokens_per_param_ratio': round(ratio, 2),
        'actual_compute_flops': actual_flops,
        'actual_compute_petaflops_days': flops_info['petaflops_days'],
        'regime': regime,
        'optimal_params_for_same_compute_b': optimal_allocation['optimal_params_billion'],
        'optimal_tokens_for_same_compute_b': optimal_allocation['optimal_tokens_billion']
    }

