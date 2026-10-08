import importlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import models
from .library import Track

EFFNET_DIM = 1280
N_STYLES = 400
FLUSH_EVERY = 50

Vectors = tuple[np.ndarray, np.ndarray, float]
EmbedFn = Callable[[str], Vectors]


class ClassNameMismatchError(Exception):
    """The cached genre class names differ from the model's."""


@dataclass
class Entry:
    path: str
    length: int
    effnet: np.ndarray | None = None
    genre: np.ndarray | None = None
    voice: float = 0.0
    error: str | None = None


class EmbeddingCache:
    def __init__(self, directory: Path, class_names: list[str]):
        if len(class_names) != N_STYLES:
            raise ClassNameMismatchError(f"expected {N_STYLES} class names, got {len(class_names)}")
        self.directory = directory
        self.class_names = class_names
        self.entries: dict[str, Entry] = {}
        self._load()

    @property
    def npz_path(self) -> Path:
        return self.directory / "embeddings.npz"

    @property
    def index_path(self) -> Path:
        return self.directory / "index.json"

    def _load(self) -> None:
        if not self.index_path.exists():
            return
        index = json.loads(self.index_path.read_text())["tracks"]
        arrays = np.load(self.npz_path) if self.npz_path.exists() else None
        if arrays is not None:
            stored = [str(name) for name in arrays["class_names"]]
            if stored != self.class_names:
                raise ClassNameMismatchError("cached class names differ from the genre model's")
        for content_id, meta in index.items():
            entry = Entry(meta["path"], meta["length"], error=meta.get("error"))
            if entry.error is None:
                if arrays is None:
                    raise FileNotFoundError(f"{self.npz_path} is missing but the index needs it")
                row = meta["row"]
                entry.effnet = arrays["effnet"][row]
                entry.genre = arrays["genre"][row]
                entry.voice = float(arrays["voice"][row])
            self.entries[content_id] = entry

    def is_fresh(self, track: Track, retry_failed: bool) -> bool:
        entry = self.entries.get(track.content_id)
        if entry is None or (entry.path, entry.length) != (track.path, track.length):
            return False
        return entry.error is None or not retry_failed

    def save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        ok = [(cid, e) for cid, e in self.entries.items() if e.error is None]
        index: dict[str, Any] = {}
        for row, (cid, e) in enumerate(ok):
            index[cid] = {"path": e.path, "length": e.length, "row": row}
        for cid, e in self.entries.items():
            if e.error is not None:
                index[cid] = {"path": e.path, "length": e.length, "error": e.error}
        arrays = {
            "ids": np.array([cid for cid, _ in ok], dtype=str),
            "effnet": np.array([e.effnet for _, e in ok], dtype=np.float32).reshape(-1, EFFNET_DIM),
            "genre": np.array([e.genre for _, e in ok], dtype=np.float32).reshape(-1, N_STYLES),
            "voice": np.array([e.voice for _, e in ok], dtype=np.float32),
            "class_names": np.array(self.class_names, dtype=str),
        }
        _atomic(self.npz_path, lambda handle: np.savez(handle, **arrays))
        _atomic(
            self.index_path,
            lambda handle: handle.write(json.dumps({"tracks": index}).encode()),
        )


def _atomic(target: Path, write: Callable[[Any], object]) -> None:
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            write(handle)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@dataclass
class EmbedSummary:
    total: int = 0
    cached: int = 0
    embedded: int = 0
    failed: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)

    def failures_by_extension(self) -> Counter[str]:
        return Counter(Path(path).suffix.lower() or "(none)" for path, _ in self.failures)

    def render(self) -> str:
        lines = [
            f"tracks considered: {self.total}",
            f"  skipped (cached): {self.cached}",
            f"  embedded now:     {self.embedded}",
            f"  failed now:       {self.failed}",
        ]
        for ext, count in sorted(self.failures_by_extension().items()):
            lines.append(f"    {ext}: {count}")
        for path, error in self.failures[:10]:
            lines.append(f"    {path}: {error}")
        if len(self.failures) > 10:
            lines.append(f"    ... {len(self.failures) - 10} more in index.json")
        return "\n".join(lines)


def run_embed(
    tracks: list[Track],
    cache: EmbeddingCache,
    embed: EmbedFn,
    *,
    limit: int | None = None,
    retry_failed: bool = False,
    progress: Callable[[str], None] = print,
) -> EmbedSummary:
    """`limit` caps how many tracks of the library (in id order) are considered."""
    considered = tracks[:limit] if limit is not None else tracks
    summary = EmbedSummary(total=len(considered))
    pending = [t for t in considered if not cache.is_fresh(t, retry_failed)]
    summary.cached = len(considered) - len(pending)
    since_flush = 0
    try:
        for i, track in enumerate(pending, 1):
            try:
                effnet, genre, voice = embed(track.path)
                if effnet.shape != (EFFNET_DIM,) or genre.shape != (N_STYLES,):
                    raise ValueError(f"bad embedding shapes {effnet.shape} {genre.shape}")
                cache.entries[track.content_id] = Entry(
                    track.path, track.length, effnet, genre, float(voice)
                )
                summary.embedded += 1
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                cache.entries[track.content_id] = Entry(track.path, track.length, error=message)
                summary.failed += 1
                summary.failures.append((track.path, message))
            since_flush += 1
            if since_flush >= FLUSH_EVERY:
                cache.save()
                since_flush = 0
                progress(f"  {i}/{len(pending)}")
    finally:
        cache.save()
    return summary


def make_essentia_embedder(model_dir: Path) -> tuple[EmbedFn, list[str]]:
    """Builds the models once. essentia is imported here only; it is an optional extra."""
    models.ensure_models(model_dir)
    try:
        std: Any = importlib.import_module("essentia.standard")
    except ImportError as exc:
        raise RuntimeError(
            "essentia is not installed; run via `deno task rb:tag` (uses the tagging extra)"
        ) from exc

    class_names = json.loads((model_dir / models.GENRE_META.name).read_text())["classes"]
    emb_model = std.TensorflowPredictEffnetDiscogs(
        graphFilename=str(model_dir / models.EFFNET.name), output=models.EFFNET_OUTPUT
    )
    genre_model = std.TensorflowPredict2D(
        graphFilename=str(model_dir / models.GENRE.name),
        input=models.GENRE_INPUT,
        output=models.GENRE_OUTPUT,
    )
    voice_model = std.TensorflowPredict2D(
        graphFilename=str(model_dir / models.VOICE.name),
        input=models.VOICE_INPUT,
        output=models.VOICE_OUTPUT,
    )

    def embed(path: str) -> Vectors:
        audio = std.MonoLoader(filename=path, sampleRate=16000, resampleQuality=4)()
        patches = emb_model(audio)
        return (
            patches.mean(0),
            genre_model(patches).mean(0),
            float(voice_model(patches).mean(0)[1]),
        )

    return embed, class_names
