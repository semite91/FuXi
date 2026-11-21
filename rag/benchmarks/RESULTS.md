# Embedding benchmark results

Run with `python benchmarks/benchmark_embedding.py --synthetic` (2026-11-21).

- Hardware: 4 vCPU Intel Xeon @ 2.3 GHz with `amx_bf16`, `amx_int8`, `avx512_bf16`, `avx512_vnni`; 16 GB RAM; no GPU.
- Model: Qwen3-0.6B architecture (28 layers, hidden 1024, vector size 1024) with **random weights** saved in BF16,
  because Hugging Face is not reachable from this environment. Speed and memory equal the real model's;
  retrieval quality could not be measured.
- Workload: 48 documents of about 150 tokens, one warm-up call, each configuration in its own process.

| Configuration | Load s | Embed s | Docs/s | Peak RSS MB | Parameter dtype |
|---|---:|---:|---:|---:|---|
| before: bf16, batch 16, max length 32768 | 4.19 | 8.13 | **5.90** | 3308 | bfloat16 |
| fp32, batch 8, max length 512 | 5.91 | 19.65 | 2.44 | 4194 | float32 |
| fp32, batch 16, max length 512 | 4.76 | 20.32 | 2.36 | 4194 | float32 |
| fp32, batch 32, max length 512 | 4.54 | 20.94 | 2.29 | 4195 | float32 |

Vector size is 1024 in every configuration.

## What the numbers say

- **On this CPU, FP32 is 2.4x slower than BF16**, the opposite of the usual assumption. The CPU has AMX-BF16 and
  AVX512-BF16, so PyTorch runs BF16 matmuls on dedicated tiles. BF16 also uses about 900 MB less memory.
  FP32 is the faster and more compatible choice only on CPUs without those instructions (for example most
  AVX2-only desktops, and older Xeons), where BF16 is emulated. That was not measured here.
- **Batch size 8, 16 and 32 differ by under 7 percent** with documents of similar length. Sorting by length inside
  `encode` already removes most padding; batch size 8 is kept as the default because it bounds peak memory.
- The 512-token limit does not change speed for 150-token documents; it matters for long ones, which are now split
  into windows instead of being truncated or run at up to 32768 tokens.

## Recommendation

`RAG_EMBEDDING_PRECISION=fp32` stays the default, because it is safe on every CPU and was the requirement.
On a CPU whose `lscpu` flags list `amx_bf16` or `avx512_bf16`, set `RAG_EMBEDDING_PRECISION=bf16`:
re-run this benchmark on the target machine to confirm before changing it.
The vectors of the two precisions differ by rounding only (not measured here with real weights),
so a switch does not re-embed existing documents (see project.md).

## ONNX Runtime INT8 and OpenVINO: not evaluated, not introduced

- `onnxruntime` 1.31 is installed, but exporting and quantizing Qwen3 needs `optimum` (and `openvino` needs its own
  package). Both are new dependencies.
- Hugging Face is unreachable here, so an INT8 model could not be checked against real-weight retrieval quality,
  and INT8 without that check is not acceptable.
- The BF16 path above is already AMX-accelerated on this hardware, which leaves INT8 little headroom to prove.
- They stay out of the project. To evaluate them on the target machine: add a configuration to `CONFIGS` that loads
  with `SentenceTransformer(..., backend="onnx")`, compare docs/s, peak memory and the cosine of each vector
  against the PyTorch vector of the same text, and adopt only a clear, measured win.
The PyTorch path remains the only one and therefore the fallback.
