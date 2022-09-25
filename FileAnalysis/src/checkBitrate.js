// .js cuz screw ESM

import * as fs from "fs";
import { parseFile } from "music-metadata";

// const djDir = '/Users/tseitz/Dropbox/DJ/SlimChance DJ Music/Collection/'
const djDir = "/Users/tseitz/Dropbox/DJ/SlimChance DJ Music/Collection";

const logger = fs.createWriteStream("fix-list.txt", {
  flags: "a", // 'a' means appending (old data will be preserved)
});

const filenames = [];
fs.readdir(djDir, (eL, localFiles) => {
  // for (const filename of localFiles) {
  localFiles.forEach(async (filename) => {
    if (filename.includes(".DS_Store")) return;
    try {
      const fileMetadata = await parseFile(`${djDir}/${filename}`);
      // console.log(fileMetadata.format.bitrate)
      if (fileMetadata.format.bitrate < 280000) {
        logger.write(`${filename}\n`);
        // console.log(
        //   Math.round(fileMetadata.format.bitrate),
        //   `${djDir}/${filename}`
        // );
      }
    } catch (e) {
      console.log(e);
    }
  });
  // }
});
