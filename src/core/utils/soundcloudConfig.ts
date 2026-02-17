import { getFolder } from "./common.ts";

/**
 * Configuration for SoundCloud downloads and Hypeddit gate handling
 */
export interface SoundCloudConfig {
  /** Email to use for Hypeddit gates */
  email?: string;
  /** SoundCloud username for follow gates */
  soundcloudUsername?: string;
  /** Default comment text for comment gates */
  defaultComment?: string;
  /** SoundCloud OAuth token for authentication (bypasses login) */
  oauthToken?: string;
  /** Directory to save downloaded files */
  downloadDir: string;
  /** Browser automation settings */
  browser: {
    /** Run browser in headless mode (default: true) */
    headless: boolean;
    /** Timeout for browser operations in ms (default: 30000) */
    timeout: number;
    /** Delay between actions in ms to avoid rate limiting */
    actionDelay: number;
  };
  /** Rate limiting settings */
  rateLimit: {
    /** Delay between track downloads in ms */
    delayBetweenTracks: number;
    /** Maximum concurrent downloads */
    maxConcurrent: number;
  };
}

/**
 * Default configuration values
 */
export const DEFAULT_SOUNDCLOUD_CONFIG: SoundCloudConfig = {
  downloadDir: "",
  browser: {
    headless: true,
    timeout: 30000,
    actionDelay: 1000,
  },
  rateLimit: {
    delayBetweenTracks: 2000,
    maxConcurrent: 1,
  },
};

/**
 * Loads SoundCloud configuration from environment variables
 * Environment variables override default values
 */
export function loadSoundCloudConfig(): SoundCloudConfig {
  const config: SoundCloudConfig = {
    ...DEFAULT_SOUNDCLOUD_CONFIG,
    browser: { ...DEFAULT_SOUNDCLOUD_CONFIG.browser },
    rateLimit: { ...DEFAULT_SOUNDCLOUD_CONFIG.rateLimit },
  };

  // Load from environment variables
  const email = Deno.env.get("TUNEWRANGLER_SC_EMAIL");
  if (email) {
    config.email = email;
  }

  const username = Deno.env.get("TUNEWRANGLER_SC_USERNAME");
  if (username) {
    config.soundcloudUsername = username;
  }

  const comment = Deno.env.get("TUNEWRANGLER_SC_COMMENT");
  if (comment) {
    config.defaultComment = comment;
  }

  // OAuth token for SoundCloud authentication (bypasses login/captcha)
  const oauthToken = Deno.env.get("SOUNDCLOUD_OAUTH_TOKEN");
  if (oauthToken) {
    config.oauthToken = oauthToken;
  }

  const downloadDir = Deno.env.get("TUNEWRANGLER_SC_DOWNLOAD_DIR");
  if (downloadDir) {
    config.downloadDir = downloadDir;
  } else {
    // Fall back to the "downloaded" folder (same as renameMusic.ts uses)
    try {
      config.downloadDir = getFolder("downloaded");
    } catch {
      // If getFolder fails, use current directory
      config.downloadDir = "./downloads";
    }
  }

  // Browser settings
  const headless = Deno.env.get("TUNEWRANGLER_SC_HEADLESS");
  if (headless !== undefined) {
    config.browser.headless = headless.toLowerCase() !== "false";
  }

  const timeout = Deno.env.get("TUNEWRANGLER_SC_TIMEOUT");
  if (timeout) {
    const parsed = parseInt(timeout, 10);
    if (!isNaN(parsed)) {
      config.browser.timeout = parsed;
    }
  }

  const actionDelay = Deno.env.get("TUNEWRANGLER_SC_ACTION_DELAY");
  if (actionDelay) {
    const parsed = parseInt(actionDelay, 10);
    if (!isNaN(parsed)) {
      config.browser.actionDelay = parsed;
    }
  }

  // Rate limit settings
  const trackDelay = Deno.env.get("TUNEWRANGLER_SC_TRACK_DELAY");
  if (trackDelay) {
    const parsed = parseInt(trackDelay, 10);
    if (!isNaN(parsed)) {
      config.rateLimit.delayBetweenTracks = parsed;
    }
  }

  return config;
}

/**
 * Validates configuration for completeness
 * Returns warnings for missing optional values
 */
export function validateSoundCloudConfig(config: SoundCloudConfig): {
  valid: boolean;
  warnings: string[];
  errors: string[];
} {
  const warnings: string[] = [];
  const errors: string[] = [];

  // Check download directory
  if (!config.downloadDir) {
    errors.push("Download directory is not configured");
  }

  // Check for credentials (warnings only, not errors)
  if (!config.email) {
    warnings.push("No email configured - Hypeddit gates requiring email will be skipped");
  }

  if (!config.soundcloudUsername) {
    warnings.push("No SoundCloud username configured - follow gates will be skipped");
  }

  if (!config.defaultComment) {
    warnings.push("No default comment configured - comment gates will be skipped");
  }

  return {
    valid: errors.length === 0,
    warnings,
    errors,
  };
}

/**
 * Gate credentials extracted from config
 */
export interface GateCredentials {
  email?: string;
  soundcloudUsername?: string;
  defaultComment?: string;
}

/**
 * Extracts gate credentials from config
 */
export function getGateCredentials(config: SoundCloudConfig): GateCredentials {
  return {
    email: config.email,
    soundcloudUsername: config.soundcloudUsername,
    defaultComment: config.defaultComment,
  };
}
