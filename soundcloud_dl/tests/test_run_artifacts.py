"""RunRecorder's on-disk naming."""

import json

import pytest

from soundcloud_dl.run_artifacts import RunRecorder


@pytest.fixture(autouse=True)
def _runs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("soundcloud_dl.run_artifacts.get_runs_dir", lambda: tmp_path)
    return tmp_path


def test_the_run_dir_lands_under_the_runs_root(_runs_dir):
    r = RunRecorder("hypeddit_jev")
    assert r.dir.parent == _runs_dir
    assert r.dir.name.startswith("hypeddit_jev-")


@pytest.mark.parametrize(
    "gate_name",
    [
        "../../../etc/passwd",
        "..",
        "a/b",
        "user:pw@host_jev",
        "..%2f..%2fetc",
    ],
)
def test_a_hostile_gate_name_cannot_escape_the_runs_root(gate_name, _runs_dir):
    """The name comes from a gate URL and a gate redirects wherever it likes. Today's
    derivation strips separators as a side effect of urlparse; this asserts it instead.
    """
    r = RunRecorder(gate_name)
    assert r.dir.resolve().parent == _runs_dir.resolve()
    assert "/" not in r.dir.name
    assert not r.dir.name.startswith(".")


def test_a_credential_shaped_host_does_not_reach_the_filename(_runs_dir):
    """A redirect to http://user:pw@host would otherwise write the userinfo into a
    directory name, result.json's gate field, and the log line announcing the run.
    """
    r = RunRecorder("user:pw@host_jev")
    assert ":" not in r.dir.name
    assert "@" not in r.dir.name


def test_an_overlong_name_does_not_break_mkdir(_runs_dir):
    """NAME_MAX is 255; an un-truncated label makes mkdir raise, which the caller
    records as a failed track rather than as a bad name.
    """
    r = RunRecorder("x" * 400)
    assert len(r.dir.name) < 255
    assert r.dir.is_dir()


def test_finish_writes_the_outcome(_runs_dir):
    r = RunRecorder("gate_jev")
    r.finish(url="https://sc/x", downloaded=True, terminal="downloaded")
    payload = json.loads((r.dir / "result.json").read_text())
    assert payload["downloaded"] is True
    assert payload["terminal"] == "downloaded"
    assert payload["gate"] == "gate_jev"
