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


def test_a_session_already_in_the_wanted_mode_is_reused(tmp_path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / chrome_bringup._MODE_MARKER).write_text("headless:4242")  # noqa: SLF001

    with (
        patch.object(chrome_bringup, "is_debug_port_open", return_value=True),
        patch.object(chrome_bringup, "pids_on_port", return_value=[4242]),
        patch("subprocess.Popen") as mock_popen,
    ):
        chrome_bringup.ensure_chrome_running(
            chrome_path="/fake/chrome",
            profile_dir=profile_dir,
            port=9222,
        )
        mock_popen.assert_not_called()


def test_a_session_in_the_other_mode_is_restarted_not_reused(tmp_path):
    # --login against a reused headless Chrome shows the user nothing to sign in to.
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / chrome_bringup._MODE_MARKER).write_text("headless:4242")  # noqa: SLF001

    with (
        patch.object(chrome_bringup, "is_debug_port_open", return_value=True),
        patch.object(chrome_bringup, "pids_on_port", return_value=[4242]),
        patch.object(chrome_bringup, "kill_chrome_on_port") as mock_kill,
        patch("subprocess.Popen") as mock_popen,
    ):
        chrome_bringup.ensure_chrome_running(
            chrome_path="/fake/chrome",
            profile_dir=profile_dir,
            port=9222,
            headed=True,
        )
        mock_kill.assert_called_once()
        mock_popen.assert_called_once()
        assert "--headless=new" not in mock_popen.call_args.args[0]


def test_an_unmarked_session_is_restarted_rather_than_assumed(tmp_path):
    # A Chrome someone else started on the port has no marker, and guessing its mode is
    # how a headed flow ends up driving an invisible browser.
    with (
        patch.object(chrome_bringup, "is_debug_port_open", return_value=True),
        patch.object(chrome_bringup, "kill_chrome_on_port"),
        patch.object(chrome_bringup, "pids_on_port", return_value=[1]),
        patch("subprocess.Popen") as mock_popen,
    ):
        chrome_bringup.ensure_chrome_running(
            chrome_path="/fake/chrome",
            profile_dir=tmp_path / "profile",
            port=9222,
        )
        mock_popen.assert_called_once()


def test_the_mode_is_recorded_only_once_the_port_answers(tmp_path):
    profile_dir = tmp_path / "profile"
    marker = profile_dir / chrome_bringup._MODE_MARKER  # noqa: SLF001

    with (
        patch.object(chrome_bringup, "is_debug_port_open", return_value=False),
        patch("subprocess.Popen"),
        pytest.raises(chrome_bringup.ChromeBringupError),
    ):
        chrome_bringup.ensure_chrome_running(
            chrome_path="/fake/chrome",
            profile_dir=profile_dir,
            port=9222,
            timeout_seconds=0.1,
            poll_interval_seconds=0.05,
        )
    assert not marker.exists()


def test_a_headless_launch_asks_for_the_new_headless(tmp_path):
    poll = {"n": 0}

    def fake_is_open(_port: int) -> bool:
        poll["n"] += 1
        return poll["n"] > 1

    with (
        patch.object(chrome_bringup, "is_debug_port_open", side_effect=fake_is_open),
        patch.object(chrome_bringup, "kill_chrome_on_port"),
        patch.object(chrome_bringup, "pids_on_port", return_value=[1]),
        patch("subprocess.Popen") as mock_popen,
    ):
        chrome_bringup.ensure_chrome_running(
            chrome_path="/fake/chrome",
            profile_dir=tmp_path / "profile",
            port=9222,
        )
        args = mock_popen.call_args.args[0]
    # The old --headless has no profile support, which is where the saved session lives.
    assert "--headless=new" in args
    assert "--headless" not in args


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
        patch.object(chrome_bringup, "pids_on_port", return_value=[1]),
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


def test_a_marker_left_by_a_dead_chrome_is_not_trusted(tmp_path):
    # The port can be taken by something else — the user's own browser, say — and driving
    # that would be driving their real session.
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / chrome_bringup._MODE_MARKER).write_text("headless:4242")  # noqa: SLF001

    with (
        patch.object(chrome_bringup, "is_debug_port_open", return_value=True),
        patch.object(chrome_bringup, "pids_on_port", return_value=[9999]),
        patch.object(chrome_bringup, "kill_chrome_on_port"),
        patch("subprocess.Popen") as mock_popen,
    ):
        chrome_bringup.ensure_chrome_running(
            chrome_path="/fake/chrome",
            profile_dir=profile_dir,
            port=9222,
        )
        mock_popen.assert_called_once()


def test_the_marker_records_whoever_holds_the_port(tmp_path):
    profile_dir = tmp_path / "profile"
    poll = {"n": 0}

    def fake_is_open(_port: int) -> bool:
        poll["n"] += 1
        return poll["n"] > 1

    with (
        patch.object(chrome_bringup, "is_debug_port_open", side_effect=fake_is_open),
        patch.object(chrome_bringup, "kill_chrome_on_port"),
        patch("subprocess.Popen") as mock_popen,
    ):
        with patch.object(chrome_bringup, "pids_on_port", return_value=[52538]):
            chrome_bringup.ensure_chrome_running(
                chrome_path="/fake/chrome",
                profile_dir=profile_dir,
                port=9222,
            )
    marker = profile_dir / chrome_bringup._MODE_MARKER  # noqa: SLF001
    # The port owner, not the launched pid — Chrome hands the socket to another process,
    # so recording proc.pid relaunched a correct browser on every run.
    assert marker.read_text() == "headless:52538"
