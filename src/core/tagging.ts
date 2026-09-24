import { extname } from "@std/path";

export interface TrackTags {
  artist: string;
  album: string;
  title: string;
}

/**
 * Artist, album and title from a name in the `artist - album - title` or `artist - title`
 * shape the rename flow produces. A title that itself contains " - " stays whole.
 */
export function tagsFromFilename(filename: string): TrackTags {
  const base = filename.slice(0, filename.length - extname(filename).length).normalize("NFC");
  const parts = base.split(" - ").map((p) => p.trim());
  if (parts.length === 1) return { artist: "", album: "", title: parts[0] };
  if (parts.length === 2) return { artist: parts[0], album: "", title: parts[1] };
  return { artist: parts[0], album: parts[1], title: parts.slice(2).join(" - ") };
}

/**
 * ffmpeg flags that make tags land where players read them. The AIFF muxer writes an ID3
 * chunk only when asked, and without one Rekordbox sees a title and nothing else. v2.3,
 * because v2.4 (ffmpeg's default) is read less reliably by DJ software.
 */
export function id3Flags(extension: string): string[] {
  const ext = extension.toLowerCase();
  if (ext === ".aiff" || ext === ".aif") return ["-write_id3v2", "1", "-id3v2_version", "3"];
  if (ext === ".mp3") return ["-id3v2_version", "3"];
  return [];
}

export function tagArgs(tags: TrackTags): string[] {
  const args = ["-metadata", `title=${tags.title}`, "-metadata", `artist=${tags.artist}`];
  if (tags.album) args.push("-metadata", `album=${tags.album}`);
  args.push("-metadata", `album_artist=${tags.artist}`);
  return args;
}

export async function readTags(path: string): Promise<TrackTags> {
  const out = await new Deno.Command("ffprobe", {
    args: ["-v", "error", "-show_entries", "format_tags=artist,album,title", "-of", "json", path],
  }).output();
  if (!out.success) {
    throw new Error(`ffprobe could not read ${path}: ${new TextDecoder().decode(out.stderr)}`);
  }
  const tags = JSON.parse(new TextDecoder().decode(out.stdout)).format?.tags ?? {};
  return { artist: tags.artist ?? "", album: tags.album ?? "", title: tags.title ?? "" };
}

/**
 * Rewrites a file's tags without touching its audio (stream copy), via a temp file in the
 * same folder so the original is only replaced once ffmpeg has succeeded.
 */
export async function writeTagsInPlace(path: string, tags: TrackTags): Promise<void> {
  const ext = extname(path);
  const tmp = `${path.slice(0, path.length - ext.length)}.retag-tmp${ext}`;
  const out = await new Deno.Command("ffmpeg", {
    args: [
      "-v", "error", "-i", path,
      "-map", "0", "-c", "copy", "-map_metadata", "0",
      ...tagArgs(tags), ...id3Flags(ext),
      "-y", tmp,
    ],
  }).output();
  if (!out.success) {
    await Deno.remove(tmp).catch(() => {});
    throw new Error(`ffmpeg could not retag ${path}: ${new TextDecoder().decode(out.stderr)}`);
  }
  await Deno.rename(tmp, path);
}
