/*
Tags local songs. Converts to flac if necessary
*/
import * as fs from "https://deno.land/std@0.165.0/fs/mod.ts";

import {
  getFolder,
  cacheMusic,
  removeBadCharacters,
  checkFeat,
  removeAnd,
  lastCheck,
  checkIfDuplicate,
  checkRemix,
  checkWith,
  logWithBreak,
  renameAndMove,
  backupFile,
} from "./common.ts";
import { DownloadedSong, LocalSong } from "./models/Song.ts";

const unix = true;
let debug = true;
let ignoreDupes = false;
let clear = true;
// let trimRating = true;

const startDir = getFolder("downloaded", unix);
const cacheDir = getFolder("djMusic", unix);
const moveDir = getFolder("rename", unix);
const backupDir = getFolder("backup", unix);

// pass arg "--move" to write tags and move file
// --no-clear does not clear out the backup directory
Deno.args.forEach((value) => {
  if (value === "--move") {
    debug = false;
  }
  if (value === "--no-clear") {
    clear = false;
  }
  if (value === "--ignore-dupes") {
    ignoreDupes = true;
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
    if (currEntry.isFile) {
      await backupFile(startDir, backupDir, currEntry.name);

      let song = new LocalSong(currEntry.name, startDir);

      if (song.dashCount < 1 || !song.extension || song.extension === ".m3u") {
        logWithBreak(`Skipping: ${song.filename}`);
        continue;
      }

      console.log("Processing: ", currEntry.name);

      try {
        song = processSongs(song);
      } catch {
        logWithBreak(`***Duplicate Song: ${song.filename}***`);
        continue;
      }

      musicCache.push(song);

      logWithBreak(song.finalFilename);

      count++;
      if (!debug) {
        renameAndMove(moveDir, song);
      }
    }
  }
  console.log(`Total Count: ${count}`);
}

function processSongs(song: DownloadedSong) {
  song = removeBadCharacters(song);

  /* GRAB ARTIST */
  song = grabLocalArtist(song);
  // console.log(song.artist);

  /* GRAB ALBUM */
  if (!song.album && song.dashCount > 1) {
    song.album = song.grabSecond();
  }

  /* GRAB TITLE */
  song.title = song.grabLast();

  /* Bandcamp labels the track # in the title */
  if (song.title.match(/^\d{2}\s/)) {
    song.title = song.title.slice(3);
  }

  /* FINAL CHECK */
  song = checkFeat(song);
  song = removeAnd(song, "artist", "album");
  song = lastCheck(song);

  /* ALL TOGETHER NOW */
  song = setFinalName(song);

  if (!ignoreDupes) {
    song.duplicate = checkIfDuplicate(song, musicCache);
    if (song.duplicate) {
      throw "Duplicate Song";
    }
  }

  return song;
}

function grabLocalArtist(song: DownloadedSong): DownloadedSong {
  song = checkRemix(song);

  if (song.remix) {
    /* if it's a remix, the original artist is assigned to album, remove &'s from it */
    song.album = song.dashCount === 1 ? song.grabFirst() : song.grabSecond();
    song = removeAnd(song, "album");
  } else {
    /* otherwise the artist is straightforward */
    song.artist = song.grabFirst();
  }

  song = checkWith(song);

  return song;
}

function setFinalName(song: DownloadedSong): DownloadedSong {
  if (song.dashCount === 1) {
    song.finalFilename = song.album
      ? `${song.artist} - ${song.album} - ${song.title}${song.extension}`
      : `${song.artist} - ${song.title}${song.extension}`;
  } else {
    song.finalFilename = `${song.artist} - ${song.album} - ${song.title}${song.extension}`;
  }
  return song;
}
