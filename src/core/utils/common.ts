import { DownloadedSong, LocalSong, Song, Tags } from "../models/Song.ts";
import { FolderLocation } from "../models/types.ts";
import { loadConfig, validatePaths } from "../../config/index.ts";
import { logError, ConfigurationError } from "./errors.ts";
// ffmpeg npm package no longer needed - using Deno.Command for all conversions
import nodeId3 from "node-id3";
import { join } from "@std/path";
import { Semaphore } from "../models/Semaphore.ts";

const MAX_CONCURRENT_OPERATIONS = 10;
const semaphore = new Semaphore(MAX_CONCURRENT_OPERATIONS);

export function getFolder(type: FolderLocation): string {
  try {
    const config = loadConfig();

    if (type in config) {
      return config[type];
    }

    throw new ConfigurationError(`Unknown folder type: ${type}`, type);
  } catch (error) {
    if (error instanceof ConfigurationError) {
      throw error;
    }
    throw new ConfigurationError(`Failed to load configuration for folder type: ${type}`, type);
  }
}

export function logWithBreak(message: string): void {
  console.log(message);
  console.log(`
----------------------------------
`);
}

/**
 * Validates the current configuration and logs any issues
 */
export async function validateConfiguration(): Promise<boolean> {
  try {
    const config = loadConfig();
    const validation = await validatePaths(config);

    if (!validation.valid) {
      console.warn(" ⚠️  Configuration validation issues:");
      validation.errors.forEach((error) => console.warn(`  - ${error}`));
      console.warn("\nPlease check your environment variables or update the default paths.");
    }

    console.log("✅ Configuration validation passed");
    return true;
  } catch (error) {
    logError(error, { operation: "validateConfiguration" });
    return false;
  }
}

export async function cacheMusic(cacheDir: string): Promise<LocalSong[]> {
  const cache: LocalSong[] = [];

  for await (const cacheEntry of Deno.readDir(cacheDir)) {
    if (cacheEntry.isFile) {
      const song = new LocalSong(cacheEntry.name, cacheDir);
      cache.push(song);
    }
  }

  return cache;
}

export function removeX(string: string) {
  return string.replace(/\sx\s/g, ", ");
}

export function addX(string: string) {
  return string.replace(/\,\s/g, " x ");
}

export function removeClip(title: string): string {
  title = title.replace(/(\(|\[).?CLIP.?(\)|\])/gi, "").trim();

  return title;
}

export function checkIfDuplicate(song: Song, musicArr: Song[] = []): boolean {
  // console.time('start')
  for (let i = 0, len = musicArr.length; i < len; i++) {
    const compare = musicArr[i];
    const songArtist = song.artist || "";
    const songTitle = song.title || "";
    const compareArtist = compare.artist || "";
    const compareTitle = compare.title || "";

    // remove clip to check if we have full version
    if (compareTitle.toUpperCase().includes("CLIP")) {
      compare.title = removeClip(compareTitle);
    }

    if (
      compare !== song && // when comparing local to itself, make sure the files don't exactly match
      songArtist.toUpperCase() === compareArtist.toUpperCase() &&
      songTitle.toUpperCase() === compareTitle.toUpperCase()
      // && !dupeExceptions.includes(
      //   `${song.artist.toUpperCase()} - ${song.title.toUpperCase()}`
      // )
    ) {
      return true;
    }
  }
  // console.time('end')
  return false;
}

export function fixItunesLabeling(str: string): string {
  str = str.replaceAll(" - Single", "");
  str = str.replaceAll(" - EP", "");
  str = str.replaceAll(/\s?\/\s?/g, " x ");
  str = str.replaceAll(", ", " ");
  return str;
}

/**
 * Detects the bit depth of an audio file using ffprobe.
 * Returns 16 or 24 (defaults to 16 if detection fails).
 */
async function detectBitDepth(filePath: string): Promise<16 | 24> {
  try {
    const probeCommand = new Deno.Command("ffprobe", {
      args: [
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=bits_per_raw_sample,bits_per_sample",
        "-of", "default=noprint_wrappers=1:nokey=0",
        filePath,
      ],
    });
    const result = await probeCommand.output();
    if (result.success) {
      const output = new TextDecoder().decode(result.stdout);
      const match = output.match(/bits_per_raw_sample=(\d+)/);
      const matchFallback = output.match(/bits_per_sample=(\d+)/);
      const bits = parseInt(match?.[1] || matchFallback?.[1] || "16", 10);
      if (bits >= 24) return 24;
    }
  } catch {
    console.log("Could not detect bit depth, defaulting to 16-bit");
  }
  return 16;
}

async function convertToAiff(song: Song, outputFile: string, _artworkFile?: string) {
  try {
    const bitDepth = await detectBitDepth(song.fullFilename);
    const codec = bitDepth === 24 ? "pcm_s24be" : "pcm_s16be";
    console.log(`Converting to AIFF (${bitDepth}-bit): ${song.filename}`);

    const convertCommand = new Deno.Command("ffmpeg", {
      args: [
        "-i",
        song.fullFilename,
        "-c:a",
        codec,
        "-map_metadata",
        "0",
        "-metadata",
        `title=${song.title}`,
        "-metadata",
        `artist=${song.artist}`,
        "-metadata",
        `album=${song.album}`,
        "-metadata",
        `album_artist=${song.artist}`,
        "-f",
        "aiff",
        "-y",
        outputFile,
      ],
    });
    const convertResult = await convertCommand.output();
    if (!convertResult.success) {
      throw new Error(
        `FFmpeg conversion failed: ${new TextDecoder().decode(convertResult.stderr)}`
      );
    } else {
      console.log("Conversion successful");
    }
  } catch (error) {
    console.error("An error occurred:", error);
    throw error;
  }
}

export function mergeMetadata(song: Song) {
  const id3Tags = nodeId3.read(song.fullFilename);

  song.tags = {
    title: song.title,
    artist: song.artist,
    album: song.album,
    performerInfo: song.artist,
  };

  return { ...id3Tags, ...song.tags } as nodeId3.Tags & Partial<Tags>;
}

export async function renameAndMove(
  moveDir: string,
  song: DownloadedSong,
  mergedMetadata?: nodeId3.Tags & Partial<Tags>,
  clear: boolean = false
) {
  await semaphore.acquire();
  try {
    let tempImageFile: string | undefined;
    if (mergedMetadata && typeof mergedMetadata.image === "object" && mergedMetadata.image !== null) {
      tempImageFile = join(Deno.makeTempDirSync(), `cover-${song.title}.jpg`);
      await Deno.writeFile(tempImageFile, mergedMetadata.image.imageBuffer);
    }

    let finalPath = `${moveDir}${song.finalFilename}`;
    if (song.extension === ".mp3") {
      await retagMp3(song, finalPath, tempImageFile);
    } else {
      // All non-MP3 formats (WAV, M4A, FLAC, OGG, OPUS, etc.) → AIFF
      const baseName = song.finalFilename.slice(0, song.extension.length * -1);
      finalPath = `${moveDir}${baseName}.aiff`;
      await convertToAiff(song, finalPath, tempImageFile);
    }

    if (clear) await Deno.remove(song.fullFilename);

    if (tempImageFile) Deno.remove(tempImageFile);
  } finally {
    semaphore.release();
  }
}

/**
 * Converts a local FLAC (or other lossless) file to AIFF with proper metadata.
 * Preserves original bit depth (16 or 24-bit) and removes the source file on success.
 */
export async function convertLocalToAiff(moveDir: string, song: LocalSong) {
  song.tags = {
    title: song.title,
    artist: song.artist,
    album: song.album,
  };

  if (song.tags) {
    const outputFile = `${moveDir}${song.filename.slice(0, song.filename.lastIndexOf("."))}.aiff`;

    try {
      await convertToAiff(song, outputFile);
      await Deno.remove(song.fullFilename);
    } catch (e) {
      console.log(e, song.filename);
    }
  } else {
    console.log("No tags for, leaving in place: ", song.filename);
  }
}

export async function backupFile(startDir: string, backupDir: string, name: string) {
  return await Deno.copyFile(`${startDir}${name}`, `${backupDir}${name}`);
}

export function setFinalDownloadedSongName(song: DownloadedSong): DownloadedSong {
  if (song.dashCount === 0) {
    song.finalFilename = `${song.artist} - ${song.title}${song.extension}`;
  } else if (song.dashCount === 1) {
    song.finalFilename = song.album
      ? `${song.artist} - ${song.album} - ${song.title}${song.extension}`
      : `${song.artist} - ${song.title}${song.extension}`;
  } else {
    song.finalFilename = `${song.artist} - ${song.album} - ${song.title}${song.extension}`;
  }
  return song;
}

/**
 * Retags an MP3 file without re-encoding the audio stream.
 * Uses -c:a copy to preserve the original audio bitstream exactly,
 * avoiding generation loss from lossy-to-lossy transcoding.
 */
async function retagMp3(song: Song, outputFile: string, _artworkFile?: string) {
  try {
    console.log(`Retagging MP3 (no re-encode): ${song.filename}`);

    const retagCommand = new Deno.Command("ffmpeg", {
      args: [
        "-i",
        song.fullFilename,
        "-c:a",
        "copy",
        "-map_metadata",
        "0",
        "-id3v2_version",
        "3",
        "-metadata",
        `title=${song.title}`,
        "-metadata",
        `artist=${song.artist}`,
        "-metadata",
        `album=${song.album}`,
        "-metadata",
        `album_artist=${song.artist}`,
        "-y",
        outputFile,
      ],
    });

    const retagResult = await retagCommand.output();
    if (retagResult.success) {
      console.log(`Retag complete: ${outputFile}`);
      return;
    }

    // If stream copy fails (e.g. corrupted metadata), try without -map_metadata
    console.log("First retag attempt failed, trying without metadata copy...");
    const retagCommandNoMetadata = new Deno.Command("ffmpeg", {
      args: [
        "-i",
        song.fullFilename,
        "-c:a",
        "copy",
        "-id3v2_version",
        "3",
        "-metadata",
        `title=${song.title}`,
        "-metadata",
        `artist=${song.artist}`,
        "-metadata",
        `album=${song.album}`,
        "-metadata",
        `album_artist=${song.artist}`,
        "-y",
        outputFile,
      ],
    });

    const retagResultNoMetadata = await retagCommandNoMetadata.output();
    if (!retagResultNoMetadata.success) {
      throw new Error(
        `FFmpeg retag failed: ${new TextDecoder().decode(retagResultNoMetadata.stderr)}`
      );
    }

    console.log(`Retag complete (without original metadata): ${outputFile}`);
  } catch (error) {
    console.error("An error occurred:", error);
    throw error;
  }
}

export function isProcessable(folderItem: Deno.DirEntry): boolean {
  return folderItem.isFile && folderItem.name !== ".DS_Store" && folderItem.name !== ".spotdl-cache";
}
