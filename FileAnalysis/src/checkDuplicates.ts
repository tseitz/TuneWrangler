import * as fs from 'fs';
import { checkOS, cacheMusic, removeClip, checkDuplicate } from './common';

const currDir = checkOS('music');

fs.readdir(currDir, (e, files) => {
  const originalArr = cacheMusic(files, currDir);
  const compareArr = [...originalArr];

  for (let i = 0, len = originalArr.length; i < len; i++) {
    const song = originalArr[i];

    // if it's got a (1) it's probably a duplicate
    if (song.filename.includes(' (1)')) {
      console.log(`***Duplicate: Check ${song.filename}***
                    --------------------------------`);
    }

    // remove clip to see if full version is there
    if (song.title && song.title.toUpperCase().includes('CLIP')) {
      song.title = removeClip(song.title);
    }

    // logging purposes only for now
    checkDuplicate(song, compareArr);
  }
});