/*
Renames downloaded music from Beatport to format I like
*/
import * as fs from "@std/fs";
import nodeId3 from "node-id3";

import {
  backupFile,
  cacheMusic,
  checkIfDuplicate,
  getFolder,
  logWithBreak,
  renameAndMove,
} from "../core/utils/common.ts";
import { DownloadedSong, Song } from "../core/models/Song.ts";

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

const startDir = getFolder("downloaded");
const cacheDir = getFolder("djMusic");
const moveDir = getFolder("rename");
const backupDir = getFolder("backup");

// empty out the backup directory
if (clear) await fs.emptyDir(backupDir);

const musicCache = await cacheMusic(cacheDir);

await main();

async function main() {
  let count = 0;
  for await (const currEntry of Deno.readDir(startDir)) {
    if (currEntry.isDirectory && currEntry.name.includes("beatport")) {
      console.log("Processing: ", currEntry.name);

      for await (const beatportItem of Deno.readDir(`${startDir}/${currEntry.name}`)) {
        await backupFile(`${startDir}/${currEntry.name}/`, backupDir, beatportItem.name);

        let song = new Song(beatportItem.name, `${startDir}${currEntry.name}/`);

        const mTags = nodeId3.read(`${startDir}/${currEntry.name}/${beatportItem.name}`);

        song.title = mTags.title || "";
        song.artist = mTags.artist || "";
        song.album = mTags.album || "";

        if (!song.extension || song.extension === ".m3u") {
          logWithBreak(`Skipping: ${song.filename}`);
          continue;
        }

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
  console.log(`Total Count: ${count}`);
}

function setFinalName(song: Song): DownloadedSong {
  if (song.dashCount === 1) {
    song.finalFilename = song.album
      ? `${song.artist} - ${song.album} - ${song.title}${song.extension}`
      : `${song.artist} - ${song.title}${song.extension}`;
  } else {
    song.finalFilename = `${song.artist} - ${song.album} - ${song.title}${song.extension}`;
  }
  return song;
}
