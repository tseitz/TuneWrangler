/*
Tags local songs. Converts to flac if necessary
*/
import * as fs from "@std/fs";

import {
  backupFile,
  cacheMusic,
  checkIfDuplicate,
  getFolder,
  logWithBreak,
  renameAndMove,
} from "../core/utils/common.ts";
import { DownloadedSong, LocalSong } from "../core/models/Song.ts";

let debug = true;
let ignoreDupes = false;
let clear = true;
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
    if (currEntry.isDirectory && currEntry.name === "bandcamp") {
      for await (const bandcampItem of Deno.readDir(`${startDir}/${currEntry.name}`)) {
        if (bandcampItem.isFile && !bandcampItem.isDirectory && !bandcampItem.name.includes(".zip")) {
          await backupFile(`${startDir}${currEntry.name}/`, backupDir, bandcampItem.name);

          let song = new LocalSong(bandcampItem.name, `${startDir}${currEntry.name}/`);

          if (song.dashCount < 1 || !song.extension || song.extension === ".m3u") {
            logWithBreak(`Skipping: ${song.filename}`);
            continue;
          }

          console.log("Processing: ", bandcampItem.name);

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
            renameAndMove(moveDir, song, undefined, clear);
          }
        }
      }
    }
  }
  console.log(`Total Count: ${count}`);
}

function processSongs(song: DownloadedSong): DownloadedSong {
  song.removeBadCharacters();

  /* GRAB ARTIST */
  song = grabLocalArtist(song);

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
  song.checkFeat();
  song.removeAnd("artist", "album");
  song.lastCheck();

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
  song.checkRemix();

  if (song.remix) {
    /* if it's a remix, the original artist is assigned to album, remove &'s from it */
    song.album = song.dashCount === 1 ? song.grabFirst() : song.grabSecond();
    song.removeAnd("album");
  } else {
    /* otherwise the artist is straightforward */
    song.artist = song.grabFirst();
  }

  song.checkWith();

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
