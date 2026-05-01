"""Unit tests for chrome_bringup module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from soundcloud_dl import chrome_bringup


def test_is_debug_port_open_true_on_200():
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        assert chrome_bringup.is_debug_port_open(9222) is True


def test_is_debug_port_open_false_on_connect_error():
    import httpx
    with patch("httpx.get", side_effect=httpx.ConnectError("nope")):
        assert chrome_bringup.is_debug_port_open(9222) is False


def test_is_debug_port_open_false_on_timeout():
    import httpx
    with patch("httpx.get", side_effect=httpx.ReadTimeout("slow")):
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
