# SoundCloud free-download automation

Python subproject (uv) for automating free downloads from a SoundCloud playlist.
Phase 1 uses the SoundCloud API; Phase 2 attaches to a dedicated Google Chrome
instance via the Chrome DevTools Protocol (CDP) and navigates gate services
(Hypeddit, Toneden) deterministically — no LLM required.

## Phase 1: Playlist extraction

Extracts track URLs from a single playlist using the SoundCloud API (no browser).

### Setup

1. **Register a SoundCloud app** to get API credentials: go to
   [SoundCloud Apps](https://soundcloud.com/you/apps), create an app, and note
   the **Client ID** and **Client Secret**.

2. Ensure Google Chrome is installed. On macOS the default path is
   `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
   On Linux/Windows, set `TUNEWRANGLER_SC_CHROME_PATH` explicitly.

3. Create `.env` at TuneWrangler root or in `soundcloud_dl/`:

   ```env
   # Phase 1: SoundCloud API
   TUNEWRANGLER_SC_PLAYLIST_URL=https://soundcloud.com/your-username/sets/your-playlist
   SOUNDCLOUD_CLIENT_ID=your_client_id
   SOUNDCLOUD_CLIENT_SECRET=your_client_secret

   # Phase 2: Gate form values
   TUNEWRANGLER_SC_EMAIL=your@email.com
   TUNEWRANGLER_SC_NAME=YourName
   TUNEWRANGLER_SC_COMMENT=🔥🔥🔥
   ```

   See `.env.example` for the full list of optional Phase 2 settings.

## Running

From the `soundcloud_dl` directory:

```bash
cd soundcloud_dl
uv run python -m soundcloud_dl.main
```

Or from repo root:

```bash
uv run --project soundcloud_dl soundcloud-dl
```

Logs go to `logs/soundcloud_dl.log` (at TuneWrangler root) and console. Phase 1
extracts track URLs via the SoundCloud API. Phase 2 attaches to a dedicated
Chrome instance via CDP, navigates each track page, finds the free download
button, navigates to the gate service (Hypeddit or Toneden), and fills the form
using a YAML-driven step config.

## Phase 2: per-track gate automation

For each track URL from Phase 1, the script attaches to your dedicated Chrome via
CDP, navigates to the track page, finds the free-download button, navigates to the
gate service, and fills the form using the YAML step config in
`soundcloud_dl/gate_handlers/<gate-name>.yaml`.

If a captcha appears mid-flow (rare with real Chrome), the tab is left open and the
track is recorded as `captcha_pending` — process the open tabs manually at the end.

If the gate sequence stalls without a captcha (likely a new gate variant), the tab
is left open and the track is recorded as `manual_review` — consider running
`--record` mode to add a handler for it.

Supported gates: **Hypeddit** (`hypeddit.com`), **Toneden** (`toneden.io`).

## Dedicated Chrome instance

Phase 2 attaches to a real Google Chrome instance via the Chrome DevTools Protocol
(CDP). On first run, the script launches Chrome with a dedicated profile directory
(`soundcloud_dl_chrome_profile/` at the repo root by default) and a debug port
(9222 by default). This profile is fully isolated from your main Chrome — different
cookies, different login sessions, different windows.

**First run:**

1. Run the script. A new Chrome window opens (signed out).
2. The script pauses with a console message: *"Please log in in the open Chrome
   window, then press Enter."*
3. Log into SoundCloud (using whichever account you want for downloads).
4. Press Enter in the terminal.

**Subsequent runs:** the profile remembers the session. The script detects the
logged-in state and continues straight to processing.

**Multi-account use:** because the dedicated profile is isolated, you can stay
logged into a different SoundCloud account in your main Chrome — the two never
interfere.

## Record mode (add new gate configs)

Bootstrap a new gate YAML config by recording a manual walkthrough:

```bash
uv run python -m soundcloud_dl.main --record toneden https://toneden.io/sometrack
```

This launches `playwright codegen`, lets you walk through the gate manually, then
scaffolds a starter YAML at `soundcloud_dl/gate_handlers/<gate-name>.yaml`.

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `TUNEWRANGLER_SC_PLAYLIST_URL` | — | SoundCloud playlist URL (required) |
| `SOUNDCLOUD_CLIENT_ID` | — | SoundCloud API client ID (required) |
| `SOUNDCLOUD_CLIENT_SECRET` | — | SoundCloud API client secret (required) |
| `TUNEWRANGLER_SC_EMAIL` | — | Email for gate forms (required). No default — gate runs refuse to start without it. |
| `TUNEWRANGLER_SC_NAME` | `Tom` | Name for gate forms |
| `TUNEWRANGLER_SC_COMMENT` | `🔥🔥🔥` | Comment for gate forms |
| `TUNEWRANGLER_SC_CHROME_PATH` | macOS Chrome path | Path to real Chrome binary. Required to be set on Linux/Windows. |
| `TUNEWRANGLER_SC_CHROME_PROFILE_DIR` | `soundcloud_dl_chrome_profile/` | Dedicated profile dir for the bot's Chrome. |
| `TUNEWRANGLER_SC_CHROME_DEBUG_PORT` | `9222` | CDP debug port. |
| `TUNEWRANGLER_SC_DOWNLOAD_DIR` | — | Download destination directory |
| `TUNEWRANGLER_SC_DELAY_SECONDS` | `3` | Seconds between tracks |
| `TUNEWRANGLER_SC_ACTION_DELAY_MIN_MS` | `300` | Min random pause between gate actions (ms) |
| `TUNEWRANGLER_SC_ACTION_DELAY_MAX_MS` | `900` | Max random pause between gate actions (ms) |
| `TUNEWRANGLER_SC_TYPE_DELAY_MS` | `80` | Per-keystroke delay when filling fields (ms) |
| `TUNEWRANGLER_SC_SCROLL_BEFORE_CLICK` | `1` | Scroll element into view before clicking |
| `TUNEWRANGLER_SC_PAGE_LOAD_WAIT` | `3` | Seconds to wait after SoundCloud page load |
| `TUNEWRANGLER_SC_RESUME` | `1` | Skip already-processed tracks |
| `TUNEWRANGLER_SC_PLAYLIST_CACHE` | `1` | Cache playlist track list |

## Dev

```bash
cd soundcloud_dl
uv run ruff check soundcloud_dl && uv run ruff format soundcloud_dl
uv run ty check soundcloud_dl
uv run pytest tests/ -v
```
