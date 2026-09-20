"""Tests for the judged filename, and for when it declines to ask."""

from __future__ import annotations

from typing import Any

import pytest

from soundcloud_dl import track_naming
from soundcloud_dl.track_naming import judge_track_filename, name_candidates

PROMO = "FTP (out now on good dub. records)"


class _FakeAnswer:
    def __init__(self, choice: str, confidence: float) -> None:
        self.choice = choice
        self.confidence = confidence


class _FakeResponse:
    def __init__(self, choice: str, confidence: float) -> None:
        self.choices = {"best_name": _FakeAnswer(choice, confidence)}


def _fake_client(choice: str, confidence: float, calls: list[dict[str, Any]]):
    class _Client:
        async def system_one(self, **kwargs: Any) -> _FakeResponse:
            calls.append(kwargs)
            return _FakeResponse(choice, confidence)

    return lambda: _Client()


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setattr(track_naming, "TYPESAFE_API_KEY", "test-key")


# ── Candidates ─────────────────────────────────────────────────────────────────


def test_a_promo_suffix_becomes_a_candidate_not_a_rule():
    # Both forms are offered; nothing here decides between them.
    assert name_candidates(PROMO, "FOSSILS") == [
        "FOSSILS - FTP (out now on good dub. records)",
        "FOSSILS - FTP",
    ]


def test_a_remix_credit_is_offered_but_never_forced_off():
    names = name_candidates("Smack My Up (Lowshade Flip)", "Lowshade")
    assert names[0] == "Lowshade - Smack My Up (Lowshade Flip)"
    assert "Lowshade - Smack My Up" in names


def test_a_plain_title_has_nothing_to_decide():
    assert name_candidates("FTP", "FOSSILS") == ["FOSSILS - FTP"]


def test_trimming_never_eats_the_whole_title():
    assert name_candidates("(FREE)", "A") == name_candidates("(FREE)", "A")
    for name in name_candidates("Go (x)", "A"):
        assert name.strip()


# ── Asking, and not asking ─────────────────────────────────────────────────────


async def test_nothing_to_decide_means_no_api_call(monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(track_naming, "AsyncTypeSafeClient", _fake_client("x", 1.0, calls))
    assert await judge_track_filename("FTP", "FOSSILS") == "FOSSILS - FTP"
    assert calls == []


async def test_a_confident_judgment_is_taken(monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        track_naming, "AsyncTypeSafeClient", _fake_client("FOSSILS - FTP", 0.9, calls)
    )
    assert await judge_track_filename(PROMO, "FOSSILS") == "FOSSILS - FTP"
    assert len(calls) == 1


async def test_a_low_confidence_judgment_keeps_the_rule_based_name(monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        track_naming, "AsyncTypeSafeClient", _fake_client("FOSSILS - FTP", 0.2, calls)
    )
    assert await judge_track_filename(PROMO, "FOSSILS") == (
        "FOSSILS - FTP (out now on good dub. records)"
    )


async def test_an_answer_outside_the_candidates_is_refused(monkeypatch):
    # Nothing invents a name here; an off-list answer is a bug, not a suggestion.
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        track_naming, "AsyncTypeSafeClient", _fake_client("something else", 0.99, calls)
    )
    assert await judge_track_filename(PROMO, "FOSSILS") == (
        "FOSSILS - FTP (out now on good dub. records)"
    )


async def test_an_api_failure_still_names_the_file(monkeypatch):
    class _Boom:
        async def system_one(self, **_kwargs: Any) -> None:
            msg = "no"
            raise RuntimeError(msg)

    monkeypatch.setattr(track_naming, "AsyncTypeSafeClient", lambda: _Boom())
    assert await judge_track_filename(PROMO, "FOSSILS") == (
        "FOSSILS - FTP (out now on good dub. records)"
    )


async def test_no_api_key_means_no_call(monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(track_naming, "TYPESAFE_API_KEY", "")
    monkeypatch.setattr(track_naming, "AsyncTypeSafeClient", _fake_client("x", 1.0, calls))
    assert await judge_track_filename(PROMO, "FOSSILS") == (
        "FOSSILS - FTP (out now on good dub. records)"
    )
    assert calls == []


async def test_the_title_is_labelled_as_untrusted_in_the_prompt(monkeypatch):
    # The upload title is attacker-controlled text; it must not read as instruction.
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        track_naming, "AsyncTypeSafeClient", _fake_client("FOSSILS - FTP", 0.9, calls)
    )
    await judge_track_filename(PROMO, "FOSSILS")
    assert calls[0]["state"]["untrusted_soundcloud_title"] == PROMO


async def test_a_missing_title_is_not_named_at_all(monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(track_naming, "AsyncTypeSafeClient", _fake_client("x", 1.0, calls))
    assert await judge_track_filename(None, "FOSSILS") is None
    assert calls == []
