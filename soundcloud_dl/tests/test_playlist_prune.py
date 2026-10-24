"""Which tracks leave the playlist, and the safety rails around the one call that removes them."""

from __future__ import annotations

import contextlib
import json
import unicodedata
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from soundcloud_dl import playlist_prune as prune
from soundcloud_dl.playlist_prune import Proof, PruneError, plan_prune

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

URN = "soundcloud:playlists:1"


def _track(n: int, *, url: str | None = None) -> dict[str, Any]:
    link = url if url is not None else f"https://soundcloud.com/a/t{n}"
    return {"id": n, "urn": f"soundcloud:tracks:{n}", "permalink_url": link, "title": f"T{n}"}


def _proof(name: str) -> Proof:
    return Proof(name=name, manifest="m.json")


# ── plan_prune ─────────────────────────────────────────────────────────────────


def test_a_track_whose_approved_file_is_in_the_collection_is_removed() -> None:
    tracks = [_track(1), _track(2)]
    plan = plan_prune(tracks, {"https://soundcloud.com/a/t1": _proof("A - One.wav")}, set(), {"A - One"})
    assert [t["id"] for t, _ in plan.remove] == [1]
    assert [t["id"] for t in plan.keep] == [2]
    assert [t["id"] for t in plan.unlinked] == [2]


def test_the_match_ignores_the_extension_and_unicode_form() -> None:
    """The rename converts .wav to .aiff, and the drive may hand names back decomposed."""
    name = unicodedata.normalize("NFD", "Dr. Ushūu - Long Goodbye.wav")
    stems = {unicodedata.normalize("NFC", "Dr. Ushūu - Long Goodbye")}
    plan = plan_prune([_track(1)], {"https://soundcloud.com/a/t1": _proof(name)}, set(), stems)
    assert len(plan.remove) == 1


def test_an_approved_track_not_yet_in_the_collection_is_kept() -> None:
    plan = plan_prune([_track(1)], {"https://soundcloud.com/a/t1": _proof("A - One.wav")}, set(), {"Other"})
    assert plan.remove == []
    assert [t["id"] for t in plan.not_in_collection] == [1]


def test_a_query_string_on_either_side_does_not_break_the_link() -> None:
    track = _track(1, url="https://soundcloud.com/a/t1?utm_source=x")
    plan = plan_prune([track], {prune.normalize_url("https://soundcloud.com/a/t1/"): _proof("A.wav")}, set(), {"A"})
    assert len(plan.remove) == 1


def test_a_track_with_no_link_is_kept_by_id() -> None:
    plan = plan_prune([_track(1, url="")], {"": _proof("A.wav")}, set(), {"A"})
    assert [t["id"] for t in plan.keep] == [1]


def test_a_track_listed_twice_keeps_both_entries() -> None:
    plan = plan_prune([_track(1), _track(2), _track(1)], {}, set(), {"A"})
    assert [t["id"] for t in plan.keep] == [1, 2, 1]


# ── linked_names ───────────────────────────────────────────────────────────────


def _manifest(folder: Path, entries: list[dict[str, Any]]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "m.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")


def test_applied_and_duplicate_entries_count_as_proof(tmp_path: Path) -> None:
    def sc(n: int) -> dict[str, str]:
        return {"url": f"https://soundcloud.com/a/t{n}"}

    _manifest(
        tmp_path,
        [
            {"proposed": "One.wav", "decision": "apply", "soundcloud": sc(1), "reasons": []},
            {"proposed": "Two.wav", "decision": "review", "soundcloud": sc(2), "reasons": []},
            {"proposed": "Three.wav", "decision": "skip", "soundcloud": sc(3), "reasons": [prune.DUPLICATE_REASON]},
            {"proposed": "Four.wav", "decision": "apply", "reasons": []},
        ],
    )
    linked, duplicates = prune.linked_names([tmp_path])
    assert set(linked) == {"https://soundcloud.com/a/t1", "https://soundcloud.com/a/t3"}
    assert linked["https://soundcloud.com/a/t3"].name == "Three.wav"
    assert duplicates == {"https://soundcloud.com/a/t3"}


def test_a_duplicate_skip_is_proven_by_the_file_it_matched(tmp_path: Path) -> None:
    dup = {"decision": "skip", "reasons": [prune.DUPLICATE_REASON]}
    _manifest(
        tmp_path,
        [
            # A same-run copy, renamed by the second opinion after the duplicate was found.
            {"src": "One (Remix).wav", "proposed": "A - B x C - One.wav", "decision": "apply", "reasons": []},
            {
                **dup,
                "src": "A - One (Remix).wav",
                "source": "soundcloud",
                "proposed": "A - One.wav",
                "soundcloud": {"url": "https://soundcloud.com/a/t1"},
                "duplicate_of": {"entry": "downloaded/One (Remix).wav"},
            },
            {
                **dup,
                "src": "Two.wav",
                "proposed": "A - Two.wav",
                "soundcloud": {"url": "https://soundcloud.com/a/t2"},
                "duplicate_of": {"file": "A x D - Two.aiff"},
            },
        ],
    )
    linked, _ = prune.linked_names([tmp_path])
    assert linked["https://soundcloud.com/a/t1"].name == "A - B x C - One.wav"
    assert linked["https://soundcloud.com/a/t2"].name == "A x D - Two.aiff"


def test_a_duplicate_of_an_entry_that_was_not_applied_proves_nothing(tmp_path: Path) -> None:
    _manifest(
        tmp_path,
        [
            {"src": "One.wav", "proposed": "A - One.wav", "decision": "review", "reasons": []},
            {
                "src": "One copy.wav",
                "proposed": "A - One.wav",
                "decision": "skip",
                "reasons": [prune.DUPLICATE_REASON],
                "soundcloud": {"url": "https://soundcloud.com/a/t1"},
                "duplicate_of": {"entry": "downloaded/One.wav"},
            },
        ],
    )
    linked, duplicates = prune.linked_names([tmp_path])
    assert "https://soundcloud.com/a/t1" not in linked
    assert duplicates == {"https://soundcloud.com/a/t1"}


def test_an_unreadable_manifest_stops_the_run(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("{half", encoding="utf-8")
    with pytest.raises(PruneError, match=r"bad\.json"):
        prune.linked_names([tmp_path])


# ── collection_stems ───────────────────────────────────────────────────────────


def test_an_unplugged_drive_stops_the_run(tmp_path: Path) -> None:
    with pytest.raises(PruneError, match="plugged in"):
        prune.collection_stems(str(tmp_path / "gone"))


def test_an_empty_collection_stops_the_run(tmp_path: Path) -> None:
    (tmp_path / ".DS_Store").write_text("", encoding="utf-8")
    with pytest.raises(PruneError, match="no files"):
        prune.collection_stems(str(tmp_path))


def test_an_unset_collection_path_stops_the_run() -> None:
    with pytest.raises(PruneError, match="TUNEWRANGLER_DJMUSIC_PATH"):
        prune.collection_stems(None)


# ── check_guards ───────────────────────────────────────────────────────────────


def _plan(remove: int, keep: int) -> prune.PrunePlan:
    return prune.PrunePlan(
        remove=[(_track(i), _proof("x")) for i in range(remove)],
        keep=[_track(100 + i) for i in range(keep)],
    )


def test_emptying_the_playlist_is_allowed() -> None:
    prune.check_guards(_plan(3, 0), allow_bulk=False)


def test_more_than_20_new_removals_need_allow_bulk() -> None:
    with pytest.raises(PruneError, match="--allow-bulk"):
        prune.check_guards(_plan(21, 200), allow_bulk=False)
    prune.check_guards(_plan(21, 200), allow_bulk=True)
    prune.check_guards(_plan(20, 0), allow_bulk=False)


def test_returned_tracks_do_not_count_toward_the_cap() -> None:
    plan = _plan(30, 0)
    plan.returned = [t for t, _ in plan.remove[:10]]
    prune.check_guards(plan, allow_bulk=False)


def test_a_proven_track_pruned_before_is_marked_returned() -> None:
    tracks = [_track(1), _track(2)]
    linked = {prune.normalize_url(t["permalink_url"]): _proof("A - One.wav") for t in tracks}
    plan = prune.plan_prune(tracks, linked, set(), {"A - One"}, frozenset({"2"}))
    assert [t["id"] for t in plan.returned] == [2]


# ── prune_playlist against a fake API ──────────────────────────────────────────


class FakeSoundCloud:
    """The playlist endpoints the prune calls, holding one playlist in memory."""

    def __init__(self, tracks: list[dict[str, Any]], *, track_count: int | None = None) -> None:
        self.tracks = tracks
        self.track_count = len(tracks) if track_count is None else track_count
        self.puts: list[list[int]] = []
        self.put_allowed = True
        self.ignore_put = False
        self.on_put: list[Any] = []
        self.put_status = 200
        #: Page boundaries for /tracks, as lists of indexes into self.tracks.
        self.pages: list[list[int]] | None = None
        self.next_host = "https://api.soundcloud.com"

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/resolve":
            body = {"id": 1, "urn": URN, "track_count": self.track_count, "tracks": self.tracks}
            return httpx.Response(200, json=body)
        if request.url.path == f"/playlists/{URN}/tracks":
            if self.pages is None:
                return httpx.Response(200, json={"collection": self.tracks, "next_href": None})
            n = int(request.url.params.get("page", "0"))
            nxt = f"{self.next_host}/playlists/{URN}/tracks?page={n + 1}" if n + 1 < len(self.pages) else None
            page = [self.tracks[i] for i in self.pages[n]]
            return httpx.Response(200, json={"collection": page, "next_href": nxt})
        if request.method == "PUT" and request.url.path == f"/playlists/{URN}":
            assert self.put_allowed, "the playlist was changed when it should not have been"
            for hook in self.on_put:
                hook()
            if self.put_status != 200:
                return httpx.Response(self.put_status)
            sent = json.loads(request.content)["playlist"]["tracks"]
            ids = [int(t["urn"].rsplit(":", 1)[1]) for t in sent]
            self.puts.append(ids)
            if not self.ignore_put:
                by_id = {t["id"]: t for t in self.tracks}
                self.tracks = [by_id[i] for i in ids]
                self.pages = None
            return httpx.Response(200, json={"tracks": self.tracks})
        return httpx.Response(404)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[FakeSoundCloud, Path]:
    """Tracks 1-3 on the playlist; 1 and 2 are approved and in the Collection."""
    collection = tmp_path / "Collection"
    collection.mkdir()
    for name in ("A - One.aiff", "B - Two.mp3"):
        (collection / name).write_text("", encoding="utf-8")
    manifests = tmp_path / "manifests"
    _manifest(
        manifests,
        [
            {"proposed": "A - One.wav", "decision": "apply", "reasons": [],
             "soundcloud": {"url": "https://soundcloud.com/a/t1"}},
            {"proposed": "B - Two.mp3", "decision": "apply", "reasons": [],
             "soundcloud": {"url": "https://soundcloud.com/a/t2"}},
        ],
    )
    fake = FakeSoundCloud([_track(1), _track(2), _track(3)])

    @contextlib.asynccontextmanager
    async def fake_client(*_a: object, **_kw: object) -> AsyncIterator[httpx.AsyncClient]:
        transport = httpx.MockTransport(fake.handle)
        async with httpx.AsyncClient(transport=transport, base_url="https://api.soundcloud.com") as client:
            yield client

    backups = tmp_path / "backups"
    monkeypatch.setattr(prune, "api_client", fake_client)
    monkeypatch.setattr(prune, "TUNEWRANGLER_DJMUSIC_PATH", str(collection))
    monkeypatch.setattr(prune, "TUNEWRANGLER_SC_PLAYLIST_URL", "https://soundcloud.com/o/sets/p")
    monkeypatch.setattr(prune, "get_manifest_dirs", lambda: [manifests])
    monkeypatch.setattr(prune, "get_playlist_backup_dir", lambda: backups)
    monkeypatch.setattr(prune, "_VERIFY_RETRY_S", 0)
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(prune, "get_log_dir", lambda: logs)
    return fake, backups


def _prune_log(world: tuple[FakeSoundCloud, Path]) -> dict[str, Any]:
    path = world[1].parent / "logs" / "prune_log.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _last_prune(world: tuple[FakeSoundCloud, Path]) -> dict[str, Any]:
    return json.loads((world[1].parent / "logs" / "last_prune.json").read_text(encoding="utf-8"))


async def test_a_successful_prune_logs_what_it_removed(world: tuple[FakeSoundCloud, Path]) -> None:
    await prune.prune_playlist(apply=True, allow_bulk=False)
    assert sorted(_prune_log(world)[URN]) == ["1", "2"]
    assert _prune_log(world)[URN]["1"]["proven_name"] == "A - One.wav"
    last = _last_prune(world)
    assert (last["removed"], last["kept"], last["error"]) == (2, 1, None)


async def test_the_playlist_can_be_emptied(world: tuple[FakeSoundCloud, Path]) -> None:
    fake, _ = world
    fake.tracks = fake.tracks[:2]
    fake.track_count = 2
    await prune.prune_playlist(apply=True, allow_bulk=False)
    assert fake.puts == [[]]


async def test_an_uncertain_update_logs_no_removals_but_records_the_error(
    world: tuple[FakeSoundCloud, Path],
) -> None:
    fake, _ = world
    fake.ignore_put = True
    with pytest.raises(prune.UpdateUncertainError):
        await prune.prune_playlist(apply=True, allow_bulk=False)
    assert _prune_log(world) == {}
    assert "may have changed" in _last_prune(world)["error"]


async def test_tracks_written_back_after_a_prune_are_counted_and_flagged(
    world: tuple[FakeSoundCloud, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, _ = world
    monkeypatch.setattr(prune, "_MASS_RETURN", 2)
    await prune.prune_playlist(apply=True, allow_bulk=False)
    fake.tracks = [_track(1), _track(2), _track(3)]
    fake.track_count = 3
    await prune.prune_playlist(apply=True, allow_bulk=False)
    assert _last_prune(world)["returned"] == 2
    assert _last_prune(world)["mass_return"] is True


async def test_a_corrupt_prune_log_stops_before_any_change(world: tuple[FakeSoundCloud, Path]) -> None:
    fake, _ = world
    fake.put_allowed = False
    (world[1].parent / "logs" / "prune_log.json").write_text("{", encoding="utf-8")
    with pytest.raises(PruneError, match="prune log"):
        await prune.prune_playlist(apply=True, allow_bulk=False)


async def test_a_dry_run_never_changes_the_playlist(world: tuple[FakeSoundCloud, Path]) -> None:
    fake, backups = world
    fake.put_allowed = False
    await prune.prune_playlist(apply=False, allow_bulk=True)
    assert fake.puts == []
    assert not backups.exists()


async def test_apply_backs_up_first_then_sends_the_kept_tracks_as_urns(
    world: tuple[FakeSoundCloud, Path],
) -> None:
    fake, backups = world
    fake.on_put.append(lambda: _assert_backed_up(backups))
    await prune.prune_playlist(apply=True, allow_bulk=True)
    assert fake.puts == [[3]]
    saved = json.loads(next(backups.iterdir()).read_text(encoding="utf-8"))
    assert [t["id"] for t in saved["tracks"]] == [1, 2, 3]


def _assert_backed_up(backups: Path) -> None:
    assert backups.exists() and any(backups.iterdir()), "updated before the backup was written"


async def test_a_short_fetch_stops_before_the_update(world: tuple[FakeSoundCloud, Path]) -> None:
    fake, _ = world
    fake.track_count = 4
    fake.put_allowed = False
    with pytest.raises(PruneError, match="says it has 4"):
        await prune.prune_playlist(apply=True, allow_bulk=True)


async def test_a_failed_backup_stops_before_the_update(
    world: tuple[FakeSoundCloud, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake, _ = world
    fake.put_allowed = False
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setattr(prune, "get_playlist_backup_dir", lambda: blocker / "backups")
    with pytest.raises(PruneError, match="back up"):
        await prune.prune_playlist(apply=True, allow_bulk=True)


async def test_the_bulk_guard_stops_apply_without_allow_bulk(
    world: tuple[FakeSoundCloud, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, _ = world
    fake.put_allowed = False
    monkeypatch.setattr(prune, "_BULK_COUNT", 1)
    with pytest.raises(PruneError, match="--allow-bulk"):
        await prune.prune_playlist(apply=True, allow_bulk=False)


async def test_an_update_that_did_not_land_says_the_playlist_may_have_changed(
    world: tuple[FakeSoundCloud, Path],
) -> None:
    fake, _ = world
    fake.ignore_put = True
    with pytest.raises(prune.UpdateUncertainError, match="expected 1.*may have changed.*backups"):
        await prune.prune_playlist(apply=True, allow_bulk=True)


async def test_a_failed_update_says_the_playlist_may_have_changed(
    world: tuple[FakeSoundCloud, Path],
) -> None:
    fake, _ = world
    fake.put_status = 503
    with pytest.raises(prune.UpdateUncertainError, match="may have changed"):
        await prune.prune_playlist(apply=True, allow_bulk=True)


async def test_every_page_is_read(world: tuple[FakeSoundCloud, Path]) -> None:
    fake, _ = world
    fake.pages = [[0], [1], [2]]
    await prune.prune_playlist(apply=True, allow_bulk=True)
    assert fake.puts == [[3]]


async def test_a_cursor_to_another_host_is_not_followed(world: tuple[FakeSoundCloud, Path]) -> None:
    fake, _ = world
    fake.pages = [[0], [1, 2]]
    fake.next_host = "https://evil.example"
    fake.put_allowed = False
    with pytest.raises(PruneError, match="off-host"):
        await prune.prune_playlist(apply=True, allow_bulk=True)


async def test_a_repeated_page_that_hides_a_missed_one_is_caught(
    world: tuple[FakeSoundCloud, Path],
) -> None:
    fake, _ = world
    fake.pages = [[0], [0], [2]]
    fake.put_allowed = False
    with pytest.raises(PruneError, match="disagrees"):
        await prune.prune_playlist(apply=True, allow_bulk=True)
