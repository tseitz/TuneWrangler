import { assertEquals } from "jsr:@std/assert@^1";
import { DownloadedSong } from "./models/Song.ts";
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
