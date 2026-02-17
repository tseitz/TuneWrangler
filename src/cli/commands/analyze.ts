import { parseArgs } from "@std/cli/parse-args";
import { analyzeDjCollection } from "../../processors/analyzeDjCollection.ts";
import { getFolder } from "../../core/utils/common.ts";
import { info, error } from "../../core/utils/logger.ts";

export async function analyzeDj(args: string[]): Promise<void> {
  const flags = parseArgs(args, {
    boolean: ["help"],
    string: ["output", "limit"],
    alias: { help: "h" },
  });

  if (flags.help) {
    console.log(`
🎵 TuneWrangler analyze-dj

Analyze your DJ music collection to see which artists have the most songs.

USAGE:
  tunewrangler analyze-dj [options]

OPTIONS:
  --help, -h              Show this help message
  --output <file>         Output CSV file path (default: output/dj-artist-analysis.csv)
  --limit <number>        Number of top artists to show (default: 50)

EXAMPLES:
  tunewrangler analyze-dj
  tunewrangler analyze-dj --output my-analysis.csv --limit 20

This command scans your configured music directory and counts songs per artist,
then displays artists with 3 or more songs in your collection, sorted by count.
`);
    return;
  }

  try {
    const outputFile = flags.output || "output/dj-artist-analysis.csv";
    const limit = flags.limit ? parseInt(flags.limit) : 50;

    // Get the music directory from config
    const musicDir = getFolder("djMusic");

    info("🎵 Starting DJ collection analysis", {
      musicDir,
      outputFile,
      limit,
    });

    const results = await analyzeDjCollection(musicDir, outputFile);

    info("✅ Analysis complete!", {
      totalArtists: results.length,
      topArtist: results[0]?.artist,
      topCount: results[0]?.count,
    });
  } catch (err) {
    error("Failed to analyze DJ collection", err as Error);
    Deno.exit(1);
  }
}
