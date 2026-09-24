/*
Renames downloaded music to the format that I like. Also converts to flac if wav.

Modes:
  (default)              dry-run: parse all files, score confidence, write a manifest
                         to logs/tunewrangler/manifests/rename-manifest-<timestamp>.json,
                         do not move anything.
  --apply <manifest>     read the given manifest and move only entries whose
                         decision is "apply". Edit the manifest first to override.
  --move                 legacy: process and immediately move all files (no manifest).
  --prune [--keep N]     list backup runs beyond the newest N (default 5) in the backup
                         folder; add --yes to delete them.

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
import { pruneBackups, runStamp, startBackupRun } from "../core/utils/backups.ts";
import { applyJudgement, assertJudgeAvailable, getJudgeThreshold, judgeEntries } from "../core/judge.ts";

const startDir = getFolder("downloaded");
const cacheDir = getFolder("djMusic");
const moveDir = getFolder("rename");
const backupDir = getFolder("backup");
const MANIFEST_DIR = "./logs/tunewrangler/manifests";

/** A duplicate skip always carries this reason first (see buildEntry) — distinguishes it from
 * the .m4s hard-skip path, which is not judged. */
const DUPLICATE_REASON = "duplicate of an existing track in the DJ collection";

const args = parseArgs(Deno.args, {
  string: ["apply", "manifest", "keep"],
  boolean: ["move", "no-clear", "judge", "prune", "yes"],
  default: { "no-clear": false, judge: false, keep: "5" },
});

// Fail before any IO: parsing 283 files only to discover TYPESAFE_API_KEY is missing
// would waste the whole dry run.
if (args.judge) {
  await assertJudgeAvailable();
}

if (args.prune) {
  await runPrune(Number(args.keep), args.yes);
} else if (args.apply) {
  await runApply(args.apply);
} else if (args.move) {
  await runLegacyMove(!args["no-clear"]);
} else {
  await runDryRun(args.manifest);
}

function isJudgeCandidate(entry: ManifestEntry): boolean {
  return entry.decision === "apply" || (entry.decision === "skip" && entry.reasons[0] === DUPLICATE_REASON);
}

/**
 * Default mode: parse + score every file, write a manifest, do not move.
 * The user reviews the manifest, edits any "review" decisions, then runs --apply.
 */
async function runDryRun(manifestOverride?: string): Promise<void> {
  const cache = await cacheMusic(cacheDir);
  const built: BuildResult[] = [];

  for await (const currEntry of Deno.readDir(startDir)) {
    if (!isProcessable(currEntry)) continue;
    const result = buildEntry(currEntry.name, cache);
    if (result) built.push(result);
  }

  const manifestPath = manifestOverride ?? defaultManifestPath();
  const manifest: Manifest = {
    version: 1,
    generated_at: new Date().toISOString(),
    source_dir: startDir,
    move_dir: moveDir,
    cache_dir: cacheDir,
    entries: built.map((b) => b.entry),
  };
  await fs.ensureDir(MANIFEST_DIR);
  await writeManifest(manifestPath, manifest);

  const finalEntries = args.judge ? await judgeAndRewrite(built, manifest, manifestPath) : manifest.entries;

  printSummary(finalEntries, manifestPath);
}

/**
 * Judges the apply/duplicate-skip subset with Jev, folds the verdicts onto the manifest, and
 * rewrites it. Runs after the unjudged manifest is already on disk, so a throw here does not
 * discard the parse.
 */
async function judgeAndRewrite(
  built: BuildResult[],
  manifest: Manifest,
  manifestPath: string,
): Promise<ManifestEntry[]> {
  const candidates = built.filter((b) => isJudgeCandidate(b.entry));
  const threshold = getJudgeThreshold();

  console.log(`\nJudging ${candidates.length} entries with Jev (threshold ${threshold})...`);
  const judgements = await judgeEntries(candidates.map(({ entry, song }) => ({ entry, song })));

  const candidateSrcs = new Set(candidates.map((c) => c.entry.src));
  const finalEntries = manifest.entries.map((entry) =>
    candidateSrcs.has(entry.src) ? applyJudgement(entry, judgements.get(entry.src), threshold) : entry
  );

  const judged = finalEntries.filter((e) => e.judgement && !e.judgement.error).length;
  const judgeFailed = finalEntries.filter((e) => e.judgement?.error).length;
  console.log(`Judged: ${judged}, could not judge: ${judgeFailed} (of ${candidates.length} candidates)`);
  if (judged + judgeFailed !== candidates.length) {
    throw new Error(
      `judge post-condition failed: judged(${judged}) + judgeFailed(${judgeFailed}) !== candidates(${candidates.length})`,
    );
  }

  manifest.entries = finalEntries;
  await writeManifest(manifestPath, manifest);
  return finalEntries;
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
  const runBackupDir = await startBackupRun(backupDir, "rename-music");

  const moveOps: Promise<void>[] = [];
  const opSources: string[] = [];
  let applied = 0;
  let skipped = 0;

  for (const entry of manifest.entries) {
    if (entry.decision !== "apply") {
      skipped++;
      continue;
    }

    if (entry.judgement && entry.judgement.judged_proposed !== entry.proposed) {
      logWithBreak(
        `***Warning: judgement for ${entry.src} graded "${entry.judgement.judged_proposed}", but proposed is now "${entry.proposed}" — its probabilities describe a different string***`,
      );
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
      backupFile(sourceDir, runBackupDir, entry.src).then(() =>
        renameAndMove(destDir, song, undefined, true)
      )
    );
    opSources.push(entry.src);
    applied++;
  }

  const failed = await settleMoves(moveOps, opSources);
  console.log(`\nApplied: ${applied - failed}, failed: ${failed}, skipped (review/skip/duplicate): ${skipped}`);
  console.log(`Originals backed up to: ${runBackupDir}`);
}

/**
 * Waits for every move, not just until the first failure: Promise.all would reject while the
 * rest kept converting in the background, and the summary would never print.
 */
async function settleMoves(ops: Promise<void>[], sources: string[]): Promise<number> {
  const results = await Promise.allSettled(ops);
  const failures = results.flatMap((r, i) => r.status === "rejected" ? [{ src: sources[i], reason: r.reason }] : []);
  if (failures.length > 0) {
    console.error(`\n${failures.length} file(s) failed — each original is still in the source folder:`);
    for (const f of failures) console.error(`  ${f.src}: ${f.reason instanceof Error ? f.reason.message : f.reason}`);
    Deno.exitCode = 1;
  }
  return failures.length;
}

async function runPrune(keep: number, apply: boolean): Promise<void> {
  const stale = await pruneBackups(backupDir, keep, { apply });
  if (stale.length === 0) {
    console.log(`Nothing to prune: ${backupDir} holds ${keep} or fewer backup runs.`);
    return;
  }
  console.log(`${apply ? "Deleted" : "Would delete"} ${stale.length} backup run(s), keeping the newest ${keep}:`);
  for (const name of stale) console.log(`  ${name}`);
  if (!apply) console.log("\nRe-run with --yes to delete them.");
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
  const runBackupDir = await startBackupRun(backupDir, "rename-music");

  const moveOps: Promise<void>[] = [];
  const opSources: string[] = [];
  let count = 0;

  for await (const currEntry of Deno.readDir(startDir)) {
    if (!isProcessable(currEntry)) continue;

    const result = buildEntry(currEntry.name, cache);
    if (!result || result.entry.decision === "skip") continue;
    const entry = result.entry;

    const song = new DownloadedSong(entry.src, startDir);
    if (song.dashCount > 0) parseDownloadedSong(song);
    setFinalDownloadedSongName(song);
    cache.add(song);

    logWithBreak(song.finalFilename);
    moveOps.push(
      backupFile(startDir, runBackupDir, entry.src).then(() =>
        renameAndMove(moveDir, song, undefined, clear)
      )
    );
    opSources.push(entry.src);
    count++;
  }

  const failed = await settleMoves(moveOps, opSources);
  console.log(`\nTotal moved: ${count - failed}, failed: ${failed}`);
  console.log(`Originals backed up to: ${runBackupDir}`);
}

interface BuildResult {
  entry: ManifestEntry;
  song: DownloadedSong;
}

/**
 * Parse one file and produce a manifest entry (plus the song it was parsed from, so a
 * --judge pass can grade the same parse without re-deriving it), or null if the file should
 * be skipped (unsupported extension, parser threw, etc.).
 */
function buildEntry(filename: string, cache: MusicCache): BuildResult | null {
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
        song,
        entry: {
          src: filename,
          proposed: song.finalFilename,
          parser_output: song.finalFilename,
          confidence: score.level,
          reasons: [DUPLICATE_REASON, ...score.reasons],
          decision: "skip",
        },
      };
    }

    cache.add(song);
    logWithBreak(`${song.finalFilename}  [${score.level}]`);

    return {
      song,
      entry: {
        src: filename,
        proposed: song.finalFilename,
        parser_output: song.finalFilename,
        confidence: score.level,
        reasons: score.reasons,
        decision: score.decision,
      },
    };
  } catch (error) {
    logWithBreak(`Skipping (parse error): ${filename} - ${error}`);
    return null;
  }
}

function printSummary(entries: ManifestEntry[], manifestPath: string): void {
  const byDecision = { apply: 0, review: 0, skip: 0 };
  const byConfidence = { high: 0, medium: 0, low: 0 };
  let downgradedByJudge = 0;
  for (const e of entries) {
    byDecision[e.decision]++;
    byConfidence[e.confidence]++;
    if (e.decision === "review" && e.judgement && !e.judgement.error) downgradedByJudge++;
  }

  console.log("\n========================================");
  console.log(`Manifest written: ${manifestPath}`);
  console.log("");
  console.log(`  will apply:   ${byDecision.apply}`);
  console.log(
    `  needs review: ${byDecision.review}${downgradedByJudge > 0 ? ` (${downgradedByJudge} downgraded by Jev)` : ""}`,
  );
  console.log(`  will skip:    ${byDecision.skip}`);
  console.log("");
  console.log(`  confidence — high: ${byConfidence.high}, medium: ${byConfidence.medium}, low: ${byConfidence.low}`);
  console.log("");
  console.log(`Next steps:`);
  console.log(`  1. Open ${manifestPath} and review the ${byDecision.review} entries needing review`);
  console.log(`  2. Edit "decision" fields ("apply" to move, "skip" to leave alone)`);
  console.log(`  3. Run: deno task rM --apply ${manifestPath}`);
  console.log(`     (will move ${byDecision.apply} files)`);
  console.log("========================================");
}

function defaultManifestPath(): string {
  return `${MANIFEST_DIR}/rename-manifest-${runStamp()}.json`;
}
