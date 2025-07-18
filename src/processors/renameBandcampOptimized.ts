/*
Optimized version of renameBandcamp processor with performance enhancements
*/
import * as fs from "https://deno.land/std@0.165.0/fs/mod.ts";

import {
  backupFile,
  cacheMusic,
  checkIfDuplicate,
  getFolder,
  renameAndMove,
  isProcessable,
  setFinalDownloadedSongName,
} from "../core/utils/common.ts";
import { DownloadedSong } from "../core/models/Song.ts";
import { performanceOptimizer, performanceMonitor, LRUCache } from "../core/utils/performance.ts";
import { getLogger } from "../core/utils/logger.ts";

const logger = getLogger();

// Configuration is now handled automatically by the config system
let debug = true;
let clear = false;

const startDir = getFolder("bandcamp");
const cacheDir = getFolder("djMusic");
const moveDir = getFolder("rename");
const backupDir = getFolder("backup");

// Performance optimization settings
const BATCH_SIZE = 15;
const MAX_CONCURRENCY = 3;
const CACHE_SIZE = 300;

// pass arg "--move" to write tags and move file
// --no-clear does not clear out the backup directory
Deno.args.forEach((value) => {
  if (value === "--move") {
    debug = false;
    clear = true;
  }
  if (value === "--no-clear") {
    clear = false;
  }
});

// Initialize performance optimizations
const bandcampCache = new LRUCache<string, DownloadedSong>(CACHE_SIZE);

// cache music
const existingMusicCache = await cacheMusic(cacheDir);

// empty out the backup directory if necessary
if (clear) await fs.emptyDir(backupDir);

// run the program
await main();

async function main() {
  const operationId = performanceMonitor.startOperation("renameBandcampOptimized", {
    startDir,
    cacheDir,
    moveDir,
    debug,
    clear,
  });

  try {
    const files: string[] = [];

    // Collect all files first for better batching
    for await (const currEntry of Deno.readDir(startDir)) {
      if (isProcessable(currEntry)) {
        files.push(currEntry.name);
      }
    }

    logger.info(`🎵 Processing ${files.length} Bandcamp files with optimization`, {
      batchSize: BATCH_SIZE,
      maxConcurrency: MAX_CONCURRENCY,
      cacheSize: CACHE_SIZE,
    });

    // Process files in optimized batches
    const results = await performanceOptimizer.processFilesOptimized(
      files,
      async (filename: string) => {
        logger.debug(`Processing: ${filename}`);

        let song = new DownloadedSong(filename, startDir);

        if (song.dashCount < 1 || !song.extension || song.extension === ".m3u" || song.extension === ".zip") {
          logger.debug(`Skipping: ${song.filename}`, { reason: "invalid format" });
          return null;
        }

        try {
          song = processBandcampMusic(song);
        } catch (error) {
          logger.warn(`Duplicate song detected: ${song.finalFilename}`, { error });
          return null;
        }

        existingMusicCache.push(song);

        logger.info(`✅ Processed: ${song.finalFilename}`);

        if (!debug) {
          await backupFile(startDir, backupDir, filename);
          await renameAndMove(moveDir, song, undefined, clear);
        }

        return song;
      },
      {
        batchSize: BATCH_SIZE,
        maxConcurrency: MAX_CONCURRENCY,
        useCache: true,
        onProgress: (processed, total) => {
          const percentage = ((processed / total) * 100).toFixed(1);
          logger.info(`📊 Progress: ${processed}/${total} (${percentage}%)`);
        },
      }
    );

    const count = results.filter((r) => r !== null).length;

    performanceMonitor.endOperation(operationId, {
      processed: count,
      totalFiles: files.length,
      cacheHits: bandcampCache.size(),
    });

    logger.info(`🎉 Bandcamp processing complete! Total processed: ${count}`);
    console.log(`Total Count: ${count}`);
  } catch (error) {
    performanceMonitor.endOperation(operationId, { error: error as Error });
    logger.error("Bandcamp processing failed", error as Error);
    throw error;
  }
}

function processBandcampMusic(song: DownloadedSong): DownloadedSong {
  song.removeBadCharacters();

  /* GRAB ARTIST */
  grabBandcampArtist(song);

  /* GRAB ALBUM */
  if (!song.album && song.dashCount > 1) {
    song.album = song.grabFirst();
  }

  /* GRAB TITLE */
  song.title = song.grabLast();

  /* FINAL CHECK */
  song.checkFeat();
  song.removeAnd("artist", "album");
  song.lastCheck();

  /* ALL TOGETHER NOW */
  song = setFinalDownloadedSongName(song);

  song.duplicate = checkIfDuplicate(song, existingMusicCache);
  if (song.duplicate) {
    throw "Duplicate Song";
  }

  return song;
}

function grabBandcampArtist(song: DownloadedSong): DownloadedSong {
  song.checkRemix();

  if (song.remix) {
    /* if it's a remix, the original artist is assigned to album, remove &'s from it */
    song.album = song.dashCount === 1 ? song.grabFirst() : song.grabSecond();
    song.removeAnd("album");
  } else {
    /* otherwise the artist is straightforward */
    song.artist = song.dashCount === 1 ? song.grabFirst() : song.grabSecond();
  }

  song.checkWith();

  return song;
}
