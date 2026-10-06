"""Tests for filename parsing and authority selection in MetadataFixer."""

from types import SimpleNamespace

import pytest

from rekordbox_smart_playlists.core.metadata_fixer import (
    MetadataAction,
    MetadataFixResult,
    MetadataFixer,
)


@pytest.fixture
def fixer() -> MetadataFixer:
    """A MetadataFixer with no real database or config behind it.

    Every method under test here is pure string handling, so the collaborators
    are never touched.
    """
    return MetadataFixer.__new__(MetadataFixer)


# --- _parse_filename -------------------------------------------------------


def test_parses_artist_title(fixer: MetadataFixer):
    assert fixer._parse_filename("Jamzigg - Doomsday.mp3") == ("Jamzigg", "Doomsday", None)


def test_parses_artist_album_title(fixer: MetadataFixer):
    assert fixer._parse_filename("Gunnar Nash - Sweet Sounds Collective - Suddenly.mp3") == (
        "Gunnar Nash",
        "Suddenly",
        "Sweet Sounds Collective",
    )


def test_single_segment_is_unparsable(fixer: MetadataFixer):
    # Sample-pack files like "MergeFX Sample Sound 101.wav" carry no separator,
    # so there is no artist to recover.
    assert fixer._parse_filename("MergeFX Sample Sound 101.wav") is None


def test_strips_unknown_placeholder_leaving_artist_title(fixer: MetadataFixer):
    # "Unknown" is a placeholder written when the downloader could not identify
    # the artist. It is not an artist name, so it must not be treated as one.
    assert fixer._parse_filename("Unknown - LV vs LAZ-R vs KHOLD - ATOMICFLANGWARE.aiff") == (
        "LV vs LAZ-R vs KHOLD",
        "ATOMICFLANGWARE",
        None,
    )


def test_strips_unknown_placeholder_leaving_artist_album_title(fixer: MetadataFixer):
    assert fixer._parse_filename("Unknown - James Hype - Eminem - Lose Yourself.aiff") == (
        "James Hype",
        "Lose Yourself",
        "Eminem",
    )


def test_unknown_placeholder_is_case_insensitive(fixer: MetadataFixer):
    assert fixer._parse_filename("unknown - SENRI - CLASS SESSION.aiff") == (
        "SENRI",
        "CLASS SESSION",
        None,
    )


def test_unknown_only_stripped_from_the_front(fixer: MetadataFixer):
    # A track genuinely titled "Unknown" keeps it.
    assert fixer._parse_filename("Raucous - Unknown.mp3") == ("Raucous", "Unknown", None)


def test_unknown_alone_is_unparsable(fixer: MetadataFixer):
    # Nothing left after stripping the placeholder.
    assert fixer._parse_filename("Unknown.aiff") is None


def test_five_segments_still_unparsable(fixer: MetadataFixer):
    # Stripping the placeholder leaves 4 segments, which remains ambiguous.
    assert fixer._parse_filename("Unknown - A - B - C - D.aiff") is None


# --- _db_metadata_is_empty -------------------------------------------------


def _comparison(artist_name):
    """A stand-in comparison whose content object carries the given artist."""
    artist = None if artist_name is None else SimpleNamespace(Name=artist_name)
    return SimpleNamespace(content_object=SimpleNamespace(Artist=artist))


def test_db_empty_when_artist_relation_missing(fixer: MetadataFixer):
    assert fixer._db_metadata_is_empty(_comparison(None)) is True


def test_db_empty_when_artist_name_blank(fixer: MetadataFixer):
    assert fixer._db_metadata_is_empty(_comparison("   ")) is True


def test_db_not_empty_when_artist_present(fixer: MetadataFixer):
    assert fixer._db_metadata_is_empty(_comparison("Jamzigg")) is False


def test_db_not_empty_when_content_object_missing(fixer: MetadataFixer):
    # No content object means we cannot claim the database side is empty.
    assert fixer._db_metadata_is_empty(SimpleNamespace(content_object=None)) is False


# --- _album_matches --------------------------------------------------------


def test_album_matches_when_both_agree(fixer: MetadataFixer):
    assert fixer._album_matches("Back160", "Back160") is True


def test_album_differs_when_both_present_and_unequal(fixer: MetadataFixer):
    assert fixer._album_matches("Back160", "Heart Of Darkness") is False


def test_album_matches_when_neither_side_has_one(fixer: MetadataFixer):
    assert fixer._album_matches(None, None) is True


def test_two_segment_name_is_not_treated_as_drift(fixer: MetadataFixer):
    # A filename with no album segment is a naming choice, not a lost album:
    # the value still lives in the file's tags and in the database. Comparing
    # it flagged 77 tracks that neither fix direction could sensibly settle.
    assert fixer._album_matches("Clutch EP", None) is True


def test_two_segment_name_fine_when_db_album_is_blank(fixer: MetadataFixer):
    assert fixer._album_matches("", None) is True
    assert fixer._album_matches("   ", None) is True


def test_unknown_db_album_is_treated_as_absent(fixer: MetadataFixer):
    # "Unknown" is the sentinel used when the album attribute is missing.
    assert fixer._album_matches("Unknown", None) is True


def test_album_comparison_ignores_case_and_unicode_form(fixer: MetadataFixer):
    assert fixer._album_matches("BACK160", "back160") is True


def test_unknown_on_both_sides_agrees(fixer: MetadataFixer):
    # Files named "Artist - Unknown - Title" carry the placeholder in the album
    # slot. It has to be read the same way on both sides, or every one of them
    # is reported as drift that no fix direction can settle.
    assert fixer._album_matches("Unknown", "Unknown") is True


def test_unknown_in_filename_matches_absent_db_album(fixer: MetadataFixer):
    assert fixer._album_matches(None, "Unknown") is True
    assert fixer._album_matches("", "Unknown") is True


def test_unknown_in_filename_still_differs_from_a_real_album(fixer: MetadataFixer):
    assert fixer._album_matches("Back160", "Unknown") is False


# --- _commit_results -------------------------------------------------------


class _SpyDatabase:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def _committing_fixer(dry_run: bool = False):
    f = MetadataFixer.__new__(MetadataFixer)
    f.db = _SpyDatabase()
    f.config = SimpleNamespace(dry_run=dry_run)
    return f


def _result(action, success=True):
    return MetadataFixResult(filename="x.mp3", success=success, action_taken=action)


def test_commits_after_renaming_a_file():
    # Renaming rewrites the filename the database stores. Without a commit,
    # Rekordbox is left pointing at a name that no longer exists on disk.
    f = _committing_fixer()
    f._commit_results([_result(MetadataAction.UPDATE_FILENAME)])
    assert f.db.commits == 1


def test_commits_after_updating_database_metadata():
    f = _committing_fixer()
    f._commit_results([_result(MetadataAction.UPDATE_DATABASE)])
    assert f.db.commits == 1


def test_no_commit_when_nothing_succeeded():
    f = _committing_fixer()
    f._commit_results([_result(MetadataAction.UPDATE_FILENAME, success=False)])
    assert f.db.commits == 0


def test_no_commit_for_skipped_results():
    f = _committing_fixer()
    f._commit_results([_result(MetadataAction.SKIP)])
    assert f.db.commits == 0


def test_no_commit_in_dry_run():
    f = _committing_fixer(dry_run=True)
    f._commit_results([_result(MetadataAction.UPDATE_FILENAME)])
    assert f.db.commits == 0


# --- config ----------------------------------------------------------------


def test_aif_is_scanned_like_aiff():
    # ".aif" and ".aiff" are the same format. Omitting one hid those files from
    # every scan the tool performs, so they were never checked for drift.
    from rekordbox_smart_playlists.core.config import Config

    exts = Config().audio_extensions
    assert ".aif" in exts
    assert ".aiff" in exts
