/*
Writes artist/album/title tags from each file's `artist - album - title` name, so players that
read tags (Rekordbox reads them on import) agree with the filename.

  deno task retag                     dry run over the rename folder: list what would change
  deno task retag --dir <folder>      any other folder, e.g. the DJ collection
  deno task retag --yes               write the tags (audio is stream-copied, never re-encoded)
  deno task retag --overwrite         also replace tags that are set but disagree with the name;
                                      by default only missing tags are filled in
*/
import { parseArgs } from "@std/cli/parse-args";
import { extname, join } from "@std/path";

import { getFolder, isProcessable } from "../core/utils/common.ts";
import { readTags, tagsFromFilename, TrackTags, writeTagsInPlace } from "../core/tagging.ts";

const TAGGABLE = new Set([".aiff", ".aif", ".mp3"]);
const FIELDS = ["artist", "album", "title"] as const;

export interface RetagPlan {
  file: string;
  next: TrackTags;
  changes: string[];
  kept: string[];
}

/** What the file's tags should become. Missing fields are filled; set ones are replaced only
 * with `overwrite`, and otherwise reported so a disagreement is never silent. */
export function planRetag(file: string, current: TrackTags, overwrite: boolean): RetagPlan {
  const wanted = tagsFromFilename(file);
  const next = { ...current };
  const changes: string[] = [];
  const kept: string[] = [];
  for (const field of FIELDS) {
    const have = current[field].trim();
    const want = wanted[field];
    if (!want || have.normalize("NFC") === want) continue;
    if (!have || overwrite) {
      next[field] = want;
      changes.push(`${field}: ${have ? `"${have}" → ` : ""}"${want}"`);
    } else {
      kept.push(`${field}: "${have}" (name says "${want}")`);
    }
  }
  return { file, next, changes, kept };
}

async function main(): Promise<void> {
  const args = parseArgs(Deno.args, { string: ["dir"], boolean: ["yes", "overwrite"] });
  const dir = args.dir ? (args.dir.endsWith("/") ? args.dir : `${args.dir}/`) : getFolder("rename");

  const plans: RetagPlan[] = [];
  const skipped: string[] = [];
  const entries = [];
  for await (const entry of Deno.readDir(dir)) entries.push(entry);
  entries.sort((a, b) => a.name.localeCompare(b.name));

  for (const entry of entries) {
    if (!isProcessable(entry) || entry.name.includes(".retag-tmp")) continue;
    if (!TAGGABLE.has(extname(entry.name).toLowerCase())) {
      skipped.push(entry.name);
      continue;
    }
    plans.push(planRetag(entry.name, await readTags(join(dir, entry.name)), args.overwrite));
  }

  const toWrite = plans.filter((p) => p.changes.length > 0);
  const disagreeing = plans.filter((p) => p.kept.length > 0);
  for (const p of toWrite) console.log(`${p.file}\n  ${p.changes.join("\n  ")}`);
  if (disagreeing.length > 0) {
    console.log(`\n${disagreeing.length} file(s) have tags that disagree with their name (kept; --overwrite replaces):`);
    for (const p of disagreeing) console.log(`${p.file}\n  ${p.kept.join("\n  ")}`);
  }
  if (skipped.length > 0) console.log(`\nNot taggable here (${skipped.length}): ${skipped.join(", ")}`);

  console.log(`\n${plans.length} taggable file(s) in ${dir}: ${toWrite.length} to update.`);
  if (!args.yes) {
    if (toWrite.length > 0) console.log("Dry run — re-run with --yes to write.");
    return;
  }

  let failed = 0;
  for (const p of toWrite) {
    try {
      await writeTagsInPlace(join(dir, p.file), p.next);
    } catch (error) {
      failed++;
      console.error(`FAILED ${p.file}: ${error instanceof Error ? error.message : error}`);
    }
  }
  console.log(`Wrote tags on ${toWrite.length - failed} file(s), ${failed} failed.`);
  if (failed > 0) Deno.exitCode = 1;
}

if (import.meta.main) await main();
