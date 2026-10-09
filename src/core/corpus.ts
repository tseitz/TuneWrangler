import { DownloadedSong } from "./models/Song.ts";
import { isTagSource, type ManifestEntry, type Source } from "./manifest.ts";
import { parseBandcampSong, parseDownloadedSong } from "./parser.ts";
import { setFinalDownloadedSongName } from "./utils/common.ts";

/** The name the current parser gives a file, exactly as the rename flow computes it. */
export function parseFilename(src: string, source: Source = "downloaded"): string {
  const song = new DownloadedSong(src, "/tmp/corpus/");
  if (source === "bandcamp") return parseBandcampSong(song).finalFilename;
  if (song.dashCount > 0) parseDownloadedSong(song);
  setFinalDownloadedSongName(song);
  return song.finalFilename;
}

export function reproducibleFromFilename(e: Pick<ManifestEntry, "source">): boolean {
  return !isTagSource(e.source);
}
