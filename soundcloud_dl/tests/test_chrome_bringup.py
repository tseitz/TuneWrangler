"""Unit tests for chrome_bringup module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from soundcloud_dl import chrome_bringup


def _patch_httpx_client(*, side_effect=None, status_code: int | None = None):
    """Patch chrome_bringup.httpx.Client so its context-manager .get() can be mocked."""
    client_mock = MagicMock()
    if side_effect is not None:
        client_mock.__enter__.return_value.get.side_effect = side_effect
    else:
        client_mock.__enter__.return_value.get.return_value = MagicMock(status_code=status_code)
    return patch.object(chrome_bringup.httpx, "Client", return_value=client_mock)


def test_is_debug_port_open_true_on_200():
    with _patch_httpx_client(status_code=200):
        assert chrome_bringup.is_debug_port_open(9222) is True


def test_is_debug_port_open_false_on_connect_error():
    import httpx

    with _patch_httpx_client(side_effect=httpx.ConnectError("nope")):
        assert chrome_bringup.is_debug_port_open(9222) is False


def test_is_debug_port_open_false_on_timeout():
    import httpx

    with _patch_httpx_client(side_effect=httpx.ReadTimeout("slow")):
        assert chrome_bringup.is_debug_port_open(9222) is False


def test_ensure_chrome_running_skips_launch_when_port_open(tmp_path):
    with (
        patch.object(chrome_bringup, "is_debug_port_open", return_value=True),
        patch("subprocess.Popen") as mock_popen,
    ):
        chrome_bringup.ensure_chrome_running(
            chrome_path="/fake/chrome",
            profile_dir=tmp_path / "profile",
            port=9222,
        )
        mock_popen.assert_not_called()


def test_ensure_chrome_running_launches_when_port_closed(tmp_path):
    profile_dir = tmp_path / "profile"
    poll_count = {"n": 0}

    def fake_is_open(_port: int) -> bool:
        # First call (pre-launch probe): closed. After launch, return True after 1 poll.
        poll_count["n"] += 1
        return poll_count["n"] > 1

    with (
        patch.object(chrome_bringup, "is_debug_port_open", side_effect=fake_is_open),
        # kill_chrome_on_port shells out via subprocess.run, which uses subprocess.Popen
        # internally — patch it out so our Popen mock only sees the Chrome launch.
        patch.object(chrome_bringup, "kill_chrome_on_port"),
        patch("subprocess.Popen") as mock_popen,
    ):
        chrome_bringup.ensure_chrome_running(
            chrome_path="/fake/chrome",
            profile_dir=profile_dir,
            port=9222,
        )
        mock_popen.assert_called_once()
        args = mock_popen.call_args.args[0]
        assert args[0] == "/fake/chrome"
        assert "--remote-debugging-port=9222" in args
        assert f"--user-data-dir={profile_dir}" in args
        assert "--no-first-run" in args
        assert "--no-default-browser-check" in args
        assert profile_dir.exists()


def test_ensure_chrome_running_raises_on_timeout(tmp_path):
    with (
        patch.object(chrome_bringup, "is_debug_port_open", return_value=False),
        patch("subprocess.Popen"),
        pytest.raises(chrome_bringup.ChromeBringupError, match="did not respond"),
    ):
        chrome_bringup.ensure_chrome_running(
            chrome_path="/fake/chrome",
            profile_dir=tmp_path / "profile",
            port=9222,
            timeout_seconds=0.1,
            poll_interval_seconds=0.05,
        )
