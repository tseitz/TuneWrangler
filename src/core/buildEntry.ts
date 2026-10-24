import { basename } from "@std/path";
import { logWithBreak, MusicCache } from "./utils/common.ts";
import { Song } from "./models/Song.ts";
import { buildSong, type TaggedSourceFile } from "./sources.ts";
import { scoreConfidence } from "./confidence.ts";
import { DUPLICATE_REASON, entryKey, ManifestEntry } from "./manifest.ts";

export interface BuildResult {
  entry: ManifestEntry;
  song: Song;
}

/** An original mix is the same recording as the plain title, so it stays a duplicate. */
const ORIGINAL = /^[([]\s*original( mix)?\s*[)\]]$/i;

/** A "(Dub Mix)" whose stripped name collides with its original is a different version. */
function keepVersion(song: Song): void {
  const version = song.strippedVersion;
  const tail = `${song.title}${song.extension}`;
  if (!version || ORIGINAL.test(version) || !song.finalFilename.endsWith(tail)) return;
  song.title = `${song.title} ${version}`;
  song.finalFilename = `${song.finalFilename.slice(0, -tail.length)}${song.title}${song.extension}`;
}

/**
 * Parse one file and produce a manifest entry (plus the song it was parsed from, so a
 * --judge pass can grade the same parse without re-deriving it), or null if the file should
 * be skipped (tags unreadable, parser threw, etc.).
 */
export function buildEntry(file: TaggedSourceFile, cache: MusicCache): BuildResult | null {
  const key = entryKey(file);
  console.log("Processing: ", key);
  if (file.tagError) {
    logWithBreak(`Skipping (could not read tags): ${key} - ${file.tagError}`);
    return null;
  }
  try {
    const song = buildSong(file.source, file.src, file.dir, file.tags);
    if (cache.has(song)) keepVersion(song);
    const score = scoreConfidence(song, basename(file.src), { source: file.source, tags: file.tags });
    const base = {
      src: file.src,
      ...(file.source === "downloaded" ? {} : { source: file.source }),
      ...(file.tags ? { tags: file.tags } : {}),
      proposed: song.finalFilename,
      parser_output: song.finalFilename,
      confidence: score.level,
    };

    const duplicateOf = cache.match(song);
    if (duplicateOf) {
      const reasons = [DUPLICATE_REASON, ...score.reasons];
      return { song, entry: { ...base, reasons, decision: "skip", duplicate_of: duplicateOf } };
    }

    cache.add(song, { entry: key });
    logWithBreak(`${song.finalFilename}  [${score.level}]`);

    return { song, entry: { ...base, reasons: score.reasons, decision: score.decision } };
  } catch (error) {
    logWithBreak(`Skipping (parse error): ${key} - ${error instanceof Error ? error.message : error}`);
    return null;
  }
}
