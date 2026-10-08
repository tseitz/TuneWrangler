import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

VERSION = 1
DECISIONS = frozenset({"apply", "review", "skip"})
SPLITS = frozenset({"random", "grouped", "product"})


class ManifestError(ValueError):
    pass


@dataclass
class Suggestion:
    tag: str
    score: float
    est_precision: float
    split: str
    decision: str


@dataclass
class Entry:
    content_id: str
    artist: str
    title: str
    bpm: float
    top_styles: list[tuple[str, float]]
    suggestions: list[Suggestion]
    proposed: list[str]
    decision: str


@dataclass
class Manifest:
    created_at: str
    vocabulary_hash: str
    thresholds: dict[str, Any]
    note: str
    entries: list[Entry] = field(default_factory=list)
    version: int = VERSION


def vocabulary_hash(vocab: frozenset[str]) -> str:
    return hashlib.sha256("\n".join(sorted(vocab)).encode()).hexdigest()[:16]


def validate(manifest: Manifest) -> None:
    if manifest.version != VERSION:
        raise ManifestError(f"unsupported manifest version {manifest.version} (expected {VERSION})")
    for name in ("created_at", "vocabulary_hash", "note"):
        if not getattr(manifest, name):
            raise ManifestError(f"manifest field {name!r} is empty")
    seen: set[str] = set()
    for e in manifest.entries:
        if not e.content_id:
            raise ManifestError("entry with empty content_id")
        if e.content_id in seen:
            raise ManifestError(f"duplicate content_id {e.content_id}")
        seen.add(e.content_id)
        if e.decision not in DECISIONS:
            raise ManifestError(
                f"{e.content_id}: decision {e.decision!r} not in {sorted(DECISIONS)}"
            )
        if len(set(e.proposed)) != len(e.proposed):
            raise ManifestError(f"{e.content_id}: duplicate tags in proposed")
        for s in e.suggestions:
            if s.decision not in DECISIONS:
                raise ManifestError(
                    f"{e.content_id}: suggestion {s.tag!r} has decision {s.decision!r}"
                )
            if s.split not in SPLITS:
                raise ManifestError(f"{e.content_id}: suggestion {s.tag!r} has split {s.split!r}")


def write_manifest(manifest: Manifest, path: Path) -> None:
    validate(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(manifest), indent=2) + "\n")


def read_manifest(path: Path) -> Manifest:
    try:
        raw = json.loads(path.read_text())
        entries = [
            Entry(
                content_id=str(e["content_id"]),
                artist=e["artist"],
                title=e["title"],
                bpm=float(e["bpm"]),
                top_styles=[(str(n), float(p)) for n, p in e["top_styles"]],
                suggestions=[Suggestion(**s) for s in e["suggestions"]],
                proposed=list(e["proposed"]),
                decision=e["decision"],
            )
            for e in raw["entries"]
        ]
        manifest = Manifest(
            created_at=raw["created_at"],
            vocabulary_hash=raw["vocabulary_hash"],
            thresholds=raw["thresholds"],
            note=raw["note"],
            entries=entries,
            version=raw["version"],
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ManifestError(f"{path}: malformed manifest ({type(e).__name__}: {e})") from e
    validate(manifest)
    return manifest
