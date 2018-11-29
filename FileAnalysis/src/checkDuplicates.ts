import * as fs from 'fs';
import { checkOS, cacheMusic, removeClip, checkDuplicate } from './common';

const currDir = checkOS('music');

fs.readdir(currDir, (e, files) => {
  const originalArr = cacheMusic(files, currDir);
  const compareArr = [...originalArr];

  for (let i = 0, len = originalArr.length; i < len; i++) {
    let song = originalArr[i];

    // remove clip to see if full version is there
    song.title = removeClip(song.title);
    if (song.title && song.title.toUpperCase().includes('CLIP')) {
      console.log(`${i} After: ${song.title}`);
    }

    // ignore wavs
    // if (song.rating === undefined && song.extension === '.wav') {
    //   console.log(song.filename);
    // }

    song = checkDuplicate(song, compareArr);
  }
});