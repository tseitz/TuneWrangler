import { ensureDir } from "@std/fs";
import { join } from "@std/path";

const RUN_DIR = /^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_/;

export function runStamp(now: Date = new Date()): string {
  return now.toISOString().replace(/[:.]/g, "-").replace("T", "_").slice(0, 19);
}

/**
 * A fresh backup folder for one run, under the shared backup root. Each run gets its own so a
 * later run never erases the only copy of an earlier run's originals.
 */
export async function startBackupRun(backupRoot: string, label: string, now: Date = new Date()): Promise<string> {
  const dir = join(backupRoot, `${runStamp(now)}_${label}`) + "/";
  await ensureDir(dir);
  return dir;
}

/** Run folders, oldest first. Loose files and folders of any other name are not runs. */
export async function listBackupRuns(backupRoot: string): Promise<string[]> {
  const runs: string[] = [];
  for await (const entry of Deno.readDir(backupRoot)) {
    if (entry.isDirectory && RUN_DIR.test(entry.name)) runs.push(entry.name);
  }
  return runs.sort();
}

/** The run folders beyond the newest `keep`; deleted only when `apply` is set. */
export async function pruneBackups(
  backupRoot: string,
  keep: number,
  { apply }: { apply: boolean },
): Promise<string[]> {
  if (!Number.isInteger(keep) || keep < 1) {
    throw new Error(`--keep must be a whole number of at least 1, got ${keep}`);
  }
  const runs = await listBackupRuns(backupRoot);
  const stale = runs.slice(0, Math.max(0, runs.length - keep));
  if (apply) {
    for (const name of stale) await Deno.remove(join(backupRoot, name), { recursive: true });
  }
  return stale;
}
