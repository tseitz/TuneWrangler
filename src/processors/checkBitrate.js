// TODO: needs to be fixed. requires a deno package that reads bitrate
// currently don't know how to get bitrate using deno, so this is standard js and node

import * as fs from "@std/fs";
import { parseFile } from "music-metadata";

const djDir = "/Users/tseitz/Dropbox/TransferMusic/Downloaded/";
// const djDir = "/Users/tseitz/Dropbox/DJ/SlimChance DJ Music/Collection";

const logger = fs.createWriteStream("fix-list.txt", {
  flags: "a", // 'a' means appending (old data will be preserved)
});

fs.readdir(djDir, (eL, localFiles) => {
  // for (const filename of localFiles) {
  localFiles.forEach(async (filename) => {
    if (filename.includes(".DS_Store")) return;
    try {
      const fileMetadata = await parseFile(`${djDir}/${filename}`);
      // console.log(fileMetadata.format.bitrate);
      if (fileMetadata.format.bitrate < 250000) {
        logger.write(`${filename.slice(0, -4)}\n`);
        console.log(
          Math.round(fileMetadata.format.bitrate),
          `${filename.slice(0, -4)}`
        );
      }
    } catch (e) {
      console.log(e);
    }
  });
  // }
});
