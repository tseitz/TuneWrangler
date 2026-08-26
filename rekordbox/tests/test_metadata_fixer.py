"""Tests for MetadataFixer."""

from types import SimpleNamespace

from rekordbox_smart_playlists.core.metadata_fixer import (
    MetadataAction,
    MetadataFixResult,
    MetadataFixer,
)


# --- _commit_results -------------------------------------------------------


class _SpyDatabase:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def _committing_fixer(dry_run: bool = False):
    """A MetadataFixer with a spy database and no real config behind it."""
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
