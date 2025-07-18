/*
Renames downloaded music to the format that I like. Also converts to flac if wav

Incoming (generally): album - artist - title
Outgoing:             artist - album - title
*/
import * as fs from "https://deno.land/std@0.165.0/fs/mod.ts";

import { backupFile, convertLocalToWav, getFolder, logWithBreak } from "../core/utils/common.ts";
import { LocalSong } from "../core/models/Song.ts";

let debug = true;
let clear = true;

const startDir = getFolder("djMusic");
const moveDir = getFolder("djMusic");
const backupDir = getFolder("backup");

// pass arg "--move" to write tags and move file
// --no-clear does not clear out the backup directory
Deno.args.forEach((value) => {
  if (value === "--move") {
    debug = false;
  }
  if (value === "--no-clear") {
    clear = false;
  }
});

// empty out the backup directory if necessary
if (clear) await fs.emptyDir(backupDir);

// run the program
await main();

async function main() {
  let count = 0;
  for await (const currEntry of Deno.readDir(startDir)) {
    if (currEntry.isFile) {
      await backupFile(startDir, backupDir, currEntry.name);

      const song = new LocalSong(currEntry.name, startDir);

      if (song.extension !== ".flac") {
        // logWithBreak(`Skipping: ${song.filename}`);
        continue;
      }

      console.log("Processing: ", currEntry.name);
      if (!debug && currEntry.name) {
        await convertLocalToWav(moveDir, song);
      }
      count++;
    } else {
      logWithBreak(`Skipping (not a file): ${currEntry.name}`);
    }
  }
  console.log(`Total Count: ${count}`);
}
