"""What SoundCloud said about each downloaded track, keyed by the filename it was saved under.

The filename keeps only the uploader and the title. The rename flow on the Deno side reads
this file to learn who SoundCloud credits, which the name alone cannot say: a label's
upload is named after the label, not the artist.
"""

from __future__ import annotations

import json
import logging
import time
import unicodedata
from typing import TYPE_CHECKING

from soundcloud_dl.config import get_log_dir

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("soundcloud_dl.track_index")


def get_track_index_file() -> Path:
    """Path of the index; read by src/core/soundcloudFacts.ts at the same repo-relative spot."""
    return get_log_dir() / "track_index.json"


def _read() -> dict[str, object]:
    path = get_track_index_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Starting over from {} would write away every entry in it, so keep the bad file.
        aside = path.with_name(f"track_index.corrupt-{int(time.time())}.json")
        path.rename(aside)
        logger.warning("Track index was unreadable — moved to %s and starting a new one", aside)
        return {}
    return data if isinstance(data, dict) else {}


def record_track(  # noqa: PLR0913
    name: str,
    *,
    url: str,
    title: str | None,
    uploader: str | None,
    metadata_artist: str | None,
    label_name: str | None,
) -> None:
    """Remember what SoundCloud reported for the file that will be named `name`.

    Never raises: losing an entry only costs a review flag in the rename manifest, while
    raising here would fail a track whose gate may already have been paid for.
    """
    try:
        path = get_track_index_file()
        data = _read()
        data[unicodedata.normalize("NFC", name)] = {
            "url": url,
            "title": title,
            "uploader": uploader,
            "metadata_artist": metadata_artist,
            "label_name": label_name,
        }
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except (OSError, TypeError) as exc:
        logger.warning("Could not record %r in the track index: %s", name, exc)
