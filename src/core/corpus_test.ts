/**
 * Regression corpus tests.
 *
 * Reads every manifest in tests/corpus/ and runs two kinds of checks:
 *
 *   REGRESSION  — entries where proposed === parser_output (the parser got it
 *                 right and the user applied as-is). These MUST keep passing.
 *
 *   IMPROVEMENT — entries where the user corrected the parser (proposed ≠
 *                 parser_output). These are logged as known parser bugs to fix.
 *                 They're skipped for now so they don't block CI, but they show
 *                 up in the summary so the gap is visible.
 *
 * Grow the corpus by running `deno task promote <manifest>` after each apply.
 */
import { assertEquals } from "jsr:@std/assert@^1";
import { DownloadedSong } from "./models/Song.ts";
import { parseDownloadedSong } from "./parser.ts";
import { setFinalDownloadedSongName } from "./utils/common.ts";
import { ManifestEntry, readManifest } from "./manifest.ts";

const CORPUS_DIR = "./tests/corpus";

interface CorpusStats {
  regressionTotal: number;
  improvementTotal: number;
  corpusFiles: number;
}

async function loadCorpusEntries(): Promise<{ entries: ManifestEntry[]; stats: CorpusStats }> {
  const entries: ManifestEntry[] = [];
  let corpusFiles = 0;

  try {
    for await (const file of Deno.readDir(CORPUS_DIR)) {
      if (!file.isFile || !file.name.endsWith(".json")) continue;
      corpusFiles++;
      const manifest = await readManifest(`${CORPUS_DIR}/${file.name}`);
      for (const entry of manifest.entries) {
        if (entry.decision === "apply") entries.push(entry);
      }
    }
  } catch (e) {
    if (!(e instanceof Deno.errors.NotFound)) throw e;
    // Empty corpus — tests are skipped gracefully
  }

  const regressionTotal = entries.filter((e) => e.proposed === e.parser_output).length;
  const improvementTotal = entries.filter((e) => e.proposed !== e.parser_output).length;

  return { entries, stats: { regressionTotal, improvementTotal, corpusFiles } };
}

function parseFilename(src: string, dir = "/tmp/corpus/"): string {
  const song = new DownloadedSong(src, dir);
  if (song.dashCount > 0) parseDownloadedSong(song);
  setFinalDownloadedSongName(song);
  return song.finalFilename;
}

// Load corpus once synchronously at module level so Deno can discover all tests
const { entries, stats } = await loadCorpusEntries();

if (stats.corpusFiles === 0) {
  Deno.test("corpus: no corpus files yet — run `deno task promote` after your first --apply", () => {
    console.log("  Tip: deno task promote ./logs/tunewrangler/manifests/<manifest>.json");
  });
} else {
  // Summary test — always runs, shows corpus health at a glance
  Deno.test(`corpus: ${stats.corpusFiles} batches | ${stats.regressionTotal} regression | ${stats.improvementTotal} improvement targets`, () => {
    if (stats.improvementTotal > 0) {
      console.log(`\n  ${stats.improvementTotal} entries where parser output was corrected:`);
      for (const e of entries.filter((e) => e.proposed !== e.parser_output)) {
        console.log(`    src:            ${e.src}`);
        console.log(`    parser output:  ${e.parser_output}`);
        console.log(`    should be:      ${e.proposed}`);
        console.log();
      }
    }
  });

  // Regression tests — one per entry where parser got it right
  for (const entry of entries.filter((e) => e.proposed === e.parser_output)) {
    const name = `corpus regression: ${entry.src}`;
    Deno.test(name, () => {
      const actual = parseFilename(entry.src);
      assertEquals(
        actual,
        entry.proposed,
        `Parser output changed for "${entry.src}":\n  was: ${entry.proposed}\n  now: ${actual}`,
      );
    });
  }
}
