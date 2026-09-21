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
    (profile_dir / chrome_bringup._MODE_MARKER).write_text("headless:4242")

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
    (profile_dir / chrome_bringup._MODE_MARKER).write_text("headless:4242")

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
    marker = profile_dir / chrome_bringup._MODE_MARKER

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
        # Gate pages autoplay the track. A headless run has no window to mute it from, so
        # the only person who can stop it is whoever is in the room.
        assert "--mute-audio" in args
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
    (profile_dir / chrome_bringup._MODE_MARKER).write_text("headless:4242")

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
    marker = profile_dir / chrome_bringup._MODE_MARKER
    # The port owner, not the launched pid — Chrome hands the socket to another process,
    # so recording proc.pid relaunched a correct browser on every run.
    assert marker.read_text() == "headless:52538"


def test_a_reused_session_is_not_reported_as_launched(tmp_path):
    # Whoever started it is still using it. Reporting a launch here is what lets a run
    # shut down a browser it does not own.
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / chrome_bringup._MODE_MARKER).write_text("headless:4242")

    with (
        patch.object(chrome_bringup, "is_debug_port_open", return_value=True),
        patch.object(chrome_bringup, "pids_on_port", return_value=[4242]),
        patch("subprocess.Popen"),
    ):
        assert (
            chrome_bringup.ensure_chrome_running(
                chrome_path="/fake/chrome",
                profile_dir=profile_dir,
                port=9222,
            )
            is False
        )


def test_a_fresh_launch_is_reported_as_launched(tmp_path):
    profile_dir = tmp_path / "profile"

    with (
        patch.object(chrome_bringup, "is_debug_port_open", side_effect=[False, True]),
        patch.object(chrome_bringup, "kill_chrome_on_port"),
        patch.object(chrome_bringup, "pids_on_port", return_value=[777]),
        patch("subprocess.Popen"),
    ):
        assert (
            chrome_bringup.ensure_chrome_running(
                chrome_path="/fake/chrome",
                profile_dir=profile_dir,
                port=9222,
            )
            is True
        )


def test_shutdown_asks_chrome_to_exit_before_killing_it(tmp_path):
    # SIGTERM, not SIGKILL: the SoundCloud login and the OAuth grants a gate run collects
    # are cookies Chrome only writes out on a clean exit.
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / chrome_bringup._MODE_MARKER).write_text("headless:4242")
    signals: list[tuple[int, int]] = []

    with (
        patch.object(chrome_bringup, "pids_on_port", return_value=[4242]),
        patch.object(chrome_bringup, "is_debug_port_open", return_value=False),
        patch.object(chrome_bringup, "kill_chrome_on_port") as mock_kill,
        patch.object(chrome_bringup.os, "kill", side_effect=lambda p, s: signals.append((p, s))),
    ):
        chrome_bringup.shutdown_chrome_on_port(profile_dir, 9222)

    import signal as signal_module

    assert signals == [(4242, signal_module.SIGTERM)]
    mock_kill.assert_not_called()
    assert not (profile_dir / chrome_bringup._MODE_MARKER).exists()


def test_shutdown_falls_back_to_kill_when_chrome_ignores_sigterm(tmp_path):
    import signal as signal_module

    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    signals: list[tuple[int, int]] = []

    with (
        patch.object(chrome_bringup, "pids_on_port", return_value=[4242]),
        patch.object(chrome_bringup, "is_debug_port_open", return_value=True),
        patch.object(chrome_bringup.os, "kill", side_effect=lambda p, s: signals.append((p, s))),
        patch.object(chrome_bringup.time, "sleep"),
    ):
        chrome_bringup.shutdown_chrome_on_port(profile_dir, 9222, wait_seconds=0.01)

    assert signals == [(4242, signal_module.SIGTERM), (4242, signal_module.SIGKILL)]


def test_a_process_that_took_the_port_after_sigterm_is_not_killed(tmp_path):
    """The gap between SIGTERM and the kill is long enough for the port to change hands.

    Chrome exits slowly, releases 9222, and the next thing to bind it — another run, or a
    browser started by hand — must not be killed in its place.
    """
    import signal as signal_module

    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    signals: list[tuple[int, int]] = []
    # Our Chrome first; by the time the kill is considered, a stranger owns the port.
    port_owners = [[4242], [9999], [9999], [9999]]

    with (
        patch.object(chrome_bringup, "pids_on_port", side_effect=lambda _p: port_owners.pop(0)),
        patch.object(chrome_bringup, "is_debug_port_open", return_value=True),
        patch.object(chrome_bringup.os, "kill", side_effect=lambda p, s: signals.append((p, s))),
        patch.object(chrome_bringup.time, "sleep"),
    ):
        chrome_bringup.shutdown_chrome_on_port(profile_dir, 9222, wait_seconds=0.01)

    assert signals == [(4242, signal_module.SIGTERM)]
    assert not any(pid == 9999 for pid, _ in signals)


def test_the_marker_survives_a_shutdown_that_did_not_free_the_port(tmp_path):
    """The marker is what stops the next run adopting a browser it does not own.

    Removing it while something is still listening is what lets the next run attach to,
    and drive, whatever that turns out to be.
    """
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / chrome_bringup._MODE_MARKER).write_text("headless:4242")

    with (
        patch.object(chrome_bringup, "pids_on_port", return_value=[4242]),
        patch.object(chrome_bringup, "is_debug_port_open", return_value=True),
        patch.object(chrome_bringup.os, "kill"),
        patch.object(chrome_bringup.time, "sleep"),
    ):
        chrome_bringup.shutdown_chrome_on_port(profile_dir, 9222, wait_seconds=0.01)

    assert (profile_dir / chrome_bringup._MODE_MARKER).exists()


def test_only_listeners_are_ever_signalled():
    """A client of the port must not end up in the list that gets SIGTERMed.

    Pointing a browser at localhost:9222 to watch a run opens a connection to it, and a
    bare ":9222" match returns that browser as if it were the automation.
    """
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="4242\n")
        chrome_bringup.pids_on_port(9222)

    argv = mock_run.call_args[0][0]
    assert "-sTCP:LISTEN" in argv
    # lsof ORs its selection flags; without -a the state filter widens the match instead
    # of narrowing it, and every client comes back anyway.
    assert "-a" in argv
