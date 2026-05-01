"""Unit tests for resume state model."""

import json
from pathlib import Path

import pytest

from soundcloud_dl import resume


@pytest.fixture
def tmp_processed_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect resume to a temp file."""
    f = tmp_path / "processed.json"
    monkeypatch.setattr(resume, "get_processed_file", lambda: f)
    return f


def test_load_states_empty_file(tmp_processed_file: Path) -> None:
    assert resume.load_states("https://soundcloud.com/x/sets/y") == {}


def test_record_and_load_state(tmp_processed_file: Path) -> None:
    playlist = "https://soundcloud.com/u/sets/p"
    resume.record_state(playlist, "https://soundcloud.com/u/track-a", "done")
    resume.record_state(playlist, "https://soundcloud.com/u/track-b", "captcha_pending")
    states = resume.load_states(playlist)
    assert states == {
        "https://soundcloud.com/u/track-a": "done",
        "https://soundcloud.com/u/track-b": "captcha_pending",
    }


def test_state_overwrite(tmp_processed_file: Path) -> None:
    playlist = "https://soundcloud.com/u/sets/p"
    resume.record_state(playlist, "https://soundcloud.com/u/track-a", "captcha_pending")
    resume.record_state(playlist, "https://soundcloud.com/u/track-a", "done")
    assert resume.load_states(playlist) == {"https://soundcloud.com/u/track-a": "done"}


def test_should_skip_only_done(tmp_processed_file: Path) -> None:
    playlist = "https://soundcloud.com/u/sets/p"
    resume.record_state(playlist, "https://soundcloud.com/u/track-a", "done")
    resume.record_state(playlist, "https://soundcloud.com/u/track-b", "captcha_pending")
    resume.record_state(playlist, "https://soundcloud.com/u/track-c", "manual_review")
    resume.record_state(playlist, "https://soundcloud.com/u/track-d", "failed")
    states = resume.load_states(playlist)
    assert resume.should_skip("https://soundcloud.com/u/track-a", states) is True
    assert resume.should_skip("https://soundcloud.com/u/track-b", states) is False
    assert resume.should_skip("https://soundcloud.com/u/track-c", states) is False
    assert resume.should_skip("https://soundcloud.com/u/track-d", states) is False


def test_legacy_list_format_read_as_done(tmp_processed_file: Path) -> None:
    """Old format was {playlist: [url1, url2]}. All entries treated as done."""
    playlist = "https://soundcloud.com/u/sets/p"
    tmp_processed_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_processed_file.write_text(json.dumps({playlist: ["https://soundcloud.com/u/old-track"]}))
    states = resume.load_states(playlist)
    assert states == {"https://soundcloud.com/u/old-track": "done"}


def test_normalizes_trailing_slash(tmp_processed_file: Path) -> None:
    resume.record_state("https://soundcloud.com/u/sets/p/", "https://x/track", "done")
    assert resume.load_states("https://soundcloud.com/u/sets/p") == {"https://x/track": "done"}
