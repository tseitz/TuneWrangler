"""Pure predicates over snapshot elements: what is the download, and is the gate open yet.

Kept separate from judgment.py so they are testable without importing the TypeSafe SDK.
"""

from __future__ import annotations

from typing import Any

# hypeddit.yaml's final_download selector list, as data.
_DOWNLOAD_IDS = frozenset({"gatedownloadbutton", "downloadprocess"})
_DOWNLOAD_CLASSES = frozenset({"free_dwln", "dp", "download-link"})

# Both spellings appear on the live page at the same time.
_DISABLED_TOKENS = frozenset({"disable", "disabled"})

_DEAD_HREFS = frozenset({"", "#", "javascript:void(0)"})


def is_download_element(el: dict[str, Any]) -> bool:
    """Identity only — is this the download control, regardless of whether it works yet."""
    if el["tag"] != "a":
        return False
    if (el.get("id") or "").lower() in _DOWNLOAD_IDS:
        return True
    if set(el["cls"].lower().split()) & _DOWNLOAD_CLASSES:
        return True
    return "download" in el["text"].lower()


def is_download_enabled(el: dict[str, Any]) -> bool:
    """A locked download button carries a disable class; hypeddit.yaml gates on the same thing.

    Deliberately not an href check: on SoundCloud-only gates #gateDownloadButton keeps
    href="javascript:void(0);" even once it works, and clicking it is what serves the file.
    """
    return not (set(el["cls"].lower().split()) & _DISABLED_TOKENS) and not el["disabled"]


def is_unlocked_href(href: str) -> bool:
    """True when an href points somewhere real.

    Hypeddit serves `javascript:void(0);` WITH a trailing semicolon, so comparing against the
    placeholder literal is not enough — strip it first, and require a navigable scheme.
    """
    normalized = href.strip().rstrip(";").lower()
    if normalized in _DEAD_HREFS or normalized.startswith("javascript:"):
        return False
    return normalized.startswith(("http://", "https://", "/"))


def is_action_done(el: dict[str, Any]) -> bool:
    """A gate action flips its class from 'undone' to 'done'.

    Token comparison, not substring: 'done' is inside 'undone'.
    """
    tokens = set(el["cls"].lower().split())
    return "done" in tokens and "undone" not in tokens


def unlock_reached(snapshot: dict[str, dict[str, Any]]) -> bool:
    """True once the gate has opened: every required action done, or a live download href."""
    actions = [el for el in snapshot.values() if el.get("step")]
    if actions and all(is_action_done(el) for el in actions):
        return True
    return any(is_download_element(el) and is_unlocked_href(el["href"]) for el in snapshot.values())


def find_download_target(snapshot: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """The download element to click, preferring one with a real href."""
    candidates = [el for el in snapshot.values() if is_download_element(el)]
    live = next((el for el in candidates if is_unlocked_href(el["href"])), None)
    if live is not None:
        return live
    return next((el for el in candidates if is_download_enabled(el)), None)
