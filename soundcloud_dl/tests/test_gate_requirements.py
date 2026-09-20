"""Tests for reading a gate's stated terms off its own page.

The wording pinned here is droploud's real requirement line, taken from a run screenshot.
It is the case that motivated the module: the gate names two profiles that are not the
track's artist, and nothing in the run could see either of them.
"""

from __future__ import annotations

import pytest

from soundcloud_dl.gate_handlers.gate_requirements import read_requirements, soundcloud_handles

DROPLOUD = (
    'FOLLOW @INDACOLLECTIVE, @ETS_WAV AND DROPLOUD ON SOUNDCLOUD\n'
    'LIKE, REPOST AND COMMENT ON "ETS - PRESSURE"'
)


class FakePage:
    """Stands in for a Playwright page, answering evaluate with a fixed value."""

    def __init__(self, reply: object) -> None:
        self.reply = reply

    async def evaluate(self, _js: str, _args: object = None) -> object:
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


# ── Parsing handles ────────────────────────────────────────────────────────────


def test_every_handle_the_gate_names_is_returned_lowercased():
    assert soundcloud_handles([DROPLOUD]) == ["indacollective", "ets_wav"]


def test_a_name_written_without_an_at_is_left_alone():
    """Droploud's terms end "AND DROPLOUD ON SOUNDCLOUD".

    Turning a display name into a permalink is a guess, and a wrong guess follows a real
    stranger from the user's account.
    """
    assert "droploud" not in soundcloud_handles([DROPLOUD])


def test_an_email_address_is_not_read_as_a_handle():
    blocks = ["Follow @realartist on SoundCloud, then email us at someone@gmail.com"]
    assert soundcloud_handles(blocks) == ["realartist"]


def test_handles_are_deduped_across_blocks_keeping_first_order():
    blocks = ["Follow @bravo and @alfa on SoundCloud", "Repost — and follow @alfa on SoundCloud"]
    assert soundcloud_handles(blocks) == ["bravo", "alfa"]


@pytest.mark.parametrize("text", ["@ab", "@", "follow us on soundcloud"])
def test_things_that_are_not_handles_are_skipped(text):
    # SoundCloud permalinks are at least three characters.
    assert soundcloud_handles([text]) == []


def test_an_over_long_token_is_rejected_not_truncated():
    """Truncating produced a *different* handle, which may be a real account.

    "@a-b-…-r" captured its first 25 characters, and that follow would have landed on
    whoever owns the shorter name.
    """
    assert soundcloud_handles(["@a-b-c-d-e-f-g-h-i-j-k-l-m-n-o-p-q-r on SoundCloud"]) == []


@pytest.mark.parametrize(
    "text",
    [
        "follow us at https://x.com/@notauser on soundcloud",
        "follow 5@@adminuser on soundcloud",
        "follow someone@gmail.com on soundcloud",
    ],
)
def test_an_at_that_is_not_a_soundcloud_handle_is_ignored(text):
    # Each of these is a real account name on some site. None of them is a request to
    # follow that name on SoundCloud.
    assert soundcloud_handles([text]) == []


def test_no_blocks_means_no_handles():
    assert soundcloud_handles([]) == []


# ── Reading the page ───────────────────────────────────────────────────────────


async def test_requirement_blocks_come_back_as_written():
    assert await read_requirements(FakePage([DROPLOUD])) == [DROPLOUD]


async def test_blank_blocks_are_dropped():
    assert await read_requirements(FakePage(["", "   ", DROPLOUD])) == [DROPLOUD]


async def test_a_page_that_cannot_be_read_is_not_fatal():
    # Called every turn, including while a click is navigating away. A raise here would
    # end a run that the gate itself had not blocked.
    assert await read_requirements(FakePage(RuntimeError("context destroyed"))) == []


@pytest.mark.parametrize("reply", [None, "a string, not a list", 42])
async def test_an_unexpected_reply_shape_reads_as_no_requirements(reply):
    assert await read_requirements(FakePage(reply)) == []
