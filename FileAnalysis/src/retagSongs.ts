/*
Tags local songs. Converts to flac if necessary
*/
import { ffmpeg } from "https://deno.land/x/dffmpeg@v1.0.0-alpha.2/mod.ts";
import * as fs from "https://deno.land/std/fs/mod.ts";

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
} from "./common.ts";
import { DownloadedSong, LocalSong } from "./models/Song.ts";

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

const startDir = getFolder("downloaded", unix);
const cacheDir = getFolder("djMusic", unix);
const moveDir = getFolder("rename", unix);
const backupFolder = getFolder("backup", unix);

const cacheNames = [];
for await (const cacheEntry of Deno.readDir(cacheDir)) {
  if (cacheEntry.isFile) {
    cacheNames.push(cacheEntry.name);
  }
}
const musicCache = cacheMusic(cacheNames, cacheDir);

await fs.emptyDir(backupFolder);

let count = 0;
for await (const currEntry of Deno.readDir(startDir)) {
  if (currEntry.isFile) {
    await Deno.copyFile(
      `${startDir}/${currEntry.name}`,
      `${backupFolder}/${currEntry.name}`
    );

    console.log("Processing: ", currEntry.name);

    let song = new LocalSong(currEntry.name, startDir);

    if (song.dashCount < 1 || !song.extension || song.extension === ".m3u") {
      logWithBreak(`Skipping: ${song.filename}`);
      continue;
    }

    // used for my local songs with ratings at the end
    // if (song.filename.match(/ \- [0-9]{1,3}/)) {
    //   const trimmedName = song.filename.replace(/ \- [0-9]{1,3}/, '')
    //   if (!debug) {
    //     console.log(trimmedName)
    //     renameFile(`${startDir}${song.filename}`, `${cacheDir}${trimmedName}`)
    //   }
    //   continue
    // }

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

    song.duplicate = checkIfDuplicate(song, musicCache);
    if (song.duplicate) {
      logWithBreak(`Duplicate Song: ${song.filename}`);
      continue;
    }

    musicCache.push(song);

    logWithBreak(song.finalFilename);

    count++;
    if (!debug) {
      renameAndMove(song);
    }
  }
}
console.log(`Total Count: ${count}`);

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

async function renameAndMove(song: DownloadedSong) {
  song.tags = {
    title: song.title,
    artist: song.artist,
    album: song.album,
  };

  if (song.tags) {
    // could potentially put comments, description, year etc
    // https://wiki.multimedia.cx/index.php/FFmpeg_Metadata

    // ignore aiff since it overwrites the cover photo as well
    // rekordbox does not like when I fix the tags, doesn't import well so keeping stock
    if (song.extension !== ".aiff") {
      const process = ffmpeg();
      // RekordBox doesn't like wav's. convert to flac
      if (song.extension === ".wav") {
        process
          .input(song.fullFilename)
          .metadata({
            artist: song.artist,
            title: song.title,
            album: song.album,
          })
          .audioCodec("flac")
          .overwrite()
          .output(`${moveDir}${song.finalFilename.slice(0, -4)}.flac`);
        // .output(`${song.directory}${song.artist} - ${song.title}.flac`);
      } else {
        process
          .input(song.fullFilename)
          .metadata({
            artist: song.artist,
            title: song.title,
            album: song.album,
          })
          .copy()
          .output(`${moveDir}${song.finalFilename}`);
      }

      try {
        await process.run();
        await Deno.remove(song.fullFilename);
      } catch (e) {
        console.log(e, song.filename);
      }
    } else {
      await renameFile(song.fullFilename, `${moveDir}${song.finalFilename}`);
    }
  } else {
    console.log("No tags for, leaving in place: ", song.filename);
    // renameFile(song.fullFilename, `${moveDir}${song.finalFilename}`);
  }
}

async function renameFile(fullFilename: string, moveName: string) {
  await Deno.rename(fullFilename, moveName);
}
