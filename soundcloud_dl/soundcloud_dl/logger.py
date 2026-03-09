"""Logging setup: console and file under project logs/."""

import logging
import sys

from soundcloud_dl.config import get_log_dir


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
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    logging.getLogger("soundcloud_dl").setLevel(level)
