# SoundCloud Gate Automation — Design

**Date:** 2026-03-22

## Problem

Free downloads on SoundCloud are gated by third-party services (primarily Hypeddit, Toneden) that
require form interactions (email, name, comment, repost/follow) before releasing a download link.
The current approach uses a browser-use LLM agent to navigate these forms, which is:

- Slow (minutes per track on local hardware)
- Non-deterministic (LLM makes different choices each run)
- Fragile (prompt engineering required for each gate variation)
- Heavy (requires a local LLM running)

## Solution

Replace the LLM agent with a **deterministic, config-driven gate handler system** backed by
**stealth Playwright** (no LLM required).

## Architecture

### Phase 1 (unchanged)

SoundCloud API → list of track URLs (existing `playlist.py` implementation).

### Phase 2 (new)

For each track URL:

1. Navigate to SoundCloud track page with stealth Playwright
2. Find the free download button → click it → new tab opens with gate URL
3. Detect gate service from URL (e.g. `hypeddit.com` → Hypeddit handler)
4. Load that service's YAML step config
5. Interpreter walks the steps: check element presence, execute action, skip if optional and absent
6. Download triggers → move to next track

### Gate Handler Registry

```
soundcloud_dl/
  gate_handlers/
    __init__.py        # URL pattern → handler class registry
    base.py            # GateHandler ABC + YAML step interpreter + stealth helpers
    hypeddit.py        # thin subclass pointing to hypeddit.yaml
    hypeddit.yaml      # step definitions for Hypeddit gates
    toneden.py
    toneden.yaml
  playwright_browser.py  # stealth browser setup (replaces agent_task.py)
  recorder.py            # --record mode: codegen wrapper + YAML scaffolding
  main.py                # updated entrypoint: --record flag, new Phase 2
```

`agent_task.py` is removed. `browser-use` and all LLM dependencies are removed from
`pyproject.toml`.

## YAML Step Config Schema

Each gate service has a YAML file defining its steps. Steps are **presence-driven**, not
order-driven — the interpreter checks for each step's trigger element independently, so form field
ordering variations across tracks are handled automatically.

```yaml
gate: hypeddit
url_pattern: "hypeddit.com"

steps:
  - id: click_gate_button
    trigger: "#gateDownloadButton"
    action: click
    required: true

  - id: fill_email
    trigger: "input[type='email'], input[placeholder*='email' i]"
    action: fill
    value: "{{email}}"
    optional: true

  - id: fill_name
    trigger: "input[name='name'], input[placeholder*='name' i]"
    action: fill
    value: "{{name}}"
    optional: true

  - id: share_comment_gate
    trigger: "button:has-text('Share a comment')"
    action: click
    optional: true

  - id: fill_comment
    trigger: "textarea"
    action: fill
    value: "{{comment}}"
    depends_on: share_comment_gate

  - id: repost_soundcloud
    trigger: "button:has-text('Repost'), a:has-text('Repost')"
    action: click
    optional: true

  - id: final_download
    trigger: "button:has-text('Download'), a:has-text('Get Download')"
    action: click
    required: true
```

### Step Fields

| Field | Description |
|---|---|
| `id` | Unique step identifier (used by `depends_on`) |
| `trigger` | CSS selector(s) to detect presence of the element |
| `action` | `click`, `fill`, or `wait` |
| `value` | For `fill` actions; supports `{{template_vars}}` |
| `required` | If `true`, failure to find element fails the whole track |
| `optional` | If `true`, step is silently skipped when element not found |
| `depends_on` | Only runs if the named step executed (e.g. comment textarea after comment gate) |

Template vars injected from config: `{{email}}`, `{{name}}`, `{{comment}}`.

## Playwright Stealth Layer

`playwright-stealth` is applied to every page to suppress automation fingerprints
(`navigator.webdriver`, plugin arrays, language inconsistencies, etc.).

```python
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

context = await p.chromium.launch_persistent_context(
    user_data_dir=profile_dir,
    headless=not HEADED,
    args=["--disable-blink-features=AutomationControlled"],
)
page = await context.new_page()
await stealth_async(page)
```

### Human-like Behaviour (configurable via `.env`)

| Config var | Default | Description |
|---|---|---|
| `TUNEWRANGLER_SC_ACTION_DELAY_MIN_MS` | 300 | Min random pause between actions |
| `TUNEWRANGLER_SC_ACTION_DELAY_MAX_MS` | 900 | Max random pause between actions |
| `TUNEWRANGLER_SC_TYPE_DELAY_MS` | 80 | Per-keystroke delay when filling fields |
| `TUNEWRANGLER_SC_SCROLL_BEFORE_CLICK` | 1 | Scroll element into view before clicking |

### CAPTCHA Handling

No auto-solving. If SoundCloud presents a CAPTCHA, the browser is headed and paused. The user
solves it manually; the script detects completion and continues.

## Record Mode (Codegen Integration)

A `--record <gate-name> <url>` CLI flag bootstraps new gate configs:

```bash
uv run python -m soundcloud_dl.main --record hypeddit https://hypeddit.com/sometrack
```

This launches `playwright codegen` against the URL. The user walks through the gate manually.
On browser close, the recorder parses the generated selectors and writes a starter YAML to
`gate_handlers/<gate-name>.yaml` with steps pre-populated. The user then annotates:
`required`/`optional`, `depends_on`, template var substitutions.

## Dependencies

Remove from `pyproject.toml`:

- `browser-use`

Add:

- `playwright` (async API)
- `playwright-stealth`
- `pyyaml` (YAML config loading)

## Fallback Plan

If stealth Playwright still triggers bot detection on SoundCloud, the next step is to attach to
a real Chrome instance via CDP (`playwright.chromium.connect_over_cdp("http://localhost:9222")`).
The gate handler architecture, YAML configs, and step interpreter are unchanged — only the browser
setup differs.

## Out of Scope

- Auto-solving CAPTCHAs
- Handling phone-number gates (logged as failure, skipped)
- Supporting non-Playwright browsers (Firefox, Safari)
