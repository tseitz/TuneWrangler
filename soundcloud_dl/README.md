# SoundCloud free-download automation

Python subproject (uv) for automating free downloads from a SoundCloud playlist. Phase 1 uses the [SoundCloud API](https://developers.soundcloud.com/docs/api/guide); Phase 2 (planned) will use [browser-use](https://github.com/browser-use/browser-use) for per-track download flows.

## Phase 1: Playlist extraction (implemented)

Extracts track URLs from a single playlist using the SoundCloud API (no browser).

### Setup

1. **Register a SoundCloud app** to get API credentials: go to [SoundCloud Apps](https://soundcloud.com/you/apps), create an app, and note the **Client ID** and **Client Secret**.

2. From repo root, `.env` is read from the TuneWrangler root. Create `.env` there (or in `soundcloud_dl/`) with:

   ```env
   TUNEWRANGLER_SC_PLAYLIST_URL=https://soundcloud.com/your-username/sets/your-playlist
   SOUNDCLOUD_CLIENT_ID=your_client_id
   SOUNDCLOUD_CLIENT_SECRET=your_client_secret
   ```

   Optional for Phase 2: `TUNEWRANGLER_SC_EMAIL`, `TUNEWRANGLER_SC_USERNAME`, `TUNEWRANGLER_SC_COMMENT`, and `TUNEWRANGLER_SC_HEADED`.

### Run Phase 1

From the `soundcloud_dl` project directory:

```bash
cd soundcloud_dl
uv run python -m soundcloud_dl.main
```

Or from repo root:

```bash
cd soundcloud_dl && uv run python -m soundcloud_dl.main
```

Logs go to `logs/soundcloud_dl.log` (under TuneWrangler root) and to the console.

### Dev

```bash
cd soundcloud_dl
uv run ruff check soundcloud_dl && uv run ruff format soundcloud_dl
uv run ty check soundcloud_dl
```

## Phase 2 (planned)

Per-track browser-use agent to click free download and handle email/comment/social prompts.
