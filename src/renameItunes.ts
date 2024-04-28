/*
Renames downloaded music from Beatport to format I like
*/
import * as fs from "https://deno.land/std@0.165.0/fs/mod.ts";
import * as mm from "npm:music-metadata";

import {
  backupFile,
  cacheMusic,
  checkFeat,
  checkIfDuplicate,
  getFolder,
  lastCheck,
  logWithBreak,
  removeAnd,
  removeBadCharacters,
  renameAndMove,
  fixItunesAlbum,
} from "./common.ts";
import { DownloadedSong, Song } from "./models/Song.ts";

const unix = true;
let debug = true;
let clear = true;
// let trimRating = true;

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

const startDir = getFolder("downloaded", unix);
const cacheDir = getFolder("djMusic", unix);
const moveDir = getFolder("rename", unix);
const backupDir = getFolder("backup", unix);

// empty out the backup directory
if (clear) await fs.emptyDir(backupDir);

const musicCache = await cacheMusic(cacheDir);

await main();

async function main() {
  let count = 0;
  for await (const currEntry of Deno.readDir(startDir)) {
    if (currEntry.isDirectory && currEntry.name.includes("itunes")) {
      console.log("Processing: ", currEntry.name);

      for await (const itunesItem of Deno.readDir(`${startDir}/${currEntry.name}`)) {
        if (!itunesItem.isDirectory) {
          await backupFile(`${startDir}/${currEntry.name}/`, backupDir, itunesItem.name);

          let song = new Song(itunesItem.name, `${startDir}${currEntry.name}/`);

          if (!song.extension || song.extension === ".plist") {
            logWithBreak(`Skipping: ${song.filename}`);
            continue;
          }

          const mTags = await mm.parseFile(`${startDir}/${currEntry.name}/${itunesItem.name}`);

          song.title = mTags.common.title || "";
          song.artist = mTags.common.artist || "";
          song.album = fixItunesAlbum(mTags.common.album || "");
          console.log(`${song.artist} - ${song.album} - ${song.title}`);

          song = removeBadCharacters(song);

          song = checkFeat(song);
          song = removeAnd(song, "artist", "album");
          song = lastCheck(song);

          song = setFinalName(song);

          song.duplicate = checkIfDuplicate(song, musicCache);
          if (song.duplicate) {
            logWithBreak(`Duplicate Song: ${song.filename}`);
            continue;
          }

          musicCache.push(song);

          logWithBreak(song.finalFilename);

          count++;

          console.log(song.fullFilename);
          if (!debug) {
            renameAndMove(moveDir, song);
          }
        }
      }
    }
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
