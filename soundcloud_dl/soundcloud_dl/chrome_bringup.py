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

# "<mode>:<pid>" for the Chrome on the debug port. --headless=new reports an ordinary
# User-Agent by design, so CDP cannot be asked; the launcher has to write it down.
_MODE_MARKER = ".tunewrangler-chrome-mode"

# A headless run has no window to raise, but a headed one is left in the background on
# purpose, and Chrome throttles a backgrounded renderer's timers hard enough to stall a
# gate's CSS carousel mid-transition.
_NO_THROTTLE_ARGS = (
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
)


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


def pids_on_port(port: int) -> list[int]:
    """Process ids listening on a TCP port, or an empty list if they cannot be read."""
    try:
        result = subprocess.run(  # noqa: S603
            ["lsof", "-ti", f":{port}"],  # noqa: S607
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        logger.debug("Could not enumerate processes on port %d", port, exc_info=True)
        return []
    return [int(p) for p in result.stdout.split() if p.strip().isdigit()]


def kill_chrome_on_port(port: int, *, wait_seconds: float = 5.0) -> None:
    """Kill any process listening on the CDP debug port and wait for it to stop answering.

    Returning while the socket is still half-alive makes the next probe read the dying
    Chrome as a session worth reusing.
    """
    try:
        pids = pids_on_port(port)
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


def _running_mode(profile_dir: Path, port: int) -> str | None:
    """The mode of the Chrome on this port, or None if that cannot be established.

    The mode alone is not enough. A marker outlives the process it describes, so a Chrome
    that died without cleanup leaves one behind — and the next thing to take the port could
    be the user's own browser, which this would then attach to and drive. Recording the pid
    and checking it still owns the port is what ties the claim to something real.
    """
    try:
        mode, _, pids = (profile_dir / _MODE_MARKER).read_text().strip().partition(":")
    except OSError:
        return None
    recorded = {p for p in pids.split(",") if p.isdigit()}
    if not mode or not recorded:
        return None
    return mode if recorded & {str(p) for p in pids_on_port(port)} else None


def ensure_chrome_running(  # noqa: PLR0913
    *,
    chrome_path: str,
    profile_dir: Path,
    port: int,
    headed: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> None:
    """
    Attach to an existing Chrome debug session if one is already running on `port`,
    otherwise kill any stale process and launch a fresh instance.

    A session already up in the other mode is replaced rather than reused: a headed run
    started against a headless Chrome shows the user nothing to act on, and the login and
    record flows depend on there being a window.

    Raises ChromeBringupError if the port doesn't open within `timeout_seconds`.
    """
    want = "headed" if headed else "headless"
    if is_debug_port_open(port):
        if _running_mode(profile_dir, port) == want:
            logger.info("Chrome already running on port %d — reusing existing session.", port)
            return
        logger.info("Chrome on port %d is not %s — restarting it.", port, want)

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
        *_NO_THROTTLE_ARGS,
    ]
    if not headed:
        # The old headless had no profile support and no extensions; =new is the one that
        # keeps the saved SoundCloud session this whole flow depends on.
        args.append("--headless=new")
    logger.info("Launching Chrome (%s): %s", want, " ".join(args))
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if is_debug_port_open(port):
            # Written only once the port answers, so a launch that died leaves no marker
            # claiming a session that is not there.
            #
            # Whoever holds the port, not proc.pid: Chrome hands the debug socket to a
            # different process than the one launched here (measured 72704 launched,
            # 52538 listening), so recording proc.pid made every run fail its own check
            # and relaunch a browser that was already up and correct.
            owners = ",".join(str(pid) for pid in pids_on_port(port))
            (profile_dir / _MODE_MARKER).write_text(f"{want}:{owners}")
            logger.info("Chrome debug port %d is up (%s).", port, want)
            return
        time.sleep(poll_interval_seconds)

    msg = f"Chrome debug port {port} did not respond within {timeout_seconds}s"
    raise ChromeBringupError(msg)
