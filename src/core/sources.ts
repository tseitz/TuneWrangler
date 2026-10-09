import { walk } from "@std/fs";
import { basename, dirname, extname, relative, SEPARATOR } from "@std/path";
import { DownloadedSong, Song } from "./models/Song.ts";
import { Semaphore } from "./models/Semaphore.ts";
import { type EntryTags, isTagSource, type Source } from "./manifest.ts";
import { parseBandcampSong, parseDownloadedSong } from "./parser.ts";
import { readTags } from "./tagging.ts";
import { fixItunesLabeling, isProcessable, setFinalDownloadedSongName } from "./utils/common.ts";

export interface SourceFile {
  source: Source;
  /** Relative to `dir`; only itunes nests, joined with "/". */
  src: string;
  dir: string;
}

export interface SourceListing {
  files: SourceFile[];
  skipped: SourceFile[];
  /** Root subfolders that are not a source folder. */
  ignoredFolders: string[];
  warnings: string[];
}

export interface TaggedSourceFile extends SourceFile {
  tags?: EntryTags;
  tagError?: string;
}

const SUBFOLDER_SOURCES = ["soundcloud", "bandcamp", "beatport"] as const satisfies readonly Source[];
const SKIPPED_EXTENSIONS = new Set([".zip", ".m3u", ".plist"]);

export function isSkippedExtension(name: string): boolean {
  const ext = extname(name).toLowerCase();
  return !ext || SKIPPED_EXTENSIONS.has(ext);
}
const MAX_CONCURRENT_FFPROBE = 10;

export async function listSourceFiles(dirs: { downloaded: string; itunes: string }): Promise<SourceListing> {
  assertNoOverlap(dirs);
  const listing: SourceListing = { files: [], skipped: [], ignoredFolders: [], warnings: [] };
  const add = (file: SourceFile) => {
    (isSkippedExtension(file.src) ? listing.skipped : listing.files).push(file);
  };

  for await (const item of Deno.readDir(dirs.downloaded)) {
    if (item.isDirectory) {
      const isSource = (SUBFOLDER_SOURCES as readonly string[]).includes(item.name) ||
        dirs.itunes.startsWith(`${dirs.downloaded}${item.name}/`);
      if (!isSource) listing.ignoredFolders.push(item.name);
    } else if (isProcessable(item)) {
      add({ source: "downloaded", src: item.name, dir: dirs.downloaded });
    }
  }

  for (const source of SUBFOLDER_SOURCES) {
    const dir = `${dirs.downloaded}${source}/`;
    if (!(await isDirectory(dir))) {
      listing.warnings.push(`${dir} not found — no ${source} files this run`);
      continue;
    }
    for await (const item of Deno.readDir(dir)) {
      if (isProcessable(item)) add({ source, src: item.name, dir });
    }
  }

  for await (const item of walk(dirs.itunes, { includeDirs: false })) {
    if (!isProcessable(item)) continue;
    add({ source: "itunes", src: relative(dirs.itunes, item.path).split(SEPARATOR).join("/"), dir: dirs.itunes });
  }

  listing.files.sort(bySourceThenSrc);
  listing.skipped.sort(bySourceThenSrc);
  listing.ignoredFolders.sort();
  return listing;
}

/** A file reachable from two sources would get two entries, and both would try to move it. */
function assertNoOverlap({ downloaded, itunes }: { downloaded: string; itunes: string }): void {
  const subfolders = SUBFOLDER_SOURCES.map((source) => `${downloaded}${source}/`);
  // Only the root's files are read, so an iTunes folder elsewhere under the root is fine.
  const clash = itunes === downloaded || downloaded.startsWith(itunes)
    ? downloaded
    : subfolders.find((dir) => itunes.startsWith(dir) || dir.startsWith(itunes));
  if (clash) throw new Error(`the iTunes folder ${itunes} overlaps ${clash}; point them at separate folders`);
}

async function isDirectory(path: string): Promise<boolean> {
  try {
    return (await Deno.stat(path)).isDirectory;
  } catch (error) {
    if (error instanceof Deno.errors.NotFound) return false;
    throw error;
  }
}

function bySourceThenSrc(a: SourceFile, b: SourceFile): number {
  return a.source === b.source ? a.src.localeCompare(b.src) : a.source.localeCompare(b.source);
}

/** Probes tags for tag sources; other files pass through. A failed probe sets `tagError`. */
export async function readSourceTags(files: SourceFile[]): Promise<TaggedSourceFile[]> {
  const semaphore = new Semaphore(MAX_CONCURRENT_FFPROBE);
  return await Promise.all(files.map(async (file): Promise<TaggedSourceFile> => {
    if (!isTagSource(file.source)) return file;
    await semaphore.acquire();
    try {
      return { ...file, tags: await readTags(file.dir + file.src) };
    } catch (error) {
      return { ...file, tagError: error instanceof Error ? error.message : String(error) };
    } finally {
      semaphore.release();
    }
  }));
}

/**
 * Builds the song (with `finalFilename`) for one source file. Throws an Error when the file
 * can't be named: a dash-less downloaded/soundcloud name with no remix artist, a dash-less
 * bandcamp name, or a tag source called without tags.
 */
export function buildSong(source: Source, src: string, dir: string, tags?: EntryTags): Song {
  if (isTagSource(source)) {
    if (!tags) throw new Error(`${source} file ${src} needs its tags to be named`);
    return buildFromTags(src, dir, tags);
  }
  const song = newDownloadedSong(src, dir);
  if (source === "bandcamp") return parseBandcampSong(song);
  if (song.dashCount > 0) parseDownloadedSong(song);
  return setFinalDownloadedSongName(song);
}

function newDownloadedSong(src: string, dir: string): DownloadedSong {
  try {
    return new DownloadedSong(src, dir);
  } catch (error) {
    // The constructor throws a bare string, not an Error.
    if (typeof error === "string") throw new Error(`${src}: ${error}`);
    throw error;
  }
}

function buildFromTags(src: string, dir: string, tags: EntryTags): Song {
  const folder = dirname(src);
  const song = new Song(basename(src), folder === "." ? dir : `${dir}${folder}/`);

  // A "/" in a tag would put a path separator in the proposed name.
  const artist = tags.artist.replaceAll(/\s?\/\s?/g, " x ");
  song.album = fixItunesLabeling(tags.album);
  song.checkRemix();
  if (song.remix) {
    song.album = artist;
    song.removeAnd("album");
  } else {
    song.artist = artist;
    if (!song.artist && song.getDashCount() >= 1) song.artist = song.grabFirst();
  }
  song.checkWith();
  song.title = fixItunesLabeling(tags.title);

  song.checkFeat();
  // A remix's album slot holds the original artists; otherwise it's the release's own title.
  song.removeAnd(...(song.remix ? ["artist", "album"] as const : ["artist"] as const));
  song.lastCheck();

  if (song.title.toLowerCase() === song.album.toLowerCase()) song.album = "";
  song.finalFilename = song.album
    ? `${song.artist} - ${song.album} - ${song.title}${song.extension}`
    : `${song.artist} - ${song.title}${song.extension}`;
  return song;
}
