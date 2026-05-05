"""Tests for playlist_cache: URL normalization, item validation, save/load roundtrip."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from soundcloud_dl import playlist_cache
from soundcloud_dl.playlist import TrackItem
from soundcloud_dl.playlist_cache import (
    _item_to_track,
    _normalize_playlist_url,
    load_cached_tracks,
    save_cached_tracks,
)

if TYPE_CHECKING:
    from pathlib import Path


# ── _normalize_playlist_url ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://soundcloud.com/u/sets/p", "https://soundcloud.com/u/sets/p"),
        ("https://soundcloud.com/u/sets/p/", "https://soundcloud.com/u/sets/p"),
        ("https://soundcloud.com/u/sets/p?si=abc", "https://soundcloud.com/u/sets/p"),
        ("https://soundcloud.com/u/sets/p?si=abc&utm_source=x", "https://soundcloud.com/u/sets/p"),
        ("https://soundcloud.com/u/sets/p#fragment", "https://soundcloud.com/u/sets/p"),
        ("  https://soundcloud.com/u/sets/p  ", "https://soundcloud.com/u/sets/p"),
        ("https://soundcloud.com/u/sets/p/?si=abc", "https://soundcloud.com/u/sets/p"),
    ],
)
def test_normalize_playlist_url_strips_query_fragment_trailing_slash(
    raw: str, expected: str
) -> None:
    assert _normalize_playlist_url(raw) == expected


def test_normalize_playlist_url_idempotent() -> None:
    once = _normalize_playlist_url("https://soundcloud.com/u/sets/p?si=abc/")
    twice = _normalize_playlist_url(once)
    assert once == twice


# ── _item_to_track ───────────────────────────────────────────────────────────


def test_item_to_track_returns_track_for_valid_dict() -> None:
    item = {
        "url": "https://soundcloud.com/foo",
        "title": "Foo",
        "purchase_url": "https://gate.sc/...",
        "artist": "Foo Artist",
    }
    track = _item_to_track(item)
    assert track == TrackItem(
        url="https://soundcloud.com/foo",
        title="Foo",
        purchase_url="https://gate.sc/...",
        artist="Foo Artist",
    )


def test_item_to_track_returns_none_for_non_dict() -> None:
    assert _item_to_track("not a dict") is None
    assert _item_to_track(None) is None
    assert _item_to_track([1, 2, 3]) is None


def test_item_to_track_returns_none_when_url_missing() -> None:
    assert _item_to_track({"title": "no url"}) is None


def test_item_to_track_returns_none_when_url_empty_or_whitespace() -> None:
    assert _item_to_track({"url": ""}) is None
    assert _item_to_track({"url": "   "}) is None


def test_item_to_track_filters_non_string_optional_fields() -> None:
    item = {"url": "https://x", "title": 123, "purchase_url": [], "artist": {}}
    track = _item_to_track(item)
    assert track is not None
    assert track.url == "https://x"
    assert track.title is None
    assert track.purchase_url is None
    assert track.artist is None


def test_item_to_track_returns_none_when_url_not_string() -> None:
    assert _item_to_track({"url": 123}) is None


# ── save_cached_tracks / load_cached_tracks roundtrip ────────────────────────


@pytest.fixture
def cache_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect cache file to a tmp_path location for isolation."""
    path = tmp_path / "playlist_cache.json"
    monkeypatch.setattr(playlist_cache, "get_playlist_cache_file", lambda: path)
    return path


def test_load_returns_none_when_cache_file_missing(cache_path: Path) -> None:
    assert not cache_path.exists()
    assert load_cached_tracks("https://soundcloud.com/u/sets/p") is None


def test_save_then_load_roundtrips_track_list(cache_path: Path) -> None:
    url = "https://soundcloud.com/u/sets/p"
    tracks = [
        TrackItem(url="https://soundcloud.com/a", title="A", artist="Alice"),
        TrackItem(url="https://soundcloud.com/b", title="B", purchase_url="https://gate.sc/?x=y"),
    ]
    save_cached_tracks(url, tracks)
    assert cache_path.exists()
    loaded = load_cached_tracks(url)
    assert loaded == tracks


def test_save_supports_multiple_playlists_in_one_file(cache_path: Path) -> None:
    save_cached_tracks("https://soundcloud.com/u/sets/p1", [TrackItem(url="https://x/1")])
    save_cached_tracks("https://soundcloud.com/u/sets/p2", [TrackItem(url="https://x/2")])
    assert load_cached_tracks("https://soundcloud.com/u/sets/p1") == [TrackItem(url="https://x/1")]
    assert load_cached_tracks("https://soundcloud.com/u/sets/p2") == [TrackItem(url="https://x/2")]


def test_load_matches_normalized_url_variants(cache_path: Path) -> None:
    """Saved with one URL form, loaded with a query-stringed variant — same key."""
    save_cached_tracks("https://soundcloud.com/u/sets/p", [TrackItem(url="https://x")])
    assert load_cached_tracks("https://soundcloud.com/u/sets/p?si=abc&utm_source=share") == [
        TrackItem(url="https://x")
    ]


def test_load_returns_none_on_corrupt_json(cache_path: Path) -> None:
    cache_path.write_text("{not valid json", encoding="utf-8")
    assert load_cached_tracks("https://soundcloud.com/u/sets/p") is None


def test_load_skips_invalid_items_returns_valid_ones(cache_path: Path) -> None:
    payload = {
        "https://soundcloud.com/u/sets/p": [
            {"url": "https://x", "title": "ok"},
            {"title": "no url"},  # invalid — skipped
            "not a dict",  # invalid — skipped
            {"url": "https://y"},
        ]
    }
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_cached_tracks("https://soundcloud.com/u/sets/p")
    assert loaded == [TrackItem(url="https://x", title="ok"), TrackItem(url="https://y")]


def test_load_returns_none_when_all_items_invalid(cache_path: Path) -> None:
    payload = {"https://soundcloud.com/u/sets/p": [{"title": "no url"}, "garbage"]}
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_cached_tracks("https://soundcloud.com/u/sets/p") is None
