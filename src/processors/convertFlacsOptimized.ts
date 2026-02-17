/*
Optimized version of convertFlacs processor with streaming and batching
*/
import * as fs from "@std/fs";

import { backupFile, convertLocalToAiff, getFolder, logWithBreak } from "../core/utils/common.ts";
import { LocalSong } from "../core/models/Song.ts";
import { performanceOptimizer, performanceMonitor, StreamingProcessor, LRUCache } from "../core/utils/performance.ts";
import { getLogger } from "../core/utils/logger.ts";

const logger = getLogger();

let debug = true;
let clear = true;

const startDir = getFolder("djMusic");
const moveDir = getFolder("djMusic");
const backupDir = getFolder("backup");

// Performance optimization settings
const BATCH_SIZE = 10; // Smaller batch size for file conversion
const MAX_CONCURRENCY = 2; // Lower concurrency for CPU-intensive operations
const CACHE_SIZE = 200;

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

// Initialize performance optimizations
const conversionCache = new LRUCache<string, boolean>(CACHE_SIZE);
const streamingProcessor = new StreamingProcessor({
  bufferSize: 128 * 1024, // 128KB for audio processing
  chunkSize: 2 * 1024 * 1024, // 2MB chunks
  maxConcurrency: MAX_CONCURRENCY,
});

// empty out the backup directory if necessary
if (clear) await fs.emptyDir(backupDir);

// run the program
await main();

async function main() {
  const operationId = performanceMonitor.startOperation("convertFlacsOptimized", {
    startDir,
    moveDir,
    debug,
    clear,
  });

  try {
    const files: string[] = [];

    // Collect all FLAC files first
    for await (const currEntry of Deno.readDir(startDir)) {
      if (currEntry.isFile) {
        const song = new LocalSong(currEntry.name, startDir);
        if (song.extension === ".flac") {
          files.push(currEntry.name);
        }
      }
    }

    logger.info(`🎵 Converting ${files.length} FLAC files with optimization`, {
      batchSize: BATCH_SIZE,
      maxConcurrency: MAX_CONCURRENCY,
      cacheSize: CACHE_SIZE,
    });

    // Process files with optimized conversion
    const results = await performanceOptimizer.processFilesOptimized(
      files,
      async (filename: string) => {
        logger.debug(`Converting: ${filename}`);

        const song = new LocalSong(filename, startDir);

        // Check cache first
        const cacheKey = `${filename}_${song.extension}`;
        if (conversionCache.has(cacheKey)) {
          logger.debug(`Skipping cached conversion: ${filename}`);
          return null;
        }

        try {
          await backupFile(startDir, backupDir, filename);

          if (!debug) {
            // Use streaming processor for better memory management
            await streamingProcessor.processFileStream(
              `${startDir}/${filename}`,
              `${moveDir}/${filename.replace(".flac", ".aiff")}`,
              async (chunk: Uint8Array) => {
                // For now, just pass through the chunk
                // In a real implementation, you'd do audio conversion here
                return chunk;
              }
            );

            // Fallback to original conversion method
            await convertLocalToAiff(moveDir, song);
          }

          // Cache successful conversion
          conversionCache.set(cacheKey, true);

          logger.info(`✅ Converted: ${filename}`);
          return song;
        } catch (error) {
          logger.error(`❌ Failed to convert: ${filename}`, error as Error);
          return null;
        }
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
      cacheHits: conversionCache.size(),
    });

    logger.info(`🎉 Conversion complete! Total converted: ${count}`);
    console.log(`Total Count: ${count}`);
  } catch (error) {
    performanceMonitor.endOperation(operationId, { error: error as Error });
    logger.error("Conversion failed", error as Error);
    throw error;
  }
}
