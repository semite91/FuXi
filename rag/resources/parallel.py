"""Bounded parallel work shared by the resources that read many items."""

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

Item = TypeVar("Item")
Result = TypeVar("Result")


def iter_parallel(work: Callable[[Item], Result], items: Iterable[Item], workers: int) -> Iterator[Result]:
    """Results in the items' order, each as soon as it and the ones before it are done; on an error, or when the
    caller stops reading, the waiting work is cancelled."""
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        yield from pool.map(work, items)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def in_parallel(work: Callable[[Item], Result], items: Iterable[Item], workers: int) -> list[Result]:
    """Results in the items' order; on an error the waiting work is cancelled and the error is raised."""
    return list(iter_parallel(work, items, workers))
