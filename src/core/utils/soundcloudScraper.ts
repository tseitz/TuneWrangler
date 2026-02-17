import { debug, info, warn, error } from "./logger.ts";
import { withNetworkRetry } from "./retry.ts";
import { delay } from "./common.ts";
import { flowConfigLoader } from "./flowConfig.ts";
import { flowExecutor } from "./flowExecutor.ts";
import { GateCredentials } from "./soundcloudConfig.ts";

/**
 * Information about a track extracted from SoundCloud
 */
export interface TrackInfo {
  /** Track URL on SoundCloud */
  url: string;
  /** Track title */
  title: string;
  /** Artist/uploader name */
  artist: string;
  /** Track duration in seconds */
  duration?: number;
  /** Artwork URL */
  artworkUrl?: string;
  /** Whether the track has a native download button */
  hasDirectDownload: boolean;
  /** URL to Hypeddit or other download gate (if any) */
  gateUrl?: string;
  /** Original filename suggested by the track */
  suggestedFilename?: string;
  /** Track ID from SoundCloud */
  trackId?: string;
}

/**
 * Result of playlist extraction
 */
export interface PlaylistInfo {
  /** Playlist title */
  title: string;
  /** Playlist creator */
  creator: string;
  /** Playlist URL */
  url: string;
  /** Tracks in the playlist */
  tracks: TrackInfo[];
  /** Total track count (may differ from tracks.length if some couldn't be loaded) */
  totalTracks: number;
}

/**
 * SoundCloud API response types (partial)
 */
interface SoundCloudTrackData {
  id: number;
  title: string;
  user: {
    username: string;
    permalink: string;
  };
  duration: number;
  artwork_url?: string;
  downloadable: boolean;
  has_downloads_left: boolean;
  download_url?: string;
  permalink_url: string;
  description?: string;
}

interface SoundCloudPlaylistData {
  id: number;
  title: string;
  user: {
    username: string;
  };
  tracks: SoundCloudTrackData[];
  track_count: number;
}

/**
 * SoundCloud scraper for extracting playlist and track information
 */
/**
 * Browser automation constants
 */
const BROWSER_ARGS = ["--no-sandbox", "--disable-setuid-sandbox"];
const DEFAULT_USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const PAGE_STABILIZATION_DELAY = 2000;
const LOGIN_WAIT_TIMEOUT = 120000; // 2 minutes

/**
 * SoundCloud scraper for extracting playlist and track information
 */
export class SoundCloudScraper {
  private clientId: string | null = null;
  private userAgent = DEFAULT_USER_AGENT;

  /**
   * Extracts all tracks from a SoundCloud playlist
   * @param useBrowser - If true, use browser-based scraping (for private playlists)
   * @param headless - If using browser, run in headless mode
   */
  async extractPlaylistTracks(
    playlistUrl: string,
    useBrowser = false,
    headless = true
  ): Promise<PlaylistInfo> {
    info("📋 Extracting playlist tracks", { url: playlistUrl, useBrowser });

    // Try browser-based scraping if requested or if it's a private playlist
    if (useBrowser || playlistUrl.includes("/s-")) {
      try {
        return await this.extractPlaylistWithBrowser(playlistUrl, headless);
      } catch (browserErr) {
        warn("Browser-based extraction failed, trying API", { error: (browserErr as Error).message });
        // Fall through to try API
      }
    }

    // Get client ID if we don't have one
    if (!this.clientId) {
      this.clientId = await this.getClientId();
    }

    try {
      // Resolve the playlist URL to get the API data
      const playlistData = await this.resolvePlaylistUrl(playlistUrl);

      const tracks: TrackInfo[] = [];

      for (const track of playlistData.tracks) {
        try {
          const trackInfo = this.parseTrackData(track);
          tracks.push(trackInfo);
          debug(`Extracted track: ${trackInfo.artist} - ${trackInfo.title}`);
        } catch (err) {
          warn(`Failed to parse track: ${track.title}`, { error: (err as Error).message });
        }
      }

      info(`📋 Extracted ${tracks.length} tracks from playlist`, {
        playlist: playlistData.title,
        total: playlistData.track_count,
      });

      return {
        title: playlistData.title,
        creator: playlistData.user.username,
        url: playlistUrl,
        tracks,
        totalTracks: playlistData.track_count,
      };
    } catch (apiErr) {
      // If API fails and we haven't tried browser yet, try it now
      if (!useBrowser) {
        warn("API extraction failed, trying browser-based scraping", {
          error: (apiErr as Error).message,
        });
        return await this.extractPlaylistWithBrowser(playlistUrl, headless);
      }
      throw apiErr;
    }
  }

  /**
   * Extract playlist using browser-based scraping (for private playlists)
   */
  private async extractPlaylistWithBrowser(
    playlistUrl: string,
    headless: boolean
  ): Promise<PlaylistInfo> {
    info("🌐 Using browser to extract playlist (may be required for private playlists)");

    // deno-lint-ignore no-explicit-any
    let playwright: any;
    // deno-lint-ignore no-explicit-any
    let browser: any;

    try {
      playwright = await import("npm:playwright");
      browser = await playwright.chromium.launch({
        headless,
        args: BROWSER_ARGS,
      });

      const page = await browser.newPage();

      // Navigate to the playlist - use "load" instead of "networkidle" to avoid timeouts
      await page.goto(playlistUrl, { waitUntil: "load", timeout: 30000 });
      
      // Wait for page to stabilize
      await delay(PAGE_STABILIZATION_DELAY);

      // Check if we're on a login page or the playlist page
      const currentUrl = page.url();
      const pageContent = await page.content();
      
      if (currentUrl.includes("/signin") || pageContent.includes("Sign in") && pageContent.includes("Continue with")) {
        if (headless) {
          throw new Error("SoundCloud requires login for this private playlist. Try running with --headed flag to log in manually.");
        }
        
        // In headed mode, prompt user to log in
        console.log("\n🔐 SoundCloud requires login for this private playlist.");
        console.log("   Please log in to SoundCloud in the browser window.");
        console.log("   Waiting up to 2 minutes for login...\n");
        
        // Wait for navigation away from login page
        await page.waitForURL((url: string) => !url.includes("/signin"), { timeout: 120000 });
        
        // Navigate back to the playlist after login
        await page.goto(playlistUrl, { waitUntil: "load", timeout: 30000 });
        await delay(3000);
      }

      // Wait for tracks to load with multiple selector attempts
      const trackSelectors = [
        ".trackList__item",
        ".soundList__item", 
        ".trackItem",
        ".compactTrackList__item",
        ".systemPlaylistTrackList__item"
      ];
      
      let foundTracks = false;
      for (const selector of trackSelectors) {
        try {
          await page.waitForSelector(selector, { timeout: 5000 });
          foundTracks = true;
          debug(`Found tracks with selector: ${selector}`);
          break;
        } catch {
          // Try next selector
        }
      }
      
      if (!foundTracks) {
        debug("No track selectors found, will try to extract from page anyway");
      }

      // Extract playlist data from the page using JavaScript that runs in browser context
      // deno-lint-ignore no-explicit-any
      const playlistData: any = await page.evaluate(`
        (() => {
          // Get playlist title
          const titleEl = document.querySelector(
            ".soundTitle__title span, .playlistHeader__title, h1 span"
          );
          const title = titleEl?.textContent?.trim() || "Unknown Playlist";

          // Get creator name
          const creatorEl = document.querySelector(
            ".soundTitle__username, .playlistHeader__username"
          );
          const creator = creatorEl?.textContent?.trim() || "Unknown";

          // Get tracks - try multiple selectors
          let trackElements = document.querySelectorAll(".trackList__item");
          
          // If that doesn't work, try other selectors
          if (trackElements.length === 0) {
            trackElements = document.querySelectorAll(".soundList__item");
          }
          if (trackElements.length === 0) {
            trackElements = document.querySelectorAll(".compactTrackList__item");
          }
          if (trackElements.length === 0) {
            trackElements = document.querySelectorAll("[class*='trackItem']");
          }

          const tracks = [];
          const seenUrls = new Set();

          trackElements.forEach((el) => {
            // Try to find the track link
            const linkEl = el.querySelector("a[href*='/'][href*='soundcloud.com'], a.trackItem__trackTitle, a.soundTitle__title");
            
            // Get the track title
            const titleEl = el.querySelector(".trackItem__trackTitle span, .soundTitle__title span, .sc-truncate");
            
            // Get the artist
            const artistEl = el.querySelector(".trackItem__username, .soundTitle__username");

            if (titleEl) {
              let href = "";
              if (linkEl) {
                href = linkEl.getAttribute("href") || "";
              }
              
              // Build full URL
              let trackUrl = "";
              if (href) {
                if (href.startsWith("http")) {
                  trackUrl = href;
                } else if (href.startsWith("/")) {
                  trackUrl = "https://soundcloud.com" + href;
                }
              }
              
              // Skip if we've already seen this URL (avoid duplicates)
              if (trackUrl && seenUrls.has(trackUrl)) {
                return;
              }
              if (trackUrl) {
                seenUrls.add(trackUrl);
              }

              tracks.push({
                url: trackUrl,
                title: titleEl?.textContent?.trim() || "Unknown Track",
                artist: artistEl?.textContent?.trim() || creator,
              });
            }
          });

          return { title, creator, tracks, totalTracks: tracks.length };
        })()
      `);
      
      debug("Browser extracted playlist data", { 
        title: playlistData.title, 
        trackCount: playlistData.tracks.length,
        tracks: playlistData.tracks.map((t: {url: string; title: string}) => ({ url: t.url, title: t.title }))
      });

      const tracks: TrackInfo[] = playlistData.tracks.map(
        (t: { url: string; title: string; artist: string }) => ({
          url: t.url,
          title: t.title,
          artist: t.artist,
          hasDirectDownload: false, // We don't know this from scraping
          gateUrl: undefined,
        })
      );

      info(`📋 Browser extracted ${tracks.length} tracks from "${playlistData.title}"`);

      return {
        title: playlistData.title,
        creator: playlistData.creator,
        url: playlistUrl,
        tracks,
        totalTracks: playlistData.totalTracks,
      };
    } catch (err) {
      error("Browser extraction failed", err as Error);
      throw new Error(`Browser extraction failed: ${(err as Error).message}`);
    } finally {
      if (browser) {
        await browser.close();
      }
    }
  }

  /**
   * Extracts information about a single track
   */
  async extractTrackInfo(trackUrl: string): Promise<TrackInfo> {
    debug("🎵 Extracting track info", { url: trackUrl });

    if (!this.clientId) {
      this.clientId = await this.getClientId();
    }

    const trackData = await this.resolveTrackUrl(trackUrl);
    return this.parseTrackData(trackData);
  }

  /**
   * Extract gate URL from a SoundCloud track page using browser scraping
   * This finds "Free DL" buttons and other custom download links that aren't in the description
   */
  async extractGateUrlWithBrowser(trackUrl: string, headless = true): Promise<string | null> {
    info("🌐 Checking track page for download buttons...", { url: trackUrl });

    // deno-lint-ignore no-explicit-any
    let playwright: any;
    // deno-lint-ignore no-explicit-any
    let browser: any;

    try {
      playwright = await import("npm:playwright");
      browser = await playwright.chromium.launch({
        headless,
        args: BROWSER_ARGS,
      });

      const page = await browser.newPage();
      await page.goto(trackUrl, { waitUntil: "load", timeout: 30000 });
      
      // Wait for page to stabilize
      await delay(3000);

      // Try to use flow-based approach first
      const flow = await flowConfigLoader.findMatchingFlow(trackUrl);
      if (flow && flow.platform === "soundcloud-track") {
        info(`📋 Using flow for gate URL extraction: ${flow.name}`);
        
        // Create a minimal browser context for flow executor
        const browserContext = {
          pages: () => [page],
          waitForEvent: () => Promise.resolve(null),
        };

        // Execute flow with empty credentials (we just need to extract URL)
        const emptyCredentials: GateCredentials = {};
        const flowResult = await flowExecutor.executeFlow(
          page,
          flow,
          emptyCredentials,
          {
            headless: true,
            timeout: 30000,
            actionDelay: 1000,
            outputDir: "./",
          },
          browserContext
        );

        // Check if flow stored gateUrl in variables
        // The flow executor stores evaluate results in variables
        // We need to check the page context for the result
        const gateUrlFromFlow = await page.evaluate(() => {
          // Check if gateUrl was set by evaluate steps
          return (window as any).gateUrl || null;
        }).catch(() => null);

        if (gateUrlFromFlow) {
          info(`✅ Found gate URL using flow: ${gateUrlFromFlow}`);
          return gateUrlFromFlow;
        }
      }

      // Fallback to hardcoded logic
      // Look for "Free DL" button or similar download buttons
      // These are often custom buttons added by the uploader
      const gateUrl = await page.evaluate(`
        (() => {
          // Look for "Free DL" button by attribute selectors (valid CSS)
          const attributeSelectors = [
            '[aria-label*="Free"]',
            '[title*="Free DL"]',
            '[title*="Download"]',
            '[aria-label*="Download"]',
          ];
          
          for (const selector of attributeSelectors) {
            const freeDlButton = document.querySelector(selector);
            if (freeDlButton) {
              // The button might have a link or trigger a modal
              const link = freeDlButton.closest('a') || freeDlButton.querySelector('a');
              if (link && link.href) {
                return link.href;
              }
            }
          }
          
          // Also search by button text content (manually check text)
          const allButtons = document.querySelectorAll('button, a.sc-button, [role="button"]');
          for (const btn of allButtons) {
            const text = (btn.textContent || '').toLowerCase();
            if (text.includes('free dl') || text.includes('free download')) {
              if (btn.href) return btn.href;
              const link = btn.closest('a') || btn.querySelector('a');
              if (link && link.href) return link.href;
            }
          }
          
          // Look for download links in the "more" menu or buy buttons
          const buyLinks = document.querySelectorAll('a[href*="toneden"], a[href*="hypeddit"], a[href*="fanlink"], a[href*="linktr"], a[href*="hype.to"]');
          for (const link of buyLinks) {
            if (link.href) {
              return link.href;
            }
          }
          
          // Check the description section for links
          const descriptionLinks = document.querySelectorAll('.truncatedAudioInfo a, .sc-text a');
          for (const link of descriptionLinks) {
            const href = link.href || '';
            if (href.includes('toneden') || href.includes('hypeddit') || href.includes('hype.to') || href.includes('fanlink')) {
              return href;
            }
          }
          
          return null;
        })()
      `);

      if (gateUrl) {
        info(`✅ Found gate URL on track page: ${gateUrl}`);
        return gateUrl;
      }

      // If no link found, try clicking the "more" or "..." button to reveal hidden options
      try {
        // Use Playwright's locator API for text-based matching
        let moreButton = await page.$('button[aria-label*="more" i], button[title*="More" i], button[aria-label*="More" i]');
        if (!moreButton) {
          // Try to find by text content using Playwright's getByText
          moreButton = await page.getByRole('button', { name: /more/i }).first().elementHandle().catch(() => null);
        }
        if (moreButton) {
          await moreButton.click();
          await delay(1000);
          
          // Check for download link in dropdown
          const dropdownGateUrl = await page.evaluate(`
            (() => {
              const dropdownLinks = document.querySelectorAll('[role="menu"] a, .sc-popup a, .moreActions a');
              for (const link of dropdownLinks) {
                const href = link.href || '';
                const text = link.textContent || '';
                if (href.includes('toneden') || href.includes('hypeddit') || href.includes('hype.to') || 
                    text.toLowerCase().includes('free') || text.toLowerCase().includes('download')) {
                  return href;
                }
              }
              return null;
            })()
          `);
          
          if (dropdownGateUrl) {
            info(`✅ Found gate URL in dropdown: ${dropdownGateUrl}`);
            return dropdownGateUrl;
          }
        }
      } catch {
        // Dropdown check failed, continue
      }

      debug("No gate URL found on track page");
      return null;
    } catch (err) {
      warn("Browser gate extraction failed", { error: (err as Error).message });
      return null;
    } finally {
      if (browser) {
        await browser.close();
      }
    }
  }

  /**
   * Gets a SoundCloud client ID by scraping the main page
   */
  async getClientId(): Promise<string> {
    debug("🔑 Fetching SoundCloud client ID");

    return await withNetworkRetry(async () => {
      // Fetch the SoundCloud homepage
      const response = await fetch("https://soundcloud.com", {
        headers: {
          "User-Agent": this.userAgent,
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch SoundCloud: ${response.status}`);
      }

      const html = await response.text();

      // Find script URLs
      const scriptUrls = this.extractScriptUrls(html);

      // Search scripts for client_id
      for (const scriptUrl of scriptUrls) {
        try {
          const scriptResponse = await fetch(scriptUrl, {
            headers: {
              "User-Agent": this.userAgent,
            },
          });

          if (!scriptResponse.ok) continue;

          const scriptContent = await scriptResponse.text();

          // Look for client_id pattern
          const clientIdMatch = scriptContent.match(/client_id\s*[:=]\s*["']([a-zA-Z0-9]{32})["']/);
          if (clientIdMatch) {
            debug("🔑 Found client ID");
            return clientIdMatch[1];
          }
        } catch {
          // Continue to next script
        }
      }

      // If we can't find it in scripts, try a known working client ID
      // (this may stop working if SoundCloud changes their API)
      warn("Could not extract client ID from scripts, using fallback");
      return "iZIs9mchVcX5lhVRyQGGAYlNPVldzAoX";
    });
  }

  /**
   * Sets the client ID manually (useful for testing or if auto-detection fails)
   */
  setClientId(clientId: string): void {
    this.clientId = clientId;
  }

  /**
   * Resolves a playlist URL to get the API data
   */
  private async resolvePlaylistUrl(playlistUrl: string): Promise<SoundCloudPlaylistData> {
    return await withNetworkRetry(async () => {
      // Extract secret token if present (for private playlists)
      const secretMatch = playlistUrl.match(/\/s-([a-zA-Z0-9]+)/);
      const secretToken = secretMatch ? secretMatch[1] : null;

      let resolveUrl = `https://api-v2.soundcloud.com/resolve?url=${encodeURIComponent(
        playlistUrl
      )}&client_id=${this.clientId}`;

      // Add secret token if present
      if (secretToken) {
        resolveUrl += `&secret_token=s-${secretToken}`;
      }

      debug("Resolving playlist URL", { resolveUrl: resolveUrl.replace(this.clientId!, "[REDACTED]") });

      const response = await fetch(resolveUrl, {
        headers: {
          "User-Agent": this.userAgent,
        },
      });

      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        debug("API response error", { status: response.status, body: errorText.slice(0, 200) });

        if (response.status === 401) {
          throw new Error(`API authentication failed (401) - client ID may be invalid`);
        } else if (response.status === 404) {
          throw new Error(`Playlist not found (404) - it may be private or the URL may be incorrect`);
        } else if (response.status === 403) {
          throw new Error(`Access forbidden (403) - playlist may be private`);
        }
        throw new Error(`Failed to resolve playlist: ${response.status}`);
      }

      const data = await response.json();

      // Validate that this is a playlist
      if (!data.tracks || !Array.isArray(data.tracks)) {
        debug("Response data", { kind: data.kind, hasUser: !!data.user });
        throw new Error("URL does not appear to be a playlist");
      }

      return data as SoundCloudPlaylistData;
    });
  }

  /**
   * Resolves a track URL to get the API data
   */
  private async resolveTrackUrl(trackUrl: string): Promise<SoundCloudTrackData> {
    return await withNetworkRetry(async () => {
      const resolveUrl = `https://api-v2.soundcloud.com/resolve?url=${encodeURIComponent(
        trackUrl
      )}&client_id=${this.clientId}`;

      const response = await fetch(resolveUrl, {
        headers: {
          "User-Agent": this.userAgent,
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to resolve track: ${response.status}`);
      }

      return (await response.json()) as SoundCloudTrackData;
    });
  }

  /**
   * Parses track data from the API into our TrackInfo format
   */
  private parseTrackData(track: SoundCloudTrackData): TrackInfo {
    const trackInfo: TrackInfo = {
      url: track.permalink_url,
      title: this.sanitizeTitle(track.title),
      artist: track.user.username,
      duration: Math.round(track.duration / 1000), // Convert ms to seconds
      artworkUrl: track.artwork_url?.replace("-large", "-t500x500"),
      hasDirectDownload: track.downloadable && track.has_downloads_left,
      trackId: track.id.toString(),
      suggestedFilename: `${track.user.username} - ${this.sanitizeTitle(track.title)}`,
    };

    // Check for Hypeddit or other gate links in the description
    if (track.description) {
      trackInfo.gateUrl = this.extractGateUrl(track.description);
    }

    return trackInfo;
  }

  /**
   * Extracts script URLs from HTML
   */
  private extractScriptUrls(html: string): string[] {
    const scriptRegex = /<script[^>]+src=["']([^"']+)["']/g;
    const urls: string[] = [];
    let match;

    while ((match = scriptRegex.exec(html)) !== null) {
      const url = match[1];
      // Only include SoundCloud scripts
      if (url.includes("soundcloud") || url.includes("sndcdn")) {
        urls.push(url);
      }
    }

    return urls;
  }

  /**
   * Extracts Hypeddit or other download gate URLs from track description
   */
  private extractGateUrl(description: string): string | undefined {
    // Common patterns for download gates
    const patterns = [
      // Hypeddit patterns
      /https?:\/\/(?:www\.)?hypeddit\.com\/[^\s<>"]+/gi,
      /https?:\/\/(?:www\.)?hype\.to\/[^\s<>"]+/gi,
      // Toneden patterns
      /https?:\/\/(?:www\.)?toneden\.io\/[^\s<>"]+/gi,
      // Generic "free download" link patterns
      /https?:\/\/[^\s<>"]*(?:free-?download|download-?gate)[^\s<>"]+/gi,
    ];

    for (const pattern of patterns) {
      const match = description.match(pattern);
      if (match) {
        return match[0];
      }
    }

    // Also check for "Free Download:" or similar text followed by a URL
    const freeDownloadPattern = /(?:free\s*download|download\s*(?:here|link)?)\s*[:@]?\s*(https?:\/\/[^\s<>"]+)/gi;
    const freeMatch = freeDownloadPattern.exec(description);
    if (freeMatch) {
      return freeMatch[1];
    }

    return undefined;
  }

  /**
   * Sanitizes a track title for use as a filename
   */
  private sanitizeTitle(title: string): string {
    return title
      .replace(/[<>:"/\\|?*]/g, "") // Remove invalid filename characters
      .replace(/\s+/g, " ") // Normalize whitespace
      .trim();
  }

  /**
   * Checks if a track has a direct download available
   */
  async checkDirectDownload(trackUrl: string): Promise<boolean> {
    try {
      const trackInfo = await this.extractTrackInfo(trackUrl);
      return trackInfo.hasDirectDownload;
    } catch {
      return false;
    }
  }

  /**
   * Gets the Hypeddit gate URL for a track (if any)
   */
  async getGateUrl(trackUrl: string): Promise<string | null> {
    try {
      const trackInfo = await this.extractTrackInfo(trackUrl);
      return trackInfo.gateUrl || null;
    } catch {
      return null;
    }
  }
}

// Export a singleton instance for convenience
export const soundcloudScraper = new SoundCloudScraper();
