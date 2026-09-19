"""Tests for the URL helpers behind the SoundCloud action flow."""

import pytest

from soundcloud_dl.soundcloud_actions import artist_url_for, track_path_for

TRACK = "https://soundcloud.com/urboin8/mph-raw-urboin8-bootleg"


@pytest.mark.parametrize(
    "url",
    [
        TRACK,
        TRACK + "?in=danedubz/sets/fire16/",
        TRACK + "?si=abc&utm_source=clipboard",
    ],
)
def test_artist_url_drops_the_track_and_any_query(url):
    assert artist_url_for(url) == "https://soundcloud.com/urboin8"


@pytest.mark.parametrize(
    "url",
    [TRACK, TRACK + "?in=danedubz/sets/fire16/"],
)
def test_track_path_matches_soundclouds_own_link_href(url):
    assert track_path_for(url) == "/urboin8/mph-raw-urboin8-bootleg"


def test_track_path_ignores_a_secret_share_segment():
    """A private-share URL has a third segment; the listing link still uses two."""
    assert track_path_for(TRACK + "/s-nTyZQLX9ZXF") == "/urboin8/mph-raw-urboin8-bootleg"
