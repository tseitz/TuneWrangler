/*
Renames downloaded music to the format that I like. Also converts to flac if wav.

Modes:
  (default)              dry-run: parse all files, score confidence, write a manifest
                         to logs/tunewrangler/manifests/rename-manifest-<timestamp>.json,
                         do not move anything.
  --apply <manifest>     read the given manifest and move only entries whose
                         decision is "apply". Edit the manifest first to override.
  --move                 legacy: process and immediately move all files (no manifest).

Incoming (generally): album - artist - title
Outgoing:             artist - album - title
*/
import * as fs from "@std/fs";
import { parseArgs } from "@std/cli/parse-args";

import {
  backupFile,
  cacheMusic,
  checkIfDuplicate,
  getFolder,
  isProcessable,
  logWithBreak,
  MusicCache,
  renameAndMove,
  setFinalDownloadedSongName,
} from "../core/utils/common.ts";
import { DownloadedSong } from "../core/models/Song.ts";
import { parseDownloadedSong } from "../core/parser.ts";
import { scoreConfidence } from "../core/confidence.ts";
import {
  Manifest,
  ManifestEntry,
  readManifest,
  writeManifest,
} from "../core/manifest.ts";

const startDir = getFolder("downloaded");
const cacheDir = getFolder("djMusic");
const moveDir = getFolder("rename");
const backupDir = getFolder("backup");
const MANIFEST_DIR = "./logs/tunewrangler/manifests";

const args = parseArgs(Deno.args, {
  string: ["apply", "manifest"],
  boolean: ["move", "no-clear"],
  default: { "no-clear": false },
});

if (args.apply) {
  await runApply(args.apply);
} else if (args.move) {
  await runLegacyMove(!args["no-clear"]);
} else {
  await runDryRun(args.manifest);
}

/**
 * Default mode: parse + score every file, write a manifest, do not move.
 * The user reviews the manifest, edits any "review" decisions, then runs --apply.
 */
async function runDryRun(manifestOverride?: string): Promise<void> {
  const cache = await cacheMusic(cacheDir);
  const entries: ManifestEntry[] = [];

  for await (const currEntry of Deno.readDir(startDir)) {
    if (!isProcessable(currEntry)) continue;
    const entry = buildEntry(currEntry.name, cache);
    if (entry) entries.push(entry);
  }

  const manifestPath = manifestOverride ?? defaultManifestPath();
  const manifest: Manifest = {
    version: 1,
    generated_at: new Date().toISOString(),
    source_dir: startDir,
    move_dir: moveDir,
    cache_dir: cacheDir,
    entries,
  };
  await fs.ensureDir(MANIFEST_DIR);
  await writeManifest(manifestPath, manifest);

  printSummary(entries, manifestPath);
}

/**
 * Apply mode: read a manifest the user has reviewed, move only entries
 * marked decision: "apply". Skip "review" and "skip" entries silently.
 */
async function runApply(manifestPath: string): Promise<void> {
  const manifest = await readManifest(manifestPath);

  // Use paths from the manifest so --apply works regardless of env vars set at
  // the time of this invocation. Ensure trailing slash for string concatenation.
  const sourceDir = trailingSlash(manifest.source_dir);
  const destDir = trailingSlash(manifest.move_dir);

  const cache = await cacheMusic(cacheDir);
  await fs.emptyDir(backupDir);

  const moveOps: Promise<void>[] = [];
  let applied = 0;
  let skipped = 0;

  for (const entry of manifest.entries) {
    if (entry.decision !== "apply") {
      skipped++;
      continue;
    }

    const song = new DownloadedSong(entry.src, sourceDir);
    if (song.dashCount > 0) parseDownloadedSong(song);
    setFinalDownloadedSongName(song);

    // Honor user override: if the manifest's proposed name differs from what
    // the parser produces, trust the manifest (the user may have edited it).
    if (entry.proposed && entry.proposed !== song.finalFilename) {
      song.finalFilename = entry.proposed;
    }

    if (checkIfDuplicate(song, cache)) {
      logWithBreak(`***Duplicate, skipping: ${song.finalFilename}***`);
      skipped++;
      continue;
    }
    cache.add(song);

    moveOps.push(
      backupFile(sourceDir, backupDir, entry.src).then(() =>
        renameAndMove(destDir, song, undefined, true)
      )
    );
    applied++;
  }

  await Promise.all(moveOps);
  console.log(`\nApplied: ${applied}, skipped (review/skip/duplicate): ${skipped}`);
}

function trailingSlash(p: string): string {
  return p.endsWith("/") ? p : p + "/";
}

/**
 * Legacy mode: parse and immediately move all files in one shot.
 * Preserved so existing workflows (deno task rM --move) keep working.
 */
async function runLegacyMove(clear: boolean): Promise<void> {
  const cache = await cacheMusic(cacheDir);
  if (clear) await fs.emptyDir(backupDir);

  const moveOps: Promise<void>[] = [];
  let count = 0;

  for await (const currEntry of Deno.readDir(startDir)) {
    if (!isProcessable(currEntry)) continue;

    const entry = buildEntry(currEntry.name, cache);
    if (!entry || entry.decision === "skip") continue;

    const song = new DownloadedSong(entry.src, startDir);
    if (song.dashCount > 0) parseDownloadedSong(song);
    setFinalDownloadedSongName(song);
    cache.add(song);

    logWithBreak(song.finalFilename);
    moveOps.push(
      backupFile(startDir, backupDir, entry.src).then(() =>
        renameAndMove(moveDir, song, undefined, clear)
      )
    );
    count++;
  }

  await Promise.all(moveOps);
  console.log(`\nTotal moved: ${count}`);
}

/**
 * Parse one file and produce a manifest entry, or null if the file should be skipped
 * (unsupported extension, parser threw, etc.).
 */
function buildEntry(filename: string, cache: MusicCache): ManifestEntry | null {
  console.log("Processing: ", filename);
  try {
    const song = new DownloadedSong(filename, startDir);

    if (!song.extension || song.extension === ".m3u" || song.extension === ".zip") {
      logWithBreak(`Skipping (unsupported extension): ${song.filename}`);
      return null;
    }

    if (song.dashCount > 0) parseDownloadedSong(song);
    setFinalDownloadedSongName(song);

    const score = scoreConfidence(song, filename);
    const isDuplicate = checkIfDuplicate(song, cache);

    if (isDuplicate) {
      return {
        src: filename,
        proposed: song.finalFilename,
        parser_output: song.finalFilename,
        confidence: score.level,
        reasons: ["duplicate of an existing track in the DJ collection", ...score.reasons],
        decision: "skip",
      };
    }

    cache.add(song);
    logWithBreak(`${song.finalFilename}  [${score.level}]`);

    return {
      src: filename,
      proposed: song.finalFilename,
      parser_output: song.finalFilename,
      confidence: score.level,
      reasons: score.reasons,
      decision: score.decision,
    };
  } catch (error) {
    logWithBreak(`Skipping (parse error): ${filename} - ${error}`);
    return null;
  }
}

function printSummary(entries: ManifestEntry[], manifestPath: string): void {
  const counts = { high: 0, medium: 0, low: 0, skip: 0 };
  for (const e of entries) {
    if (e.decision === "skip") counts.skip++;
    else counts[e.confidence]++;
  }
  const willApply = counts.high + counts.medium;
  const needsReview = counts.low;

  console.log("\n========================================");
  console.log(`Manifest written: ${manifestPath}`);
  console.log("");
  console.log(`  high confidence:   ${counts.high}  (will apply)`);
  console.log(`  medium confidence: ${counts.medium}  (will apply)`);
  console.log(`  low confidence:    ${counts.low}  (needs review)`);
  console.log(`  duplicates:        ${counts.skip}  (will skip)`);
  console.log("");
  console.log(`Next steps:`);
  console.log(`  1. Open ${manifestPath} and review the ${needsReview} low-confidence entries`);
  console.log(`  2. Edit "decision" fields ("apply" to move, "skip" to leave alone)`);
  console.log(`  3. Run: deno task rM --apply ${manifestPath}`);
  console.log(`     (will move ${willApply} files)`);
  console.log("========================================");
}

function defaultManifestPath(): string {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").replace("T", "_").slice(0, 19);
  return `${MANIFEST_DIR}/rename-manifest-${stamp}.json`;
}
