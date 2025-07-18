/*
Renames downloaded music to the format that I like. Also converts to flac if wav

Incoming (generally): album - artist - title
Outgoing:             artist - album - title
*/
import * as fs from "https://deno.land/std@0.165.0/fs/mod.ts";

import {
  backupFile,
  cacheMusic,
  checkIfDuplicate,
  getFolder,
  logWithBreak,
  renameAndMove,
  isProcessable,
  setFinalDownloadedSongName,
} from "../core/utils/common.ts";
import { DownloadedSong } from "../core/models/Song.ts";

// Configuration is now handled automatically by the config system
let debug = true;
let clear = false;
// let trimRating = true;

const startDir = getFolder("downloaded");
const cacheDir = getFolder("djMusic");
const moveDir = getFolder("rename");
const backupDir = getFolder("backup");

// pass arg "--move" to write tags and move file
// --no-clear does not clear out the backup directory
Deno.args.forEach((value) => {
  if (value === "--move") {
    debug = false;
    clear = true;
  }
  if (value === "--no-clear") {
    clear = false;
  }
});

// cache music
const musicCache = await cacheMusic(cacheDir);

// empty out the backup directory if necessary
if (clear) await fs.emptyDir(backupDir);

// run the program
await main();

async function main() {
  let count = 0;

  for await (const currEntry of Deno.readDir(startDir)) {
    if (isProcessable(currEntry)) {
      console.log("Processing: ", currEntry.name);

      try {
        let song = new DownloadedSong(currEntry.name, startDir);

        if (!song.extension || song.extension === ".m3u" || song.extension === ".zip") {
          logWithBreak(`Skipping: ${song.filename}`);
          continue;
        }

        if (song.dashCount > 0) {
          song = processDownloadedMusic(song);
        }

        try {
          /* ALL TOGETHER NOW */
          song = setFinalDownloadedSongName(song);

          song.duplicate = checkIfDuplicate(song, musicCache);
          if (song.duplicate) {
            throw "Duplicate Song";
          }
        } catch {
          logWithBreak(`***Duplicate Song: ${song.finalFilename}***`);
          continue;
        }

        musicCache.push(song);

        logWithBreak(song.finalFilename);

        count++;
        if (!debug) {
          await backupFile(startDir, backupDir, currEntry.name);
          // renameAndMove(moveDir, song);
          renameAndMove(moveDir, song, undefined, clear);
        }
      } catch (error) {
        logWithBreak(`Skipping: ${currEntry.name} - ${error}`);
        continue;
      }
    }
  }

  console.log(`Total Count: ${count}`);
}

function processDownloadedMusic(song: DownloadedSong): DownloadedSong {
  song.removeBadCharacters();

  /* GRAB ARTIST */
  grabDownloadedArtist(song);

  /* GRAB ALBUM */
  if (!song.album && song.dashCount > 1) {
    song.album = song.grabFirst();
  }

  /* GRAB TITLE */
  song.title = song.grabLast();

  /* FINAL CHECK */
  song.checkFeat();
  song.removeAnd("artist", "album");
  song.lastCheck();

  return song;
}

function grabDownloadedArtist(song: DownloadedSong): DownloadedSong {
  song.checkRemix();

  if (song.remix) {
    /* if it's a remix, the original artist is assigned to album, remove &'s from it */
    song.album = song.dashCount === 1 ? song.grabFirst() : song.grabSecond();
    song.removeAnd("album");
  } else {
    /* otherwise the artist is straightforward */
    song.artist = song.dashCount === 1 ? song.grabFirst() : song.grabSecond();
  }

  song.checkWith();

  return song;
}
