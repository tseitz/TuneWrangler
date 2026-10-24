from types import SimpleNamespace

import pytest

from rekordbox_smart_playlists.cli import commands
from rekordbox_smart_playlists.core.config import Config
from rekordbox_smart_playlists.core.playlist_manager import ExistingPlaylistStrategy

ROOTS = [{"name": "Halloween", "child_count": 2}]


def _strategy(existing, roots, *, tty, monkeypatch):
    monkeypatch.setattr(commands.sys.stdin, "isatty", lambda: tty)
    command = commands.PlaylistCommand(Config())
    return command._existing_strategy(SimpleNamespace(existing=existing), roots)


@pytest.mark.parametrize(("existing", "roots"), [(None, ROOTS), ("prompt", []), ("prompt", ROOTS)])
def test_a_prompt_without_a_terminal_fails_before_input(existing, roots, monkeypatch):
    def no_input(*_a):
        raise AssertionError("input() called")

    monkeypatch.setattr("builtins.input", no_input)
    with pytest.raises(commands.NoTerminalError, match="--existing"):
        _strategy(existing, roots, tty=False, monkeypatch=monkeypatch)


@pytest.mark.parametrize(
    ("existing", "expected"),
    [
        ("skip", ExistingPlaylistStrategy.SKIP_ALL),
        ("overwrite", ExistingPlaylistStrategy.OVERWRITE_ALL),
    ],
)
def test_an_explicit_choice_needs_no_terminal(existing, expected, monkeypatch):
    assert _strategy(existing, ROOTS, tty=False, monkeypatch=monkeypatch) == expected


def test_no_existing_folders_needs_no_terminal(monkeypatch):
    assert (
        _strategy(None, [], tty=False, monkeypatch=monkeypatch) == ExistingPlaylistStrategy.SKIP_ALL
    )


def test_a_terminal_still_gets_the_menu(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_a: "2")
    assert (
        _strategy(None, ROOTS, tty=True, monkeypatch=monkeypatch)
        == ExistingPlaylistStrategy.SKIP_ALL
    )
