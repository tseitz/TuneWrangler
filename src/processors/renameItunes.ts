/*
Renames downloaded music from iTunes to format I like.
Parallelizes ffprobe metadata extraction for much faster processing.
*/
import * as fs from "@std/fs";
import { walk, type WalkEntry } from "@std/fs";

import {
  backupFile,
  cacheMusic,
  checkIfDuplicate,
  getFolder,
  logWithBreak,
  renameAndMove,
  fixItunesLabeling,
  isProcessable,
} from "../core/utils/common.ts";
import { DownloadedSong, Song } from "../core/models/Song.ts";
import { Semaphore } from "../core/models/Semaphore.ts";

const MAX_CONCURRENT_FFPROBE = 10;

let debug = true;
let clear = true;

// pass arg "--move" to write tags and move file
Deno.args.forEach((value) => {
  console.log(value);
  if (value === "--move") {
    debug = false;
  }
  if (value === "--no-clear") {
    clear = false;
  }
});

const startDir = getFolder("itunes");
const cacheDir = getFolder("djMusic");
const moveDir = getFolder("rename");
const backupDir = getFolder("backup");

// empty out the backup directory
if (clear) await fs.emptyDir(backupDir);

const musicCache = await cacheMusic(cacheDir);

await main();

interface FileWithMetadata {
  entry: WalkEntry;
  song: Song;
  metadata: Record<string, Record<string, Record<string, string>>>;
}

async function main() {
  // Phase 1: Collect all processable files
  const entries: WalkEntry[] = [];
  for await (const item of walk(startDir)) {
    if (isProcessable(item)) {
      const song = new Song(item.name, item.path.replace(item.name, ""));
      if (song.extension && song.extension !== ".plist") {
        entries.push(item);
      } else {
        logWithBreak(`Skipping: ${item.name}`);
      }
    }
  }
  console.log(`Found ${entries.length} files to process`);

  // Phase 2: Parallel ffprobe metadata extraction
  const probeSemaphore = new Semaphore(MAX_CONCURRENT_FFPROBE);
  const metadataResults = await Promise.all(
    entries.map(async (entry): Promise<FileWithMetadata | null> => {
      await probeSemaphore.acquire();
      try {
        const song = new Song(entry.name, entry.path.replace(entry.name, ""));
        const command = new Deno.Command("ffprobe", {
          args: ["-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", song.fullFilename],
        });
        const { stdout } = await command.output();
        const output = new TextDecoder().decode(stdout);
        const metadata = JSON.parse(output);
        return { entry, song, metadata };
      } catch (e) {
        console.error(`ffprobe failed for ${entry.name}:`, e);
        return null;
      } finally {
        probeSemaphore.release();
      }
    })
  );

  // Phase 3: Sequential naming + dedup (fast, just string ops)
  let count = 0;
  const toMove: { song: DownloadedSong; entryName: string }[] = [];

  for (const result of metadataResults) {
    if (!result) continue;
    const { entry, metadata } = result;
    let { song } = result;

    console.log("Processing: ", entry.name);

    song.album = fixItunesLabeling(metadata.format?.tags?.album || "");
    song = grabItunesArtist(song, metadata.format?.tags?.artist);
    song.title = fixItunesLabeling(song.title || metadata.format?.tags?.title || "");

    song.removeBadCharacters();
    song.checkFeat();
    song.removeAnd("artist", "album");
    song.lastCheck();

    song = setFinalName(song);

    song.duplicate = checkIfDuplicate(song, musicCache);
    if (song.duplicate) {
      logWithBreak(`Duplicate Song: ${song.filename}`);
      continue;
    }

    musicCache.add(song);
    logWithBreak(song.finalFilename);
    count++;

    if (!debug) {
      toMove.push({ song, entryName: entry.name });
    }
  }

  // Phase 4: Parallel backup + rename/move
  if (toMove.length > 0) {
    await Promise.all(
      toMove.map(async ({ song, entryName }) => {
        await backupFile(song.directory, backupDir, entryName);
        await renameAndMove(moveDir, song, undefined, clear);
      })
    );
  }

  console.log(`Total Count: ${count}`);
}

function setFinalName(song: Song): DownloadedSong {
  if (song.title == song.album) {
    song.album = "";
  }
  song.finalFilename = song.album
    ? `${song.artist} - ${song.album} - ${song.title}${song.extension}`
    : `${song.artist} - ${song.title}${song.extension}`;
  return song;
}

function grabItunesArtist(song: Song, artist: string = ""): Song {
  song.checkRemix();

  if (song.remix) {
    /* if it's a remix, the original artist is assigned to album, remove &'s from it */
    song.album = artist;
    song.title = getRemixTitle(song.filename, song.extension);
    song.removeAnd("album");
  } else {
    /* otherwise the artist is straightforward */
    song.artist = artist;
  }

  song.checkWith();

  return song;
}

function getRemixTitle(filename: string, extension: string) {
  const regex = new RegExp(`^\\d{2}\\s(.+)\\.(${extension.replace(".", "")})$`);
  const match = filename.match(regex);
  return match ? match[1] : "";
}
