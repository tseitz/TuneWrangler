"""Logging setup: console and file under project logs/."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from soundcloud_dl.config import get_log_dir

# A plain FileHandler appends forever. This log reached 84 MB, which made it
# useless to read back after a run. Cap it and keep a few older files.
MAX_LOG_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 3


def setup_logging(
    *,
    log_file_name: str = "soundcloud_dl.log",
    level: int = logging.INFO,
) -> None:
    """Configure root logger with console and file handlers."""
    log_dir = get_log_dir()
    log_path = log_dir / log_file_name

    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=date_fmt)

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers when called multiple times
    if not root.handlers:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        root.addHandler(console)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=MAX_LOG_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    logging.getLogger("soundcloud_dl").setLevel(level)
