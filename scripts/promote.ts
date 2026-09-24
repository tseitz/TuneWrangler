/**
 * Promote a rename manifest into the regression test corpus.
 *
 * Usage:
 *   deno task promote ./logs/tunewrangler/manifests/rename-manifest-2026-05-03_15-35-10.json
 *
 * What it does:
 *   1. Reads the source manifest and validates it.
 *   2. Copies it into tests/corpus/ under a stable dated name.
 *   3. Prints a summary of what was promoted.
 *
 * Run this after `deno task rM --apply <manifest>` so the batch you just
 * approved (including any corrections you made) becomes permanent regression
 * coverage for future parser changes.
 *
 *   deno task promote --refresh
 *     After a parser fix: every corpus entry the parser now names exactly as you corrected it
 *     has its parser_output updated, turning it from an improvement target into a regression
 *     test. Re-promoting a manifest cannot do this — its parser_output is frozen at dry-run time.
 */
import { readManifest, writeManifest } from "../src/core/manifest.ts";
import { parseFilename } from "../src/core/corpus.ts";
import { ensureDir } from "@std/fs";
import { basename } from "@std/path";

const CORPUS_DIR = "./tests/corpus";

if (Deno.args[0] === "--refresh") {
  await refreshCorpus();
  Deno.exit(0);
}

async function refreshCorpus(): Promise<void> {
  let locked = 0;
  for await (const file of Deno.readDir(CORPUS_DIR)) {
    if (!file.isFile || !file.name.endsWith(".json")) continue;
    const path = `${CORPUS_DIR}/${file.name}`;
    const manifest = await readManifest(path);
    let changed = 0;
    for (const e of manifest.entries) {
      if (e.decision !== "apply" || e.proposed === e.parser_output) continue;
      if (parseFilename(e.src) !== e.proposed) continue;
      console.log(`  locked in: ${e.proposed}`);
      e.parser_output = e.proposed;
      changed++;
    }
    if (changed > 0) await writeManifest(path, manifest);
    locked += changed;
  }
  console.log(`\n✓ ${locked} improvement target(s) now match the parser and are regression tests.`);
}

const sourcePath = Deno.args[0];
if (!sourcePath) {
  console.error("Usage: deno task promote <path-to-manifest.json>");
  console.error(
    "Example: deno task promote ./logs/tunewrangler/manifests/rename-manifest-2026-05-03_15-35-10.json",
  );
  Deno.exit(1);
}

const manifest = await readManifest(sourcePath);
await ensureDir(CORPUS_DIR);

const destName = basename(sourcePath);
const destPath = `${CORPUS_DIR}/${destName}`;

await Deno.copyFile(sourcePath, destPath);

const applied = manifest.entries.filter((e) => e.decision === "apply");
const regressions = applied.filter((e) => e.proposed === e.parser_output);
const improvements = applied.filter((e) => e.proposed !== e.parser_output);
const skipped = manifest.entries.filter((e) => e.decision === "skip");
const review = manifest.entries.filter((e) => e.decision === "review");

console.log(`\n✓ Promoted: ${sourcePath}`);
console.log(`  → ${destPath}\n`);
console.log(`  Applied entries: ${applied.length}`);
console.log(
  `    ${regressions.length} regression tests (parser output matches — locked in)`,
);
if (improvements.length > 0) {
  console.log(
    `    ${improvements.length} improvement targets (you corrected the parser — documented)`,
  );
  for (const e of improvements) {
    console.log(`      • ${e.src}`);
    console.log(`        parser: ${e.parser_output}`);
    console.log(`        fixed:  ${e.proposed}`);
  }
}
console.log(`  Skipped (duplicate): ${skipped.length}`);
if (review.length > 0) {
  console.log(
    `  Still needs review: ${review.length} (these were not applied)`,
  );
}
console.log(`\nRun \`deno task test\` to verify the corpus passes.`);
