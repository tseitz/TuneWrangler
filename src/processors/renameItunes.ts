/*
Renames downloaded music from Beatport to format I like
*/
import * as fs from "https://deno.land/std@0.170.0/fs/mod.ts";
import { walk } from "https://deno.land/std@0.170.0/fs/walk.ts";

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

const startDir = getFolder("itunes", unix);
const cacheDir = getFolder("djMusic", unix);
const moveDir = getFolder("rename", unix);
const backupDir = getFolder("backup", unix);

// empty out the backup directory
if (clear) await fs.emptyDir(backupDir);

const musicCache = await cacheMusic(cacheDir);

await main();

async function main() {
  let count = 0;

  for await (const itunesItem of walk(startDir)) {
    if (isProcessable(itunesItem)) {
      console.log("Processing: ", itunesItem.name);

      let song = new Song(itunesItem.name, itunesItem.path.replace(itunesItem.name, ""));
      // console.log(song);

      if (!song.extension || song.extension === ".plist") {
        logWithBreak(`Skipping: ${song.filename}`);
        continue;
      }

      const command = new Deno.Command("ffprobe", {
        args: ["-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", song.fullFilename],
      });
      const { stdout } = await command.output();
      const output = new TextDecoder().decode(stdout);
      const metadata = JSON.parse(output);

      song.album = fixItunesLabeling(metadata.format.tags.album || "");
      song = grabItunesArtist(song, metadata.format.tags.artist);
      song.title = fixItunesLabeling(song.title || metadata.format.tags.title || "");

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

      if (!debug) {
        await backupFile(song.directory, backupDir, itunesItem.name);
        renameAndMove(moveDir, song, undefined, clear);
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
