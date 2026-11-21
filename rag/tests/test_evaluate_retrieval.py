import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from evaluate_retrieval import best_threshold, rank_documents, recall_and_mrr  # noqa: E402

IDS = ["a", "b", "c"]
DOCUMENTS = np.array([[1.0, 0.0], [0.0, 1.0], [0.6, 0.8]])


def test_ranking_and_metrics_on_known_vectors():
    queries = np.array([[1.0, 0.0], [0.0, 1.0]])
    order, similarities = rank_documents(queries, DOCUMENTS)

    assert order[0].tolist() == [0, 2, 1] and order[1].tolist() == [1, 2, 0]
    assert np.isclose(similarities[0, 1], 0.6)
    recall, mrr = recall_and_mrr(order, IDS, [{"a"}, {"c"}], k=1)
    assert (recall, mrr) == (0.5, (1 + 1 / 2) / 2)  # the second query finds c at rank 2, outside k=1


def test_best_threshold_separates_relevant_from_irrelevant():
    queries = np.array([[1.0, 0.0]])
    order, similarities = rank_documents(queries, DOCUMENTS)

    threshold, f1 = best_threshold(order, similarities, IDS, [{"a"}], k=3)

    assert threshold > 0.6 and f1 == 1.0  # only "a" (similarity 1.0) is kept; "c" at 0.6 and "b" at 0.0 are cut
