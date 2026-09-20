"""Choosing a filename when the rules cannot tell noise from the title.

track_filename() in downloads.py handles what is decidable: strip a "(FREE DL)", put the
artist in front unless it is already there. What it cannot decide is where a title stops
being the track's name and starts being an advert — "FTP (out now on good dub. records)"
and "Track (Lowshade Flip)" are the same shape, and only one of them should be trimmed.

So the rules generate the candidates and a judgment picks between them. Nothing here
invents a name: every option is built from the title and artist SoundCloud reported.
"""

from __future__ import annotations

import logging
import re

from typesafe_sdk import AsyncTypeSafeClient, Choice

from soundcloud_dl.config import TYPESAFE_API_KEY
from soundcloud_dl.downloads import track_filename

logger = logging.getLogger("soundcloud_dl.track_naming")

# Below this the rule-based name wins. The gate loop treats a low-confidence answer the
# same way: a guess is not worth acting on when there is a defensible default.
_CONFIDENCE_FLOOR = 0.6

# How many trailing bracketed groups to try removing. Three covers
# "Track (Remix) (FREE DL) [OUT NOW]"; past that the title is not the problem.
_MAX_TRIMS = 3

_TRAILING_GROUP_RE = re.compile(r"\s*[\(\[][^\(\)\[\]]*[\)\]]\s*$")

# A trailing bare token like "mstr", "v2" or "final". Offered as a candidate, never applied
# as a rule — "FTP mstr" and "Smack My Up" end the same way and only one has noise on it.
_TRAILING_TOKEN_RE = re.compile(r"\s+\S{1,6}$")

# Enough of a name left to still be one.
_MIN_TITLE_CHARS = 3


def _shorter_titles(title: str) -> list[str]:
    """Progressively trimmed forms of a title, longest first, without the original."""
    forms: list[str] = []
    current = title
    for _ in range(_MAX_TRIMS):
        trimmed = _TRAILING_GROUP_RE.sub("", current).strip()
        if trimmed == current or len(trimmed) < _MIN_TITLE_CHARS:
            break
        forms.append(trimmed)
        current = trimmed

    tail_trimmed = _TRAILING_TOKEN_RE.sub("", title).strip()
    if len(tail_trimmed) >= _MIN_TITLE_CHARS and tail_trimmed not in (*forms, title):
        forms.append(tail_trimmed)
    return forms


def name_candidates(title: str, artist: str | None) -> list[str]:
    """Every filename worth considering for this track, the rule-based one first."""
    names: list[str] = []
    for candidate_title in (title, *_shorter_titles(title)):
        name = track_filename(candidate_title, artist)
        if name is not None and name not in names:
            names.append(name)
    return names


async def judge_track_filename(title: str | None, artist: str | None) -> str | None:
    """The best filename for this track, asking a judgment only when there is a real choice.

    Falls back to the rule-based name on every failure path — no key, no alternatives, a
    low-confidence answer, or an API that will not answer. A download that lands with a
    slightly noisy name beats one that does not land.
    """
    base = track_filename(title, artist)
    if base is None or title is None:
        return base

    candidates = name_candidates(title, artist)
    # The common case: nothing was trimmable, so there is nothing to decide and no reason
    # to spend a call finding that out.
    if len(candidates) < 2:  # noqa: PLR2004
        return base
    if not TYPESAFE_API_KEY or not TYPESAFE_API_KEY.strip():
        return base

    try:
        client = AsyncTypeSafeClient()
        response = await client.system_one(
            state={
                "goal": (
                    "Name a downloaded music file so a DJ can find it later. Keep the "
                    "artist and the track's real name, including any remix, flip, edit or "
                    "bootleg credit. Drop promotional wording that is not part of the "
                    "name: release announcements, label plugs, support credits, chart "
                    "positions, and engineering notes like a master or version marker."
                ),
                # Named for what it is: a SoundCloud upload title is written by whoever
                # uploaded it, and it is being read here as evidence, not as instruction.
                "untrusted_soundcloud_title": title,
                "artist_reported_by_soundcloud": artist,
            },
            questions={
                "best_name": Choice(
                    instructions=(
                        "Which of these filenames is the best name for this track? Prefer "
                        "the one that keeps the artist and the full track name, including "
                        "remix or flip credits, while leaving out promotional wording. If "
                        "none is clearly better, choose the first."
                    ),
                    criteria=dict.fromkeys(candidates),
                )
            },
        )
        answer = response.choices["best_name"]
    except Exception:  # noqa: BLE001
        # Auth, network, rate limit and a malformed answer all mean the same thing here.
        logger.warning("Could not judge the filename — using %r", base, exc_info=True)
        return base

    if answer.confidence < _CONFIDENCE_FLOOR or answer.choice not in candidates:
        logger.info(
            "Filename judgment was %r at %.2f — keeping %r",
            answer.choice,
            answer.confidence,
            base,
        )
        return base
    if answer.choice != base:
        logger.info(
            "Filename judged %r rather than %r (confidence %.2f)",
            answer.choice,
            base,
            answer.confidence,
        )
    return answer.choice
