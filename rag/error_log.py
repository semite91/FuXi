"""Writes every warning and error of the RAG engine to a file per day: rag/logs/error/yyyy_MM_dd.txt."""

import logging
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from settings import RAG_DIR

DEFAULT_ERROR_LOGS_DIR = RAG_DIR / "logs" / "error"
ERROR_LOG_FILE_NAME_FORMAT = "%Y_%m_%d"
ERROR_LOG_FILE_SUFFIX = ".txt"
ERROR_LOG_ENCODING = "utf-8"
ERROR_LOG_LINE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
ERROR_LOG_LEVEL = logging.WARNING  # the failures of one word or one source are warnings, so they are written too

Clock = Callable[[], datetime]


class DailyErrorFileHandler(logging.Handler):
    """Appends each record to the file of the day it was logged, so a process that runs past midnight starts a new file."""

    def __init__(self, logs_dir: Path = DEFAULT_ERROR_LOGS_DIR, clock: Clock = datetime.now) -> None:
        super().__init__(level=ERROR_LOG_LEVEL)
        self._logs_dir = logs_dir
        self._clock = clock
        self._write_lock = threading.Lock()
        self.setFormatter(logging.Formatter(ERROR_LOG_LINE_FORMAT))

    def path_for(self, moment: datetime) -> Path:
        return self._logs_dir / f"{moment.strftime(ERROR_LOG_FILE_NAME_FORMAT)}{ERROR_LOG_FILE_SUFFIX}"

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            path = self.path_for(self._clock())
            with self._write_lock:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding=ERROR_LOG_ENCODING) as log_file:
                    log_file.write(line + "\n")
        except Exception:  # a log that cannot be written must never break the request or the build
            self.handleError(record)


def install_error_log(
    logs_dir: Path = DEFAULT_ERROR_LOGS_DIR, clock: Clock = datetime.now, logger: logging.Logger | None = None
) -> DailyErrorFileHandler:
    """Adds the handler to the root logger (so every module and uvicorn reach it) once; a second call returns the first."""
    target = logger or logging.getLogger()
    for handler in target.handlers:
        if isinstance(handler, DailyErrorFileHandler):
            return handler
    handler = DailyErrorFileHandler(logs_dir, clock)
    target.addHandler(handler)
    return handler
