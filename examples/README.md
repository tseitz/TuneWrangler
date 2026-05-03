# Examples

## `env.example`

Template for the repo-root `.env` file. Copy and fill in:

```bash
cp examples/env.example .env
$EDITOR .env
```

Variables fall into two namespaces:

- `TUNEWRANGLER_*_PATH` — path overrides for the main Deno tool. Defaults
  live in [`src/config/paths.ts`](../src/config/paths.ts) and are platform-specific.
- `TUNEWRANGLER_SC_*` and `SOUNDCLOUD_CLIENT_*` — soundcloud_dl config.

After editing, verify the main-tool paths exist:

```bash
deno task validate
```
