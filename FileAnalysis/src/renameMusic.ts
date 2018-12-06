import * as fs from 'fs';
import * as tw from './common';
import { LocalSong, Song } from './models/Song';
const NodeID3 = require('node-id3');

let currDir = tw.checkOS('transfer');
let moveDir = tw.checkOS('music');
let musicCache: LocalSong[] = [];

/* Incoming: album - artist - title */
/* Outgoing: artist - album - title */
fs.readdir(moveDir, (e, files) => {
  /* cache to check for duplicates */
  musicCache = tw.cacheMusic(files, moveDir);

  fs.readdir(currDir, (e, files) => {
    files.forEach((filename) => {
      let song = new Song(filename, currDir);
      // let song = new DownloadedSong(filename, currDir); if it's straightforward, simply create new song and return it

      if (song.count < 1 || !song.extension || song.extension === '.m3u') {
        return
      }
      song = tw.removeBadCharacters(song);

      /* GRAB ARTIST */
      song = tw.checkRemix(song);

      if (song.remix) {
        /* if it's a remix, the original artist is assigned to album, remove &'s from it */
        song.album = song.count === 1 ? song.grabFirst() : song.grabSecond();
        song = tw.removeAnd(song, 'album');
      } else {
        /* otherwise the artist is straightforward */
        song.artist = song.count === 1 ? song.grabFirst() : song.grabSecond();
      }

      song = tw.checkWith(song);


      /* GRAB ALBUM */
      if (!song.album && song.count > 1) {
        song.album = song.grabFirst();
      }

      /* GRAB TITLE */
      song.title = song.grabLast();

      /* FINAL CHECK */
      song = tw.checkFeat(song);
      song = tw.removeAnd(song, 'artist'); // spread this
      song = tw.removeAnd(song, 'album');
      song = tw.lastCheck(song);

      /* ALL TOGETHER NOW */
      let finalFilename;

      if (song.count === 1) {
        finalFilename = song.album ? `${song.artist} - ${song.album} - ${song.title}${song.extension}` : `${song.artist} - ${song.title}${song.extension}`;

        if (song.changed) { /* TODO TAGS AREN'T WORKING */
          let tags = {
            title: song.title,
            artist: song.artist,
            album: song.album
          }

          let success = NodeID3.update(tags, song.fullFilename);
          if (!success) console.log(`Failed to tag ${song.filename}`);
        }
      } else {
        finalFilename = `${song.artist} - ${song.album} - ${song.title}${song.extension}`;

        if (song.changed) {
          let tags = {
            title: song.title,
            artist: song.artist,
            album: song.album
          }

          let success = NodeID3.update(tags, song.fullFilename);
          if (!success) console.log(`Failed to tag ${song.filename}`);
        }
      }

      song = tw.checkDuplicate(song, musicCache);
      if (song.duplicate) {
        return
      };

      console.log(`${finalFilename}
                    `);
      console.log(`-----------------------
                    `);

      musicCache.push(song);

      /* RENAME FILE AND MOVE */
      fs.rename(song.fullFilename, `${moveDir}${finalFilename}`, (e) => {
        if (e) {
          console.log(e);
        }
      });
    });
  });
});