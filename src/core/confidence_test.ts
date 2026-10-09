import { assertEquals } from "jsr:@std/assert@^1";
import { DownloadedSong, Song } from "./models/Song.ts";
import { setFinalDownloadedSongName } from "./utils/common.ts";
import { parseDownloadedSong } from "./parser.ts";
import { scoreConfidence } from "./confidence.ts";

function buildSong(filename: string): DownloadedSong {
  const song = new DownloadedSong(filename, "/tmp/test/");
  parseDownloadedSong(song);
  return setFinalDownloadedSongName(song);
}

Deno.test("high: clean 1-dash filename, no remix, no transformation", () => {
  const song = buildSong("BUGGY - Pillage Dub.wav");
  const result = scoreConfidence(song, song.filename);
  assertEquals(result.level, "high");
});

Deno.test("medium: 2-separator filename without danger signals", () => {
  // We can't tell if "Album" is really an album or actually a title — uncertainty is honest
  const song = buildSong("Artist - Album - Title.wav");
  const result = scoreConfidence(song, song.filename);
  assertEquals(result.level, "medium");
});

Deno.test("medium: remix detected with clean parse", () => {
  const song = buildSong("Daft Punk - Digital Love (STAR SEED Remix).wav");
  const result = scoreConfidence(song, song.filename);
  assertEquals(result.level, "medium");
});

Deno.test("low: bare remix keyword in last segment of 3-part source", () => {
  const song = buildSong("Halsey - Gasoline - Fang Shui Flip.wav");
  const result = scoreConfidence(song, song.filename);
  assertEquals(result.level, "low");
  const reasonText = result.reasons.join(" ");
  assertEquals(reasonText.includes("bare remix keyword"), true);
});

Deno.test("low: bare 'Edit' in last segment", () => {
  const song = buildSong("Eminem - Lose Yourself - James Hype Edit.aif");
  const result = scoreConfidence(song, song.filename);
  assertEquals(result.level, "low");
});

Deno.test("low: bare 'Dub' in last segment", () => {
  const song = buildSong("Delerium - Silence - Average Citizens Dub.wav");
  const result = scoreConfidence(song, song.filename);
  assertEquals(result.level, "low");
});

Deno.test("low: empty title after parsing", () => {
  const song = buildSong("phompy - Title.wav");
  song.title = "";
  setFinalDownloadedSongName(song);
  const result = scoreConfidence(song, "phompy - Title.wav");
  assertEquals(result.level, "low");
  const reasonText = result.reasons.join(" ");
  assertEquals(reasonText.includes("empty"), true);
});

Deno.test("low: empty artist after parsing", () => {
  const song = buildSong("Artist - Title.wav");
  song.artist = "";
  setFinalDownloadedSongName(song);
  const result = scoreConfidence(song, "Artist - Title.wav");
  assertEquals(result.level, "low");
});

Deno.test("not mangled: .aif inside .aiff is not double-counted", () => {
  const song = buildSong("WeeWah - I Feel It.aiff");
  const result = scoreConfidence(song, song.filename);
  const reasonText = result.reasons.join(" ");
  assertEquals(reasonText.includes("mangled"), false);
});

Deno.test("not mangled: band name with .Wav suffix and .wav extension differ in case", () => {
  const song = buildSong("Hemi.Wav - Haul It Up!.wav");
  const result = scoreConfidence(song, song.filename);
  const reasonText = result.reasons.join(" ");
  assertEquals(reasonText.includes("mangled"), false);
});

Deno.test("low: finalFilename has duplicate extension (mangled)", () => {
  const song = buildSong("Artist - Title.wav");
  song.finalFilename = "Lindley X - HOLD ON.mp3 - LD ON.mp3";
  const result = scoreConfidence(song, "HOLD ON (Lindley X Remix) - Justin Bieber.mp3");
  assertEquals(result.level, "low");
  const reasonText = result.reasons.join(" ");
  assertEquals(reasonText.includes("mangled") || reasonText.includes("duplicate extension"), true);
});

Deno.test("low: artist name appears twice in finalFilename (self-remix duplication)", () => {
  const song = buildSong("Artist - Title.wav");
  song.artist = "Ballads";
  song.album = "BALLADS";
  song.title = "Good Flirts";
  setFinalDownloadedSongName(song);
  const result = scoreConfidence(song, "BALLADS - Good Flirts (Ballads Edit).mp3");
  assertEquals(result.level, "low");
});

Deno.test("default decision: high → apply", () => {
  const song = buildSong("BUGGY - Pillage Dub.wav");
  const result = scoreConfidence(song, song.filename);
  assertEquals(result.decision, "apply");
});

Deno.test("default decision: medium → apply", () => {
  const song = buildSong("Daft Punk - Digital Love (STAR SEED Remix).wav");
  const result = scoreConfidence(song, song.filename);
  assertEquals(result.decision, "apply");
});

Deno.test("default decision: low → review", () => {
  const song = buildSong("Halsey - Gasoline - Fang Shui Flip.wav");
  const result = scoreConfidence(song, song.filename);
  assertEquals(result.decision, "review");
});

Deno.test("m4s: MPEG-DASH segment auto-skipped", () => {
  const song = buildSong("Jadon Woods - I Remember.m4s");
  const result = scoreConfidence(song, song.filename);
  assertEquals(result.decision, "skip");
  assertEquals(result.level, "low");
});

function tagSong(filename: string, artist: string, title: string): Song {
  const song = new Song(filename, "/tmp/itunes/Artist/Album/");
  song.artist = artist;
  song.title = title;
  song.finalFilename = `${artist} - ${title}${song.extension}`;
  return song;
}

Deno.test("tag source: a missing title tag sends the entry to review", () => {
  const song = tagSong("01 Title.m4a", "Artist", "Title");
  const result = scoreConfidence(song, "01 Title.m4a", {
    source: "itunes",
    tags: { artist: "Artist", album: "Album", title: "" },
  });
  assertEquals(result.decision, "review");
  assertEquals(result.reasons.includes("file has no title tag"), true);
});

Deno.test("tag source: a missing artist tag sends the entry to review", () => {
  const song = tagSong("01 Title.m4a", "", "Title");
  const result = scoreConfidence(song, "01 Title.m4a", {
    source: "beatport",
    tags: { artist: "", album: "", title: "Title" },
  });
  assertEquals(result.decision, "review");
});

Deno.test("tag source: filename-shape signals don't fire on a track-numbered name", () => {
  for (const filename of ["01 Title.m4a", "01 Intro - Live - Club Edit.m4a"]) {
    const song = tagSong(filename, "Artist", "Title");
    const result = scoreConfidence(song, filename, {
      source: "itunes",
      tags: { artist: "Artist", album: "Album", title: "Title" },
    });
    assertEquals(result, { level: "high", reasons: ["named from tags"], decision: "apply" }, filename);
  }
});

Deno.test("bandcamp: the 2-dash reason names the artist-first order for an album download", () => {
  const song = buildSong("Artist - Album - 01 Title.wav");
  const result = scoreConfidence(song, song.filename, { source: "bandcamp" });
  assertEquals(result.reasons.some((r) => r.includes("assumed artist-album-title")), true);
});

Deno.test("bandcamp: a 4-part name goes to review", () => {
  const src = "Substance - No God - Bass Pit - 02 Bass Pit.aiff";
  const result = scoreConfidence(buildSong(src), src, { source: "bandcamp" });
  assertEquals(result.decision, "review");
});

Deno.test("a title that is only digits goes to review", () => {
  const song = buildSong("Acct - 01.wav");
  assertEquals(scoreConfidence(song, song.filename).decision, "review");
});
