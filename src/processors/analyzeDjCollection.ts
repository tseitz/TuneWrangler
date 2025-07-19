import { LocalSong } from "../core/models/Song.ts";
import { ArtistAnalysis } from "../core/models/ArtistAnalysis.ts";
import { getFolder } from "../core/utils/common.ts";
import { info, error } from "../core/utils/logger.ts";

/**
 * Analyzes a DJ music collection to count which artists have the most songs
 */
export async function analyzeDjCollection(
  musicDir?: string,
  outputFile?: string
  // limit: number = 50
): Promise<ArtistAnalysis[]> {
  try {
    // Use provided music directory or get from config
    const directory = musicDir || getFolder("djMusic");

    info("🎵 Starting DJ collection analysis", { directory });

    const songs: LocalSong[] = [];

    // Recursively scan directory for music files
    for await (const entry of Deno.readDir(directory)) {
      if (entry.isFile && isMusicFile(entry.name)) {
        const song = new LocalSong(entry.name, directory);
        songs.push(song);
      }
    }

    info(`📊 Found ${songs.length} music files`);

    // Count artists
    const artistCounts: Record<string, number> = {};

    songs.forEach((song) => {
      // Split artists by " x " (collaborations)
      const artists = song.splitArtist();

      artists.forEach((artist) => {
        const normalizedArtist = artist.toLowerCase().trim();
        if (normalizedArtist) {
          artistCounts[normalizedArtist] = (artistCounts[normalizedArtist] || 0) + 1;
        }
      });
    });

    // Convert to array, filter by minimum count, and sort by count
    const artistAnalysis: ArtistAnalysis[] = Object.entries(artistCounts)
      .map(([artist, count]) => ({ artist, count }))
      .filter((analysis) => analysis.count >= 3) // Only include artists with 3+ songs
      .sort((a, b) => b.count - a.count);
    // .slice(0, limit);

    // Log results
    info(`🏆 Top artists in your DJ collection (3+ songs):`);
    artistAnalysis.forEach((analysis, index) => {
      console.log(`${index + 1}. ${analysis.artist} - ${analysis.count} songs`);
    });

    // Write to file if requested
    if (outputFile) {
      await writeToCsv(outputFile, artistAnalysis);
      info(`💾 Results saved to ${outputFile}`);
    }

    return artistAnalysis;
  } catch (err) {
    error("Failed to analyze DJ collection", err as Error);
    throw err;
  }
}

/**
 * Check if a file is a music file based on extension
 */
function isMusicFile(filename: string): boolean {
  const musicExtensions = [".mp3", ".wav", ".flac", ".m4a", ".aiff", ".aac", ".ogg"];
  const extension = filename.toLowerCase().substring(filename.lastIndexOf("."));
  return musicExtensions.includes(extension);
}

/**
 * Write artist analysis results to CSV file
 */
async function writeToCsv(filename: string, artistAnalysis: ArtistAnalysis[]): Promise<void> {
  let csvContent = "Artist,Count\n";

  artistAnalysis.forEach((analysis) => {
    csvContent += `"${analysis.artist}",${analysis.count}\n`;
  });

  await Deno.writeTextFile(filename, csvContent);
}

/**
 * CLI entry point
 */
if (import.meta.main) {
  const args = Deno.args;
  const musicDir = args[0];
  const outputFile = args[1] || "output/dj-artist-analysis.csv";
  // const limit = parseInt(args[2]) || 50;

  try {
    await analyzeDjCollection(musicDir, outputFile);
  } catch (error) {
    console.error("❌ Analysis failed:", error);
    Deno.exit(1);
  }
}
