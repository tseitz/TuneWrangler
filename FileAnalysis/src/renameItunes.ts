import * as fs from 'fs';
import * as tw from './common';
import * as nodeId3 from 'node-id3';
import { LocalSong, DownloadedSong } from './models/Song';

// Incoming: track # title
// Outgoing: title
const currDir = tw.checkOS('transfer');
const moveDir = tw.checkOS('music');
let musicCache: LocalSong[] = [];
let debug = true;

// pass arg "-- move" to write tags and move file
process.argv.forEach((value) => {
  if (value === 'move') { debug = false; }
});

fs.readdir(moveDir, (eL, localFiles) => {
  musicCache = tw.cacheMusic(localFiles, moveDir);

  fs.readdir(currDir, (eD, downloadedFiles) => {
    downloadedFiles.forEach((filename, index) => {
      const song = new DownloadedSong(filename, currDir);

      // remove track number
      song.filename = song.filename.slice(3).trim();

      song.duplicate = tw.checkDuplicate(song, musicCache);
      if (song.duplicate) { return; }

      console.log(song.filename);
      console.log('-----------------------------------');

      if (!debug) { renameAndMove(song); }
    });
  });
});

function renameAndMove(song: DownloadedSong) {
  song.tags = {
    title: song.title,
    artist: song.artist,
    album: song.album
  };

  if (song.tags) {
    const success = nodeId3.update(song.tags, song.fullFilename);
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