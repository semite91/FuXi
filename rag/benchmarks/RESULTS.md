# Embedding benchmark results

Run with `python benchmarks/benchmark_embedding.py --synthetic` (2026-11-21).

- Hardware: 4 vCPU Intel Xeon @ 2.3 GHz with `amx_bf16`, `amx_int8`, `avx512_bf16`, `avx512_vnni`; 16 GB RAM; no GPU.
- Models: the architectures of Qwen3-Embedding-0.6B (28 layers, hidden 1024) and multilingual-e5-small
  (BERT, 12 layers, hidden 384, 250k vocabulary) with **random weights**, because Hugging Face is not reachable from
  this environment. Speed and memory match the real models; **retrieval quality was not measured**.
- Workload: 48 documents of about 150 tokens, one warm-up call, each configuration in its own process.
- Peak memory is `VmHWM` of the process. (An earlier run used `ru_maxrss`, which carries the parent's peak
  across fork and showed wrong numbers; it was replaced.)

| Configuration | Load s | Embed s | Docs/s | Peak MB | Vector |
|---|---:|---:|---:|---:|---:|
| Qwen3-0.6B, bf16, batch 16, len 32768 (**before**) | 4.39 | 7.17 | 6.69 | 1809 | 1024 |
| Qwen3-0.6B, fp32, batch 8, len 512 | 5.27 | 23.05 | 2.08 | 4195 | 1024 |
| **e5-small, fp32, batch 8, len 512 (new default)** | 4.02 | 1.36 | **35.3** | **928** | 384 |
| e5-small, fp32, batch 16, len 512 | 4.65 | 1.17 | 40.9 | 968 | 384 |
| e5-small, bf16, batch 8, len 512 | 3.75 | 0.56 | 85.7 | 1455 | 384 |

## Versus the existing system (Qwen3, BF16, as it ran before this work)

- **Speed:** e5-small in FP32 is about **5.3x faster** (35.3 vs 6.7 docs/s); e5-small in BF16 is about **12.8x faster**.
- **Memory:** e5-small FP32 peaks at 928 MB, about half of the old 1809 MB (and a quarter of Qwen FP32's 4195 MB).
  BF16 e5 peaks higher than FP32 (1455 MB) because the FP32 checkpoint is converted while loading.
- **Vector size:** 384 instead of 1024, so the stored vectors are 2.7x smaller. They are not compatible with the old
  ones; the text collection is rebuilt once (the engine detects this by the embedder fingerprint).
- **Load time:** similar here, but this is loaded from a local, cached directory. The real Qwen checkpoint is about
  1.2 GB and e5-small about 470 MB, so a cold download and load is faster for e5.

## What this does not show

- **Retrieval quality.** A 118M-parameter model is generally weaker than a 600M one, especially for subtle or
  cross-language matches. There is no labelled query set in the repository and the real weights are unreachable
  here, so nothing here proves e5-small retrieves as well. Measure it on your own Notion notes, movies and songs.
- **`RAG_TEXT_THRESHOLD`.** 0.5 was chosen for Qwen scores. E5 cosine scores are higher and closer together, so
  0.5 will likely let almost everything through (top_k 20 then does the limiting). Tune it on real queries.
- **Other CPUs.** BF16 is fast here only because of AMX/AVX512-BF16. FP32 stays the default because it is safe
  everywhere; check `lscpu` flags and rerun the script before setting `RAG_EMBEDDING_PRECISION=bf16`.
- Batch 16 was 16 percent faster than batch 8 for e5-small on this workload. The default stays at 8 (the value
  requested); raise `RAG_BATCH_SIZE` if memory allows.

## ONNX Runtime INT8 and OpenVINO: not evaluated, not introduced

- Exporting and quantizing needs `optimum` and `openvino`, which are new dependencies, and an INT8 model cannot be
  accepted without a real-weight quality check. The e5-small repository ships `onnx` and `openvino` variants, so this is
  worth testing on a machine with Hugging Face access.
- e5-small in FP32 or BF16 on PyTorch is already 5 to 13 times faster than the previous setup, which leaves little to
  prove. The PyTorch path remains the only one and the fallback.
