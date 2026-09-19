"""Tests for what counts as the downloaded track."""

import pytest

from soundcloud_dl.downloads import looks_like_audio, rename_to_track, save_bytes


@pytest.mark.parametrize(
    ("url", "ct", "cd", "expected"),
    [
        # The real miss: a webfont served as octet-stream was saved as the track.
        ("https://hypeddit.com/css/fontawesome-webfont.woff2", "application/octet-stream", "", False),
        ("https://cdn.x/app.js", "application/octet-stream", "", False),
        ("https://cdn.x/logo.png", "image/png", "", False),
        ("https://cdn.x/page.html", "text/html", "", False),
        ("https://cdn.x/track.mp3", "", "", True),
        ("https://cdn.x/track.wav", "text/html", "", True),
        ("https://cdn.x/dl/6353", "audio/mpeg", "", True),
        ("https://cdn.x/dl/6353", "application/octet-stream", "", True),
        ("https://cdn.x/dl/6353", "", 'attachment; filename="t.mp3"', True),
        ("https://cdn.x/dl/6353", "text/html", "", False),
        ("https://cdn.x/dl/6353", None, None, False),
    ],
)
def test_looks_like_audio(url, ct, cd, expected):
    assert looks_like_audio(url, ct, cd) is expected


def test_save_bytes_creates_a_missing_download_directory(tmp_path):
    dest = tmp_path / "does" / "not" / "exist" / "track.mp3"
    assert save_bytes(dest, b"abc") == dest
    assert dest.read_bytes() == b"abc"


def test_rename_to_track_keeps_the_extension(tmp_path):
    src = tmp_path / "suggested.mp3"
    src.write_bytes(b"x")
    assert rename_to_track(src, "Artist - Title").name == "Artist - Title.mp3"


def test_rename_to_track_is_a_no_op_without_a_title(tmp_path):
    src = tmp_path / "suggested.mp3"
    src.write_bytes(b"x")
    assert rename_to_track(src, None) == src
