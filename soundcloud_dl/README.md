# SoundCloud free-download automation

Python subproject (uv) for automating free downloads from a SoundCloud playlist.
Phase 1 uses the SoundCloud API; Phase 2 uses stealth Playwright to navigate gate
services (Hypeddit, Toneden) deterministically — no LLM required.

## Phase 1: Playlist extraction

Extracts track URLs from a single playlist using the SoundCloud API (no browser).

### Setup

1. **Register a SoundCloud app** to get API credentials: go to
   [SoundCloud Apps](https://soundcloud.com/you/apps), create an app, and note
   the **Client ID** and **Client Secret**.

2. Install Playwright Chromium (required, one-time):

   ```bash
   cd soundcloud_dl && uv run playwright install chromium
   ```

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

   # Optional: show browser window (useful for first login to SoundCloud)
   TUNEWRANGLER_SC_HEADED=1
   ```

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
extracts track URLs via the SoundCloud API. Phase 2 runs stealth Playwright for
each track to find the free download button, navigate to the gate service
(Hypeddit or Toneden), and fill the form using a YAML-driven step config.

## Phase 2: Per-track gate automation

For each track URL from Phase 1, Playwright navigates the track page, finds and
clicks the free download button, then navigates to the gate service and fills
the form automatically using configuration from
`soundcloud_dl/gate_handlers/<gate-name>.yaml`.

Supported gates: **Hypeddit** (`hypeddit.com`), **Toneden** (`toneden.io`).

## Persistent browser profile

By default a persistent Chromium profile is stored at `soundcloud_browser_profile/`
at the project root. On first run with `TUNEWRANGLER_SC_HEADED=1`, log into
SoundCloud — subsequent runs reuse that session.

Set `TUNEWRANGLER_SC_BROWSER_PROFILE=0` to use an ephemeral session. Set to an
absolute path to use a custom location.

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
| `TUNEWRANGLER_SC_EMAIL` | `tdseitz10@outlook.com` | Email for gate forms |
| `TUNEWRANGLER_SC_NAME` | `Tom` | Name for gate forms |
| `TUNEWRANGLER_SC_COMMENT` | `🔥🔥🔥` | Comment for gate forms |
| `TUNEWRANGLER_SC_HEADED` | `0` | Show browser window (set to `1`) |
| `TUNEWRANGLER_SC_BROWSER_PROFILE` | `soundcloud_browser_profile/` | Persistent profile path or `0` to disable |
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
