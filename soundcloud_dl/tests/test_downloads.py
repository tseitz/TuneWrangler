"""Tests for what counts as the downloaded track."""

import pytest

from soundcloud_dl import downloads
from soundcloud_dl.downloads import (
    MIN_TRACK_BYTES,
    discard_if_fragment,
    is_whole_track,
    looks_like_asset,
    looks_like_audio,
    rename_to_track,
    save_bytes,
)


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
        # The gate page's own embedded SoundCloud player, streaming while the gate is
        # worked through. Served as audio/mp4, so only the extension rejects it.
        ("https://cf-hls-media.sndcdn.com/media/0/60/x.m4s", "audio/mp4", "", False),
        ("https://cf-hls-media.sndcdn.com/playlist.m3u8", "application/x-mpegURL", "", False),
        ("https://cdn.x/seg1.ts", "video/mp2t", "", False),
    ],
)
def test_looks_like_audio(url, ct, cd, expected):
    assert looks_like_audio(url, ct, cd) is expected


def test_a_stream_segment_is_not_a_finished_download():
    """A 197K .m4s was saved as the track, reported DOWNLOAD_SUCCESS and recorded done,
    so the track was never retried. A segment is never what a gate hands over."""
    assert looks_like_asset("https://cf-hls-media.sndcdn.com/media/0/60/x.m4s") is True


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


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # The real ToneDen download: extensionless URL, and no content type on a Download.
        ("https://io.toneden.io/523319/c971d7da-9975-4414-9a19-389a583c80ec", False),
        ("LYES & IZZY VADIM - PRESSURE (STONED LEVEL EDIT).wav", False),
        ("track.mp3", False),
        ("fontawesome-webfont.woff2", True),
        ("https://gate.example/assets/app.js", True),
        ("style.CSS", True),
        ("", False),
    ],
)
def test_looks_like_asset(name, expected):
    assert looks_like_asset(name) is expected


@pytest.mark.parametrize(
    ("url", "ct", "status", "expected"),
    [
        # The hole the extension list could not close: SoundCloud serves the same HLS
        # segments as .mp4 and with no extension at all, and an extensionless name is
        # handed .mp3 downstream, so it reaches the library looking like a real track.
        ("https://cf-hls-media.sndcdn.com/media/0/60/a.128.mp4?Policy=x", "audio/mp4", 200, True),
        ("https://cf-hls-media.sndcdn.com/media/0/60/a?Policy=x", "audio/mp4", 200, True),
        # 206 is a fragment whatever it carries, and the CDN cannot spoof it away.
        ("https://cdn.x/track.mp3", "audio/mpeg", 206, False),
        ("https://cdn.x/track.mp3", "audio/mpeg", 200, True),
    ],
)
def test_looks_like_audio_rejects_partial_responses(url, ct, status, expected):
    assert looks_like_audio(url, ct, "", status) is expected


def test_a_short_payload_is_not_a_whole_track():
    """The 197K .m4s that shipped. Extensions are the far end's to choose; length is not."""
    assert is_whole_track("https://cdn.x/a.mp4", 197_000) is False
    assert is_whole_track("https://cdn.x/a.mp4", MIN_TRACK_BYTES) is True


def test_discard_if_fragment_removes_the_file_so_the_track_stays_retryable(tmp_path):
    """A kept fragment means _note_saved fires and resume records done — permanently."""
    frag = tmp_path / "seg.mp4"
    frag.write_bytes(b"x" * 197_000)
    assert discard_if_fragment(frag, "https://cdn.x/seg.mp4") is None
    assert not frag.exists()

    real = tmp_path / "track.wav"
    real.write_bytes(b"x" * MIN_TRACK_BYTES)
    assert discard_if_fragment(real, "https://cdn.x/track.wav") == real
    assert real.exists()


def test_a_wav_is_not_named_mp3():
    """SoundCloud's download endpoint serves the artist's original upload and does not
    always name it. Falling back to .mp3 mislabels a wav for every tool downstream,
    including this repo's own renamer.
    """
    from soundcloud_dl.downloads import audio_extension_for

    assert audio_extension_for(b"RIFF\x00\x00\x00\x00WAVEfmt ") == ".wav"


def test_each_container_is_named_from_its_own_bytes():
    from soundcloud_dl.downloads import audio_extension_for

    assert audio_extension_for(b"fLaC\x00\x00\x00\x22") == ".flac"
    assert audio_extension_for(b"OggS\x00\x02\x00\x00") == ".ogg"
    assert audio_extension_for(b"ID3\x04\x00\x00\x00\x00") == ".mp3"
    assert audio_extension_for(b"\x00\x00\x00\x20ftypM4A ") == ".m4a"
    assert audio_extension_for(b"FORM\x00\x00\x00\x00AIFF") == ".aiff"


def test_a_tagless_mp3_is_still_an_mp3():
    """No ID3 tag, just a bare MPEG frame sync — common after a tag stripper."""
    from soundcloud_dl.downloads import audio_extension_for

    assert audio_extension_for(b"\xff\xfb\x90\x00") == ".mp3"


def test_something_unrecognised_keeps_the_fallback():
    from soundcloud_dl.downloads import audio_extension_for

    assert audio_extension_for(b"not audio at all") == ".mp3"
    assert audio_extension_for(b"", fallback=".bin") == ".bin"
