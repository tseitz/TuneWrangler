import json
from pathlib import Path

import pytest

from rekordbox_smart_playlists.audit import (
    UNIFORM_CONTEXTS,
    _context_files,
    _signature,
    main,
    resolve_context,
)


def _write(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def _uniform_context(parent: str) -> dict:
    """A minimal context whose resolved shape is identical across parents."""
    return {
        "data": [
            {
                "parent": parent,
                "mainConditions": [parent],
                "negativeConditions": ["Archive"],
                "playlists": [{"name": "All", "operator": 1, "contains": []}],
            }
        ]
    }


def _write_uniform_dir(directory: Path, names) -> None:
    for name in names:
        _write(directory / f"{name}.json", _uniform_context(name))


def test_top_level_conditions_and_base(tmp_path: Path):
    # base file (dict-style) with two genre playlists
    _write(
        tmp_path / "_genres.json",
        {
            "data": {
                "playlists": [
                    {"name": "Dub", "operator": 1, "contains": ["Dub"]},
                    {"name": "House", "operator": 1, "contains": ["House"]},
                ]
            }
        },
    )
    # a Genre lens that injects the base
    _write(
        tmp_path / "lens-genre.json",
        {"data": [{"mainConditions": [], "base": "_genres.json", "playlists": []}]},
    )
    # context linking to the Genre folder + a direct "All"
    _write(
        tmp_path / "nighttime.json",
        {
            "data": [
                {
                    "parent": "Nighttime",
                    "mainConditions": ["Nighttime"],
                    "negativeConditions": ["Archive"],
                    "playlists": [
                        {"name": "All", "operator": 1, "contains": []},
                        {
                            "name": "Genre",
                            "operator": 1,
                            "playlistType": "folder",
                            "link": "lens-genre.json",
                        },
                    ],
                }
            ]
        },
    )

    result = resolve_context(tmp_path / "nighttime.json", tmp_path)

    assert result.errors == []
    by_name = {leaf.name: leaf for leaf in result.leaves}
    # 1 "All" + 2 injected genres
    assert set(by_name) == {"All", "Dub", "House"}
    # "All" lives directly under the context, carries only the context tag
    assert by_name["All"].path == ("Nighttime",)
    assert by_name["All"].conditions == frozenset({"Nighttime"})
    assert by_name["All"].negatives == frozenset({"Archive"})
    # genres live under Nighttime/Genre and AND the context tag
    assert by_name["Dub"].path == ("Nighttime", "Genre")
    assert by_name["Dub"].conditions == frozenset({"Nighttime", "Dub"})


def test_mainconditions_accumulate_across_nested_links(tmp_path: Path):
    _write(
        tmp_path / "_genres.json",
        {"data": {"playlists": [{"name": "Dub", "operator": 1, "contains": ["Dub"]}]}},
    )
    _write(
        tmp_path / "lens-genre.json",
        {"data": [{"mainConditions": [], "base": "_genres.json", "playlists": []}]},
    )
    # caliber sub-tree that adds "My Set" and re-links the Genre lens
    _write(
        tmp_path / "caliber-my-set.json",
        {
            "data": [
                {
                    "mainConditions": ["My Set"],
                    "playlists": [
                        {
                            "name": "Genre",
                            "operator": 1,
                            "playlistType": "folder",
                            "link": "lens-genre.json",
                        },
                    ],
                }
            ]
        },
    )
    _write(
        tmp_path / "nighttime.json",
        {
            "data": [
                {
                    "parent": "Nighttime",
                    "mainConditions": ["Nighttime"],
                    "negativeConditions": ["Archive"],
                    "playlists": [
                        {
                            "name": "My Set",
                            "operator": 1,
                            "playlistType": "folder",
                            "link": "caliber-my-set.json",
                        },
                    ],
                }
            ]
        },
    )

    result = resolve_context(tmp_path / "nighttime.json", tmp_path)

    assert result.errors == []
    assert len(result.leaves) == 1
    dub = result.leaves[0]
    assert dub.name == "Dub"
    assert dub.path == ("Nighttime", "My Set", "Genre")
    assert dub.conditions == frozenset({"Nighttime", "My Set", "Dub"})


def test_broken_link_is_reported_not_raised(tmp_path: Path):
    _write(
        tmp_path / "nighttime.json",
        {
            "data": [
                {
                    "parent": "Nighttime",
                    "mainConditions": ["Nighttime"],
                    "playlists": [
                        {
                            "name": "Genre",
                            "operator": 1,
                            "playlistType": "folder",
                            "link": "does-not-exist.json",
                        },
                    ],
                }
            ]
        },
    )

    result = resolve_context(tmp_path / "nighttime.json", tmp_path)

    assert result.leaves == []
    assert len(result.errors) == 1
    assert "does-not-exist.json" in result.errors[0]


# --- bad-file tolerance ----------------------------------------------------


def test_malformed_context_is_reported_not_raised(tmp_path: Path):
    (tmp_path / "nighttime.json").write_text("{ this is not json", encoding="utf-8")

    result = resolve_context(tmp_path / "nighttime.json", tmp_path)

    assert result.leaves == []
    assert len(result.errors) == 1
    assert "nighttime.json" in result.errors[0]


def test_missing_base_file_is_reported(tmp_path: Path):
    _write(
        tmp_path / "nighttime.json",
        {
            "data": [
                {
                    "parent": "Nighttime",
                    "mainConditions": ["Nighttime"],
                    "base": "_missing.json",
                    "playlists": [],
                }
            ]
        },
    )

    result = resolve_context(tmp_path / "nighttime.json", tmp_path)

    assert result.leaves == []
    assert len(result.errors) == 1
    assert "_missing.json" in result.errors[0]


def test_malformed_base_file_is_reported(tmp_path: Path):
    (tmp_path / "_genres.json").write_text("{bad", encoding="utf-8")
    _write(
        tmp_path / "nighttime.json",
        {
            "data": [
                {
                    "parent": "Nighttime",
                    "mainConditions": ["Nighttime"],
                    "base": "_genres.json",
                    "playlists": [],
                }
            ]
        },
    )

    result = resolve_context(tmp_path / "nighttime.json", tmp_path)

    assert result.leaves == []
    assert len(result.errors) == 1
    assert "_genres.json" in result.errors[0]


def test_folder_missing_link_is_reported(tmp_path: Path):
    _write(
        tmp_path / "nighttime.json",
        {
            "data": [
                {
                    "parent": "Nighttime",
                    "mainConditions": ["Nighttime"],
                    "playlists": [
                        {"name": "Genre", "operator": 1, "playlistType": "folder"},
                    ],
                }
            ]
        },
    )

    result = resolve_context(tmp_path / "nighttime.json", tmp_path)

    assert result.leaves == []
    assert len(result.errors) == 1
    assert "missing link" in result.errors[0]


def test_malformed_linked_file_is_reported(tmp_path: Path):
    (tmp_path / "lens-genre.json").write_text("{bad", encoding="utf-8")
    _write(
        tmp_path / "nighttime.json",
        {
            "data": [
                {
                    "parent": "Nighttime",
                    "mainConditions": ["Nighttime"],
                    "playlists": [
                        {
                            "name": "Genre",
                            "operator": 1,
                            "playlistType": "folder",
                            "link": "lens-genre.json",
                        },
                    ],
                }
            ]
        },
    )

    result = resolve_context(tmp_path / "nighttime.json", tmp_path)

    assert result.leaves == []
    assert len(result.errors) == 1
    assert "lens-genre.json" in result.errors[0]


# --- leaf rules ------------------------------------------------------------


def _single_context(playlists: list[dict], negatives=("Archive",)) -> dict:
    return {
        "data": [
            {
                "parent": "Ctx",
                "mainConditions": ["Ctx"],
                "negativeConditions": list(negatives),
                "playlists": playlists,
            }
        ]
    }


def test_leaf_without_archive_is_reported(tmp_path: Path):
    _write(
        tmp_path / "ctx.json",
        _single_context([{"name": "All", "operator": 1, "contains": []}], negatives=()),
    )

    res = resolve_context(tmp_path / "ctx.json", tmp_path)

    assert any("lacks Archive" in e and "'All'" in e for e in res.errors)


def test_go_through_is_exempt_from_archive(tmp_path: Path):
    _write(
        tmp_path / "go-through.json",
        _single_context([{"name": "Bad Grid", "operator": 1, "contains": []}], negatives=()),
    )

    assert resolve_context(tmp_path / "go-through.json", tmp_path).errors == []


def test_duplicate_leaf_name_in_one_folder_is_reported(tmp_path: Path):
    _write(
        tmp_path / "ctx.json",
        _single_context(
            [
                {"name": "Dup", "operator": 1, "contains": []},
                {"name": "Dup", "operator": 1, "contains": ["X"]},
            ]
        ),
    )

    res = resolve_context(tmp_path / "ctx.json", tmp_path)

    assert [e for e in res.errors if "Duplicate leaf 'Dup'" in e]


def test_same_leaf_name_in_different_folders_is_fine(tmp_path: Path):
    _write(
        tmp_path / "ctx.json",
        _single_context(
            [
                {"name": "A", "playlistType": "folder", "link": "a.json"},
                {"name": "B", "playlistType": "folder", "link": "b.json"},
            ]
        ),
    )
    for name in ("a", "b"):
        _write(
            tmp_path / f"{name}.json",
            {"data": [{"playlists": [{"name": "All", "operator": 1, "contains": []}]}]},
        )

    assert resolve_context(tmp_path / "ctx.json", tmp_path).errors == []


def test_operator_other_than_1_is_reported(tmp_path: Path):
    _write(
        tmp_path / "ctx.json",
        _single_context([{"name": "Any", "operator": 2, "contains": []}]),
    )

    res = resolve_context(tmp_path / "ctx.json", tmp_path)

    assert any("operator 2" in e and "'Any'" in e for e in res.errors)


# --- main() exit codes and uniformity --------------------------------------


def test_main_clean_and_uniform_ok(tmp_path: Path, capsys):
    _write_uniform_dir(tmp_path, UNIFORM_CONTEXTS)

    rc = main([str(tmp_path)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "Uniformity: OK" in out
    assert "ERRORS" not in out


def test_main_uniformity_mismatch_differing_shape(tmp_path: Path, capsys):
    _write_uniform_dir(tmp_path, UNIFORM_CONTEXTS)
    # give one context an extra leaf so its structural shape diverges
    odd = UNIFORM_CONTEXTS[0]
    cfg = _uniform_context(odd)
    cfg["data"][0]["playlists"].append({"name": "Extra", "operator": 1, "contains": []})
    _write(tmp_path / f"{odd}.json", cfg)

    rc = main([str(tmp_path)])

    out = capsys.readouterr().out
    assert rc == 1
    assert "Uniformity: MISMATCH" in out
    assert "distinct shapes" in out


def test_main_uniformity_mismatch_missing_context(tmp_path: Path, capsys):
    # write all but the last expected uniform context
    _write_uniform_dir(tmp_path, UNIFORM_CONTEXTS[:-1])

    rc = main([str(tmp_path)])

    out = capsys.readouterr().out
    assert rc == 1
    assert "Uniformity: MISMATCH" in out
    assert UNIFORM_CONTEXTS[-1] in out


def test_main_returns_1_on_errors_and_skips_uniformity(tmp_path: Path, capsys):
    # a non-uniform context with a broken link: uniformity is skipped, but the
    # error still forces a non-zero exit.
    _write(
        tmp_path / "go-through.json",
        {
            "data": [
                {
                    "parent": "GoThrough",
                    "mainConditions": [],
                    "playlists": [
                        {
                            "name": "Genre",
                            "operator": 1,
                            "playlistType": "folder",
                            "link": "does-not-exist.json",
                        },
                    ],
                }
            ]
        },
    )

    rc = main([str(tmp_path)])

    out = capsys.readouterr().out
    assert rc == 1
    assert "ERRORS" in out
    assert "does-not-exist.json" in out
    assert "Uniformity" not in out


def test_main_one_bad_file_does_not_abort_others(tmp_path: Path, capsys):
    (tmp_path / "broken.json").write_text("{ not json", encoding="utf-8")
    _write(
        tmp_path / "good.json",
        {
            "data": [
                {
                    "parent": "Good",
                    "mainConditions": ["Good"],
                    "negativeConditions": ["Archive"],
                    "playlists": [
                        {"name": "All", "operator": 1, "contains": []},
                    ],
                }
            ]
        },
    )

    rc = main([str(tmp_path)])

    out = capsys.readouterr().out
    assert rc == 1  # the bad file produced an error
    assert "good.json" in out  # the good file was still processed
    assert "1 leaves" in out  # and its single leaf counted
    assert "broken.json" in out  # bad file reported in ERRORS


# --- Integration tests over the real playlist-data/ library -----------------

PLAYLIST_DATA = Path(__file__).resolve().parents[1] / "playlist-data"


@pytest.mark.integration
def test_real_library_has_no_broken_links():
    errors = []
    for f in _context_files(PLAYLIST_DATA):
        errors.extend(resolve_context(f, PLAYLIST_DATA).errors)
    assert errors == [], f"resolution errors: {errors}"


@pytest.mark.integration
def test_uniform_contexts_share_identical_core():
    sigs = {}
    for stem in UNIFORM_CONTEXTS:
        res = resolve_context(PLAYLIST_DATA / f"{stem}.json", PLAYLIST_DATA)
        assert len(res.leaves) == 29, f"{stem} has {len(res.leaves)} leaves, expected 29"
        sigs[stem] = _signature(res.leaves)
    assert len(set(sigs.values())) == 1, "lane roots do not share an identical core"


@pytest.mark.integration
def test_library_total_is_within_expected_range():
    total = sum(
        len(resolve_context(f, PLAYLIST_DATA).leaves) for f in _context_files(PLAYLIST_DATA)
    )
    # 16 lane roots * 29 + Gigs 7 + Recent Additions 4 + Go Through 3 = 478. Upper
    # bound: the audit can't see minTracks, which skips the redundant lane at runtime.
    assert total == 478, f"unexpected library total: {total}"
