"""Bounded parallel work shared by the resources that read many items."""

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

Item = TypeVar("Item")
Result = TypeVar("Result")


def in_parallel(work: Callable[[Item], Result], items: Iterable[Item], workers: int) -> list[Result]:
    """Results in the items' order; on an error the waiting work is cancelled and the error is raised."""
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        return list(pool.map(work, items))
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
