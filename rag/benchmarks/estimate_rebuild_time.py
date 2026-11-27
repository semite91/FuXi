"""Estimate the time of a full text rebuild, old model against new, from measured throughput.

Measures documents/second for short, medium and long documents (each in its own process, random weights of the
real architectures), then multiplies by your document counts. Pass your own counts; the defaults are placeholders.

  python benchmarks/estimate_rebuild_time.py --songs 2000 --movies 800 --notes 600
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark_embedding import make_synthetic_model  # noqa: E402

BENCHMARK = Path(__file__).resolve().parent / "benchmark_embedding.py"
# kind of document -> tokens per document (a song title line, a movie row, a Notion chunk of up to 2000 characters)
LENGTHS = {"songs": 25, "movies": 90, "notes": 450}
SETUPS = {
    "before (Qwen3 bf16, batch 16)": ("qwen", "bf16", 16, 32768),
    "now (e5-small fp32, batch 8)": ("e5", "fp32", 8, 512),
    "e5-small bf16, batch 8 (on AMX CPUs)": ("e5", "bf16", 8, 512),
}


def throughput(model: str, precision: str, batch: int, max_len: int, words: int, documents: int) -> float:
    command = [
        sys.executable, str(BENCHMARK), "--child", "--model", model, "--precision", precision,
        "--batch-size", str(batch), "--max-seq-length", str(max_len), "--documents", str(documents), "--words", str(words),
    ]
    output = subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
    return float(json.loads(output)["docs_per_s"])


def format_time(seconds: float) -> str:
    return f"{seconds:.0f} s" if seconds < 90 else f"{seconds / 60:.1f} min"


def main() -> None:
    parser = argparse.ArgumentParser()
    for kind, default in {"songs": 2000, "movies": 800, "notes": 600}.items():
        parser.add_argument(f"--{kind}", type=int, default=default, help=f"number of {kind} (documents or chunks)")
    parser.add_argument("--changed", type=float, default=0.02, help="share of documents changed since the last build")
    args = parser.parse_args()
    counts = {kind: getattr(args, kind) for kind in LENGTHS}
    with tempfile.TemporaryDirectory() as scratch:
        models = {}
        for kind in ("qwen", "e5"):
            models[kind] = str(Path(scratch) / kind)
            make_synthetic_model(Path(models[kind]), kind)
        print(f"documents: {counts} (about {LENGTHS} tokens each); {args.changed:.0%} changed for the update case\n")
        print(f"{'setup':40} {'full rebuild':>14} {'update (reuse)':>16}   docs/s songs / movies / notes")
        for name, (kind, precision, batch, max_len) in SETUPS.items():
            rates = {
                length_kind: throughput(models[kind], precision, batch, max_len, tokens, min(48, max(16, counts[length_kind])))
                for length_kind, tokens in LENGTHS.items()
            }
            full = sum(counts[length_kind] / rates[length_kind] for length_kind in LENGTHS)
            print(f"{name:40} {format_time(full):>14} {format_time(full * args.changed):>16}   "
                  + " / ".join(f"{rates[length_kind]:.1f}" for length_kind in LENGTHS))


if __name__ == "__main__":
    main()
