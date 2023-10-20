/*
Renames downloaded music from iTunes to format I like. Converts to flac as well
*/
import {
  getFolder,
  cacheMusic,
  removeBadCharacters,
  checkFeat,
  removeAnd,
  lastCheck,
  checkIfDuplicate,
  logWithBreak,
  renameAndMove,
  setFinalDownloadedSongName,
} from "./common.ts";
import { DownloadedSong } from "./models/Song.ts";

const unix = true;
let debug = true;
// let trimRating = true;

// pass arg "--move" to write tags and move file
Deno.args.forEach((value) => {
  console.log(value);
  if (value === "--move") {
    debug = false;
  }
});

const startDir = getFolder("transfer", unix);
const cacheDir = getFolder("djMusic", unix);
const moveDir = getFolder("rename", unix);

const musicCache = await cacheMusic(cacheDir);

let count = 0;
for await (const currEntry of Deno.readDir(startDir)) {
  if (currEntry.isFile) {
    console.log("Processing: ", currEntry.name);

    let song = new DownloadedSong(currEntry.name, startDir);

    if (!song.extension || song.extension === ".m3u") {
      logWithBreak(`Skipping: ${song.filename}`);
      continue;
    }

    song = removeBadCharacters(song);

    /* FINAL CHECK */
    song = checkFeat(song);
    song = removeAnd(song, "artist", "album");
    song = lastCheck(song);

    /* ALL TOGETHER NOW */
    song = setFinalDownloadedSongName(song);

    song.duplicate = checkIfDuplicate(song, musicCache);
    if (song.duplicate) {
      logWithBreak(`Duplicate Song: ${song.filename}`);
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
