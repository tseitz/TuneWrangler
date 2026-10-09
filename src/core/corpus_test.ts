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
import { parseFilename, reproducibleFromFilename } from "./corpus.ts";
import { Manifest, ManifestEntry, readManifest } from "./manifest.ts";

const CORPUS_DIR = "./tests/corpus";

interface CorpusStats {
  regressionTotal: number;
  improvementTotal: number;
  corpusFiles: number;
}

function parsedName(e: ManifestEntry): string {
  return parseFilename(e.src, e.source);
}

async function loadCorpusEntries(
  dir: string,
): Promise<{ entries: ManifestEntry[]; stats: CorpusStats }> {
  const entries: ManifestEntry[] = [];
  let corpusFiles = 0;

  try {
    for await (const file of Deno.readDir(dir)) {
      if (!file.isFile || !file.name.endsWith(".json")) continue;
      corpusFiles++;
      const manifest = await readManifest(`${dir}/${file.name}`);
      for (const entry of manifest.entries) {
        if (entry.decision === "apply" && reproducibleFromFilename(entry)) entries.push(entry);
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

// Load corpus once synchronously at module level so Deno can discover all tests
const { entries, stats } = await loadCorpusEntries(CORPUS_DIR);

if (stats.corpusFiles === 0) {
  Deno.test("corpus: no corpus files yet — run `deno task promote` after your first --apply", () => {
    console.log("  Tip: deno task promote ./logs/tunewrangler/manifests/<manifest>.json");
  });
} else {
  // Summary test — always runs, shows corpus health at a glance
  // Targets are counted from the stored parser_output, so a parser fix only shows up here.
  const nowMatching = entries.filter((e) => e.proposed !== e.parser_output && parsedName(e) === e.proposed);
  const fixedNote = nowMatching.length > 0
    ? ` (${nowMatching.length} now match — run \`deno task promote --refresh\` to lock them in)`
    : "";
  Deno.test(`corpus: ${stats.corpusFiles} batches | ${stats.regressionTotal} regression | ${stats.improvementTotal} improvement targets${fixedNote}`, () => {
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
      const actual = parsedName(entry);
      assertEquals(
        actual,
        entry.proposed,
        `Parser output changed for "${entry.src}":\n  was: ${entry.proposed}\n  now: ${actual}`,
      );
    });
  }
}

Deno.test("corpus: bandcamp entries use the bandcamp parser, itunes entries are skipped", async () => {
  const dir = await Deno.makeTempDir();
  try {
    const base = { confidence: "high" as const, reasons: [] as string[], decision: "apply" as const };
    const bandcamp = "Artist - Album - 01 Song.mp3";
    const manifest: Manifest = {
      version: 1,
      generated_at: "",
      source_dir: "",
      move_dir: "",
      cache_dir: "",
      entries: [
        { ...base, src: bandcamp, source: "bandcamp", proposed: "Artist - Album - Song.mp3", parser_output: "Artist - Album - Song.mp3" },
        { ...base, src: "Artist/Album/01 Song.mp3", source: "itunes", proposed: "x.mp3", parser_output: "x.mp3" },
        { ...base, src: "Beat - Port.mp3", source: "beatport", proposed: "x.mp3", parser_output: "x.mp3" },
      ],
    };
    await Deno.writeTextFile(`${dir}/m.json`, JSON.stringify(manifest));
    const loaded = await loadCorpusEntries(dir);
    assertEquals(loaded.entries.map((e) => e.source), ["bandcamp"]);
    assertEquals(parsedName(loaded.entries[0]), loaded.entries[0].proposed);
    assertEquals(parseFilename(bandcamp), "Album - Artist - 01 Song.mp3");
  } finally {
    await Deno.remove(dir, { recursive: true });
  }
});
