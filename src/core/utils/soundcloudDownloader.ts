import { join } from "https://deno.land/std@0.224.0/path/mod.ts";
import { ensureDir } from "https://deno.land/std@0.224.0/fs/mod.ts";
import { debug, info, warn, error } from "./logger.ts";
import { withNetworkRetry } from "./retry.ts";
import { TrackInfo, soundcloudScraper } from "./soundcloudScraper.ts";

/**
 * Result of a download attempt
 */
export interface DownloadResult {
  success: boolean;
  filePath?: string;
  error?: string;
  skipped?: boolean;
  skipReason?: string;
}

/**
 * Options for downloading
 */
export interface DownloadOptions {
  /** Output directory for downloads */
  outputDir: string;
  /** Whether to overwrite existing files */
  overwrite?: boolean;
  /** Progress callback */
  onProgress?: (downloaded: number, total: number) => void;
}

/**
 * SoundCloud direct downloader
 * Handles downloading tracks that have the native download button enabled
 */
/**
 * Default user agent for SoundCloud API requests
 */
const DEFAULT_USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

/**
 * SoundCloud direct downloader
 * Handles downloading tracks that have the native download button enabled
 */
export class SoundCloudDownloader {
  private clientId: string | null = null;
  private userAgent = DEFAULT_USER_AGENT;

  /**
   * Downloads a track directly from SoundCloud (if download is enabled)
   */
  async downloadTrack(track: TrackInfo, options: DownloadOptions): Promise<DownloadResult> {
    info(`📥 Attempting direct download: ${track.artist} - ${track.title}`);

    try {
      // Ensure output directory exists
      await ensureDir(options.outputDir);

      // Check if track has direct download
      if (!track.hasDirectDownload) {
        debug("Track does not have direct download enabled");
        return {
          success: false,
          skipped: true,
          skipReason: "No direct download available",
        };
      }

      // Get client ID if needed
      if (!this.clientId) {
        this.clientId = await soundcloudScraper.getClientId();
      }

      // Get the download URL
      const downloadUrl = await this.getDownloadUrl(track);
      if (!downloadUrl) {
        return {
          success: false,
          skipped: true,
          skipReason: "Could not get download URL",
        };
      }

      // Determine filename
      const filename = this.getFilename(track, downloadUrl);
      const filePath = join(options.outputDir, filename);

      // Check if file already exists
      if (!options.overwrite) {
        try {
          await Deno.stat(filePath);
          info(`⏭️ File already exists: ${filename}`);
          return {
            success: false,
            skipped: true,
            skipReason: "File already exists",
            filePath,
          };
        } catch {
          // File doesn't exist, continue with download
        }
      }

      // Download the file
      await this.downloadFile(downloadUrl, filePath, options.onProgress);

      info(`✅ Downloaded: ${filename}`);
      return {
        success: true,
        filePath,
      };
    } catch (err) {
      error(`Failed to download track: ${track.title}`, err as Error);
      return {
        success: false,
        error: (err as Error).message,
      };
    }
  }

  /**
   * Gets the direct download URL for a track
   */
  private async getDownloadUrl(track: TrackInfo): Promise<string | null> {
    if (!track.trackId) {
      warn("Track ID not available, cannot get download URL");
      return null;
    }

    return await withNetworkRetry(async () => {
      // Try to get the download URL from the API
      const apiUrl = `https://api-v2.soundcloud.com/tracks/${track.trackId}/download?client_id=${this.clientId}`;

      const response = await fetch(apiUrl, {
        headers: {
          "User-Agent": this.userAgent,
        },
        redirect: "follow",
      });

      if (response.status === 401 || response.status === 403) {
        debug("Download not authorized - track may require login or payment");
        return null;
      }

      if (!response.ok) {
        throw new Error(`Failed to get download URL: ${response.status}`);
      }

      const data = await response.json();
      return data.redirectUri || null;
    });
  }

  /**
   * Downloads a file from a URL to the specified path
   */
  private async downloadFile(
    url: string,
    filePath: string,
    onProgress?: (downloaded: number, total: number) => void
  ): Promise<void> {
    await withNetworkRetry(async () => {
      const response = await fetch(url, {
        headers: {
          "User-Agent": this.userAgent,
        },
      });

      if (!response.ok) {
        throw new Error(`Download failed: ${response.status}`);
      }

      const contentLength = response.headers.get("content-length");
      const total = contentLength ? parseInt(contentLength, 10) : 0;

      // Create file
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

        let downloaded = 0;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          await file.write(value);
          downloaded += value.length;

          if (onProgress && total > 0) {
            onProgress(downloaded, total);
          }
        }
      } finally {
        file.close();
      }
    });
  }

  /**
   * Generates a filename for a track
   */
  private getFilename(track: TrackInfo, downloadUrl: string): string {
    // Try to get extension from URL
    let extension = ".mp3";
    try {
      const url = new URL(downloadUrl);
      const pathParts = url.pathname.split(".");
      if (pathParts.length > 1) {
        const ext = pathParts[pathParts.length - 1].toLowerCase();
        if (["mp3", "wav", "flac", "aac", "m4a", "ogg"].includes(ext)) {
          extension = `.${ext}`;
        }
      }
    } catch {
      // Use default extension
    }

    // Build filename
    const artist = this.sanitizeFilename(track.artist);
    const title = this.sanitizeFilename(track.title);

    return `${artist} - ${title}${extension}`;
  }

  /**
   * Sanitizes a string for use as a filename
   * @deprecated Use sanitizeFilename from common.ts instead
   */
  private sanitizeFilename(str: string): string {
    return str
      .replace(/[<>:"/\\|?*]/g, "") // Remove invalid filename characters
      .replace(/\s+/g, " ") // Normalize whitespace
      .trim()
      .slice(0, 100); // Limit length
  }

  /**
   * Attempts to stream a track (for tracks without download enabled)
   * This extracts the streaming URL which can be used to download
   */
  async getStreamUrl(track: TrackInfo): Promise<string | null> {
    if (!track.trackId) {
      return null;
    }

    if (!this.clientId) {
      this.clientId = await soundcloudScraper.getClientId();
    }

    return await withNetworkRetry(async () => {
      // Get track info with stream URL
      const apiUrl = `https://api-v2.soundcloud.com/tracks/${track.trackId}?client_id=${this.clientId}`;

      const response = await fetch(apiUrl, {
        headers: {
          "User-Agent": this.userAgent,
        },
      });

      if (!response.ok) {
        return null;
      }

      const data = await response.json();

      // Find the progressive stream URL
      if (data.media?.transcodings) {
        for (const transcoding of data.media.transcodings) {
          if (transcoding.format?.protocol === "progressive") {
            // Get the actual stream URL
            const streamResponse = await fetch(`${transcoding.url}?client_id=${this.clientId}`, {
              headers: {
                "User-Agent": this.userAgent,
              },
            });

            if (streamResponse.ok) {
              const streamData = await streamResponse.json();
              return streamData.url || null;
            }
          }
        }
      }

      return null;
    });
  }

  /**
   * Downloads a track using the stream URL (fallback for tracks without download button)
   */
  async downloadFromStream(track: TrackInfo, options: DownloadOptions): Promise<DownloadResult> {
    info(`📥 Attempting stream download: ${track.artist} - ${track.title}`);

    try {
      await ensureDir(options.outputDir);

      const streamUrl = await this.getStreamUrl(track);
      if (!streamUrl) {
        return {
          success: false,
          skipped: true,
          skipReason: "Could not get stream URL",
        };
      }

      const filename = this.getFilename(track, streamUrl);
      const filePath = join(options.outputDir, filename);

      // Check if file already exists
      if (!options.overwrite) {
        try {
          await Deno.stat(filePath);
          info(`⏭️ File already exists: ${filename}`);
          return {
            success: false,
            skipped: true,
            skipReason: "File already exists",
            filePath,
          };
        } catch {
          // File doesn't exist, continue
        }
      }

      await this.downloadFile(streamUrl, filePath, options.onProgress);

      info(`✅ Downloaded (stream): ${filename}`);
      return {
        success: true,
        filePath,
      };
    } catch (err) {
      error(`Failed to download track from stream: ${track.title}`, err as Error);
      return {
        success: false,
        error: (err as Error).message,
      };
    }
  }
}

// Export singleton
export const soundcloudDownloader = new SoundCloudDownloader();
