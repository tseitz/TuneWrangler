import { DownloadedSong } from "./models/Song.ts";
import { parseDownloadedSong } from "./parser.ts";
import { setFinalDownloadedSongName } from "./utils/common.ts";

/** The name the current parser gives a file, exactly as the rename flow computes it. */
export function parseFilename(src: string, dir = "/tmp/corpus/"): string {
  const song = new DownloadedSong(src, dir);
  if (song.dashCount > 0) parseDownloadedSong(song);
  setFinalDownloadedSongName(song);
  return song.finalFilename;
}
