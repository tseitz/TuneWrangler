import { backupFile, cacheMusic, checkIfDuplicate, logWithBreak, renameAndMove } from "./utils/common.ts";
import { Song } from "./models/Song.ts";
import { buildSong } from "./sources.ts";
import { tagsFromFilename } from "./tagging.ts";
import { entryKey, Manifest, sourceDirFor } from "./manifest.ts";
import { startBackupRun } from "./utils/backups.ts";

export interface MoveFailure {
  src: string;
  reason: unknown;
}

export interface ApplyResult {
  applied: number;
  skipped: number;
  failures: MoveFailure[];
  /** Null when nothing moved: an empty run folder would push a real one out of `rM --prune --keep`. */
  runBackupDir: string | null;
}

export function withTrailingSlash(p: string): string {
  return p.endsWith("/") ? p : p + "/";
}

/**
 * Waits for every move, not just until the first failure: Promise.all would reject while the
 * rest kept converting in the background, and the summary would never print.
 */
export async function settleMoves(ops: Promise<void>[], sources: string[]): Promise<MoveFailure[]> {
  const results = await Promise.allSettled(ops);
  return results.flatMap((r, i) => r.status === "rejected" ? [{ src: sources[i], reason: r.reason }] : []);
}

/** `src` is text from an editable manifest; a symlinked folder on its path could lead outside `dir`. */
async function assertRegularFileInside(dir: string, src: string): Promise<void> {
  const path = `${dir}${src}`;
  if (!(await Deno.lstat(path)).isFile) throw new Error(`${path} is not a regular file`);
  const [realDir, realPath] = await Promise.all([Deno.realPath(dir), Deno.realPath(path)]);
  if (!realPath.startsWith(`${realDir}/`)) throw new Error(`${path} resolves outside ${dir}`);
}

/** Downloaded-root files keep the flat backup layout older runs used. */
export function backupNameFor(entry: { source?: string; src: string }): string {
  return !entry.source || entry.source === "downloaded" ? entry.src : `${entry.source}/${entry.src}`;
}

/**
 * Moves only entries with decision "apply", from each entry's source folder into its move_dir,
 * checking duplicates against its cache_dir. The folders come from the manifest, not the env, so
 * an apply lands where the dry run said it would.
 */
export async function applyManifest(manifest: Manifest, { backupDir }: { backupDir: string }): Promise<ApplyResult> {
  const destDir = withTrailingSlash(manifest.move_dir);

  const cache = await cacheMusic(withTrailingSlash(manifest.cache_dir));

  const moves: { key: string; dir: string; src: string; backupName: string; song: Song }[] = [];
  const failures: MoveFailure[] = [];
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

    let song: Song;
    let dir: string;
    try {
      dir = withTrailingSlash(sourceDirFor(manifest, entry));
      await assertRegularFileInside(dir, entry.src);
      song = buildSong(entry.source ?? "downloaded", entry.src, dir, entry.tags);
    } catch (reason) {
      failures.push({ src: entryKey(entry), reason });
      continue;
    }

    // Honor user override: if the manifest's proposed name differs from what
    // the parser produces, trust the manifest (the user may have edited it).
    if (entry.proposed && entry.proposed !== song.finalFilename) {
      song.finalFilename = entry.proposed;
      // The tags are written from these fields, so without this an override renames the
      // file while its tags keep the parse the user rejected.
      Object.assign(song, tagsFromFilename(entry.proposed));
    }

    if (checkIfDuplicate(song, cache)) {
      logWithBreak(`***Duplicate, skipping: ${song.finalFilename}***`);
      skipped++;
      continue;
    }
    cache.add(song);
    moves.push({ key: entryKey(entry), dir, src: entry.src, backupName: backupNameFor(entry), song });
  }

  if (moves.length === 0) return { applied: 0, skipped, failures, runBackupDir: null };

  const runBackupDir = await startBackupRun(backupDir, "rename-music");
  const moveFailures = await settleMoves(
    moves.map(({ dir, src, backupName, song }) =>
      backupFile(dir, runBackupDir, src, backupName).then(() => renameAndMove(destDir, song, undefined, true))
    ),
    moves.map(({ key }) => key),
  );
  return {
    applied: moves.length - moveFailures.length,
    skipped,
    failures: [...failures, ...moveFailures],
    runBackupDir,
  };
}
