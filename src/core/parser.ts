import { DownloadedSong } from "./models/Song.ts";
import { foldName as fold, normalizeUnicode } from "./utils/unicode.ts";
import { setFinalDownloadedSongName } from "./utils/common.ts";

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

const TRACK_NUMBER = /^\d{2}\s/;

/**
 * Album downloads are `artist - album - NN title`. Without a track number it's a single-track
 * download, named `account - [track artist -] title` like any other download.
 */
export function parseBandcampSong(song: DownloadedSong): DownloadedSong {
  if (song.dashCount < 1) throw new Error(`Not a Bandcamp name (no " - "): ${song.filename}`);
  if (!stemOf(song).split(" - ").slice(1).some((s) => TRACK_NUMBER.test(s.trim()))) {
    parseDownloadedSong(song);
    return setFinalDownloadedSongName(song);
  }

  song.removeBadCharacters();
  const stem = stemOf(song);
  const account = song.grabFirst();
  song.artist = account;
  song.album = "";
  song.checkRemix();
  // checkRemix sees no change when the credit is the release's own artist, so it misses the remix.
  if (!song.remix && selfRemix(stem, account)) song.remix = true;
  // A credit that starts with the release's own artist: the words after it are a style, not a name.
  const remixer = song.remix && song.artist.toLowerCase().startsWith(`${account.toLowerCase()} `)
    ? account
    : song.artist;

  const segments = stemOf(song).split(" - ").map((s) => s.trim());
  const numbered = segments.findIndex((s, i) => i > 0 && TRACK_NUMBER.test(s));
  const album = segments.slice(1, numbered).join(" - ");
  const hasTrackArtist = numbered < segments.length - 1;
  const trackArtist = hasTrackArtist ? segments[numbered].replace(TRACK_NUMBER, "") : account;
  song.title = segments.slice(hasTrackArtist ? numbered + 1 : numbered).join(" - ").replace(TRACK_NUMBER, "");

  if (song.remix) {
    song.artist = remixer;
    song.album = trackArtist !== remixer ? trackArtist : album;
  } else {
    song.artist = trackArtist;
    song.album = album;
  }
  song.checkWith();
  song.checkFeat();
  song.removeAnd(...(song.remix ? ["artist", "album"] as const : ["artist"] as const));
  song.lastCheck();
  if (song.album.toLowerCase() === song.title.toLowerCase()) song.album = "";

  song.finalFilename = song.album
    ? `${song.artist} - ${song.album} - ${song.title}${song.extension}`
    : `${song.artist} - ${song.title}${song.extension}`;
  return song;
}

function selfRemix(stem: string, account: string): boolean {
  const credit = /[(\[]([^)\]]+) (REMIX|REFIX|FLIP|EDIT|BOOTLEG|REBOOT|DUB)[)\]]/i.exec(stem)?.[1];
  return credit?.trim().toLowerCase() === account.toLowerCase();
}

function stemOf(song: DownloadedSong): string {
  return song.filename.slice(0, song.filename.length - song.extension.length);
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
