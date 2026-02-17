import { ensureDir } from "https://deno.land/std@0.224.0/fs/mod.ts";
import { join } from "https://deno.land/std@0.224.0/path/mod.ts";
import { debug, info, warn, error } from "../core/utils/logger.ts";
import { SoundCloudScraper, TrackInfo, PlaylistInfo } from "../core/utils/soundcloudScraper.ts";
import { HypedditGateHandler, BrowserOptions } from "../core/utils/hypedditGate.ts";
import { loadSoundCloudConfig, getGateCredentials, GateCredentials } from "../core/utils/soundcloudConfig.ts";
import { SoundCloudDownloadOptions } from "../cli/commands/soundcloud.ts";
import { delay, sanitizeFilename as sanitizeFilenameUtil } from "../core/utils/common.ts";

/**
 * Result of a single track download attempt
 */
export interface TrackDownloadResult {
  track: TrackInfo;
  status: "downloaded" | "skipped" | "failed";
  filePath?: string;
  error?: string;
  gateUrl?: string;
}

/**
 * Overall result of playlist download
 */
export interface PlaylistDownloadResult {
  playlist: PlaylistInfo;
  total: number;
  downloaded: number;
  skipped: number;
  failed: number;
  results: TrackDownloadResult[];
  errors: Array<{ track: string; reason: string }>;
}

/**
 * Downloads free tracks from a SoundCloud playlist via download gates (Hypeddit, Toneden, etc.)
 *
 * IMPORTANT: This does NOT rip/stream audio from SoundCloud.
 * It only downloads original high-quality files that artists have made available
 * for free download via download gate platforms.
 */
export async function downloadSoundCloudPlaylist(
  options: SoundCloudDownloadOptions
): Promise<PlaylistDownloadResult> {
  const scraper = new SoundCloudScraper();
  const gateHandler = new HypedditGateHandler();

  const config = loadSoundCloudConfig();
  const credentials = getGateCredentials(config);

  // Ensure output directory exists
  await ensureDir(options.outputDir);

  info("🎵 Starting SoundCloud free download extraction", {
    url: options.url,
    outputDir: options.outputDir,
    dryRun: options.dryRun,
  });

  console.log("\n📋 NOTE: This tool only downloads original files from download gates");
  console.log("   (Hypeddit, Toneden, etc.) - NOT ripped/streamed SoundCloud audio.\n");

  // Step 1: Extract playlist information
  info("📋 Fetching playlist information...");
  let playlist: PlaylistInfo;

  // Use browser-based scraping for private playlists (URLs with /s- token)
  const isPrivatePlaylist = options.url.includes("/s-");
  const useBrowser = isPrivatePlaylist;
  const headless = !options.headed;

  try {
    playlist = await scraper.extractPlaylistTracks(options.url, useBrowser, headless);
  } catch (err) {
    error("Failed to fetch playlist", err as Error);
    throw new Error(`Failed to fetch playlist: ${(err as Error).message}`);
  }

  info(`📋 Found ${playlist.tracks.length} tracks in "${playlist.title}" by ${playlist.creator}`);

  const results: TrackDownloadResult[] = [];
  const errors: Array<{ track: string; reason: string }> = [];
  let downloaded = 0;
  let skipped = 0;
  let failed = 0;

  // Browser options for gate handling
  const browserOptions: BrowserOptions = {
    headless: !options.headed,
    timeout: config.browser.timeout,
    actionDelay: config.browser.actionDelay,
    outputDir: options.outputDir,
    sessionPath: options.sessionPath,
    oauthToken: config.oauthToken,
  };

  // Override credentials from CLI if provided
  const effectiveCredentials: GateCredentials = {
    email: options.email || credentials.email,
    soundcloudUsername: options.soundcloudUsername || credentials.soundcloudUsername,
    defaultComment: options.defaultComment || credentials.defaultComment,
  };

  // Step 2: De-duplicate tracks (browser scraping can pick up duplicates)
  const seenTracks = new Set<string>();
  const uniqueTracks: TrackInfo[] = [];
  
  for (const track of playlist.tracks) {
    // Create a unique key from artist + title
    const key = `${track.artist}-${track.title}`.toLowerCase();
    if (!seenTracks.has(key)) {
      seenTracks.add(key);
      uniqueTracks.push(track);
    }
  }
  
  if (uniqueTracks.length !== playlist.tracks.length) {
    info(`📋 Removed ${playlist.tracks.length - uniqueTracks.length} duplicate tracks`);
  }

  // Step 3: For each track, we need to find the download gate URL
  // This requires visiting each track page to find the gate link in the description
  info("🔍 Scanning tracks for download gate links...");
  console.log("   (Fetching track details from SoundCloud API...)\n");

  const tracksWithGates: Array<{ track: TrackInfo; gateUrl: string }> = [];
  const tracksWithoutGates: TrackInfo[] = [];

  for (let i = 0; i < uniqueTracks.length; i++) {
    const track = uniqueTracks[i];
    console.log(`   [${i + 1}/${uniqueTracks.length}] Checking: ${track.artist} - ${track.title}`);
    
    // If we already have a gate URL from the scraper, use it
    if (track.gateUrl) {
      console.log(`      ✅ Gate URL found in initial scrape`);
      tracksWithGates.push({ track, gateUrl: track.gateUrl });
    } else if (track.url && track.url.includes("soundcloud.com")) {
      // We need to fetch the track page to find the gate URL
      let foundGate = false;
      
      // First try: API call to get description
      try {
        debug(`Fetching track details from API: ${track.url}`);
        const trackDetails = await scraper.extractTrackInfo(track.url);
        
        if (trackDetails.gateUrl) {
          console.log(`      ✅ Gate URL found in description: ${trackDetails.gateUrl}`);
          tracksWithGates.push({ track: trackDetails, gateUrl: trackDetails.gateUrl });
          foundGate = true;
        }
      } catch (err) {
        debug(`API fetch failed: ${(err as Error).message}`);
      }
      
      // Second try: Browser scraping to find "Free DL" button or hidden links
      if (!foundGate) {
        console.log(`      🔍 Checking track page for download buttons...`);
        try {
          const browserGateUrl = await scraper.extractGateUrlWithBrowser(track.url, !options.headed);
          if (browserGateUrl) {
            console.log(`      ✅ Gate URL found on track page: ${browserGateUrl}`);
            tracksWithGates.push({ track, gateUrl: browserGateUrl });
            foundGate = true;
          }
        } catch (err) {
          debug(`Browser extraction failed: ${(err as Error).message}`);
        }
      }
      
      if (!foundGate) {
        console.log(`      ❌ No download gate found`);
        tracksWithoutGates.push(track);
      }

      // Small delay to avoid rate limiting
      await delay(1000);
    } else {
      console.log(`      ❌ No valid track URL to fetch details from`);
      debug(`Track URL was: "${track.url}"`);
      tracksWithoutGates.push(track);
    }
  }

  console.log(`\n📊 Scan Results:`);
  console.log(`   Tracks with download gates: ${tracksWithGates.length}`);
  console.log(`   Tracks without download gates: ${tracksWithoutGates.length}`);

  if (tracksWithoutGates.length > 0) {
    console.log(`\n⚠️  Tracks without free download gates (will be skipped):`);
    for (const track of tracksWithoutGates) {
      console.log(`   - ${track.artist} - ${track.title}`);
      results.push({
        track,
        status: "skipped",
        error: "No download gate found in track description",
      });
      skipped++;
    }
  }

  if (tracksWithGates.length === 0) {
    console.log("\n❌ No tracks with download gates found in this playlist.");
    return {
      playlist,
      total: playlist.tracks.length,
      downloaded: 0,
      skipped: playlist.tracks.length,
      failed: 0,
      results,
      errors,
    };
  }

  console.log(`\n🎵 Processing ${tracksWithGates.length} tracks with download gates...\n`);

  try {
    // Step 3: Process each track with a gate
    for (let i = 0; i < tracksWithGates.length; i++) {
      const { track, gateUrl } = tracksWithGates[i];
      const trackNum = i + 1;
      const trackName = `${track.artist} - ${track.title}`;

      info(`[${trackNum}/${tracksWithGates.length}] Processing: ${trackName}`);
      debug("Gate URL", { gateUrl });

      if (options.dryRun) {
        // Dry run - just report what would happen
        console.log(`  📥 Would download via gate: ${gateUrl}`);
        results.push({
          track,
          status: "downloaded",
          gateUrl,
        });
        downloaded++;
        continue;
      }

      // Process the download gate
      const result = await processGateDownload(
        track,
        gateUrl,
        gateHandler,
        effectiveCredentials,
        options,
        browserOptions
      );

      results.push(result);

      if (result.status === "downloaded") {
        downloaded++;
        console.log(`  ✅ Downloaded: ${result.filePath}`);
      } else if (result.status === "skipped") {
        skipped++;
        console.log(`  ⏭️ Skipped: ${result.error}`);
      } else {
        failed++;
        console.log(`  ❌ Failed: ${result.error}`);
        errors.push({ track: trackName, reason: result.error || "Unknown error" });
      }

      // Rate limiting delay between tracks
      if (i < tracksWithGates.length - 1) {
        await delay(config.rateLimit.delayBetweenTracks);
      }
    }
  } finally {
    // Cleanup browser if it was used
    await gateHandler.close();
  }

  return {
    playlist,
    total: playlist.tracks.length,
    downloaded,
    skipped,
    failed,
    results,
    errors,
  };
}

/**
 * Process a single track's download gate to get the original file
 */
async function processGateDownload(
  track: TrackInfo,
  gateUrl: string,
  gateHandler: HypedditGateHandler,
  credentials: GateCredentials,
  options: SoundCloudDownloadOptions,
  browserOptions: BrowserOptions
): Promise<TrackDownloadResult> {
  info(`🔓 Processing download gate: ${gateUrl}`);

  try {
    const gateResult = await gateHandler.bypassGate(gateUrl, credentials, browserOptions);

    if (gateResult.success) {
      // If we got a download URL but not a file, download it
      if (gateResult.downloadUrl && !gateResult.downloadedFilePath) {
        // Try to determine extension from URL, default to original format
        const extension = getExtensionFromUrl(gateResult.downloadUrl) || ".mp3";
        const filename = `${sanitizeFilenameUtil(track.artist)} - ${sanitizeFilenameUtil(track.title)}${extension}`;
        const filePath = join(options.outputDir, filename);

        try {
          await downloadFromUrl(gateResult.downloadUrl, filePath);
          return {
            track,
            status: "downloaded",
            filePath,
            gateUrl,
          };
        } catch (err) {
          return {
            track,
            status: "failed",
            error: `Download failed: ${(err as Error).message}`,
            gateUrl,
          };
        }
      }

      return {
        track,
        status: "downloaded",
        filePath: gateResult.downloadedFilePath,
        gateUrl,
      };
    }

    if (gateResult.skipped) {
      return {
        track,
        status: "skipped",
        error: gateResult.skipReason || "Gate requirements not met",
        gateUrl,
      };
    }

    // Gate bypass failed
    return {
      track,
      status: "failed",
      error: gateResult.error || "Gate bypass failed",
      gateUrl,
    };
  } catch (err) {
    warn("Gate processing error", { error: (err as Error).message, gateUrl });
    return {
      track,
      status: "failed",
      error: `Gate error: ${(err as Error).message}`,
      gateUrl,
    };
  }
}

/**
 * Extract file extension from URL
 */
function getExtensionFromUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname;
    const match = path.match(/\.(mp3|wav|flac|aiff|aif|m4a|ogg)$/i);
    return match ? match[0].toLowerCase() : null;
  } catch {
    return null;
  }
}

/**
 * Download a file from a URL
 */
async function downloadFromUrl(url: string, filePath: string): Promise<void> {
  info(`📥 Downloading original file...`);

  const response = await fetch(url, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    },
  });

  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`);
  }

  const contentLength = response.headers.get("content-length");
  const totalSize = contentLength ? parseInt(contentLength, 10) : 0;

  const file = await Deno.open(filePath, {
    write: true,
    create: true,
    truncate: true,
  });

  try {
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("No response body");
    }

    let downloadedSize = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      await file.write(value);

      downloadedSize += value.length;
      if (totalSize > 0) {
        const percent = Math.round((downloadedSize / totalSize) * 100);
        debug(`Download progress: ${percent}%`);
      }
    }

    info(`📥 Downloaded ${(downloadedSize / 1024 / 1024).toFixed(2)} MB`);
  } finally {
    file.close();
  }
}

