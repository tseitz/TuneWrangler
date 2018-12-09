import * as fs from 'fs';
import * as tw from './common';
import { LocalSong, DownloadedSong } from './models/Song';
const nodeID3 = require('node-id3');

const currDir = tw.checkOS('transfer');
const moveDir = tw.checkOS('music');
let musicCache: LocalSong[] = [];
let debug = true;

// pass arg "-- move" to write tags and move file
process.argv.forEach((value) => {
  if (value === 'move') { debug = false; }
});

/* Incoming: album - artist - title */
/* Outgoing: artist - album - title */
fs.readdir(moveDir, (eL, localFiles) => {
  /* cache local to check for dupes later */
  musicCache = tw.cacheMusic(localFiles, moveDir);

  fs.readdir(currDir, (eD, downloadedFiles) => {
    downloadedFiles.forEach((filename) => {
      let song = new DownloadedSong(filename, currDir);

      if (song.dashCount < 1 || !song.extension || song.extension === '.m3u') { return; }

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
      song = tw.removeAnd(song, 'artist', 'album');
      song = tw.lastCheck(song);

      /* ALL TOGETHER NOW */
      song = setFinalName(song);

      /* TAG AND BAG */
      if (song.changed) {
        song.tags = {
          title: song.title,
          artist: song.artist,
          album: song.album
        };
      }

      song = tw.checkDuplicate(song, musicCache);
      if (song.duplicate) { return; }

      musicCache.push(song);

      console.log(`${song.finalFilename}
                      `);
      console.log(`-----------------------
                      `);

      if (!debug) {
        renameAndMove(song);
      }
    });
  });
});

function grabArtist(song: DownloadedSong): DownloadedSong {
  song = tw.checkRemix(song);

  if (song.remix) {
    /* if it's a remix, the original artist is assigned to album, remove &'s from it */
    song.album = song.dashCount === 1 ? song.grabFirst() : song.grabSecond();
    song = tw.removeAnd(song, 'album');
  } else {
    /* otherwise the artist is straightforward */
    song.artist = song.dashCount === 1 ? song.grabFirst() : song.grabSecond();
  }

  song = tw.checkWith(song);

  return song;
}

function setFinalName(song: DownloadedSong): DownloadedSong {
  if (song.dashCount === 1) {
    song.finalFilename = song.album ?
      `${song.artist} - ${song.album} - ${song.title}${song.extension}` :
      `${song.artist} - ${song.title}${song.extension}`;
  } else {
    song.finalFilename = `${song.artist} - ${song.album} - ${song.title}${song.extension}`;
  }
  return song;
}

function renameAndMove(song: DownloadedSong) {
  if (song.tags) {
    const success = nodeID3.update(song.tags, song.fullFilename);
    if (!success) { console.log(`Failed to tag ${song.filename}`); }
  }

  if (moveDir.length) {
    fs.rename(song.fullFilename, `${moveDir}${song.finalFilename}`, (e) => {
      if (e) { console.log(e); }
    });
  } else {
    console.log('Error: No active move directory.');
  }
}