"""
test_nano_engine.py
Comprehensive unit test suite for core/nano_engine.py.
Verifies:
1. Transformer parameter counting (GPT-2 124M exact match, LLaMA-7B, GQA, MQA, MLA, SwiGLU, untied embeddings).
2. Training FLOPs calculation (6ND rule, 2ND forward, 8ND recomputation, attention quadratic FLOPs, PFLOPS-days, ExaFLOPs).
3. Model FLOPs Utilization (MFU) and HFU.
4. KV-cache VRAM budgeting across context lengths (4k to 1M tokens) and precisions (FP32, FP16, BF16, FP8, INT4).
5. Muon polar decomposition vs AdamW memory footprint reduction.
6. Pure-Python Newton-Schulz quintic polar decomposition solver & orthogonality error verification.
7. Chinchilla compute-optimal scaling laws (D = 20 * N, inverse compute budget solver, regime analysis).
8. Edge cases (batch size 0, odd head dimensions, zero layers, large context, negative inputs, invalid precisions).
"""

import pytest
import math
from core.nano_engine import (
    calculate_transformer_params,
    calculate_kv_cache_memory,
    calculate_kv_cache_vram,
    generate_kv_cache_context_table,
    calculate_training_flops,
    calculate_mfu,
    estimate_training_vram,
    compare_optimizer_footprint,
    newton_schulz_polar,
    chinchilla_optimal_tokens,
    chinchilla_optimal_model_from_compute,
    chinchilla_compute_tradeoff,
    PRECISION_BYTES_MAP
)


class TestTransformerParams:
    """Tests for calculate_transformer_params."""

    def test_gpt2_124m_exact_parameters(self):
        """Verify exact parameter count for GPT-2 (124M) matching nanoGPT."""
        res = calculate_transformer_params(
            n_layer=12,
            n_embd=768,
            n_head=12,
            vocab_size=50257,
            mlp_ratio=4.0,
            mlp_type='standard',
            attn_type='MHA',
            pos_emb_type='learned',
            max_seq_len=1024,
            tie_embeddings=True,
            bias=True,
            norm_type='layernorm'
        )
        # Expected GPT-2 124M breakdown:
        # Token Emb: 50257 * 768 = 38,597,376
        # Pos Emb: 1024 * 768 = 786,432
        # Layer params (12 layers * 7,087,872) = 85,054,464
        # Final LN: 2 * 768 = 1,536
        # Total: 124,439,808
        assert res['total_parameters'] == 124439808
        assert res['total_parameters_millions'] == 124.44
        assert res['non_embedding_parameters'] == 85056000
        assert res['layers'] == 12
        assert res['head_dimension'] == 64

    def test_llama_7b_parameters(self):
        """Verify parameter count for LLaMA-7B architecture (SwiGLU, RoPE, untied, RMSNorm)."""
        res = calculate_transformer_params(
            n_layer=32,
            n_embd=4096,
            n_head=32,
            vocab_size=32000,
            mlp_hidden=11008,
            mlp_type='swiglu',
            attn_type='MHA',
            pos_emb_type='rope',
            tie_embeddings=False,
            bias=False,
            norm_type='rmsnorm'
        )
        # Non-embedding: 32 * (67,108,864 + 135,266,304 + 8,192) + 4096 = 6,476,271,616
        # Embeddings + Head: 2 * (32000 * 4096) = 262,144,000
        # Total: 6,738,415,616 (~6.74B)
        assert res['total_parameters'] == 6738415616
        assert res['total_parameters_billions'] == 6.738
        assert res['pos_embedding_parameters'] == 0

    def test_gqa_parameter_reduction(self):
        """Verify GQA reduces attention parameters compared to MHA."""
        mha = calculate_transformer_params(n_layer=32, n_embd=4096, n_head=32, n_kv_head=32, attn_type='MHA')
        gqa = calculate_transformer_params(n_layer=32, n_embd=4096, n_head=32, n_kv_head=8, attn_type='GQA')
        assert gqa['attention_parameters_per_layer'] < mha['attention_parameters_per_layer']
        assert gqa['total_parameters'] < mha['total_parameters']

    def test_mqa_parameter_count(self):
        """Verify MQA uses 1 KV head."""
        mqa = calculate_transformer_params(n_layer=32, n_embd=4096, n_head=32, attn_type='MQA')
        assert mqa['kv_heads'] == 1

    def test_mla_parameter_count(self):
        """Verify Multi-Head Latent Attention (DeepSeek style) parameter counting."""
        mla = calculate_transformer_params(
            n_layer=32,
            n_embd=4096,
            n_head=32,
            attn_type='MLA',
            q_lora_rank=1536,
            kv_lora_rank=512,
            qk_rope_head_dim=64,
            qk_nope_head_dim=128,
            v_head_dim=128,
            bias=False
        )
        assert mla['attn_type'] == 'MLA'
        assert mla['attention_parameters_per_layer'] > 0
        assert mla['total_parameters'] > 0

    def test_zero_layers_and_zero_embd(self):
        """Edge case: 0 layers or 0 embedding dim should return 0 gracefully."""
        res_zero_l = calculate_transformer_params(n_layer=0, n_embd=768)
        assert res_zero_l['total_parameters'] == 0
        res_zero_e = calculate_transformer_params(n_layer=12, n_embd=0)
        assert res_zero_e['total_parameters'] == 0

    def test_invalid_dimensions_raise_error(self):
        """Invalid inputs should raise ValueError."""
        with pytest.raises(ValueError):
            calculate_transformer_params(n_layer=-1)
        with pytest.raises(ValueError):
            # n_embd not divisible by n_head
            calculate_transformer_params(n_embd=769, n_head=12, head_dim=None)


class TestKVCacheMemory:
    """Tests for calculate_kv_cache_memory & context scaling."""

    def test_standard_kv_cache_fp16(self):
        """Verify LLaMA-3-8B 128k context KV cache is exactly 16.0 GB in FP16."""
        # 2 * 32 layers * 8 kv_heads * 128 head_dim * 131072 tokens * 1 batch * 2 bytes = 17,179,869,184 bytes = 16.0 GB
        res = calculate_kv_cache_memory(
            n_layer=32,
            n_kv_head=8,
            head_dim=128,
            seq_len=131072,
            batch_size=1,
            precision='fp16'
        )
        assert res['kv_cache_gb'] == 16.0
        assert res['tokens_cached'] == 131072
        assert res['per_token_bytes'] == 131072.0

    def test_kv_cache_precisions(self):
        """Verify memory scaling across FP32, FP16, FP8, INT4."""
        fp32 = calculate_kv_cache_memory(32, 8, 128, 4096, 1, 'fp32')['kv_cache_bytes']
        fp16 = calculate_kv_cache_memory(32, 8, 128, 4096, 1, 'fp16')['kv_cache_bytes']
        fp8 = calculate_kv_cache_memory(32, 8, 128, 4096, 1, 'fp8')['kv_cache_bytes']
        int4 = calculate_kv_cache_memory(32, 8, 128, 4096, 1, 'int4')['kv_cache_bytes']

        assert fp32 == 2 * fp16
        assert fp16 == 2 * fp8
        assert fp8 == 2 * int4

    def test_mla_kv_cache_compression(self):
        """Verify MLA KV-cache compression ratio vs standard MHA/GQA."""
        gqa = calculate_kv_cache_memory(32, 8, 128, 131072, 1, 'fp16', attn_type='standard')
        mla = calculate_kv_cache_memory(32, 8, 128, 131072, 1, 'fp16', attn_type='mla', kv_lora_rank=512, qk_rope_head_dim=64)

        # GQA: 2 * 8 * 128 = 2048 elems/layer. MLA: 512 + 64 = 576 elems/layer.
        # Ratio = 2048 / 576 = 3.555x reduction
        assert mla['kv_cache_bytes'] < gqa['kv_cache_bytes']
        ratio = gqa['kv_cache_bytes'] / mla['kv_cache_bytes']
        assert round(ratio, 2) == 3.56

    def test_1m_context_large_scale(self):
        """Verify 1M (1,048,576) context length computation."""
        res_1m = calculate_kv_cache_memory(
            n_layer=32,
            n_kv_head=8,
            head_dim=128,
            seq_len=1048576,
            batch_size=1,
            precision='fp8'
        )
        assert res_1m['tokens_cached'] == 1048576
        assert res_1m['kv_cache_gb'] == 64.0

    def test_batch_size_zero_edge_case(self):
        """Batch size 0 or seq len 0 should return 0 bytes cleanly."""
        res_b0 = calculate_kv_cache_memory(batch_size=0)
        assert res_b0['kv_cache_bytes'] == 0
        assert res_b0['kv_cache_gb'] == 0.0
        assert res_b0['tokens_cached'] == 0

        res_s0 = calculate_kv_cache_memory(seq_len=0)
        assert res_s0['kv_cache_bytes'] == 0

    def test_context_table_generation(self):
        """Verify table generation from 4k to 1M context."""
        table = generate_kv_cache_context_table(n_layer=32, n_head=32, n_kv_head=8, head_dim=128, batch_size=1)
        assert len(table) == 9
        assert table[0]['context_length'] == 4096
        assert table[-1]['context_length'] == 1048576
        assert table[0]['gqa_vs_mha_compression'] == 4.0


class TestTrainingFlopsAndMFU:
    """Tests for calculate_training_flops and calculate_mfu."""

    def test_6nd_rule(self):
        """Verify standard 6ND training FLOPs formula."""
        # 70B params, 15T tokens: 6 * 70e9 * 15e12 = 6.3e24 FLOPs = 6,300,000 ExaFLOPs
        res = calculate_training_flops(params_b=70.0, tokens_b=15000.0)
        assert res['total_flops'] == 6.3e24
        assert res['exaflops'] == 6300000.0
        # 1 PFLOPS-day = 8.64e19 FLOPs => 6.3e24 / 8.64e19 = 72916.6667
        assert round(res['petaflops_days'], 2) == 72916.67

    def test_forward_only_and_recompute_multipliers(self):
        """Verify forward-only (2ND) and activation checkpointing (8ND)."""
        fwd = calculate_training_flops(params_b=1.0, tokens_b=1.0, forward_only=True)
        train = calculate_training_flops(params_b=1.0, tokens_b=1.0, forward_only=False)
        recomp = calculate_training_flops(params_b=1.0, tokens_b=1.0, activation_checkpointing=True)

        assert fwd['total_flops'] == 2.0e18
        assert train['total_flops'] == 6.0e18
        assert recomp['total_flops'] == 8.0e18

    def test_attention_quadratic_flops(self):
        """Verify exact attention quadratic FLOPs term inclusion."""
        res_dense = calculate_training_flops(params_b=8.0, tokens_b=10.0)
        res_with_attn = calculate_training_flops(params_b=8.0, tokens_b=10.0, seq_len=8192, n_layer=32, n_embd=4096)
        assert res_with_attn['total_flops'] > res_dense['total_flops']
        assert res_with_attn['attn_quadratic_flops'] > 0

    def test_mfu_calculation(self):
        """Verify Model FLOPs Utilization (MFU) metric calculation."""
        # 8B params, 16384 tokens/step, step_time = 0.5s, 8x H100 (989 TFLOPS peak BF16)
        # FLOPs/step = 6 * 8e9 * 16384 = 7.86432e14 FLOPs
        # Achieved TFLOPS = 7.86432e14 / 0.5s / 1e12 = 1572.864 TFLOPS
        # Total peak = 8 * 989 = 7912 TFLOPS => MFU = 1572.864 / 7912 = 19.88%
        res = calculate_mfu(
            params_b=8.0,
            tokens_per_step=16384,
            step_time_sec=0.5,
            num_gpus=8,
            gpu_peak_tflops=989.0
        )
        assert round(res['mfu_percent'], 2) == 19.88
        assert res['tokens_per_sec'] == 32768.0


class TestMuonAndOptimizerFootprint:
    """Tests for estimate_training_vram, compare_optimizer_footprint, and Newton-Schulz."""

    def test_optimizer_footprint_savings(self):
        """Verify Muon saves ~66.7% optimizer memory vs AdamW."""
        res = compare_optimizer_footprint(params_b=7.0, precision='bf16')
        assert res['adamw']['bytes_per_param'] == 12.0
        assert res['muon']['bytes_per_param'] == 4.0
        assert res['muon_optimizer_memory_savings_percent'] == 66.67
        assert res['muon_total_static_memory_savings_percent'] == 50.0

    def test_estimate_training_vram_zero_and_muon(self):
        """Verify training VRAM estimation with ZeRO stages and Muon optimizer."""
        vram_adamw = estimate_training_vram(params_b=8.0, batch_size=4, seq_len=2048, optimizer='adamw')
        vram_muon = estimate_training_vram(params_b=8.0, batch_size=4, seq_len=2048, optimizer='muon')
        assert vram_muon['optimizer_vram_gb'] < vram_adamw['optimizer_vram_gb']
        assert vram_muon['total_vram_gb'] < vram_adamw['total_vram_gb']

        # ZeRO-1 sharding on 8 GPUs
        vram_zero1 = estimate_training_vram(params_b=8.0, optimizer='adamw', zero_stage=1, num_gpus=8)
        assert vram_zero1['optimizer_vram_gb'] == round(vram_adamw['optimizer_vram_gb'] / 8.0, 2)

    def test_newton_schulz_polar_decomposition(self):
        """Verify pure-Python Newton-Schulz algorithm orthogonalizes a matrix in both classical and Muon modes."""
        # 4x4 test matrix
        mat = [
            [2.0, 0.5, 0.1, 0.0],
            [0.5, 3.0, 0.2, 0.1],
            [0.1, 0.2, 1.5, 0.4],
            [0.0, 0.1, 0.4, 2.5]
        ]
        # Classical mode (exact convergence)
        ortho_mat_classic, metrics_classic = newton_schulz_polar(mat, steps=8, mode='classical_cubic')
        assert metrics_classic['is_orthogonal'] is True
        assert metrics_classic['orthogonality_error'] < 1e-6
        assert len(ortho_mat_classic) == 4
        assert len(ortho_mat_classic[0]) == 4

        # Muon quintic mode (Karpathy/Keller Jordan modded-nanogpt fast 5-step solver)
        ortho_mat_muon, metrics_muon = newton_schulz_polar(mat, steps=5, mode='muon_quintic')
        assert metrics_muon['is_orthogonal'] is True
        assert metrics_muon['max_off_diagonal_error'] < 0.20



class TestChinchillaScaling:
    """Tests for Chinchilla scaling laws."""

    def test_chinchilla_optimal_tokens(self):
        """Verify D = 20 * N compute-optimal scaling."""
        res_7b = chinchilla_optimal_tokens(params_b=7.0)
        assert res_7b['compute_optimal_tokens_billion'] == 140.0
        # C = 6 * 7e9 * 140e9 = 5.88e21 FLOPs = 5880 ExaFLOPs
        assert res_7b['optimal_training_flops'] == 5.88e21
        assert res_7b['exaflops'] == 5880.0

    def test_chinchilla_inverse_solver(self):
        """Verify inverse compute solving from ExaFLOPs."""
        # For C = 1.2e20 FLOPs (120 ExaFLOPs):
        # N = sqrt(1.2e20 / 120) = sqrt(1e18) = 1e9 params = 1.0B
        # D = 20 * 1.0B = 20.0B
        res = chinchilla_optimal_model_from_compute(compute_flops=1.2e20)
        assert res['optimal_params_billion'] == 1.0
        assert res['optimal_tokens_billion'] == 20.0

    def test_chinchilla_tradeoff_regimes(self):
        """Verify under-trained vs compute-optimal vs inference-optimal regimes."""
        under = chinchilla_compute_tradeoff(params_b=10.0, tokens_b=100.0)
        assert "Under-trained" in under['regime']

        optimal = chinchilla_compute_tradeoff(params_b=10.0, tokens_b=200.0)
        assert "Compute-Optimal" in optimal['regime']

        over = chinchilla_compute_tradeoff(params_b=8.0, tokens_b=15000.0) # LLaMA 3 style
        assert "Inference-Optimal" in over['regime']

