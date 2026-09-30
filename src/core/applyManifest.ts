import { backupFile, cacheMusic, checkIfDuplicate, logWithBreak, renameAndMove, setFinalDownloadedSongName } from "./utils/common.ts";
import { DownloadedSong } from "./models/Song.ts";
import { parseDownloadedSong } from "./parser.ts";
import { tagsFromFilename } from "./tagging.ts";
import { Manifest } from "./manifest.ts";
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

/**
 * Moves only entries with decision "apply", from the manifest's source_dir into its move_dir,
 * checking duplicates against its cache_dir. The folders come from the manifest, not the env, so
 * an apply lands where the dry run said it would.
 */
export async function applyManifest(manifest: Manifest, { backupDir }: { backupDir: string }): Promise<ApplyResult> {
  const sourceDir = withTrailingSlash(manifest.source_dir);
  const destDir = withTrailingSlash(manifest.move_dir);

  const cache = await cacheMusic(withTrailingSlash(manifest.cache_dir));

  const moves: { src: string; song: DownloadedSong }[] = [];
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
    moves.push({ src: entry.src, song });
  }

  if (moves.length === 0) return { applied: 0, skipped, failures: [], runBackupDir: null };

  const runBackupDir = await startBackupRun(backupDir, "rename-music");
  const failures = await settleMoves(
    moves.map(({ src, song }) =>
      backupFile(sourceDir, runBackupDir, src).then(() => renameAndMove(destDir, song, undefined, true))
    ),
    moves.map(({ src }) => src),
  );
  return { applied: moves.length - failures.length, skipped, failures, runBackupDir };
}
