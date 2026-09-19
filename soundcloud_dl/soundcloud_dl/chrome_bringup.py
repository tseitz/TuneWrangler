"""Ensure a real Chrome instance is running with --remote-debugging-port for CDP attach."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("soundcloud_dl.chrome_bringup")

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.25
HTTP_OK = 200


class ChromeBringupError(RuntimeError):
    """Raised when Chrome cannot be brought up on the requested debug port."""


def is_debug_port_open(port: int, *, timeout_seconds: float = 1.0) -> bool:
    """Probe the CDP debug port. True if Chrome is listening and answering.

    Every transport-level failure means the same thing to a probe: not usable. A Chrome
    that has just been killed still accepts the connection and then resets it, which
    surfaces as ReadError rather than ConnectError.
    """
    try:
        with httpx.Client(trust_env=False) as client:
            resp = client.get(f"http://localhost:{port}/json/version", timeout=timeout_seconds)
    except httpx.TransportError:
        return False
    return resp.status_code == HTTP_OK


def kill_chrome_on_port(port: int, *, wait_seconds: float = 5.0) -> None:
    """Kill any process listening on the CDP debug port and wait for it to stop answering.

    Returning while the socket is still half-alive makes the next probe read the dying
    Chrome as a session worth reusing.
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["lsof", "-ti", f":{port}"],  # noqa: S607
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
        pids = [int(p) for p in result.stdout.split() if p.strip().isdigit()]
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
                logger.info("Killed stale Chrome process (pid=%d) on port %d.", pid, port)
            except ProcessLookupError:
                pass
    except (subprocess.TimeoutExpired, OSError, ValueError):
        logger.debug("Could not enumerate processes on port %d", port, exc_info=True)

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if not is_debug_port_open(port):
            return
        time.sleep(DEFAULT_POLL_INTERVAL_SECONDS)
    logger.warning("Port %d still answering %.0fs after kill.", port, wait_seconds)


def ensure_chrome_running(
    *,
    chrome_path: str,
    profile_dir: Path,
    port: int,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> None:
    """
    Attach to an existing Chrome debug session if one is already running on `port`,
    otherwise kill any stale process and launch a fresh instance.

    Raises ChromeBringupError if the port doesn't open within `timeout_seconds`.
    """
    if is_debug_port_open(port):
        logger.info("Chrome already running on port %d — reusing existing session.", port)
        return

    kill_chrome_on_port(port)

    profile_dir.mkdir(parents=True, exist_ok=True)
    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--enable-automation",
        "--disable-blink-features=AutomationControlled",
        "--disable-session-crashed-bubble",
        "--disable-infobars",
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
