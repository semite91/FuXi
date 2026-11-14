import threading

import pytest

from resources.parallel import in_parallel

WORKERS = 4
WAIT_SECONDS = 5.0


def test_results_keep_the_items_order_when_a_later_item_finishes_first():
    # Phase 5c J-DRY
    last_is_done = threading.Event()

    def work(number: int) -> int:
        if number == 0:
            assert last_is_done.wait(WAIT_SECONDS)
        if number == WORKERS - 1:
            last_is_done.set()
        return number * 10

    assert in_parallel(work, range(WORKERS), WORKERS) == [0, 10, 20, 30]


def test_at_most_the_given_workers_run_at_the_same_time():
    # Phase 5c J-DRY
    lock = threading.Lock()
    all_workers_run = threading.Barrier(WORKERS, timeout=WAIT_SECONDS)
    running = {"now": 0, "most": 0}

    def work(number: int) -> int:
        with lock:
            running["now"] += 1
            running["most"] = max(running["most"], running["now"])
        if number < WORKERS:
            all_workers_run.wait()
        with lock:
            running["now"] -= 1
        return number

    assert in_parallel(work, range(WORKERS * 3), WORKERS) == list(range(WORKERS * 3))
    assert running["most"] == WORKERS


def test_an_error_is_raised_and_the_waiting_work_is_cancelled():
    # Phase 5c J-DRY
    started: list[int] = []

    def work(number: int) -> int:
        started.append(number)
        raise ValueError(f"item {number}")

    with pytest.raises(ValueError, match="item 0"):
        in_parallel(work, range(100), workers=1)

    assert len(started) < 100


def test_no_items_give_no_results():
    # Phase 5c J-DRY
    assert in_parallel(lambda item: item, [], WORKERS) == []
