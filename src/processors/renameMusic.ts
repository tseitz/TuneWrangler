/*
Renames downloaded music to the format that I like. Also converts to flac if wav.

Modes:
  (default)              dry-run: parse all files, score confidence, write a manifest
                         to logs/tunewrangler/manifests/rename-manifest-<timestamp>.json,
                         do not move anything.
  --apply <manifest>     read the given manifest and move only entries whose
                         decision is "apply" into the DJ Collection. Edit the manifest
                         first to override.
  --auto                 dry run, then apply the manifest it just wrote (unattended runs).
  --move                 legacy: process and immediately move all files (no manifest).
  --prune [--keep N]     list backup runs beyond the newest N (default 5) in the backup
                         folder; add --yes to delete them.

Exits 75 when a folder is unavailable or another run holds the lock; nothing was changed.

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
import { applyManifest, MoveFailure, settleMoves, withTrailingSlash } from "../core/applyManifest.ts";
import { PATH_ENV_VARS, requireFolders } from "../config/paths.ts";
import { TryLaterError } from "../core/utils/errors.ts";
import { acquireRunLock } from "../core/utils/runLock.ts";
import { scoreConfidence } from "../core/confidence.ts";
import { applySoundcloudCredits, factsFor, loadSoundcloudIndex } from "../core/soundcloudFacts.ts";
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
const moveDir = cacheDir;
const backupDir = getFolder("backup");
const MANIFEST_DIR = "./logs/tunewrangler/manifests";
const LOCK_PATH = "./logs/tunewrangler/rm.lock";
const EX_TEMPFAIL = 75;

/** A duplicate skip always carries this reason first (see buildEntry) — distinguishes it from
 * the .m4s hard-skip path, which is not judged. */
const DUPLICATE_REASON = "duplicate of an existing track in the DJ collection";

const args = parseArgs(Deno.args, {
  string: ["apply", "manifest", "keep"],
  boolean: ["move", "no-clear", "judge", "prune", "yes", "auto"],
  default: { "no-clear": false, judge: false, keep: "5" },
});

// Fail before any IO: parsing 283 files only to discover TYPESAFE_API_KEY is missing
// would waste the whole dry run.
if (args.judge) {
  await assertJudgeAvailable();
}

const modes = [args.prune, Boolean(args.apply), args.move, args.auto].filter(Boolean).length;
if (modes > 1) {
  console.error("Pick one of --prune, --apply, --move, --auto.");
  Deno.exit(2);
}

try {
  if (args.prune) {
    await runPrune(Number(args.keep), args.yes);
  } else if (args.apply) {
    await withRunLock(() => runApply(args.apply!));
  } else if (args.move) {
    await withRunLock(() => runLegacyMove(!args["no-clear"]));
  } else if (args.auto) {
    await withRunLock(async () => await runApply(await runDryRun(args.manifest, { auto: true })));
  } else {
    await runDryRun(args.manifest);
  }
} catch (error) {
  if (!(error instanceof TryLaterError)) throw error;
  console.error(error.message);
  Deno.exit(EX_TEMPFAIL);
}

async function withRunLock(run: () => Promise<void>): Promise<void> {
  await fs.ensureDir("./logs/tunewrangler");
  const release = await acquireRunLock(LOCK_PATH);
  try {
    await run();
  } finally {
    // The OS frees the lock on exit anyway; a failed release must not hide the run's own error.
    await release().catch((error) => console.error(`Could not release ${LOCK_PATH}: ${error}`));
  }
}

function envFolders(...keys: (keyof typeof PATH_ENV_VARS)[]): Record<string, string> {
  return Object.fromEntries(keys.map((key) => [PATH_ENV_VARS[key], getFolder(key)]));
}

function isJudgeCandidate(entry: ManifestEntry): boolean {
  return entry.decision === "apply" || (entry.decision === "skip" && entry.reasons[0] === DUPLICATE_REASON);
}

/**
 * Default mode: parse + score every file, write a manifest, do not move.
 * The user reviews the manifest, edits any "review" decisions, then runs --apply.
 * Returns the manifest path once it is final, i.e. after any --judge rewrite.
 */
async function runDryRun(manifestOverride?: string, { auto = false } = {}): Promise<string> {
  await requireFolders(envFolders("downloaded", "djMusic", ...(auto ? ["backup" as const] : [])));
  const cache = await cacheMusic(cacheDir);
  const soundcloud = await loadSoundcloudIndex();
  const built: BuildResult[] = [];

  for await (const currEntry of Deno.readDir(startDir)) {
    if (!isProcessable(currEntry)) continue;
    const result = buildEntry(currEntry.name, cache);
    if (!result) continue;
    const facts = factsFor(soundcloud, result.entry.src);
    built.push(facts ? { ...result, entry: applySoundcloudCredits(result.entry, facts) } : result);
  }
  const matched = built.filter((b) => b.entry.soundcloud).length;
  console.log(`\nsoundcloud facts: ${matched}/${built.length} entries matched (index has ${soundcloud.size})`);

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

  printSummary(finalEntries, manifestPath, { auto });
  return manifestPath;
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
  // The manifest's folders, not the env's: apply lands where the dry run said it would.
  await requireFolders({
    [`${manifestPath} source_dir`]: manifest.source_dir,
    [`${manifestPath} move_dir`]: manifest.move_dir,
    [`${manifestPath} cache_dir`]: manifest.cache_dir,
    [PATH_ENV_VARS.backup]: backupDir,
  });

  const result = await applyManifest(manifest, { backupDir });
  reportFailures(result.failures);
  console.log(
    `\nApplied: ${result.applied}, failed: ${result.failures.length}, skipped (review/skip/duplicate): ${result.skipped}`,
  );
  console.log(`Moved into: ${withTrailingSlash(manifest.move_dir)}`);
  if (result.runBackupDir) console.log(`Originals backed up to: ${result.runBackupDir}`);
}

function reportFailures(failures: MoveFailure[]): void {
  if (failures.length === 0) return;
  console.error(`\n${failures.length} file(s) failed — each original is still in the source folder:`);
  for (const f of failures) console.error(`  ${f.src}: ${f.reason instanceof Error ? f.reason.message : f.reason}`);
  Deno.exitCode = 1;
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

/**
 * Legacy mode: parse and immediately move all files in one shot.
 * Preserved so existing workflows (deno task rM --move) keep working.
 */
async function runLegacyMove(clear: boolean): Promise<void> {
  await requireFolders(envFolders("downloaded", "djMusic", "backup"));
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

  const failures = await settleMoves(moveOps, opSources);
  reportFailures(failures);
  console.log(`\nTotal moved: ${count - failures.length}, failed: ${failures.length}`);
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

function printSummary(entries: ManifestEntry[], manifestPath: string, { auto }: { auto: boolean }): void {
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
  if (auto) {
    console.log(`Applying the ${byDecision.apply} "apply" entries now. The ${byDecision.review} needing review stay in`);
    console.log(`the source folder, and every run lists them again until they are handled.`);
    console.log("========================================");
    return;
  }
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
