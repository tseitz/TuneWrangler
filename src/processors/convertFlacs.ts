/*
Renames downloaded music to the format that I like. Also converts to flac if wav

Incoming (generally): album - artist - title
Outgoing:             artist - album - title
*/
import * as fs from "@std/fs";

import { backupFile, convertLocalToAiff, getFolder, logWithBreak } from "../core/utils/common.ts";
import { LocalSong } from "../core/models/Song.ts";
import { Semaphore } from "../core/models/Semaphore.ts";

const MAX_CONCURRENT_CONVERSIONS = 4;

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
  // Phase 1: Collect all FLAC files
  const flacFiles: { name: string; song: LocalSong }[] = [];
  for await (const currEntry of Deno.readDir(startDir)) {
    if (currEntry.isFile) {
      const song = new LocalSong(currEntry.name, startDir);
      if (song.extension === ".flac") {
        flacFiles.push({ name: currEntry.name, song });
      }
    } else {
      logWithBreak(`Skipping (not a file): ${currEntry.name}`);
    }
  }

  console.log(`Found ${flacFiles.length} FLAC files to process`);

  // Phase 2: Parallel backup
  await Promise.all(
    flacFiles.map(({ name }) => backupFile(startDir, backupDir, name))
  );

  // Phase 3: Parallel conversion with concurrency limit
  if (!debug) {
    const sem = new Semaphore(MAX_CONCURRENT_CONVERSIONS);
    await Promise.all(
      flacFiles.map(async ({ name, song }) => {
        await sem.acquire();
        try {
          console.log("Processing: ", name);
          await convertLocalToAiff(moveDir, song);
        } finally {
          sem.release();
        }
      })
    );
  } else {
    flacFiles.forEach(({ name }) => console.log("Processing: ", name));
  }

  console.log(`Total Count: ${flacFiles.length}`);
}
