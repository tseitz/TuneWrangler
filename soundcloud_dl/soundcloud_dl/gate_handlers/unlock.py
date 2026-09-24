"""Pure predicates over snapshot elements: what is the download, and is the gate open yet.

Kept separate from judgment.py so they are testable without importing the TypeSafe SDK.
"""

from __future__ import annotations

from typing import Any

# hypeddit.yaml's final_download selector list, as data.
_DOWNLOAD_IDS = frozenset({"gatedownloadbutton", "downloadprocess"})
_DOWNLOAD_CLASSES = frozenset({"free_dwln", "dp", "download-link", "post-gate-btn"})

# These open the gate rather than serve the file; see _is_href_gated.
_HREF_GATED_IDS = frozenset({"downloadprocess"})
_HREF_GATED_CLASSES = frozenset({"dp"})

# Controls whose only readiness signal is the icon they show; see _is_icon_gated.
_ICON_GATED_CLASSES = frozenset({"post-gate-btn"})
_READY_ICON = "download"

# A padlock means locked wherever it appears, so this needs no per-host opt-in. The
# converse is not true — an open control is free to show any icon — which is why
# _ICON_GATED_CLASSES still exists alongside it.
_LOCKED_ICONS = frozenset({"lock", "padlock", "lock-keyhole"})

# Both spellings appear on the live page at the same time. `pointer-events-none` is the
# Tailwind spelling of the same thing; it is matched as a whole token, never a substring,
# because the same class list carries `disabled:pointer-events-none` and
# `[&_svg]:pointer-events-none` while the control is perfectly clickable.
_DISABLED_TOKENS = frozenset({"disable", "disabled", "pointer-events-none"})

# A <button> is judged by its label, which an <a> is not: the miss that made
# is_download_element id-and-class-only was hypeddit's site nav, and nav links are anchors.
# Exact labels rather than a substring so "Download the app on iOS" cannot match; a gate
# with a label not listed here fails closed, which costs a run rather than a wrong click.
_DOWNLOAD_BUTTON_TEXTS = frozenset(
    {
        "download",
        "free download",
        "download now",
        "download file",
        "download track",
        # droploud's success page, when the download it starts on arrival does not fire.
        "download again",
    }
)

_DEAD_HREFS = frozenset({"", "#", "javascript:void(0)"})


def is_download_element(el: dict[str, Any]) -> bool:
    """Identity only — is this the download control, regardless of whether it works yet.

    Deliberately id and class only. Matching on the word "download" in the text also
    matched Hypeddit's own site navigation, and because those nav links carry real hrefs
    they outranked the actual button; one run clicked through to a genre listing page.
    """
    if el["tag"] == "button":
        return " ".join(el["text"].lower().split()).strip(".!… ") in _DOWNLOAD_BUTTON_TEXTS
    if el["tag"] != "a":
        return False
    if (el.get("id") or "").lower() in _DOWNLOAD_IDS:
        return True
    return bool(set(el["cls"].lower().split()) & _DOWNLOAD_CLASSES)


def is_download_enabled(el: dict[str, Any]) -> bool:
    """A locked download button carries a disable class; hypeddit.yaml gates on the same thing.

    Deliberately not an href check: on SoundCloud-only gates #gateDownloadButton keeps
    href="javascript:void(0);" even once it works, and clicking it is what serves the file.
    """
    if set(el["cls"].lower().split()) & _DISABLED_TOKENS or el["disabled"]:
        return False
    if set(el.get("icons") or ()) & _LOCKED_ICONS:
        return False
    if _is_icon_gated(el):
        return _READY_ICON in el.get("icons", ())
    return True


def _is_icon_gated(el: dict[str, Any]) -> bool:
    """True for controls that look identical locked and open apart from the icon they show.

    ToneDen renders one <a class="post-gate-btn">FREE DOWNLOAD</a> in both states: no href,
    no disable class, and the same text. Everything else here would call the locked one
    ready. That matters more than a wasted click, because judgment.py banks a download key
    before trying it and keys are derived from text — so clicking the locked button burns
    the real one for the rest of the run.

    Stated as "must show the download icon" rather than "must not show a padlock": the open
    state is the one that was observed, and a gate is free to invent a third icon for
    locked. Controls with no icons at all are unaffected, which is every hypeddit button.
    """
    return bool(set(el["cls"].lower().split()) & _ICON_GATED_CLASSES)


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


def page_actions_complete(snapshot: dict[str, dict[str, Any]]) -> bool:
    """Every gate action on the CURRENT page is done. Says nothing about the gate as a whole."""
    actions = [el for el in snapshot.values() if el.get("step")]
    return bool(actions) and all(is_action_done(el) for el in actions)


def _is_href_gated(el: dict[str, Any]) -> bool:
    """True for controls whose class never says locked, so only a real href proves readiness.

    #downloadProcess is the button that OPENS the gate, and it carries no disable class at
    any point. Judging it by class alone makes a freshly-loaded, fully-locked gate look
    ready. hypeddit.yaml only ever matched it with a non-placeholder href, for this reason.
    """
    return (el.get("id") or "").lower() in _HREF_GATED_IDS or bool(
        set(el["cls"].lower().split()) & _HREF_GATED_CLASSES
    )


def find_download_target(snapshot: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """The download element to click, preferring one with a real href.

    Readiness is checked before the href is, not after: a live href used to be taken as
    proof on its own, which let a locked control through as long as it was linked at all.
    """
    candidates = [
        el for el in snapshot.values() if is_download_element(el) and is_download_enabled(el)
    ]
    live = next((el for el in candidates if is_unlocked_href(el["href"])), None)
    if live is not None:
        return live
    return next((el for el in candidates if not _is_href_gated(el)), None)


def unlock_reached(snapshot: dict[str, dict[str, Any]]) -> bool:
    """True only when a usable download control is on screen.

    Finishing a page's actions is NOT enough: the gate is a carousel and the real download
    button is several 'Next' clicks further on. Counting actions-done as unlocked sent the
    loop hunting for a download it had not reached, and it stalled there.
    """
    return find_download_target(snapshot) is not None
