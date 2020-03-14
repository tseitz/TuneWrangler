import * as fs from "fs";
import * as tw from "./common";
import * as nodeId3 from "node-id3";
import { LocalSong, DownloadedSong } from "./models/Song";

// scdl -l https://soundcloud.com/we-are-gentle-giants/sets/goodhouse -c --addtofile --onlymp3 -o [offset]

let musicCache: LocalSong[] = [];
let debug = true;
let wsl = true;

// pass arg "-- move" to write tags and move file
process.argv.forEach(value => {
  if (value === "move") {
    debug = false;
  }
  if (value === "nowsl") {
    wsl = false;
  }
});

const currDir = tw.checkOS("transfer", wsl);
const moveDir = tw.checkOS("music", wsl);

/* Incoming: album - artist - title */
/* Outgoing: artist - album - title */
fs.readdir(moveDir, (eL, localFiles) => {
  /* cache local to check for dupes later */
  musicCache = tw.cacheMusic(localFiles, moveDir);

  fs.readdir(currDir, (eD, downloadedFiles) => {
    let count = 0;
    downloadedFiles.forEach(filename => {
      let song = new DownloadedSong(filename, currDir);

      if (song.dashCount < 1 || !song.extension || song.extension === ".m3u") {
        return;
      }

      song = tw.removeBadCharacters(song);

      /* GRAB ARTIST */
      song = grabArtist(song);

      /* GRAB ALBUM */
      if (!song.album && song.dashCount > 1) {
        song.album = song.grabFirst();
      }

      /* GRAB TITLE */
      song.title = song.grabLast();

      /* FINAL CHECK */
      song = tw.checkFeat(song);
      song = tw.removeAnd(song, "artist", "album");
      song = tw.lastCheck(song);

      /* ALL TOGETHER NOW */
      song = setFinalName(song);

      song.duplicate = tw.checkDuplicate(song, musicCache);
      if (song.duplicate) {
        return;
      }

      musicCache.push(song);

      console.log(`${song.finalFilename}
                      `);
      console.log(`-----------------------
                      `);

      count++;
      if (!debug) {
        renameAndMove(song);
      }
    });
    console.log(`Total Count: ${count}`);
  });
});

function grabArtist(song: DownloadedSong): DownloadedSong {
  song = tw.checkRemix(song);

  if (song.remix) {
    /* if it's a remix, the original artist is assigned to album, remove &'s from it */
    song.album = song.dashCount === 1 ? song.grabFirst() : song.grabSecond();
    song = tw.removeAnd(song, "album");
  } else {
    /* otherwise the artist is straightforward */
    song.artist = song.dashCount === 1 ? song.grabFirst() : song.grabSecond();
  }

  song = tw.checkWith(song);

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

function renameAndMove(song: DownloadedSong) {
  song.tags = {
    title: song.title,
    artist: song.artist,
    album: song.album
  };

  if (song.tags) {
    const success = nodeId3.update(song.tags, song.fullFilename);
    if (!success) {
      console.log(`Failed to tag ${song.filename}`);
    }
  }

  fs.rename(song.fullFilename, `${moveDir}${song.finalFilename}`, e => {
    if (e) {
      console.log(e);
    }
  });
}
