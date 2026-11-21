"""Compare retrieval quality of the text models on your own data, and suggest RAG_TEXT_THRESHOLD.

Needs the real models (Hugging Face access), a corpus and a list of queries with the documents that answer them.

  corpus.jsonl:   {"id": "note-1", "text": "..."}                one document per line
  queries.jsonl:  {"query": "...", "relevant": ["note-1"]}       ids of the documents that should be found

  python benchmarks/evaluate_retrieval.py --corpus benchmarks/eval_example/corpus.jsonl \\
         --queries benchmarks/eval_example/queries.jsonl

Reported per model: Recall@k (share of queries with a relevant document in the top k), MRR (mean of 1/rank of the
first relevant document) and the similarity threshold that gives the best F1 over the top-k results, which is the
value to try for RAG_TEXT_THRESHOLD. Similarity is the cosine of unit vectors, as in the engine (1 - cosine distance).
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TOP_K = 20  # the engine's top_k


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    query_prefix: str = ""
    document_prefix: str = ""
    query_prompt_name: str | None = None  # Qwen3 defines a "query" prompt in its sentence-transformers config


MODELS = {
    "qwen3-0.6B (before)": ModelSpec("Qwen/Qwen3-Embedding-0.6B", query_prompt_name="query"),
    "e5-small (now)": ModelSpec("intfloat/multilingual-e5-small", "query: ", "passage: "),
}


def rank_documents(query_vectors: np.ndarray, document_vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For every query the document indexes best first, and the similarities in that order."""
    similarities = query_vectors @ document_vectors.T
    order = np.argsort(-similarities, axis=1)
    return order, np.take_along_axis(similarities, order, axis=1)


def recall_and_mrr(order: np.ndarray, document_ids: list[str], relevant: list[set[str]], k: int) -> tuple[float, float]:
    hits, reciprocal_ranks = 0, 0.0
    for ranking, wanted in zip(order, relevant):
        ranked_ids = [document_ids[index] for index in ranking]
        if wanted & set(ranked_ids[:k]):
            hits += 1
        first = next((rank for rank, found in enumerate(ranked_ids, start=1) if found in wanted), None)
        reciprocal_ranks += 1 / first if first else 0.0
    return hits / len(relevant), reciprocal_ranks / len(relevant)


def best_threshold(
    order: np.ndarray, similarities: np.ndarray, document_ids: list[str], relevant: list[set[str]], k: int
) -> tuple[float, float]:
    """The similarity cut-off with the best F1 over the top-k results of all queries, and that F1."""
    candidates = np.unique(np.round(similarities[:, :k], 3))
    total_relevant = sum(len(wanted) for wanted in relevant)
    best = (0.0, 0.0)
    for threshold in candidates:
        returned = correct = 0
        for ranking, scores, wanted in zip(order, similarities, relevant):
            for index, score in zip(ranking[:k], scores[:k]):
                if score >= threshold:
                    returned += 1
                    correct += document_ids[index] in wanted
        if not returned or not correct:
            continue
        precision, recall = correct / returned, correct / total_relevant
        f1 = 2 * precision * recall / (precision + recall)
        if f1 > best[1]:
            best = (float(threshold), f1)
    return best


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def embed(spec: ModelSpec, corpus: list[dict], queries: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    from sentence_transformers import SentenceTransformer  # imported here: needs torch and the real weights

    model = SentenceTransformer(spec.model_id, device="cpu", model_kwargs={"dtype": "float32"})
    model.max_seq_length = 512
    options = {"normalize_embeddings": True, "batch_size": 8}
    documents = model.encode([spec.document_prefix + item["text"] for item in corpus], **options)
    query_options = {**options, **({"prompt_name": spec.query_prompt_name} if spec.query_prompt_name else {})}
    questions = model.encode([spec.query_prefix + item["query"] for item in queries], **query_options)
    return np.asarray(questions), np.asarray(documents)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--k", type=int, default=5, help="k for Recall@k (the engine returns up to 20)")
    args = parser.parse_args()
    corpus, queries = read_jsonl(args.corpus), read_jsonl(args.queries)
    document_ids = [item["id"] for item in corpus]
    relevant = [set(item["relevant"]) for item in queries]
    print(f"{len(corpus)} documents, {len(queries)} queries\n")
    print(f"{'model':22} {'dim':>5} {'Recall@' + str(args.k):>9} {'MRR':>6} {'best threshold':>15} {'F1':>6}")
    for name, spec in MODELS.items():
        query_vectors, document_vectors = embed(spec, corpus, queries)
        order, similarities = rank_documents(query_vectors, document_vectors)
        recall, mrr = recall_and_mrr(order, document_ids, relevant, args.k)
        threshold, f1 = best_threshold(order, similarities, document_ids, relevant, min(TOP_K, len(corpus)))
        print(f"{name:22} {document_vectors.shape[1]:5} {recall:9.2f} {mrr:6.2f} {threshold:15.3f} {f1:6.2f}")


if __name__ == "__main__":
    main()
