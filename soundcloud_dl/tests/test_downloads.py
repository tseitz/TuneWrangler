"""Tests for what counts as the downloaded track."""

import pytest

from soundcloud_dl import downloads
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


def test_save_bytes_falls_back_when_the_destination_is_unwritable(tmp_path, monkeypatch, caplog):
    """The gate is spent by this point — a bad path must not cost us the track."""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr("soundcloud_dl.downloads.get_log_dir", lambda: log_dir)

    blocked = tmp_path / "blocked"
    blocked.write_text("i am a file, not a directory")

    saved = save_bytes(blocked / "sub" / "track.mp3", b"audio")

    assert saved == log_dir / "downloads" / "track.mp3"
    assert saved.read_bytes() == b"audio"
    assert "saved to" in caplog.text


# ── Naming a saved file ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("title", "artist", "expected"),
    [
        ("FTP", "fossils", "fossils - FTP"),
        ("afters ahh tune", "DEVOWR.", "DEVOWR. - afters ahh tune"),
        # Already led by this artist — a second one would read "A - A - Track".
        ("Someone - Track", "Someone", "Someone - Track"),
        # Punctuation and case in the API's name must not defeat that match.
        ("DEVOWR - afters ahh tune", "DEVOWR.", "DEVOWR - afters ahh tune"),
        # The dash belongs to the title, not to an artist — this is the case the old
        # "any ' - ' means it has an artist" rule dropped the artist on.
        (
            "Smack My B  Up - (Lowshade Flip)",
            "Lowshade",
            "Lowshade - Smack My B  Up - (Lowshade Flip)",
        ),
        # A different artist leading the title is still not this uploader.
        ("Prodigy - Smack My Up", "Lowshade", "Lowshade - Prodigy - Smack My Up"),
        ("Track (FREE DOWNLOAD)", "Artist", "Artist - Track"),
        ("Track [Free DL]", "Artist", "Artist - Track"),
        # A slash in either half would otherwise open a directory that does not exist.
        ("A/B: Track", "Some/One", "SomeOne - AB Track"),
        ("Track", None, "Track"),
        (None, "Artist", None),
        ("", "Artist", None),
    ],
)
def test_track_filename(title, artist, expected):
    assert downloads.track_filename(title, artist) == expected


def test_a_very_long_title_is_cut_to_something_the_filesystem_accepts():
    # Over NAME_MAX the rename raises ENAMETOOLONG, and by then the gate is already spent.
    name = downloads.track_filename("A" * 400, "B" * 100)
    assert name is not None
    assert len(name.encode()) <= 200


def test_length_is_counted_in_bytes_not_characters():
    name = downloads.track_filename("🔥" * 200, "DJ")
    assert name is not None
    assert len(name.encode()) <= 200


@pytest.mark.parametrize("title", [".", "..", "...", "-", "   "])
def test_a_title_that_names_no_file_is_refused(title):
    assert downloads.track_filename(title, None) is None


def test_a_leading_dash_is_dropped():
    # These filenames are handed to ffmpeg and the Deno side later; a leading dash there
    # reads as a flag.
    assert downloads.track_filename("-rf", "artist") == "artist - -rf"
    assert downloads.track_filename("-rf", None) == "rf"
