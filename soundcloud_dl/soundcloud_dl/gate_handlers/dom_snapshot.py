"""Shared DOM snapshot for the gate tools.

judgment.py picks an element by key and re-finds it by key at click time; inspect_gate.py
diffs two snapshots by key. Both must derive keys identically, or they name different
elements the same thing, so the derivation lives here once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Page

# Keys must survive a DOM insertion. A positional key (tag + querySelectorAll index)
# re-points at a different element the moment a node is added ahead of it, so the click
# lands somewhere other than what was chosen and nothing in the log says so. Content-derived
# instead: two identical elements collide and first-match wins, which is a far better
# failure than an arbitrary re-point.
#
# isVisible: Hypeddit's carousel keeps every slide in the DOM at once (marked
# 'upcomming-slide' — their real, misspelled class name) with a CSS transform that still
# passes offsetParent and display checks. Without excluding it, elements on a not-yet-active
# slide look clickable but silently do nothing.
_HELPERS_JS = """
const elKey = (el) => {
  if (el.id) return el.id;
  const step = el.getAttribute('data-step');
  if (step) return 'data-step=' + step;
  const parts = [
    el.tagName.toLowerCase(),
    el.getAttribute('href') || '',
    el.getAttribute('name') || '',
    (el.innerText || el.value || '').trim().slice(0, 40),
  ].join('|');
  let h = 5381;
  for (let i = 0; i < parts.length; i += 1) {
    h = ((h * 33) ^ parts.charCodeAt(i)) >>> 0;
  }
  return el.tagName.toLowerCase() + '@' + h.toString(36);
};
const isVisible = (el) => (
  el.offsetParent !== null
  && getComputedStyle(el).display !== 'none'
  && el.closest('.upcomming-slide') === null
);
"""

_SELECTOR = "a, button, input, form"


def _js(body: str) -> str:
    return body.replace("__HELPERS__", _HELPERS_JS).replace("__SELECTOR__", _SELECTOR)


SNAPSHOT_JS = _js("""
() => {
  __HELPERS__
  return Array.from(document.querySelectorAll('__SELECTOR__')).map((el) => ({
    key: elKey(el),
    id: el.id || '',
    step: el.getAttribute('data-step') || '',
    tag: el.tagName.toLowerCase(),
    cls: el.className || '',
    href: el.getAttribute('href') || '',
    disabled: el.disabled === true || el.hasAttribute('disabled'),
    visible: isVisible(el),
    text: (el.innerText || el.value || '').trim().slice(0, 60),
    placeholder: el.getAttribute('placeholder') || '',
    name: el.getAttribute('name') || '',
  }));
}
""")

# Prefers a visible match: a colliding key on a hidden carousel slide must not win over
# the on-screen element the snapshot actually offered to the model.
FIND_BY_KEY_JS = _js("""
(key) => {
  __HELPERS__
  const matches = Array.from(document.querySelectorAll('__SELECTOR__'))
    .filter((el) => elKey(el) === key);
  if (matches.length === 0) return null;
  return matches.find(isVisible) || matches[0];
}
""")


async def snapshot_elements(page: Page) -> list[dict[str, Any]]:
    """Return one record per interactive element on the page, in document order."""
    return await page.evaluate(SNAPSHOT_JS)


async def find_element_by_key(page: Page, key: str) -> Any | None:  # noqa: ANN401
    """Re-locate the element a snapshot key pointed at, or None."""
    handle = await page.evaluate_handle(FIND_BY_KEY_JS, key)
    return handle.as_element()
