"""Phase 1 entrypoint: extract track URLs from SoundCloud playlist and log results."""

import logging

from soundcloud_dl.config import (
    TUNEWRANGLER_SC_PLAYLIST_URL,
    validate_phase1_config,
)
from soundcloud_dl.logger import setup_logging
from soundcloud_dl.playlist import extract_track_urls

logger = logging.getLogger("soundcloud_dl.main")


def main() -> None:
    """Run Phase 1: load config, setup logging, extract playlist tracks via API, log summary."""
    setup_logging()
    validate_phase1_config()
    if not TUNEWRANGLER_SC_PLAYLIST_URL:
        msg = "TUNEWRANGLER_SC_PLAYLIST_URL is required"
        raise RuntimeError(msg)
    playlist_url = TUNEWRANGLER_SC_PLAYLIST_URL.strip()
    logger.info("Phase 1: extracting track URLs from playlist: %s", playlist_url)

    tracks = extract_track_urls(playlist_url)

    logger.info("Playlist URL: %s", playlist_url)
    logger.info("Number of tracks found: %d", len(tracks))
    for i, t in enumerate(tracks, 1):
        if t.title:
            logger.info("  %d. %s | %s", i, t.title, t.url)
        else:
            logger.info("  %d. %s", i, t.url)


if __name__ == "__main__":
    main()
