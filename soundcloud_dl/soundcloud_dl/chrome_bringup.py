"""Ensure a real Chrome instance is running with --remote-debugging-port for CDP attach."""

from __future__ import annotations

import logging
import subprocess
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("soundcloud_dl.chrome_bringup")

#: Default time to wait for Chrome to expose its debug port after launch.
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.25
HTTP_OK = 200


class ChromeBringupError(RuntimeError):
    """Raised when Chrome cannot be brought up on the requested debug port."""


def is_debug_port_open(port: int, *, timeout_seconds: float = 1.0) -> bool:
    """Probe the CDP debug port. True if Chrome is listening."""
    try:
        resp = httpx.get(f"http://localhost:{port}/json/version", timeout=timeout_seconds)
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout):
        return False
    return resp.status_code == HTTP_OK


def ensure_chrome_running(
    *,
    chrome_path: str,
    profile_dir: Path,
    port: int,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> None:
    """
    Ensure a Chrome process is running with the given debug port.

    If a process is already listening on `port`, this is a no-op (we attach to it).
    Otherwise launch Chrome with the dedicated profile and wait for the port to open.

    Raises ChromeBringupError if the port doesn't open within `timeout_seconds`.
    """
    if is_debug_port_open(port):
        logger.info("Chrome already running on debug port %d; will attach.", port)
        return

    profile_dir.mkdir(parents=True, exist_ok=True)
    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    logger.info("Launching Chrome: %s", " ".join(args))
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if is_debug_port_open(port):
            logger.info("Chrome debug port %d is up.", port)
            return
        time.sleep(poll_interval_seconds)

    msg = f"Chrome debug port {port} did not respond within {timeout_seconds}s"
    raise ChromeBringupError(msg)
