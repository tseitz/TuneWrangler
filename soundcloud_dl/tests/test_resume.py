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


def test_a_gate_that_stays_stuck_is_eventually_left_alone(tmp_processed_file: Path) -> None:
    """A gate needing a person cannot be got past by trying again.

    Retried every run it costs a minute of every batch for good — one batch of 12 spent
    seven of its twelve minutes on four tracks that had already failed identically.
    """
    playlist = "https://soundcloud.com/u/sets/p"
    url = "https://soundcloud.com/u/stuck"

    for _ in range(3):
        resume.record_state(playlist, url, "manual_review")

    states, attempts = resume.load_states(playlist), resume.load_attempts(playlist)
    assert resume.should_skip(url, states, attempts) is True
    assert resume.is_given_up_on(url, states, attempts) is True


def test_a_gate_is_retried_while_it_still_has_budget(tmp_processed_file: Path) -> None:
    playlist = "https://soundcloud.com/u/sets/p"
    url = "https://soundcloud.com/u/stuck"

    for _ in range(2):
        resume.record_state(playlist, url, "manual_review")

    states, attempts = resume.load_states(playlist), resume.load_attempts(playlist)
    assert resume.should_skip(url, states, attempts) is False


def test_getting_somewhere_new_gives_a_track_its_budget_back(tmp_processed_file: Path) -> None:
    """A run that stopped for a transient reason has not spent an attempt on being stuck."""
    playlist = "https://soundcloud.com/u/sets/p"
    url = "https://soundcloud.com/u/flaky"

    resume.record_state(playlist, url, "manual_review")
    resume.record_state(playlist, url, "manual_review")
    resume.record_state(playlist, url, "failed")
    resume.record_state(playlist, url, "manual_review")

    assert resume.load_attempts(playlist)[url] == 1


def test_an_entry_written_before_attempts_existed_still_loads(tmp_processed_file: Path) -> None:
    """The stored value used to be a bare state string; those must not read as unknown."""
    playlist = "https://soundcloud.com/u/sets/p"
    tmp_processed_file.write_text(
        json.dumps({playlist: {"https://soundcloud.com/u/a": "manual_review"}}), encoding="utf-8"
    )

    states, attempts = resume.load_states(playlist), resume.load_attempts(playlist)
    assert states == {"https://soundcloud.com/u/a": "manual_review"}
    # Zero, not "already spent": nothing recorded those runs, so the budget starts here.
    assert attempts == {"https://soundcloud.com/u/a": 0}
    assert resume.should_skip("https://soundcloud.com/u/a", states, attempts) is False


def test_the_run_actually_drops_a_track_it_has_given_up_on(tmp_processed_file: Path) -> None:
    """Through _get_tracks_to_process, because a budget the run never consults is no budget."""
    from soundcloud_dl.main import _get_tracks_to_process
    from soundcloud_dl.playlist import TrackItem

    playlist = "https://soundcloud.com/u/sets/p"
    stuck = TrackItem(url="https://soundcloud.com/u/stuck")
    fresh = TrackItem(url="https://soundcloud.com/u/fresh")
    for _ in range(3):
        resume.record_state(playlist, stuck.url, "manual_review")

    assert _get_tracks_to_process([stuck, fresh], playlist) == [fresh]


def test_a_track_with_budget_left_is_still_queued(tmp_processed_file: Path) -> None:
    from soundcloud_dl.main import _get_tracks_to_process
    from soundcloud_dl.playlist import TrackItem

    playlist = "https://soundcloud.com/u/sets/p"
    stuck = TrackItem(url="https://soundcloud.com/u/stuck")
    resume.record_state(playlist, stuck.url, "manual_review")

    assert _get_tracks_to_process([stuck], playlist) == [stuck]


def test_a_track_that_needs_attention_says_why(tmp_processed_file: Path) -> None:
    """Otherwise picking the work back up means correlating against a rotating log."""
    playlist = "https://soundcloud.com/u/sets/p"
    url = "https://soundcloud.com/u/stuck"

    resume.record_state(playlist, url, "manual_review", reason="stuck at jev_cap_25")

    assert resume.load_reasons(playlist)[url] == "stuck at jev_cap_25"


def test_a_later_attempt_replaces_the_earlier_reason(tmp_processed_file: Path) -> None:
    playlist = "https://soundcloud.com/u/sets/p"
    url = "https://soundcloud.com/u/flaky"

    resume.record_state(playlist, url, "failed", reason="TimeoutError: page took too long")
    resume.record_state(playlist, url, "manual_review", reason="stuck at jev_cap_25")

    assert resume.load_reasons(playlist)[url] == "stuck at jev_cap_25"


def test_a_successful_track_stores_no_reason(tmp_processed_file: Path) -> None:
    """Nothing to say, so nothing written — the file stays readable."""
    playlist = "https://soundcloud.com/u/sets/p"
    url = "https://soundcloud.com/u/fine"

    resume.record_state(playlist, url, "done")

    stored = json.loads(tmp_processed_file.read_text())[playlist][url]
    assert "reason" not in stored
    assert resume.load_reasons(playlist)[url] == ""


def test_reasons_survive_an_entry_written_before_they_existed(tmp_processed_file: Path) -> None:
    playlist = "https://soundcloud.com/u/sets/p"
    tmp_processed_file.write_text(
        json.dumps({playlist: {"https://soundcloud.com/u/a": {"state": "failed", "attempts": 1}}}),
        encoding="utf-8",
    )

    assert resume.load_reasons(playlist) == {"https://soundcloud.com/u/a": ""}
    # And recording a fresh one does not lose the neighbouring record.
    resume.record_state(playlist, "https://soundcloud.com/u/b", "failed", reason="boom")
    assert resume.load_states(playlist)["https://soundcloud.com/u/a"] == "failed"
