"""Tests for playlist: track parsing + access token error handling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from soundcloud_dl.playlist import (
    TrackItem,
    _get_access_token,
    _track_to_item,
    _tracks_from_playlist_data,
    extract_track_urls,
)

# ── TrackItem ────────────────────────────────────────────────────────────────


def test_track_item_defaults_optional_fields_to_none() -> None:
    item = TrackItem(url="https://soundcloud.com/foo")
    assert item.url == "https://soundcloud.com/foo"
    assert item.title is None
    assert item.purchase_url is None
    assert item.artist is None


# ── _track_to_item ───────────────────────────────────────────────────────────


def test_track_to_item_keeps_who_soundcloud_credits() -> None:
    track = {
        "permalink_url": "https://soundcloud.com/subcarbon/stealth",
        "user": {"username": "SubCarbon Records"},
        "metadata_artist": "IDHS, XI ",
        "label_name": "Subcarbon Records",
    }
    item = _track_to_item(track)
    assert item is not None
    assert item.metadata_artist == "IDHS, XI"
    assert item.label_name == "Subcarbon Records"


def test_track_to_item_reads_blank_credits_as_absent() -> None:
    track = {"permalink_url": "https://soundcloud.com/u/t", "metadata_artist": " ", "label_name": ""}
    item = _track_to_item(track)
    assert item is not None
    assert item.metadata_artist is None
    assert item.label_name is None


def test_track_to_item_prefers_permalink_url() -> None:
    track = {
        "permalink_url": "https://soundcloud.com/u/track-a",
        "permalink": "different",
        "user": {"permalink": "u", "username": "Alice"},
        "title": "Track A",
    }
    item = _track_to_item(track)
    assert item is not None
    assert item.url == "https://soundcloud.com/u/track-a"


def test_track_to_item_falls_back_to_constructed_url() -> None:
    track = {
        "permalink": "track-a",
        "user": {"permalink": "alice"},
    }
    item = _track_to_item(track)
    assert item is not None
    assert item.url == "https://soundcloud.com/alice/track-a"


def test_track_to_item_falls_back_to_uri() -> None:
    track = {"uri": "soundcloud:tracks:12345"}
    item = _track_to_item(track)
    assert item is not None
    assert item.url == "soundcloud:tracks:12345"


def test_track_to_item_returns_none_when_no_url_can_be_determined() -> None:
    assert _track_to_item({}) is None
    assert _track_to_item({"title": "no url info"}) is None


def test_track_to_item_extracts_title_purchase_artist() -> None:
    track = {
        "permalink_url": "https://soundcloud.com/u/x",
        "title": "Banger",
        "purchase_url": "https://gate.sc/?url=...",
        "user": {"username": "Producer Name"},
    }
    item = _track_to_item(track)
    assert item is not None
    assert item.title == "Banger"
    assert item.purchase_url == "https://gate.sc/?url=..."
    assert item.artist == "Producer Name"


def test_track_to_item_filters_non_string_optional_fields() -> None:
    track = {
        "permalink_url": "https://soundcloud.com/u/x",
        "title": 42,
        "purchase_url": [],
        "user": {"username": None},
    }
    item = _track_to_item(track)
    assert item is not None
    assert item.title is None
    assert item.purchase_url is None
    assert item.artist is None


# ── _tracks_from_playlist_data ───────────────────────────────────────────────


def test_tracks_from_playlist_data_extracts_valid_tracks() -> None:
    data = {
        "tracks": [
            {"permalink_url": "https://soundcloud.com/u/a", "title": "A"},
            {"permalink_url": "https://soundcloud.com/u/b", "title": "B"},
        ]
    }
    tracks = _tracks_from_playlist_data(data)
    assert [t.url for t in tracks] == [
        "https://soundcloud.com/u/a",
        "https://soundcloud.com/u/b",
    ]


def test_tracks_from_playlist_data_skips_invalid_entries() -> None:
    data = {
        "tracks": [
            {"permalink_url": "https://soundcloud.com/u/a"},
            "not a dict",
            {},  # no URL — skipped by _track_to_item
            {"permalink_url": "https://soundcloud.com/u/b"},
        ]
    }
    tracks = _tracks_from_playlist_data(data)
    assert len(tracks) == 2


def test_tracks_from_playlist_data_returns_empty_when_tracks_missing_or_wrong_type() -> None:
    assert _tracks_from_playlist_data({}) == []
    assert _tracks_from_playlist_data({"tracks": None}) == []
    assert _tracks_from_playlist_data({"tracks": "not a list"}) == []


# ── _get_access_token ────────────────────────────────────────────────────────


def _patch_httpx_post(*, json_data: dict | None = None, side_effect=None):
    """Build a patcher for httpx.Client used by _get_access_token."""
    client_mock = MagicMock()
    response_mock = MagicMock()
    if json_data is not None:
        response_mock.json.return_value = json_data
        response_mock.raise_for_status = MagicMock()
    if side_effect is not None:
        client_mock.__enter__.return_value.post.side_effect = side_effect
    else:
        client_mock.__enter__.return_value.post.return_value = response_mock
    return patch("soundcloud_dl.playlist.httpx.Client", return_value=client_mock)


def test_get_access_token_returns_token_on_success() -> None:
    with _patch_httpx_post(json_data={"access_token": "tok_xyz"}):
        assert _get_access_token("client", "secret") == "tok_xyz"


def test_get_access_token_raises_when_response_missing_token() -> None:
    with _patch_httpx_post(json_data={}), pytest.raises(RuntimeError, match="missing access_token"):
        _get_access_token("client", "secret")


def test_get_access_token_raises_when_token_is_empty_string() -> None:
    with _patch_httpx_post(json_data={"access_token": ""}), pytest.raises(RuntimeError):
        _get_access_token("client", "secret")


def test_get_access_token_propagates_http_error() -> None:
    err = httpx.HTTPStatusError("401", request=MagicMock(), response=MagicMock())
    with _patch_httpx_post(side_effect=err), pytest.raises(httpx.HTTPStatusError):
        _get_access_token("client", "secret")


# ── extract_track_urls ───────────────────────────────────────────────────────


def test_extract_track_urls_raises_when_credentials_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("soundcloud_dl.playlist.SOUNDCLOUD_CLIENT_ID", "")
    monkeypatch.setattr("soundcloud_dl.playlist.SOUNDCLOUD_CLIENT_SECRET", "")
    with pytest.raises(RuntimeError, match="CLIENT_ID and SOUNDCLOUD_CLIENT_SECRET"):
        extract_track_urls("https://soundcloud.com/u/sets/p")


def test_extract_track_urls_aggregates_tracks_across_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("soundcloud_dl.playlist.SOUNDCLOUD_CLIENT_ID", "id")
    monkeypatch.setattr("soundcloud_dl.playlist.SOUNDCLOUD_CLIENT_SECRET", "secret")
    monkeypatch.setattr("soundcloud_dl.playlist._get_access_token", lambda _i, _s: "tok")

    page1 = {
        "tracks": [{"permalink_url": "https://soundcloud.com/a"}],
        "next_href": "https://api.soundcloud.com/playlists/1/tracks?cursor=2",
    }
    page2 = {
        "tracks": [{"permalink_url": "https://soundcloud.com/b"}],
        "next_href": None,
    }

    monkeypatch.setattr(
        "soundcloud_dl.playlist._resolve_playlist", lambda _u, _t: dict(page1, kind="playlist")
    )
    monkeypatch.setattr(
        "soundcloud_dl.playlist._fetch_next_page", lambda _u, _t: (page2, page2["next_href"])
    )

    tracks = extract_track_urls("https://soundcloud.com/u/sets/p")
    assert [t.url for t in tracks] == ["https://soundcloud.com/a", "https://soundcloud.com/b"]
