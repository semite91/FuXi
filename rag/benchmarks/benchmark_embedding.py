"""Compare text embedding models: load time, embedding time, throughput and peak memory.

Each configuration runs in its own process so the memory numbers do not mix. Compared: the previous
Qwen3-Embedding-0.6B (as the engine ran it: BF16, batch 16, 32768 tokens) and multilingual-e5-small.

  python benchmarks/benchmark_embedding.py                    # real weights from the Hugging Face cache / Hub
  python benchmarks/benchmark_embedding.py --synthetic        # same architectures with random weights, offline

Random weights give the same compute cost as the real ones (speed does not depend on the weights) but no
retrieval quality. Retrieval quality needs the real models and a labelled set of your own queries.
"""

import argparse
import json
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REAL_MODELS = {"qwen": "Qwen/Qwen3-Embedding-0.6B", "e5": "intfloat/multilingual-e5-small"}
WORDS = "the quick brown fox jumps over the lazy dog notes about movies songs pictures and places".split()
# name -> (model, precision, batch size, max sequence length). The Qwen row is what the engine did before:
# the checkpoint's own BF16, batch size 16 and the model's 32768-token limit.
CONFIGS = {
    "qwen3-0.6B bf16 b16 len32768 (before)": ("qwen", "bf16", 16, 32768),
    "qwen3-0.6B fp32 b8 len512": ("qwen", "fp32", 8, 512),
    "e5-small fp32 b8 len512": ("e5", "fp32", 8, 512),
    "e5-small fp32 b16 len512": ("e5", "fp32", 16, 512),
    "e5-small bf16 b8 len512": ("e5", "bf16", 8, 512),
}


def make_synthetic_model(path: Path, kind: str) -> None:
    """The architecture of a model with random weights: Qwen3-0.6B (28 layers, hidden 1024, saved in BF16 like its
    checkpoint) or multilingual-e5-small (BERT, 12 layers, hidden 384, FP32 like its checkpoint)."""
    import torch
    import transformers
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers

    tokenizer = Tokenizer(models.BPE(unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer.train_from_iterator([" ".join(WORDS) * 4], trainers.BpeTrainer(vocab_size=200, special_tokens=["[UNK]", "[PAD]"]))
    fast = transformers.PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="[UNK]", pad_token="[PAD]")
    fast.save_pretrained(path)
    torch.manual_seed(0)
    if kind == "qwen":
        config = transformers.Qwen3Config(
            vocab_size=151936, hidden_size=1024, intermediate_size=3072, num_hidden_layers=28,
            num_attention_heads=16, num_key_value_heads=8, head_dim=128, max_position_embeddings=40960,
        )
        transformers.Qwen3Model(config).to(torch.bfloat16).save_pretrained(path)
    else:
        config = transformers.BertConfig(
            vocab_size=250037, hidden_size=384, intermediate_size=1536, num_hidden_layers=12,
            num_attention_heads=12, max_position_embeddings=512, type_vocab_size=2,
        )
        transformers.BertModel(config).save_pretrained(path)


def make_texts(count: int, words: int) -> list[str]:
    return [" ".join(WORDS[(index + step) % len(WORDS)] for step in range(words + index % 7)) for index in range(count)]


def run_one(args: argparse.Namespace) -> None:
    import torch

    from embedders import load_sentence_transformer, parameter_dtypes

    started = time.perf_counter()
    model = load_sentence_transformer(args.model, "cpu", args.precision, args.max_seq_length)
    load_seconds = time.perf_counter() - started
    texts = make_texts(args.documents, args.words)
    model.encode(texts[:2], batch_size=args.batch_size)  # warm-up: allocator, threads, kernels
    started = time.perf_counter()
    vectors = model.encode(texts, batch_size=args.batch_size)
    embed_seconds = time.perf_counter() - started
    print(json.dumps({
        "load_s": round(load_seconds, 2),
        "embed_s": round(embed_seconds, 2),
        "docs_per_s": round(len(texts) / embed_seconds, 2),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
        "dtype": sorted(str(dtype) for dtype in parameter_dtypes(model)),
        "dimension": int(vectors.shape[1]),
        "threads": torch.get_num_threads(),
        "sample": [round(float(value), 5) for value in vectors[0][:8]],
    }))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--model", default="", help="model directory or id (child processes only)")
    parser.add_argument("--documents", type=int, default=48)
    parser.add_argument("--words", type=int, default=150, help="words per document (about one token each)")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--precision", default="fp32")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-seq-length", type=int, default=512)
    args = parser.parse_args()
    if args.child:
        run_one(args)
        return
    with tempfile.TemporaryDirectory() as scratch:
        models = {}
        for kind, real_id in REAL_MODELS.items():
            models[kind] = real_id
            if args.synthetic:
                models[kind] = str(Path(scratch) / f"{kind}_random")
                make_synthetic_model(Path(models[kind]), kind)
        print(f"{'synthetic (random weights)' if args.synthetic else 'real weights'}: "
              f"documents={args.documents} words/doc~{args.words}")
        print(f"{'configuration':38} {'load s':>7} {'embed s':>8} {'docs/s':>7} {'peak MB':>8}  dtype")
        for name, (kind, precision, batch_size, max_length) in CONFIGS.items():
            command = [
                sys.executable, __file__, "--child", "--model", models[kind], "--precision", precision,
                "--batch-size", str(batch_size), "--max-seq-length", str(max_length),
                "--documents", str(args.documents), "--words", str(args.words),
            ]
            output = subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
            result = json.loads(output)
            print(f"{name:38} {result['load_s']:7} {result['embed_s']:8} {result['docs_per_s']:7} "
                  f"{result['peak_rss_mb']:8}  {','.join(result['dtype'])} dim={result['dimension']}")


if __name__ == "__main__":
    main()
