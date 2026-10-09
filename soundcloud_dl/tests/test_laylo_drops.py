"""Laylo drop store, Dropbox fetch and track matching."""

import io
import os
import time
import zipfile
from pathlib import Path

import httpx
import pytest

from soundcloud_dl import config, laylo_drops
from soundcloud_dl.laylo_drops import DropRecord, LayloDropStoreError, LayloFetchError

SPAG_LINK = "https://www.dropbox.com/scl/fo/abc123/AKey-xyz?rlkey=k3y&dl=0"
SLUG = "spagheddy-flips"


@pytest.fixture
def save_root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "dl"
    monkeypatch.setattr(config, "DOWNLOAD_DIR", root)
    monkeypatch.setattr("soundcloud_dl.downloads.get_log_dir", lambda: tmp_path / "logs")
    return root


def _zip(members: dict[str, bytes], compression: int = zipfile.ZIP_STORED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)


def _serve(body: bytes, headers: dict[str, str] | None = None, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body, headers=headers or {})

    return handler


def _tmp_dir_is_empty() -> bool:
    tmp = config.get_laylo_tmp_dir()
    return not tmp.exists() or not any(tmp.iterdir())


# ── drop_key / dropbox_direct ──────────────────────────────────────────────────


def test_drop_key_ignores_case_scheme_www_query_and_trailing_slash() -> None:
    expected = "laylo.com/spagheddy/flips"
    assert laylo_drops.drop_key("https://laylo.com/spagheddy/flips") == expected
    assert laylo_drops.drop_key("http://www.Laylo.com/SPAGheddy/Flips/?utm=1#x") == expected


def test_drop_key_keeps_distinct_drops_apart() -> None:
    a = laylo_drops.drop_key("https://laylo.com/secretstvsh/5QleDw")
    b = laylo_drops.drop_key("https://laylo.com/flozone/rlVDtY")
    assert a != b


def test_dropbox_direct_sets_dl_and_keeps_rlkey() -> None:
    direct = laylo_drops.dropbox_direct(SPAG_LINK)
    assert direct == "https://www.dropbox.com/scl/fo/abc123/AKey-xyz?rlkey=k3y&dl=1"


def test_dropbox_direct_adds_dl_when_missing() -> None:
    direct = laylo_drops.dropbox_direct("https://dropbox.com/scl/fi/abc/f.wav?rlkey=k")
    assert direct == "https://dropbox.com/scl/fi/abc/f.wav?rlkey=k&dl=1"


@pytest.mark.parametrize(
    "url",
    [
        "https://drive.google.com/file/d/abc",
        "https://dropbox.com.evil.example/scl/fo/abc/k?dl=0",
        "https://www.dropbox.com/s/abc/old.zip?dl=0",
        "http://www.dropbox.com/scl/fo/abc/k?dl=0",
        "https://www.dropbox.com:8443/scl/fo/abc/k?dl=0",
        "https://user:pw@www.dropbox.com/scl/fo/abc/k?dl=0",
        "https://www.dropbox.com@evil.example/scl/fo/abc/k?dl=0",
        "https://www.dropbox.com/scl/fo/../../l/abc",
        "https://www.dropbox.com/scl/fo/%2e%2e/%2E%2e/l/abc",
        "https://www.dropbox.com/scl/fo/a/./b?dl=0",
        "https://www.dropbox.com/scl/fo//abc/k?dl=0",
        "https://www.dropbox.com/scl/fo/abc%2f..%2f..%2fl/x",
    ],
)
def test_dropbox_direct_rejects_everything_else(url) -> None:
    assert laylo_drops.dropbox_direct(url) is None


# ── Drop store ─────────────────────────────────────────────────────────────────


def test_known_senders_collects_every_non_empty_sender() -> None:
    laylo_drops.save("one", DropRecord(sender="2134748783"))
    laylo_drops.save("two", DropRecord(gmail_id="g"))
    laylo_drops.save("three", DropRecord(sender="5551234567"))
    assert laylo_drops.known_senders() == {"2134748783", "5551234567"}


def test_a_record_stored_before_senders_existed_still_loads() -> None:
    path = config.get_laylo_drops_file()
    path.write_text('{"k": {"submitted_at": 5.0, "gmail_id": "g"}}', encoding="utf-8")
    assert laylo_drops.load("k") == DropRecord(submitted_at=5.0, gmail_id="g")
    assert laylo_drops.known_senders() == set()


def test_a_saved_record_round_trips() -> None:
    record = DropRecord(submitted_at=100.0, link=SPAG_LINK, gmail_id="g1")
    laylo_drops.save("laylo.com/a/b", record)
    assert laylo_drops.load("laylo.com/a/b") == record
    assert laylo_drops.load("laylo.com/a/other") is None


def test_saving_keeps_the_other_records() -> None:
    laylo_drops.save("one", DropRecord(submitted_at=1.0))
    laylo_drops.save("two", DropRecord(submitted_at=2.0))
    laylo_drops.save("one", DropRecord(submitted_at=3.0))
    assert laylo_drops.load("one") == DropRecord(submitted_at=3.0)
    assert laylo_drops.load("two") == DropRecord(submitted_at=2.0)


def test_forget_removes_one_record_and_reports_whether_it_existed() -> None:
    laylo_drops.save("one", DropRecord(submitted_at=1.0))
    assert laylo_drops.forget("one") is True
    assert laylo_drops.forget("one") is False
    assert laylo_drops.load("one") is None


def test_used_gmail_ids_collects_every_record() -> None:
    laylo_drops.save("one", DropRecord(gmail_id="g1"))
    laylo_drops.save("two", DropRecord(submitted_at=2.0))
    laylo_drops.save("three", DropRecord(gmail_id="g3"))
    assert laylo_drops.used_gmail_ids() == {"g1", "g3"}


def test_unknown_fields_in_a_stored_record_are_ignored() -> None:
    path = config.get_laylo_drops_file()
    path.write_text('{"k": {"submitted_at": 5.0, "future_field": 1}}', encoding="utf-8")
    assert laylo_drops.load("k") == DropRecord(submitted_at=5.0)


def test_an_unreadable_store_raises_instead_of_starting_over() -> None:
    path = config.get_laylo_drops_file()
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(LayloDropStoreError):
        laylo_drops.load("k")
    with pytest.raises(LayloDropStoreError):
        laylo_drops.save("k", DropRecord())
    assert path.read_text(encoding="utf-8") == "{not json"


# ── fetch ──────────────────────────────────────────────────────────────────────


async def test_a_zip_is_extracted_to_the_laylo_folder(save_root) -> None:
    body = _zip({"EPTIC - OCTANE (SPAG FLIP).wav": b"a", "sub/B - C.wav": b"b"})
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=body, headers={"content-type": "application/zip"})

    async with _client(handler) as client:
        folder = await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert folder == save_root / "laylo" / SLUG
    assert seen == ["https://www.dropbox.com/scl/fo/abc123/AKey-xyz?rlkey=k3y&dl=1"]
    assert (folder / "EPTIC - OCTANE (SPAG FLIP).wav").read_bytes() == b"a"
    assert (folder / "sub" / "B - C.wav").read_bytes() == b"b"
    assert sorted(p.name for p in (save_root / "laylo").iterdir()) == [SLUG]
    assert _tmp_dir_is_empty()


async def test_zip_members_that_escape_the_folder_or_are_mac_litter_are_skipped(
    save_root,
) -> None:
    body = _zip(
        {
            "../escaped.wav": b"x",
            "/abs-escaped.wav": b"x",
            "sub/../../escaped2.wav": b"x",
            "__MACOSX/._track.wav": b"x",
            "track.wav": b"ok",
        }
    )
    async with _client(_serve(body)) as client:
        folder = await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert [p.name for p in folder.rglob("*")] == ["track.wav"]
    assert not (save_root / "laylo" / "escaped.wav").exists()
    assert not (save_root / "escaped.wav").exists()
    assert not (save_root / "laylo" / "escaped2.wav").exists()


async def test_an_html_body_is_rejected_and_nothing_is_cached(save_root) -> None:
    body = b"<html><body>This link has expired</body></html>"
    async with _client(_serve(body, {"content-type": "text/html"})) as client:
        with pytest.raises(LayloFetchError):
            await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert not (save_root / "laylo" / SLUG).exists()
    assert list((save_root / "laylo").iterdir()) == []
    assert _tmp_dir_is_empty()


async def test_a_truncated_body_is_rejected(save_root) -> None:
    body = _zip({"a.wav": b"a"})
    headers = {"content-length": str(len(body) + 10)}
    async with _client(_serve(body, headers)) as client:
        with pytest.raises(LayloFetchError, match="truncated"):
            await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert list((save_root / "laylo").iterdir()) == []
    assert _tmp_dir_is_empty()


async def test_pk_bytes_that_are_not_a_zip_are_rejected(save_root) -> None:
    async with _client(_serve(b"PK not really a zip")) as client:
        with pytest.raises(LayloFetchError):
            await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert list((save_root / "laylo").iterdir()) == []
    assert _tmp_dir_is_empty()


async def test_an_error_status_is_a_fetch_error(save_root) -> None:
    async with _client(_serve(b"nope", status=404)) as client:
        with pytest.raises(LayloFetchError, match="404"):
            await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)


async def test_a_transport_failure_is_a_fetch_error(save_root) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        msg = "down"
        raise httpx.ConnectError(msg, request=request)

    async with _client(boom) as client:
        with pytest.raises(LayloFetchError):
            await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)


async def test_a_non_dropbox_link_makes_no_request(save_root) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("no request expected")

    async with _client(handler) as client:
        with pytest.raises(LayloFetchError):
            await laylo_drops.fetch("https://wetransfer.com/downloads/x", SLUG, client=client)


async def test_a_single_audio_file_is_kept_under_its_own_name(save_root) -> None:
    headers = {
        "content-type": "audio/wav",
        "content-disposition": 'attachment; filename="EPTIC - OCTANE (SPAG FLIP).wav"',
    }
    async with _client(_serve(b"RIFFxxxxWAVEdata", headers)) as client:
        folder = await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert [p.name for p in folder.iterdir()] == ["EPTIC - OCTANE (SPAG FLIP).wav"]
    assert _tmp_dir_is_empty()


async def test_a_single_audio_file_without_a_name_gets_an_extension_from_its_bytes(
    save_root,
) -> None:
    async with _client(_serve(b"RIFFxxxxWAVEdata", {"content-type": "audio/wav"})) as client:
        folder = await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert [p.name for p in folder.iterdir()] == [f"{SLUG}.wav"]


async def test_an_existing_folder_is_reused_without_a_request(save_root) -> None:
    existing = save_root / "laylo" / SLUG
    existing.mkdir(parents=True)
    (existing / "keep.wav").write_bytes(b"mine")

    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("no request expected")

    async with _client(handler) as client:
        folder = await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert folder == existing
    assert (existing / "keep.wav").read_bytes() == b"mine"


async def test_the_slug_cannot_leave_the_laylo_folder(save_root) -> None:
    async with _client(_serve(_zip({"a.wav": b"a"}))) as client:
        folder = await laylo_drops.fetch(SPAG_LINK, "../../evil", client=client)

    assert folder.parent == save_root / "laylo"


async def test_an_unusable_download_dir_falls_back_to_the_logs_folder(
    tmp_path, monkeypatch
) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("file", encoding="utf-8")
    monkeypatch.setattr(config, "DOWNLOAD_DIR", blocker / "dl")
    monkeypatch.setattr("soundcloud_dl.downloads.get_log_dir", lambda: tmp_path / "logs")

    async with _client(_serve(_zip({"a.wav": b"a"}))) as client:
        folder = await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert folder == tmp_path / "logs" / "downloads" / "laylo" / SLUG
    assert laylo_drops.save_dir() == tmp_path / "logs" / "downloads"


def test_save_dir_is_the_download_dir_when_it_works(save_root) -> None:
    assert laylo_drops.save_dir() == save_root
    assert save_root.is_dir()


# ── match_track ────────────────────────────────────────────────────────────────


def _touch(folder: Path, *names: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"x")


def test_match_track_finds_the_one_file_with_the_full_title(tmp_path) -> None:
    _touch(tmp_path, "EPTIC - OCTANE (SPAG FLIP).wav", "SUBTRONICS - EYES (SPAG FLIP).wav")
    hit = laylo_drops.match_track(tmp_path, "EPTIC - OCTANE (SPAG FLIP)")
    assert hit == tmp_path / "EPTIC - OCTANE (SPAG FLIP).wav"


def test_match_track_ignores_case_and_punctuation(tmp_path) -> None:
    _touch(tmp_path, "eptic - octane (spag flip).WAV")
    assert laylo_drops.match_track(tmp_path, "EPTIC - OCTANE (SPAG FLIP)!") is not None


def test_match_track_accepts_a_file_named_for_the_part_after_the_dash(tmp_path) -> None:
    _touch(tmp_path, "OCTANE (SPAG FLIP).wav", "OTHER (SPAG FLIP).wav")
    hit = laylo_drops.match_track(tmp_path, "EPTIC - OCTANE (SPAG FLIP)")
    assert hit == tmp_path / "OCTANE (SPAG FLIP).wav"


def test_match_track_finds_a_file_inside_a_subfolder(tmp_path) -> None:
    _touch(tmp_path / "SPAG FLIPS", "EPTIC - OCTANE (SPAG FLIP).mp3")
    assert laylo_drops.match_track(tmp_path, "EPTIC - OCTANE (SPAG FLIP)") is not None


def test_match_track_is_none_when_nothing_matches(tmp_path) -> None:
    _touch(tmp_path, "SUBTRONICS - EYES (SPAG FLIP).wav", "cover.jpg")
    assert laylo_drops.match_track(tmp_path, "EPTIC - OCTANE (SPAG FLIP)") is None


def test_match_track_is_none_when_ambiguous(tmp_path) -> None:
    _touch(tmp_path / "a", "EPTIC - OCTANE (SPAG FLIP).wav")
    _touch(tmp_path / "b", "EPTIC - OCTANE (SPAG FLIP).mp3")
    assert laylo_drops.match_track(tmp_path, "EPTIC - OCTANE (SPAG FLIP)") is None


def test_match_track_ignores_non_audio_and_apple_double_files(tmp_path) -> None:
    _touch(tmp_path, "EPTIC - OCTANE (SPAG FLIP).txt", "._EPTIC - OCTANE (SPAG FLIP).wav")
    assert laylo_drops.match_track(tmp_path, "EPTIC - OCTANE (SPAG FLIP)") is None


# ── place_match ────────────────────────────────────────────────────────────────


def test_place_match_copies_under_the_track_title_and_keeps_the_source(tmp_path) -> None:
    src = tmp_path / "folder" / "EPTIC - OCTANE (SPAG FLIP).wav"
    _touch(src.parent, src.name)
    dest = laylo_drops.place_match(src, tmp_path / "dl", "EPTIC - OCTANE (SPAG FLIP)")

    assert dest == tmp_path / "dl" / "EPTIC - OCTANE (SPAG FLIP).wav"
    assert dest.read_bytes() == b"x"
    assert src.exists()


def test_place_match_never_overwrites(tmp_path) -> None:
    src = tmp_path / "src.wav"
    src.write_bytes(b"new")
    dest_dir = tmp_path / "dl"
    dest_dir.mkdir()
    (dest_dir / "Title.wav").write_bytes(b"old")

    assert laylo_drops.place_match(src, dest_dir, "Title") is None
    assert (dest_dir / "Title.wav").read_bytes() == b"old"


def test_a_failed_copy_leaves_no_partial_file(tmp_path) -> None:
    dest_dir = tmp_path / "dl"
    with pytest.raises(FileNotFoundError):
        laylo_drops.place_match(tmp_path / "missing.wav", dest_dir, "Title")
    assert list(dest_dir.iterdir()) == []


def test_place_match_rejects_a_title_with_a_path_separator(tmp_path) -> None:
    src = tmp_path / "src.wav"
    src.write_bytes(b"x")
    with pytest.raises(ValueError, match="plain filename"):
        laylo_drops.place_match(src, tmp_path / "dl", "../Title")


def test_octet_stream_audio_is_accepted_by_its_bytes():
    assert laylo_drops._classify(b"ID3\x04\x00rest", "application/octet-stream") == "audio"


def test_octet_stream_html_is_rejected():
    with pytest.raises(laylo_drops.LayloFetchError):
        laylo_drops._classify(b"<!doctype html>", "application/octet-stream")


# ── hardening ──────────────────────────────────────────────────────────────────

DROPBOX = "https://www.dropbox.com/scl/fo/abc123/AKey-xyz?rlkey=k3y&dl=1"


def _redirecting(locations: list[str], final: bytes):
    hops = iter(locations)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        nxt = next(hops, None)
        if nxt is None:
            return httpx.Response(200, content=final, headers={"content-type": "application/zip"})
        return httpx.Response(302, headers={"location": nxt})

    return handler, seen


async def test_redirects_to_dropbox_hosts_are_followed(save_root) -> None:
    handler, seen = _redirecting(
        ["https://uc123.dl.dropboxusercontent.com/cd/0/get/x"], _zip({"a.wav": b"a"})
    )
    async with _client(handler) as client:
        folder = await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert seen[-1] == "https://uc123.dl.dropboxusercontent.com/cd/0/get/x"
    assert (folder / "a.wav").read_bytes() == b"a"


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example/x.zip",
        "http://www.dropbox.com/scl/fo/abc/k",
        "https://dropbox.com.evil.example/x",
        "https://evildropboxusercontent.com/x",
        "https://127.0.0.1/x",
        "file:///etc/passwd",
    ],
)
async def test_a_redirect_off_the_allowlist_is_a_fetch_error(save_root, target) -> None:
    handler, seen = _redirecting([target], _zip({"a.wav": b"a"}))
    async with _client(handler) as client:
        with pytest.raises(LayloFetchError, match="redirect"):
            await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert len(seen) == 1
    assert _tmp_dir_is_empty()


async def test_too_many_redirects_is_a_fetch_error(save_root) -> None:
    hop = "https://www.dropbox.com/scl/fo/abc123/AKey-xyz?dl=1"
    handler, seen = _redirecting([hop] * 6, _zip({"a.wav": b"a"}))
    async with _client(handler) as client:
        with pytest.raises(LayloFetchError, match="redirects"):
            await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert len(seen) == laylo_drops._MAX_REDIRECTS + 1


async def test_five_redirects_are_allowed(save_root) -> None:
    hop = "https://www.dropbox.com/scl/fo/abc123/AKey-xyz?dl=1"
    handler, _ = _redirecting([hop] * 5, _zip({"a.wav": b"a"}))
    async with _client(handler) as client:
        folder = await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)
    assert (folder / "a.wav").exists()


async def test_a_client_that_follows_redirects_itself_cannot_skip_the_check(save_root) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "evil.example":
            pytest.fail("the evil host must never be requested")
        return httpx.Response(302, headers={"location": "https://evil.example/x"})

    async with _client(handler) as client:
        with pytest.raises(LayloFetchError):
            await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)


async def test_a_response_from_a_foreign_host_is_rejected(save_root) -> None:
    resp = httpx.Response(
        200,
        content=_zip({"a.wav": b"a"}),
        request=httpx.Request("GET", "https://evil.example/x"),
    )
    with pytest.raises(LayloFetchError, match="not Dropbox"):
        await laylo_drops._read_body(resp, io.BytesIO())


async def test_a_download_that_declares_too_much_is_rejected_up_front(
    save_root, monkeypatch
) -> None:
    monkeypatch.setattr(laylo_drops, "_MAX_DOWNLOAD_BYTES", 10)
    body = _zip({"a.wav": b"a"})
    async with _client(_serve(body, {"content-length": str(len(body))})) as client:
        with pytest.raises(LayloFetchError, match="declares"):
            await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert _tmp_dir_is_empty()


async def test_a_download_that_streams_past_the_cap_is_aborted(save_root, monkeypatch) -> None:
    monkeypatch.setattr(laylo_drops, "_MAX_DOWNLOAD_BYTES", 10)
    body = _zip({"a.wav": b"a"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(body))

    async with _client(handler) as client:
        with pytest.raises(LayloFetchError, match="passed the"):
            await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert list((save_root / "laylo").iterdir()) == []
    assert _tmp_dir_is_empty()


@pytest.mark.parametrize(
    ("cap", "value", "members"),
    [
        ("_MAX_ZIP_MEMBERS", 2, {"a.wav": b"a", "b.wav": b"b", "c.wav": b"c"}),
        ("_MAX_ZIP_TOTAL_BYTES", 5, {"a.wav": b"abcdef"}),
        ("_MAX_ZIP_RATIO", 5, {"a.wav": b"\0" * 5000}),
    ],
)
async def test_a_zip_over_a_limit_is_rejected_before_anything_is_written(
    save_root, monkeypatch, cap, value, members
) -> None:
    monkeypatch.setattr(laylo_drops, cap, value)
    body = _zip(members, zipfile.ZIP_DEFLATED)
    async with _client(_serve(body)) as client:
        with pytest.raises(LayloFetchError):
            await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert list((save_root / "laylo").iterdir()) == []
    assert _tmp_dir_is_empty()


def test_the_running_byte_count_aborts_a_member_that_lies_about_its_size(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(laylo_drops, "_MAX_ZIP_TOTAL_BYTES", 100)
    monkeypatch.setattr(laylo_drops, "_check_zip_limits", lambda infos: None)
    zip_path = tmp_path / "x.zip"
    zip_path.write_bytes(_zip({"a.wav": os.urandom(500)}))
    staging = tmp_path / "staging"
    staging.mkdir()
    with pytest.raises(LayloFetchError, match="unpacked past"):
        laylo_drops._extract_zip(zip_path, staging)


async def test_an_unwritable_member_name_is_skipped_not_fatal(save_root) -> None:
    body = _zip({"x" * 300 + ".wav": b"long", "track.wav": b"ok"})
    async with _client(_serve(body)) as client:
        folder = await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert [p.name for p in folder.rglob("*")] == ["track.wav"]


async def test_a_zip_of_only_unwritable_members_is_a_fetch_error(save_root) -> None:
    async with _client(_serve(_zip({"x" * 300 + ".wav": b"long"}))) as client:
        with pytest.raises(LayloFetchError, match="no files"):
            await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert list((save_root / "laylo").iterdir()) == []


@pytest.mark.parametrize("title", ["bad\0title", "x" * 300])
def test_place_match_returns_none_for_an_unusable_title(tmp_path, title) -> None:
    src = tmp_path / "src.wav"
    src.write_bytes(b"x")
    dest_dir = tmp_path / "dl"
    assert laylo_drops.place_match(src, dest_dir, title) is None
    assert list(dest_dir.iterdir()) == []


def _age(path: Path, seconds: float) -> None:
    old = time.time() - seconds
    os.utime(path, (old, old))


async def test_fetch_clears_stale_debris_but_not_fresh_work(save_root) -> None:
    tmp = config.get_laylo_tmp_dir()
    tmp.mkdir(parents=True)
    stale_part, fresh_part = tmp / "old.part", tmp / "new.part"
    stale_part.write_bytes(b"x")
    fresh_part.write_bytes(b"x")
    laylo = save_root / "laylo"
    stale_dir, fresh_dir, visible = laylo / ".old-abc", laylo / ".new-abc", laylo / "keep"
    for d in (stale_dir, fresh_dir, visible):
        d.mkdir(parents=True)
        (d / "f.wav").write_bytes(b"x")
    _age(stale_part, 7200)
    _age(stale_dir, 7200)
    _age(visible, 7200)

    async with _client(_serve(_zip({"a.wav": b"a"}))) as client:
        await laylo_drops.fetch(SPAG_LINK, SLUG, client=client)

    assert not stale_part.exists()
    assert not stale_dir.exists()
    assert fresh_part.exists()
    assert fresh_dir.exists()
    assert visible.exists()
