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
// A gate repeats a data-step: hypeddit prints one "follow" button per artist, the track's
// and the remixer's. Keyed on the step alone the two collide, the snapshot offers only the
// first, and the second can never be chosen or clicked — so the gate refuses to unlock and
// the run reports whatever it was stuck on instead. data-url is what actually differs
// (the profile or track being acted on) and, unlike the label, does not change when the
// button flips to done.
const hash = (s) => {
  let h = 5381;
  for (let i = 0; i < s.length; i += 1) {
    h = ((h * 33) ^ s.charCodeAt(i)) >>> 0;
  }
  return h.toString(36);
};
// The hash is what makes the key unique — it covers the whole attribute, so two buttons
// whose URLs end the same way (/users/1/follow and /users/2/follow) still differ. The
// readable half is for the log only, so it is truncated and stripped: a key is page-supplied
// text that ends up in a log line, a CSS selector and a prompt.
const stepSuffix = (el) => {
  const sub = el.getAttribute('data-url') || el.getAttribute('data-title') || '';
  if (!sub) return '';
  const clean = sub.split('?')[0].split('#')[0].replace(/\\/+$/, '');
  const tail = clean
    .slice(clean.lastIndexOf('/') + 1)
    .replace(/[^A-Za-z0-9._-]/g, '')
    .slice(0, 24);
  return ':' + tail + '@' + hash(sub);
};
const elKey = (el) => {
  if (el.id) return el.id;
  const step = el.getAttribute('data-step');
  if (step) return 'data-step=' + step + stepSuffix(el);
  const parts = [
    el.tagName.toLowerCase(),
    el.getAttribute('href') || '',
    el.getAttribute('name') || '',
    (el.innerText || el.value || '').trim().slice(0, 40),
  ].join('|');
  return el.tagName.toLowerCase() + '@' + hash(parts);
};
const isVisible = (el) => (
  el.offsetParent !== null
  && getComputedStyle(el).display !== 'none'
  && el.closest('.upcomming-slide') === null
);
const TOGGLE_SEL = 'input[type="checkbox"], input[type="radio"]';
// A styled checkbox hides the real input (droploud: display:none, 0x0) and paints a span
// inside the wrapping label. The input therefore fails isVisible and is never offered, so
// the label is the only thing that can be clicked — and clicking it toggles the input
// natively, with a trusted event.
const toggleOf = (el) => (
  el.matches(TOGGLE_SEL) ? el : el.querySelector(TOGGLE_SEL)
);
// Site furniture, never the gate. Recorded rather than dropped so a gate that does put a
// control in its own header is still reachable through judgment.py's fallback.
const CHROME_SEL = 'nav, header, footer, [role="navigation"], [role="contentinfo"],'
  + ' [role="banner"]';
const isChrome = (el) => el.closest(CHROME_SEL) !== null;
// A gate is a small card; the page around it can run for thousands of pixels. Droploud's
// FAQ accordions are interactive, far below the fold, and every expand counts as the page
// changing — enough to keep the stuck-detector quiet while a run burns all its turns.
const ON_SCREEN_MARGIN = 150;
const onScreen = (el) => {
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return false;
  const m = ON_SCREEN_MARGIN;
  return r.bottom > -m && r.top < window.innerHeight + m
    && r.right > -m && r.left < window.innerWidth + m;
};
"""

_SELECTOR = "a, button, input, textarea, form, label"


def _js(body: str) -> str:
    return body.replace("__HELPERS__", _HELPERS_JS).replace("__SELECTOR__", _SELECTOR)


SNAPSHOT_JS = _js("""
() => {
  __HELPERS__
  return Array.from(document.querySelectorAll('__SELECTOR__')).map((el) => {
    const toggle = toggleOf(el);
    // Only a label that wraps a checkbox or radio is a control. Every other label is
    // caption text for a field already offered in its own right.
    if (el.tagName === 'LABEL' && toggle === null) return null;
    return {
      key: elKey(el),
      id: el.id || '',
      step: el.getAttribute('data-step') || '',
      tag: el.tagName.toLowerCase(),
      // An SVG <a> matches the 'a' selector but its className is an SVGAnimatedString, not
      // a string. Every reader here calls .lower().split() on it.
      cls: typeof el.className === 'string' ? el.className : (el.getAttribute('class') || ''),
      href: el.getAttribute('href') || '',
      type: ((toggle || el).getAttribute('type') || '').toLowerCase(),
      // Without this a tick is invisible to the snapshot diff, so _did_it_move reports
      // changed=False and the only control that opens the gate is banned as dead.
      checked: toggle !== null && toggle.checked === true,
      disabled: el.disabled === true || el.hasAttribute('disabled')
        || el.getAttribute('aria-disabled') === 'true',
      visible: isVisible(el),
      chrome: isChrome(el),
      onscreen: onScreen(el),
      text: (el.innerText || el.value || '').trim().slice(0, 60),
      placeholder: el.getAttribute('placeholder') || '',
      name: el.getAttribute('name') || '',
    };
  }).filter((rec) => rec !== null);
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
