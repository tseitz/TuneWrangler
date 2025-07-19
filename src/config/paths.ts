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

/**
 * Gets the default paths based on the current platform
 */
export function getDefaultPaths(): PathConfig {
  const platform = detectPlatform();

  if (platform.isMac) {
    const transferMusic = "/Users/tseitz/Dropbox/TransferMusic";
    return {
      music: `${transferMusic}Music/`,
      downloads: "/Users/tseitz/Downloads/",
      bandcamp: `${transferMusic}/Downloaded/bandcamp/`,
      youtube: `${transferMusic}/Youtube/`,
      downloaded: `${transferMusic}/Downloaded/`,
      itunes: `${transferMusic}/Downloaded/itunes/Music`,
      djMusic: "/Users/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Collection/",
      djPlaylists: "/Users/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Playlist Backups/",
      djPlaylistImport: "/Users/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Playlist Backups/Import/",
      rename: `${transferMusic}/Renamed/`,
      backup: `${transferMusic}/bak/`,
      transfer: transferMusic,
    };
  } else if (platform.isWindows) {
    return {
      music: "G:\\Dropbox\\Music\\",
      downloads: "C:\\Users\\tdsei\\Downloads\\",
      bandcamp: "G:\\Dropbox\\TransferMusic\\bandcamp\\",
      youtube: "G:\\Dropbox\\TransferMusic\\Youtube\\",
      downloaded: "G:\\Dropbox\\TransferMusic\\Downloaded\\",
      itunes: "G:\\Dropbox\\TransferMusic\\Downloaded\\itunes\\Music",
      djMusic: "G:\\Dropbox\\DJ\\Dane Dubz DJ Music\\Collection\\",
      djPlaylists: "G:\\Dropbox\\DJ\\Dane Dubz DJ Music\\Playlist Backups\\",
      djPlaylistImport: "G:\\Dropbox\\DJ\\Dane Dubz DJ Music\\Playlist Backups\\Import\\",
      rename: "G:\\Dropbox\\TransferMusic\\Renamed\\",
      backup: "G:\\Dropbox\\TransferMusic\\bak\\",
      transfer: "G:\\Dropbox\\TransferMusic\\",
    };
  } else {
    // Linux
    return {
      music: "/media/tseitz/Storage SSD/Dropbox/Music/",
      downloads: "/home/tseitz/Downloads/",
      bandcamp: "/home/tseitz/Dropbox/TransferMusic/bandcamp/",
      youtube: "/home/tseitz/Dropbox/TransferMusic/Youtube/",
      downloaded: "/home/tseitz/Dropbox/TransferMusic/Downloaded/",
      itunes: "/home/tseitz/Dropbox/TransferMusic/Downloaded/itunes/Music",
      djMusic: "/home/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Collection/",
      djPlaylists: "/home/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Playlist Backups/",
      djPlaylistImport: "/home/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Playlist Backups/Import/",
      rename: "/home/tseitz/Dropbox/TransferMusic/Renamed/",
      backup: "/home/tseitz/Dropbox/TransferMusic/bak/",
      transfer: "/home/tseitz/Dropbox/TransferMusic/",
    };
  }
}

/**
 * Loads configuration from environment variables, falling back to defaults
 */
export function loadConfig(): PathConfig {
  const defaults = getDefaultPaths();

  return {
    music: Deno.env.get("TUNEWRANGLER_MUSIC_PATH") || defaults.music,
    downloads: Deno.env.get("TUNEWRANGLER_DOWNLOADS_PATH") || defaults.downloads,
    bandcamp: Deno.env.get("TUNEWRANGLER_BANDCAMP_PATH") || defaults.bandcamp,
    youtube: Deno.env.get("TUNEWRANGLER_YOUTUBE_PATH") || defaults.youtube,
    downloaded: Deno.env.get("TUNEWRANGLER_DOWNLOADED_PATH") || defaults.downloaded,
    itunes: Deno.env.get("TUNEWRANGLER_ITUNES_PATH") || defaults.itunes,
    djMusic: Deno.env.get("TUNEWRANGLER_DJMUSIC_PATH") || defaults.djMusic,
    djPlaylists: Deno.env.get("TUNEWRANGLER_DJPLAYLISTS_PATH") || defaults.djPlaylists,
    djPlaylistImport: Deno.env.get("TUNEWRANGLER_DJPLAYLISTIMPORT_PATH") || defaults.djPlaylistImport,
    rename: Deno.env.get("TUNEWRANGLER_RENAME_PATH") || defaults.rename,
    backup: Deno.env.get("TUNEWRANGLER_BACKUP_PATH") || defaults.backup,
    transfer: Deno.env.get("TUNEWRANGLER_TRANSFER_PATH") || defaults.transfer,
  };
}

/**
 * Validates that all configured paths exist
 */
export async function validatePaths(config: PathConfig): Promise<{ valid: boolean; errors: string[] }> {
  const errors: string[] = [];

  for (const [key, path] of Object.entries(config)) {
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
