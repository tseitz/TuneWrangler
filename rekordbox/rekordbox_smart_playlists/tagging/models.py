import hashlib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

BASE_URL = "https://essentia.upf.edu/models/"


@dataclass(frozen=True)
class ModelFile:
    name: str
    subdir: str
    sha256: str


EFFNET = ModelFile(
    "discogs-effnet-bs64-1.pb",
    "feature-extractors/discogs-effnet/",
    "3ed9af50d5367c0b9c795b294b00e7599e4943244f4cbd376869f3bfc87721b1",
)
GENRE = ModelFile(
    "genre_discogs400-discogs-effnet-1.pb",
    "classification-heads/genre_discogs400/",
    "3885ba078a35249af94b8e5e4247689afac40deca4401a4bc888daf5a579c01c",
)
GENRE_META = ModelFile(
    "genre_discogs400-discogs-effnet-1.json",
    "classification-heads/genre_discogs400/",
    "2d367319d9b782ffa10f69abf0e805b3ac4e10899025e5bdbaceda3919b243e0",
)
VOICE = ModelFile(
    "voice_instrumental-discogs-effnet-1.pb",
    "classification-heads/voice_instrumental/",
    "c8033548e17c292874265db62e82a051247768d10375a35a769e7bf695f16acf",
)
VOICE_META = ModelFile(
    "voice_instrumental-discogs-effnet-1.json",
    "classification-heads/voice_instrumental/",
    "43ac2c3b055dfaed20f6232e0f10636c287f1c5a6e5bd02c5585860031964c8f",
)
ALL_MODELS = (EFFNET, GENRE, GENRE_META, VOICE, VOICE_META)

EFFNET_OUTPUT = "PartitionedCall:1"
GENRE_INPUT = "serving_default_model_Placeholder"
GENRE_OUTPUT = "PartitionedCall:0"
VOICE_INPUT = "model/Placeholder"
VOICE_OUTPUT = "model/Softmax"


class ModelIntegrityError(Exception):
    """A model file does not match its pinned sha256."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path, model: ModelFile) -> None:
    actual = _sha256(path)
    if actual != model.sha256:
        raise ModelIntegrityError(
            f"{path} sha256 {actual} does not match the pinned {model.sha256}"
        )


def ensure_models(directory: Path) -> Path:
    """Download missing model files; every file, cached or fresh, is hash-checked."""
    directory.mkdir(parents=True, exist_ok=True)
    for model in ALL_MODELS:
        target = directory / model.name
        if not target.exists():
            partial = target.with_suffix(target.suffix + ".part")
            urllib.request.urlretrieve(BASE_URL + model.subdir + model.name, partial)
            try:
                verify(partial, model)
            except ModelIntegrityError:
                partial.unlink(missing_ok=True)
                raise
            partial.replace(target)
        else:
            verify(target, model)
    return directory
