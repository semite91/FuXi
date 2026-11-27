import logging
from datetime import datetime

from error_log import DailyErrorFileHandler, install_error_log


def make_logger(tmp_path, clock):
    logger = logging.getLogger(f"error_log_test_{tmp_path.name}")
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    install_error_log(tmp_path / "logs" / "error", clock, logger)
    return logger


def test_a_warning_and_an_error_are_written_to_the_file_of_the_day(tmp_path):
    logger = make_logger(tmp_path, lambda: datetime(2026, 11, 27, 9, 30))

    logger.warning("Search query for humanity failed: RuntimeError")
    logger.error("Resource notion failed: NotionTokenRejected")

    lines = (tmp_path / "logs" / "error" / "2026_11_27.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "WARNING" in lines[0] and "Search query for humanity failed" in lines[0]
    assert "ERROR" in lines[1] and "Resource notion failed" in lines[1]


def test_info_is_not_written(tmp_path):
    logger = make_logger(tmp_path, datetime.now)

    logger.info("Loaded model")

    assert not (tmp_path / "logs").exists()


def test_a_new_day_starts_a_new_file(tmp_path):
    now = [datetime(2026, 11, 27, 23, 59)]
    logger = make_logger(tmp_path, lambda: now[0])

    logger.error("late")
    now[0] = datetime(2026, 11, 28, 0, 1)
    logger.error("early")

    names = sorted(path.name for path in (tmp_path / "logs" / "error").iterdir())
    assert names == ["2026_11_27.txt", "2026_11_28.txt"]


def test_installing_twice_adds_one_handler(tmp_path):
    logger = make_logger(tmp_path, datetime.now)

    install_error_log(tmp_path / "logs" / "error", datetime.now, logger)

    assert sum(isinstance(h, DailyErrorFileHandler) for h in logger.handlers) == 1


def test_a_log_that_cannot_be_written_does_not_raise(tmp_path):
    blocked = tmp_path / "logs"
    blocked.write_text("a file where the folder should be", encoding="utf-8")
    logger = make_logger(tmp_path, datetime.now)

    logger.error("still fine")  # the handler reports to stderr instead of raising
