import { DownloadedSong } from "./models/Song.ts";
import { normalizeUnicode } from "./utils/unicode.ts";

/**
 * Runs the full filename-parsing pipeline on a DownloadedSong.
 * Mirrors the logic that renameMusic.ts has used inline historically;
 * extracted so confidence scoring and tests can call it directly.
 */
export function parseDownloadedSong(song: DownloadedSong): DownloadedSong {
  if (song.dashCount === 0) return song;

  song.removeBadCharacters();
  // Before checkRemix, which cuts everything from the remix bracket to the end of the name.
  const segments = song.filename.slice(0, song.filename.length - song.extension.length).split(" - ");
  grabDownloadedArtist(song);

  if (!song.album && song.dashCount > 1) {
    song.album = song.grabFirst();
  }

  song.title = song.grabLast();

  resolvePrefix(song, segments);

  song.checkFeat();
  song.removeAnd("artist", "album");
  song.lastCheck();

  return song;
}

function grabDownloadedArtist(song: DownloadedSong): DownloadedSong {
  song.checkRemix();

  if (song.remix) {
    song.album = song.dashCount === 1 ? song.grabFirst() : song.grabSecond();
    song.removeAnd("album");
  } else {
    song.artist = song.dashCount === 1 ? song.grabFirst() : song.grabSecond();
  }

  song.checkWith();

  return song;
}

const COLLAB_SEPARATOR = /\s+(?:x|&|and)\s+|,\s+/i;
const TRAILING_BRACKET = /[[(]([^\])]+)[\])]\s*$/;
const MIN_NAME = 3;

function fold(text: string): string {
  return normalizeUnicode(text.normalize("NFC")).toLowerCase().replace(/[^a-z0-9]/g, "");
}

function lower(text: string): string {
  return normalizeUnicode(text.normalize("NFC")).toLowerCase();
}

/**
 * SoundCloud downloads are named `<uploader> - <track title>`, so the first segment says who
 * posted the track. Uses it to settle who the artist is where the rest of the name is ambiguous.
 */
function resolvePrefix(song: DownloadedSong, segments: string[]): DownloadedSong {
  if (segments.length < 2 || segments.length > 3) return song;
  const prefix = segments[0].replace(/\s*[[(][^\])]*[\])]\s*/g, " ").trim();
  const fp = fold(prefix);
  if (fp.length < MIN_NAME) return song;

  if (song.remix) {
    preferUploaderSpelling(song, prefix, fp);
  } else if (segments.length === 3) {
    if (!uploaderInBracket(song, segments, prefix, fp)) dropRepeatedUploader(song, segments, prefix, fp);
  }

  // A self-remix names the same artist twice (`ALIAS - … (ALIAS UKG FLIP)`).
  if (song.album && fold(song.album) === fold(song.artist)) {
    song.artist = song.album;
    song.album = "";
  }
  return song;
}

/** `(Morty UKG Bootleg)` posted by MORTY: the bracket's extra words are not part of the name. */
function preferUploaderSpelling(song: DownloadedSong, prefix: string, fp: string): void {
  // A remix credited to several people keeps all of them.
  if (COLLAB_SEPARATOR.test(song.artist)) return;
  const fa = fold(song.artist);
  // Equal names keep the bracket's spelling, as approved batches do (`COZY KEV`).
  if (fa === fp) return;
  const firstWord = fold(song.artist.split(/\s+/)[0] ?? "");
  if (fa.startsWith(fp) || (firstWord.length >= MIN_NAME && fp.startsWith(firstWord))) {
    song.artist = prefix;
  }
}

/** `Blosso - Tim Deluxe - It Just Won't Do (Blosso Edition)`: a remix word checkRemix doesn't know. */
function uploaderInBracket(song: DownloadedSong, segments: string[], prefix: string, fp: string): boolean {
  const bracket = TRAILING_BRACKET.exec(segments[2]);
  if (!bracket || !fold(bracket[1]).startsWith(fp)) return false;
  song.artist = prefix;
  song.album = segments[1].trim();
  song.remix = true;
  return true;
}

/** `CCIV - CCIV x Portals - Discombobulated`: the uploader is already one of the artists. */
function dropRepeatedUploader(song: DownloadedSong, segments: string[], prefix: string, fp: string): void {
  const collab = segments[1].trim();
  if (collab.split(COLLAB_SEPARATOR).some((member) => fold(member) === fp)) {
    song.artist = collab;
    song.album = "";
    return;
  }
  // `statiq. - statiq. niko - guns of fury`: the uploader and a partner with no separator.
  if (lower(collab).startsWith(`${lower(prefix)} `)) {
    song.artist = `${collab.slice(0, prefix.length)} x ${collab.slice(prefix.length).trim()}`;
    song.album = "";
  }
}
