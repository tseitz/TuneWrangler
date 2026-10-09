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
import { basename } from "@std/path";
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
import { DownloadedSong, Song } from "../core/models/Song.ts";
import { parseDownloadedSong } from "../core/parser.ts";
import { buildSong, isSkippedExtension, listSourceFiles, readSourceTags, type TaggedSourceFile } from "../core/sources.ts";
import { applyManifest, MoveFailure, settleMoves, withTrailingSlash } from "../core/applyManifest.ts";
import { PATH_ENV_VARS, requireFolders } from "../config/paths.ts";
import { TryLaterError } from "../core/utils/errors.ts";
import { acquireRunLock } from "../core/utils/runLock.ts";
import { scoreConfidence } from "../core/confidence.ts";
import { applySoundcloudCredits, factsFor, loadSoundcloudIndex } from "../core/soundcloudFacts.ts";
import {
  entryKey,
  Manifest,
  ManifestEntry,
  readManifest,
  type Source,
  sourceDirFor,
  writeManifest,
} from "../core/manifest.ts";
import { pruneBackups, runStamp, startBackupRun } from "../core/utils/backups.ts";
import { applyJudgement, assertJudgeAvailable, getJudgeThreshold, judgeEntries } from "../core/judge.ts";

const startDir = getFolder("downloaded");
const itunesDir = getFolder("itunes");
const cacheDir = getFolder("djMusic");
const moveDir = cacheDir;
const backupDir = getFolder("backup");
const MANIFEST_DIR = "./logs/tunewrangler/manifests";
const LOCK_PATH = "./logs/tunewrangler/rm.lock";
const EX_TEMPFAIL = 75;

/** A duplicate skip always carries this reason first (see buildEntry) — distinguishes it from
 * the .m4s hard-skip path, which is not judged. */
const DUPLICATE_REASON = "duplicate of an existing track in the DJ collection";

/** --auto runs unattended, so it only applies what arrives on its own; purchases wait for --apply. */
const AUTO_SOURCES: readonly Source[] = ["downloaded", "soundcloud"];

const SOURCE_DIRS: Record<Source, string> = {
  downloaded: startDir,
  soundcloud: `${startDir}soundcloud/`,
  bandcamp: `${startDir}bandcamp/`,
  beatport: `${startDir}beatport/`,
  itunes: itunesDir,
};

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
  await requireFolders(envFolders("downloaded", "itunes", "djMusic", ...(auto ? ["backup" as const] : [])));
  assertSoundcloudDirMatches();
  const cache = await cacheMusic(cacheDir);
  const soundcloud = await loadSoundcloudIndex();
  const built: BuildResult[] = [];

  const listing = await listSourceFiles({ downloaded: startDir, itunes: itunesDir });
  for (const warning of listing.warnings) console.warn(`Warning: ${warning}`);
  for (const folder of listing.ignoredFolders) console.log(`Ignoring folder (not a source): ${startDir}${folder}/`);
  for (const file of listing.skipped) logWithBreak(`Skipping (unsupported extension): ${entryKey(file)}`);

  for (const file of await readSourceTags(listing.files)) {
    const result = buildEntry(file, cache, { auto });
    if (!result) continue;
    const facts = factsFor(soundcloud, basename(result.entry.src));
    built.push(facts ? { ...result, entry: applySoundcloudCredits(result.entry, facts) } : result);
  }
  const matched = built.filter((b) => b.entry.soundcloud).length;
  console.log(`\nsoundcloud facts: ${matched}/${built.length} entries matched (index has ${soundcloud.size})`);

  const manifestPath = manifestOverride ?? defaultManifestPath();
  const manifest: Manifest = {
    version: 1,
    generated_at: new Date().toISOString(),
    source_dir: startDir,
    source_dirs: SOURCE_DIRS,
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

  const candidateKeys = new Set(candidates.map((c) => entryKey(c.entry)));
  const finalEntries = manifest.entries.map((entry) =>
    candidateKeys.has(entryKey(entry)) ? applyJudgement(entry, judgements.get(entryKey(entry)), threshold) : entry
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
  const usedSources = new Set(manifest.entries.filter((e) => e.decision === "apply").map((e) => e.source ?? "downloaded"));
  const sourceFolders = Object.fromEntries(
    [...usedSources].map((source) => [`${manifestPath} ${source} folder`, sourceDirFor(manifest, { source, src: "" })]),
  );
  await requireFolders({
    ...sourceFolders,
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
    if (!isProcessable(currEntry) || isSkippedExtension(currEntry.name)) continue;

    const result = buildEntry({ source: "downloaded", src: currEntry.name, dir: startDir }, cache);
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
  song: Song;
}

/**
 * Parse one file and produce a manifest entry (plus the song it was parsed from, so a
 * --judge pass can grade the same parse without re-deriving it), or null if the file should
 * be skipped (tags unreadable, parser threw, etc.).
 */
function buildEntry(file: TaggedSourceFile, cache: MusicCache, { auto = false } = {}): BuildResult | null {
  const key = entryKey(file);
  console.log("Processing: ", key);
  if (file.tagError) {
    logWithBreak(`Skipping (could not read tags): ${key} - ${file.tagError}`);
    return null;
  }
  try {
    const song = buildSong(file.source, file.src, file.dir, file.tags);
    const score = scoreConfidence(song, basename(file.src), { source: file.source, tags: file.tags });
    const base = {
      src: file.src,
      ...(file.source === "downloaded" ? {} : { source: file.source }),
      ...(file.tags ? { tags: file.tags } : {}),
      proposed: song.finalFilename,
      parser_output: song.finalFilename,
      confidence: score.level,
    };

    if (checkIfDuplicate(song, cache)) {
      return { song, entry: { ...base, reasons: [DUPLICATE_REASON, ...score.reasons], decision: "skip" } };
    }

    cache.add(song);
    logWithBreak(`${song.finalFilename}  [${score.level}]`);

    if (auto && score.decision === "apply" && !AUTO_SOURCES.includes(file.source)) {
      const reason = `--auto applies only the Downloaded root and soundcloud/; run --apply for ${file.source}`;
      return { song, entry: { ...base, reasons: [...score.reasons, reason], decision: "review" } };
    }
    return { song, entry: { ...base, reasons: score.reasons, decision: score.decision } };
  } catch (error) {
    logWithBreak(`Skipping (parse error): ${key} - ${error instanceof Error ? error.message : error}`);
    return null;
  }
}

/** soundcloud_dl writes where TUNEWRANGLER_SC_DOWNLOAD_DIR says; rM reads <downloaded>soundcloud/. */
function assertSoundcloudDirMatches(): void {
  const scDir = Deno.env.get("TUNEWRANGLER_SC_DOWNLOAD_DIR")?.trim();
  if (!scDir) return;
  const expected = withTrailingSlash(SOURCE_DIRS.soundcloud);
  if (withTrailingSlash(scDir) !== expected) {
    throw new Error(
      `TUNEWRANGLER_SC_DOWNLOAD_DIR is ${scDir}, but rM reads SoundCloud downloads from ${expected}. ` +
        `Point it at ${expected} (or move ${PATH_ENV_VARS.downloaded} to its parent).`,
    );
  }
}

function printSummary(entries: ManifestEntry[], manifestPath: string, { auto }: { auto: boolean }): void {
  const byDecision = { apply: 0, review: 0, skip: 0 };
  const byConfidence = { high: 0, medium: 0, low: 0 };
  const bySource = new Map<string, number>();
  let downgradedByJudge = 0;
  for (const e of entries) {
    const source = e.source ?? "downloaded";
    bySource.set(source, (bySource.get(source) ?? 0) + 1);
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
  console.log(`  by source — ${[...bySource].map(([source, n]) => `${source}: ${n}`).join(", ") || "none"}`);
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
