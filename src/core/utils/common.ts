import { DownloadedSong, LocalSong, Song, Tags } from "../models/Song.ts";
import { FolderLocation } from "../models/types.ts";
import { loadConfig, validatePaths } from "../../config/index.ts";
import { logError, ConfigurationError } from "./errors.ts";
// import ffmpeg from "npm:fluent-ffmpeg";
import ffmpeg from "npm:ffmpeg";
import nodeId3 from "npm:node-id3";
import { join } from "https://deno.land/std/path/mod.ts";
import { Semaphore } from "../models/Semaphore.ts";

const MAX_CONCURRENT_OPERATIONS = 10;
const semaphore = new Semaphore(MAX_CONCURRENT_OPERATIONS);

export function getFolder(type: FolderLocation): string {
  try {
    const config = loadConfig();

    switch (type) {
      case "youtube":
        return config.youtube;
      case "downloaded":
        return config.downloaded;
      case "itunes":
        return config.itunes;
      case "music":
        return config.music;
      case "downloads":
        return config.downloads;
      case "djMusic":
        return config.djMusic;
      case "djPlaylists":
        return config.djPlaylists;
      case "djPlaylistImport":
        return config.djPlaylistImport;
      case "rename":
        return config.rename;
      case "backup":
        return config.backup;
      case "transfer":
        return config.transfer;
      default:
        throw new ConfigurationError(`Unknown folder type: ${type}`, type);
    }
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
      console.error("❌ Configuration validation failed:");
      validation.errors.forEach((error) => console.error(`  - ${error}`));
      console.error("\nPlease check your environment variables or update the default paths.");
      return false;
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

async function convertToAiff(song: Song, outputFile: string, artworkFile?: string) {
  // const tempOutputFile = join(Deno.makeTempDirSync(), `temp_${Date.now()}.aiff`);

  try {
    // Step 1: Convert audio to FLAC
    // const convertCommand = new Deno.Command("ffmpeg", {
    //   args: ["-i", inputFile, "-c:a", "flac", tempOutputFile],
    // });
    const convertCommand = new Deno.Command("ffmpeg", {
      args: [
        "-i",
        song.fullFilename,
        "-c:a",
        "pcm_s16be",
        // "-c:a",
        // "copy", // Copy audio without re-encoding
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
        "aiff", // Ensure output is AIFF
        "-y", // Overwrite output file if it exists
        outputFile,
      ],
    });
    const convertResult = await convertCommand.output();
    if (!convertResult.success) {
      throw new Error(`FFmpeg conversion failed: ${new TextDecoder().decode(convertResult.stderr)}`);
    } else {
      console.log("Conversion successful");
    }

    // if (artworkFile) {
    //   console.log("Adding artwork", artworkFile);
    //   const artworkCommand = new Deno.Command("ffmpeg", {
    //     args: [
    //       "-i",
    //       tempOutputFile,
    //       "-i",
    //       artworkFile,
    //       "-map",
    //       "0:0",
    //       "-map",
    //       "1:0",
    //       "-c",
    //       "copy",
    //       "-id3v2_version",
    //       "3",
    //       "-disposition:v:0",
    //       "attached_pic",
    //       "-y",
    //       "-metadata:s:v",
    //       `title="Album cover"`,
    //       "-metadata:s:v",
    //       `comment="Cover (front)"`,
    //       outputFile,
    //     ],
    //   });
    //   const artworkResult = await artworkCommand.output();
    //   if (!artworkResult.success) {
    //     throw new Error(`FFmpeg artwork addition failed: ${new TextDecoder().decode(artworkResult.stderr)}`);
    //   } else {
    //     console.log("Artwork added");
    //   }

    //   await Deno.remove(tempOutputFile);
    // } else {
    //   // If no artwork, just rename the temp file
    //   await Deno.rename(tempOutputFile, outputFile);
    // }
  } catch (error) {
    console.error("An error occurred:", error);
    // Clean up temp file if it exists
    try {
      // await Deno.remove(tempOutputFile);
    } catch {
      // Ignore error if temp file doesn't exist
    }
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
    if (song.extension === ".wav" || song.extension === ".m4a") {
      finalPath = `${moveDir}${song.finalFilename.slice(0, song.extension.length * -1)}.aiff`;
      await convertToAiff(song, finalPath, tempImageFile);
    } else if (song.extension === ".mp3") {
      await convertToMp3(song, finalPath, tempImageFile);
    } else {
      finalPath = `${moveDir}${song.finalFilename}`;
      await convertToAiff(song, finalPath, tempImageFile);
    }

    if (clear) await Deno.remove(song.fullFilename);

    if (tempImageFile) Deno.remove(tempImageFile);
  } finally {
    semaphore.release();
  }
}

export async function convertLocalToWav(moveDir: string, song: LocalSong) {
  song.tags = {
    title: song.title,
    artist: song.artist,
    album: song.album,
  };

  if (song.tags) {
    console.log("Setting Tags");

    const process = ffmpeg();
    process
      .input(song.fullFilename)
      .metadata({ artist: song.artist, title: song.title, album: song.album })
      .audioBitrate("320k")
      .overwrite() // overwrite any existing output files
      .output(`${moveDir}${song.filename.slice(0, -5)}.mp3`);

    try {
      await process.run();
      await Deno.remove(song.fullFilename);
    } catch (e) {
      console.log(e, song.filename);
    }
  } else {
    console.log("No tags for, leaving in place: ", song.filename);
    // renameFile(song.fullFilename, `${moveDir}${song.finalFilename}`);
  }
}

export async function backupFile(startDir: string, backupDir: string, name: string) {
  return await Deno.copyFile(`${startDir}${name}`, `${backupDir}${name}`);
}

export function setFinalDownloadedSongName(song: DownloadedSong): DownloadedSong {
  if (song.dashCount === 1) {
    song.finalFilename = song.album
      ? `${song.artist} - ${song.album} - ${song.title}${song.extension}`
      : `${song.artist} - ${song.title}${song.extension}`;
  } else {
    song.finalFilename = `${song.artist} - ${song.album} - ${song.title}${song.extension}`;
  }
  return song;
}

async function convertToMp3(song: Song, outputFile: string, artworkFile?: string) {
  try {
    const convertCommand = new Deno.Command("ffmpeg", {
      args: [
        "-i",
        song.fullFilename,
        "-c:a",
        "libmp3lame",
        "-b:a",
        "320k",
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

    const convertResult = await convertCommand.output();
    if (!convertResult.success) {
      throw new Error(`FFmpeg conversion failed: ${new TextDecoder().decode(convertResult.stderr)}`);
    }

    console.log(`Conversion complete: ${outputFile}`);
  } catch (error) {
    console.error("An error occurred:", error);
    throw error;
  }
}

export function isProcessable(folderItem: Deno.DirEntry): boolean {
  return folderItem.isFile && folderItem.name !== ".DS_Store" && folderItem.name !== ".spotdl-cache";
}
