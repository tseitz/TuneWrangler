"""Read what a gate is asking for, from the gate's own text.

The DOM snapshot in dom_snapshot.py only collects interactive elements, so a gate that
states its terms in a paragraph — droploud prints "FOLLOW @INDACOLLECTIVE, @ETS_WAV AND
DROPLOUD ON SOUNDCLOUD" — is invisible to the model driving it and to the code doing the
SoundCloud actions. Both were working from the track's own artist and nothing else.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("soundcloud_dl.gate_handlers.gate_requirements")

# A gate's terms name the platform and at least one action. Requiring both keeps out the
# page furniture that says "SoundCloud" on its own (a player embed, a footer link).
MAX_BLOCKS = 5
_MAX_BLOCK_CHARS = 400

# The containment filter below is O(n²) and el.innerText forces layout, so an uncapped
# hit list is a way for a page to hang the browser for the whole run. A gate states its
# terms in a line or two; anything past this ceiling is not a gate stating terms.
_MAX_HITS = 40

_REQUIREMENTS_JS = """
(limits) => {
  const [maxHits, maxChars, maxBlocks] = limits;
  const PLATFORM = /soundcloud/i;
  const ACTION = /\\b(follow|like|repost|comment|subscribe)\\b/i;
  const hits = [];
  for (const el of document.querySelectorAll('p, span, div, h1, h2, h3, h4, li, small')) {
    if (hits.length >= maxHits) break;
    if (el.offsetParent === null) continue;
    const t = (el.innerText || '').trim();
    if (!t || t.length > maxChars) continue;
    if (!PLATFORM.test(t) || !ACTION.test(t)) continue;
    hits.push(el);
  }
  // Every ancestor of a match also matches, up to <body>. Keeping only the ones with no
  // matching descendant turns "the whole card" back into "the line that states the terms".
  return hits
    .filter((el) => !hits.some((o) => o !== el && el.contains(o)))
    .slice(0, maxBlocks)
    .map((el) => el.innerText.trim());
}
"""

# A SoundCloud permalink is 3-25 chars of letters, digits, hyphen and underscore.
#
# Both guards exist because a match becomes a real follow on a real stranger's account:
#   - the lookbehind drops the domain half of an email ("someone@gmail.com"), a handle for
#     another site pasted as a URL ("x.com/@name"), and a stray second "@".
#   - the lookahead REJECTS an over-long token rather than truncating it. Without it
#     "@a-b-c-…-r" captured its first 25 characters, which is a different account that may
#     well exist.
_HANDLE_RE = re.compile(r"(?<![\w./@])@([a-zA-Z0-9][\w-]{2,24})(?![\w-])")


def soundcloud_handles(blocks: list[str]) -> list[str]:
    """The @handles a gate named, lowercased, in the order they were written.

    Only @-prefixed names. A gate also names profiles in prose — droploud's terms end
    "AND DROPLOUD ON SOUNDCLOUD" — but turning a display name into a permalink is a guess,
    and a wrong guess follows a real stranger from the user's account.
    """
    seen: dict[str, None] = {}
    for block in blocks:
        for match in _HANDLE_RE.finditer(block):
            seen.setdefault(match.group(1).lower(), None)
    return list(seen)


async def read_requirements(page: Page) -> list[str]:
    """The gate's stated terms, or an empty list.

    Never raises. A gate that states nothing is normal, and a page that is mid-navigation
    must not end the run — the caller reads this every turn.
    """
    try:
        blocks = await page.evaluate(_REQUIREMENTS_JS, [_MAX_HITS, _MAX_BLOCK_CHARS, MAX_BLOCKS])
    except Exception:  # noqa: BLE001
        logger.debug("could not read gate requirements", exc_info=True)
        return []
    if not isinstance(blocks, list):
        return []
    return [b for b in blocks if isinstance(b, str) and b.strip()]
