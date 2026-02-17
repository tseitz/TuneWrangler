import { parse } from "https://deno.land/std@0.224.0/flags/mod.ts";
import { load as loadEnv } from "https://deno.land/std@0.224.0/dotenv/mod.ts";
import { join } from "https://deno.land/std@0.224.0/path/mod.ts";
import { downloadSoundCloudPlaylist } from "../../processors/downloadSoundCloudPlaylist.ts";
import { getFolder } from "../../core/utils/common.ts";
import { info, error, warn, debug } from "../../core/utils/logger.ts";
import { loadSoundCloudConfig } from "../../core/utils/soundcloudConfig.ts";
import { HypedditGateHandler } from "../../core/utils/hypedditGate.ts";

// Load .env file at module initialization
try {
  await loadEnv({ export: true });
} catch {
  // .env file may not exist, that's okay
}

// Default session storage path (in user's home directory)
const SESSION_PATH = join(Deno.env.get("HOME") || ".", ".tunewrangler", "browser-session");

export interface SoundCloudDownloadOptions {
  url: string;
  outputDir: string;
  headed: boolean;
  skipGates: boolean;
  email?: string;
  soundcloudUsername?: string;
  defaultComment?: string;
  dryRun: boolean;
  sessionPath?: string;
}

/**
 * SoundCloud download command handler
 * 
 * Downloads free tracks from SoundCloud playlists via download gates (Hypeddit, ToneDen, etc.).
 * This does NOT rip or stream audio from SoundCloud - it only downloads original files
 * that artists have made available for free download.
 * 
 * @param args - Command line arguments (parsed by parse function)
 * @throws Error if playlist URL is invalid or download fails
 */
export async function soundcloudDownload(args: string[]): Promise<void> {
  const flags = parse(args, {
    boolean: ["help", "headed", "skip-gates", "dry-run", "login"],
    string: ["url", "output", "email", "username", "comment"],
    alias: {
      help: "h",
      url: "u",
      output: "o",
      headed: "H",
      "skip-gates": "s",
      email: "e",
      username: "U",
      comment: "c",
      "dry-run": "d",
      login: "L",
    },
    default: {
      headed: false,
      "skip-gates": false,
      "dry-run": false,
      login: false,
    },
  });

  if (flags.help) {
    console.log(`
🎵 TuneWrangler soundcloud-download

Download FREE tracks from SoundCloud playlists via download gates (Hypeddit,
Toneden, etc.). This tool automates the process of completing gate requirements
(email signup, follow, like, comment) to download the ORIGINAL high-quality
files that artists have made available for free.

IMPORTANT: This does NOT rip or stream audio from SoundCloud. It only downloads
original files from download gate platforms where artists offer free downloads.

USAGE:
  tunewrangler soundcloud-download --url <playlist-url> [options]
  tunewrangler soundcloud-download --login  # Login to SoundCloud first

OPTIONS:
  --help, -h              Show this help message
  --url, -u <url>         SoundCloud playlist URL (required unless --login)
  --output, -o <dir>      Output directory for downloads (default: downloaded folder)
  --headed, -H            Run browser in headed mode (visible) for debugging
  --login, -L             Login to SoundCloud (saves session for future runs)
  --email, -e <email>     Email to use for Hypeddit gates (required for most gates)
  --username, -U <name>   SoundCloud username for follow gates
  --comment, -c <text>    Default comment for comment gates
  --dry-run, -d           Show what would be downloaded without downloading

CONFIGURATION:
  Set these via environment variables in your .env file:
  - TUNEWRANGLER_SC_EMAIL: Email for Hypeddit gates (required)
  - TUNEWRANGLER_SC_USERNAME: SoundCloud username for follow gates
  - TUNEWRANGLER_SC_COMMENT: Default comment text (e.g., "🔥🔥🔥")

EXAMPLES:
  # First time: Login to SoundCloud (session saved for future runs)
  tunewrangler soundcloud-download --login
  
  # Then download from playlists (uses saved session)
  tunewrangler soundcloud-download --url "https://soundcloud.com/user/sets/playlist"
  tunewrangler soundcloud-download -u "https://soundcloud.com/user/sets/playlist" --headed
  tunewrangler soundcloud-download -u "https://soundcloud.com/user/sets/playlist" --dry-run

HOW IT WORKS:
  1. Scans the playlist for tracks with download gate links in their descriptions
  2. Opens each gate URL in a browser (headless by default, use --headed to watch)
  3. Automatically completes gate requirements using your credentials
  4. Downloads the original high-quality file the artist uploaded
  5. Saves to your configured output directory with "Artist - Title" naming

SESSION MANAGEMENT:
  The browser session is saved to ~/.tunewrangler/browser-session/
  Use --login once to authenticate with SoundCloud, then the session persists.
`);
    return;
  }

  // Handle login mode
  if (flags.login) {
    info("🔐 Starting SoundCloud login flow...");
    const handler = new HypedditGateHandler();
    try {
      const success = await handler.loginToSoundCloud({
        headless: false, // Always headed for login
        timeout: 60000,
        actionDelay: 1000,
        outputDir: getFolder("downloaded"),
        sessionPath: SESSION_PATH,
      });
      
      if (success) {
        console.log("\n✅ Login successful! Session saved.");
        console.log("   You can now run downloads without logging in again.\n");
      } else {
        console.log("\n⚠️ Login was not completed.");
        console.log("   Please try again and complete the login in the browser.\n");
      }
    } finally {
      await handler.close();
    }
    return;
  }

  // Validate required URL
  let url = flags.url;
  if (!url) {
    error("Playlist URL is required");
    console.error("❌ Playlist URL is required. Use --url or -u to specify.");
    console.log("Run 'tunewrangler soundcloud-download --help' for usage information.");
    Deno.exit(1);
  }

  // Clean the URL - remove shell escape artifacts and query params
  url = cleanSoundCloudUrl(url);
  debug("Cleaned URL", { original: flags.url, cleaned: url });

  // Validate URL format
  if (!isValidSoundCloudPlaylistUrl(url)) {
    error("Invalid SoundCloud playlist URL", undefined, { url });
    console.error("❌ Invalid SoundCloud playlist URL.");
    console.log("Expected format: https://soundcloud.com/username/sets/playlist-name");
    Deno.exit(1);
  }

  try {
    // Load configuration from env vars and config file
    const config = loadSoundCloudConfig();

    // CLI flags override config file values
    // Default to "downloaded" folder (same as renameMusic.ts uses)
    const outputDir = flags.output || config.downloadDir || getFolder("downloaded");

    const options: SoundCloudDownloadOptions = {
      url,
      outputDir,
      headed: flags.headed || !config.browser.headless,
      skipGates: flags["skip-gates"],
      email: flags.email || config.email,
      soundcloudUsername: flags.username || config.soundcloudUsername,
      defaultComment: flags.comment || config.defaultComment,
      dryRun: flags["dry-run"],
      sessionPath: SESSION_PATH,
    };

    info("🎵 Starting SoundCloud playlist download", {
      url: options.url,
      outputDir: options.outputDir,
      headed: options.headed,
      skipGates: options.skipGates,
      dryRun: options.dryRun,
    });

    if (options.dryRun) {
      warn("🔍 Dry run mode - no files will be downloaded");
    }

    // Check for required credentials if not skipping gates
    if (!options.skipGates && !options.email) {
      warn("⚠️  No email configured for Hypeddit gates. Gates requiring email will be skipped.");
      warn("   Set via --email flag or TUNEWRANGLER_SC_EMAIL environment variable.");
    }

    const results = await downloadSoundCloudPlaylist(options);

    // Display results
    console.log("\n📊 Download Summary:");
    console.log(`   Total tracks: ${results.total}`);
    console.log(`   Downloaded: ${results.downloaded}`);
    console.log(`   Skipped: ${results.skipped}`);
    console.log(`   Failed: ${results.failed}`);

    if (results.errors.length > 0) {
      console.log("\n❌ Errors:");
      for (const err of results.errors) {
        console.log(`   - ${err.track}: ${err.reason}`);
      }
    }

    info("✅ SoundCloud download complete!", {
      total: results.total,
      downloaded: results.downloaded,
      skipped: results.skipped,
      failed: results.failed,
    });
  } catch (err) {
    error("Failed to download SoundCloud playlist", err as Error);
    console.error(`❌ Failed to download playlist: ${(err as Error).message}`);
    Deno.exit(1);
  }
}

/**
 * Cleans a SoundCloud URL by removing shell escape artifacts and unnecessary query params
 */
function cleanSoundCloudUrl(url: string): string {
  // Remove shell escape backslashes (e.g., \? becomes ?, \& becomes &)
  let cleaned = url.replace(/\\([?&=])/g, "$1");

  // Parse the URL to extract just the essential parts
  try {
    const parsed = new URL(cleaned);

    // Keep only the essential path (remove tracking params but keep secret token if present)
    // Secret playlists have format: /sets/playlist-name/s-SECRETTOKEN
    const pathMatch = parsed.pathname.match(/^(\/[^/]+\/sets\/[^/]+(?:\/s-[a-zA-Z0-9]+)?)/);
    if (pathMatch) {
      cleaned = `${parsed.origin}${pathMatch[1]}`;
    } else {
      cleaned = `${parsed.origin}${parsed.pathname}`;
    }
  } catch {
    // If URL parsing fails, just return the escape-cleaned version
  }

  return cleaned;
}

/**
 * Validates that a URL is a valid SoundCloud playlist URL
 */
function isValidSoundCloudPlaylistUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    // Check if it's a soundcloud.com URL with /sets/ in the path
    return (
      parsed.hostname === "soundcloud.com" ||
      parsed.hostname === "www.soundcloud.com" ||
      parsed.hostname.endsWith(".soundcloud.com")
    ) && parsed.pathname.includes("/sets/");
  } catch {
    return false;
  }
}
