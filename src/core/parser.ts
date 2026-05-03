import { DownloadedSong } from "./models/Song.ts";

/**
 * Runs the full filename-parsing pipeline on a DownloadedSong.
 * Mirrors the logic that renameMusic.ts has used inline historically;
 * extracted so confidence scoring and tests can call it directly.
 */
export function parseDownloadedSong(song: DownloadedSong): DownloadedSong {
  if (song.dashCount === 0) return song;

  song.removeBadCharacters();
  grabDownloadedArtist(song);

  if (!song.album && song.dashCount > 1) {
    song.album = song.grabFirst();
  }

  song.title = song.grabLast();

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
