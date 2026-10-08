import json
import os
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

EXCLUDED = frozenset({"Weapons", "Party Hits"})
ARCHIVE_TAG = "Archive"
SAMPLER_MARKER = "/rekordbox/Sampler/"

GENRES = frozenset(
    {
        "House",
        "UKG",
        "Dub",
        "Dubstep",
        "Riddim",
        "Halftime",
        "Jungle",
        "DnB",
        "Feels",
        "Beats",
        "Vibes",
    }
)
SUB_PARENT = {
    "Dub Wobblers": "Dub",
    "Dub Sound System": "Dub",
    "Dub Reggae": "Dub",
    "Dub Trippy/Interesting": "Dub",
    "DnB Rollers": "DnB",
    "DnB Liquid": "DnB",
    "DnB Jump Up": "DnB",
    "DnB Dancefloor": "DnB",
}
MODIFIERS = frozenset({"GROOVY", "HEAVY", "VOCALS", "WEIRD", "ORGANIC"})

_BRACKET_FEAT = re.compile(r"[(\[]\s*(?:feat|ft)\.?\s+([^)\]]*)[)\]]")
_ARTIST_SPLIT = re.compile(r"\s*,\s*|\s*&\s*|\s+x\s+|\s+feat\.?\s+|\s+ft\.?\s+")


@dataclass(frozen=True)
class Track:
    content_id: str
    path: str
    artist: str
    artists: frozenset[str]
    group: str
    title: str
    bpm: float
    length: int
    tags: frozenset[str]
    lead: str = ""
    raw_tags: frozenset[str] = frozenset()


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip()


def split_artists(artist_name: str | None) -> list[str]:
    """Normalized artists in credit order, duplicates removed."""
    seen: dict[str, None] = {}
    folded = _BRACKET_FEAT.sub(r" feat \1", _fold(artist_name or ""))
    for part in _ARTIST_SPLIT.split(folded):
        part = part.strip()
        if part:
            seen.setdefault(part)
    return list(seen)


def artist_components(artist_sets: list[frozenset[str]]) -> list[str]:
    """Group label per track: connected components of the graph joining co-credited artists, so
    no artist's tracks land on both sides of a grouped split."""
    parent: dict[str, str] = {}

    def find(a: str) -> str:
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for artists in artist_sets:
        first, *rest = sorted(artists)
        for other in rest:
            parent[find(other)] = find(first)
        find(first)
    roots: dict[str, str] = {}
    for a in sorted(parent):
        roots.setdefault(find(a), a)
    return [roots[find(min(artists))] for artists in artist_sets]


def vocabulary(lanes_json: dict[str, Any]) -> frozenset[str]:
    tags: set[str] = set()
    for playlist in lanes_json["data"]["playlists"]:
        tags.update(playlist.get("contains", []))
    return frozenset(tags - EXCLUDED)


def load_vocabulary(path: Path) -> frozenset[str]:
    return vocabulary(json.loads(path.read_text()))


def load_library(
    db: Any, vocab: frozenset[str], exists: Callable[[str], bool] = os.path.exists
) -> list[Track]:
    """Read-only. Every field is copied here because rows lazy-load and detach on close."""
    tracks: list[Track] = []
    for row in db.get_content():
        if row.rb_local_deleted:
            continue
        path = row.FolderPath or ""
        if not path or SAMPLER_MARKER in path:
            continue
        names = frozenset(row.MyTagNames or [])
        if ARCHIVE_TAG in names or not exists(path):
            continue
        content_id = str(row.ID)
        artists = split_artists(row.ArtistName)
        group = artists[0] if artists else f"__none__{content_id}"
        tracks.append(
            Track(
                content_id=content_id,
                path=path,
                artist=row.ArtistName or "",
                artists=frozenset(artists) or frozenset({group}),
                group=group,
                title=row.Title or "",
                bpm=(row.BPM or 0) / 100,
                length=int(row.Length or 0),
                tags=names & vocab,
                lead=group,
                raw_tags=names,
            )
        )
    labels = artist_components([t.artists for t in tracks])
    return sorted(
        (replace(t, group=g) for t, g in zip(tracks, labels, strict=True)),
        key=lambda t: t.content_id,
    )
