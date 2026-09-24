export interface PathConfig {
  readonly music: string;
  readonly downloads: string;
  readonly youtube: string;
  readonly downloaded: string;
  readonly itunes: string;
  readonly bandcamp: string;
  readonly djMusic: string;
  readonly djPlaylists: string;
  readonly djPlaylistImport: string;
  readonly rename: string;
  readonly backup: string;
  readonly transfer: string;
}

export interface PlatformConfig {
  readonly isMac: boolean;
  readonly isWindows: boolean;
  readonly isLinux: boolean;
  readonly homeDir: string;
}

/**
 * Detects the current platform and returns platform-specific information
 */
export function detectPlatform(): PlatformConfig {
  const platform = Deno.build.os;
  const homeDir = Deno.env.get("HOME") || Deno.env.get("USERPROFILE") || "";

  return {
    isMac: platform === "darwin",
    isWindows: platform === "windows",
    isLinux: platform === "linux",
    homeDir,
  };
}

import { ConfigurationError } from "../core/utils/errors.ts";

export const PATH_ENV_VARS: Readonly<Record<keyof PathConfig, string>> = {
  music: "TUNEWRANGLER_MUSIC_PATH",
  downloads: "TUNEWRANGLER_DOWNLOADS_PATH",
  bandcamp: "TUNEWRANGLER_BANDCAMP_PATH",
  youtube: "TUNEWRANGLER_YOUTUBE_PATH",
  downloaded: "TUNEWRANGLER_DOWNLOADED_PATH",
  itunes: "TUNEWRANGLER_ITUNES_PATH",
  djMusic: "TUNEWRANGLER_DJMUSIC_PATH",
  djPlaylists: "TUNEWRANGLER_DJPLAYLISTS_PATH",
  djPlaylistImport: "TUNEWRANGLER_DJPLAYLISTIMPORT_PATH",
  rename: "TUNEWRANGLER_RENAME_PATH",
  backup: "TUNEWRANGLER_BACKUP_PATH",
  transfer: "TUNEWRANGLER_TRANSFER_PATH",
};

/**
 * A folder from its environment variable. No built-in default: a hardcoded path went stale
 * when the drive moved, and a missing variable is safer as an error than as a guess.
 */
export function getPath(key: keyof PathConfig): string {
  const name = PATH_ENV_VARS[key];
  const value = Deno.env.get(name)?.trim();
  if (!value) {
    throw new ConfigurationError(`${name} is not set — add it to .env (see .env.example)`, key);
  }
  // Callers build paths as `${dir}${name}`.
  return value.endsWith("/") || value.endsWith("\\") ? value : `${value}/`;
}

/** Every path whose variable is set; the unset ones are left out. */
export function loadConfig(): Partial<PathConfig> {
  const config: Partial<Record<keyof PathConfig, string>> = {};
  for (const key of Object.keys(PATH_ENV_VARS) as (keyof PathConfig)[]) {
    if (Deno.env.get(PATH_ENV_VARS[key])?.trim()) config[key] = getPath(key);
  }
  return config;
}

/**
 * Validates that all configured paths exist
 */
export async function validatePaths(
  config: Partial<PathConfig>,
): Promise<{ valid: boolean; errors: string[] }> {
  const errors: string[] = [];

  for (const key of Object.keys(PATH_ENV_VARS) as (keyof PathConfig)[]) {
    const path = config[key];
    if (path === undefined) {
      errors.push(`${PATH_ENV_VARS[key]} is not set`);
      continue;
    }
    try {
      await Deno.stat(path);
    } catch {
      errors.push(`Path '${key}' does not exist: ${path}`);
    }
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
