import { assertEquals, assertRejects, assertThrows } from "jsr:@std/assert@^1";
import { join } from "@std/path";
import { buildSong, listSourceFiles, readSourceTags } from "./sources.ts";
import { scoreConfidence } from "./confidence.ts";

async function tone(path: string, tags: Record<string, string> = {}): Promise<void> {
  const metadata = Object.entries(tags).flatMap(([key, value]) => ["-metadata", `${key}=${value}`]);
  const args = ["-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2", ...metadata, "-y", path];
  const out = await new Deno.Command("ffmpeg", { args }).output();
  if (!out.success) throw new Error(new TextDecoder().decode(out.stderr));
}

async function touch(path: string): Promise<void> {
  await Deno.mkdir(join(path, ".."), { recursive: true });
  await Deno.writeTextFile(path, "");
}

async function listTree(dir: string): Promise<string[]> {
  const out: string[] = [];
  for await (const e of Deno.readDir(dir)) {
    out.push(e.name + (e.isDirectory ? "/" : ""));
    if (e.isDirectory) out.push(...(await listTree(join(dir, e.name))).map((n) => `${e.name}/${n}`));
  }
  return out.sort();
}

Deno.test("listSourceFiles: one listing across every source folder", async () => {
  const root = await Deno.makeTempDir();
  const downloaded = `${root}/Downloaded/`;
  const itunes = `${root}/iTunes/`;
  for (
    const path of [
      "Downloaded/A - B.wav",
      "Downloaded/.DS_Store",
      "Downloaded/._A - B.wav",
      "Downloaded/playlist.m3u",
      "Downloaded/BADMOUTH RECS SONGS/X - Y.wav",
      "Downloaded/soundcloud/C - D.mp3",
      "Downloaded/soundcloud/nested/E - F.mp3",
      "Downloaded/bandcamp/G - H - 01 I.aiff",
      "Downloaded/bandcamp/G - H.zip",
      "Downloaded/bandcamp/G - H/01 I.aiff",
      "iTunes/Artist/Album/05 Title.m4a",
      "iTunes/Artist/Album/._05 Title.m4a",
      "iTunes/Artist/.DS_Store",
      "iTunes/Library.plist",
      "iTunes/noext",
      "iTunes/Top.m4a",
    ]
  ) await touch(join(root, path));
  const before = await listTree(root);

  const listing = await listSourceFiles({ downloaded, itunes });

  assertEquals(listing.files.map((f) => [f.source, f.src, f.dir]), [
    ["bandcamp", "G - H - 01 I.aiff", `${downloaded}bandcamp/`],
    ["downloaded", "A - B.wav", downloaded],
    ["itunes", "Artist/Album/05 Title.m4a", itunes],
    ["itunes", "Top.m4a", itunes],
    ["soundcloud", "C - D.mp3", `${downloaded}soundcloud/`],
  ]);
  assertEquals(listing.skipped.map((f) => `${f.source}/${f.src}`), [
    "bandcamp/G - H.zip",
    "downloaded/playlist.m3u",
    "itunes/Library.plist",
    "itunes/noext",
  ]);
  assertEquals(listing.ignoredFolders, ["BADMOUTH RECS SONGS"]);
  assertEquals(listing.warnings.length, 1);
  assertEquals(listing.warnings[0].includes(`${downloaded}beatport/`), true);
  assertEquals(await listTree(root), before);
});

Deno.test("buildSong: a dash-less nested itunes path is named from its tags", async () => {
  const itunes = await Deno.makeTempDir() + "/";
  await Deno.mkdir(`${itunes}Artist/Album`, { recursive: true });
  await tone(`${itunes}Artist/Album/05 Title.m4a`, { artist: "Real Artist", album: "Real Album", title: "Real Title" });

  const [file] = await readSourceTags([{ source: "itunes", src: "Artist/Album/05 Title.m4a", dir: itunes }]);
  const song = buildSong("itunes", file.src, file.dir, file.tags);

  assertEquals(song.finalFilename, "Real Artist - Real Album - Real Title.m4a");
  assertEquals(song.fullFilename, `${itunes}Artist/Album/05 Title.m4a`);
});

Deno.test("buildSong: an itunes remix keeps the remixer as artist, without doubling the remix", async () => {
  const itunes = await Deno.makeTempDir() + "/";
  const src = "X/Y - Single/01 Z (A Remix).m4a";
  await Deno.mkdir(`${itunes}X/Y - Single`, { recursive: true });
  await tone(itunes + src, { artist: "X", album: "Y - Single", title: "Z (A Remix)" });

  const [file] = await readSourceTags([{ source: "itunes", src, dir: itunes }]);
  // What the retired rI produced for these tags.
  assertEquals(buildSong("itunes", src, itunes, file.tags).finalFilename, "A - X - Z.m4a");
});

Deno.test("buildSong: an empty album tag gives artist - title", async () => {
  const dir = await Deno.makeTempDir() + "/";
  await tone(`${dir}Some Download.m4a`, { artist: "Solo", title: "Track" });

  const [file] = await readSourceTags([{ source: "beatport", src: "Some Download.m4a", dir }]);
  assertEquals(file.tags?.album, "");
  assertEquals(buildSong("beatport", file.src, dir, file.tags).finalFilename, "Solo - Track.m4a");
});

Deno.test("buildSong: title comes from the tag, not the filename", () => {
  const song = buildSong("itunes", "A/B/03 Wrong Name.m4a", "/i/", { artist: "A", album: "B", title: "Right Name" });
  assertEquals(song.finalFilename, "A - B - Right Name.m4a");
});

Deno.test("buildSong: unnameable input throws an Error", () => {
  assertThrows(() => buildSong("downloaded", "No Dash Here.wav", "/d/"), Error, "No artist found");
  assertThrows(() => buildSong("bandcamp", "No Dash Here.wav", "/d/"), Error);
  assertThrows(() => buildSong("itunes", "A/B/01 T.m4a", "/i/"), Error, "needs its tags");
});

Deno.test("buildSong: filename sources match the existing parsers", () => {
  assertEquals(buildSong("soundcloud", "Album - Artist - Title.wav", "/d/").finalFilename, "Artist - Album - Title.wav");
  assertEquals(buildSong("bandcamp", "D-FORM - BURN EP - 01 Statik.aiff", "/d/").finalFilename, "D-FORM - BURN EP - Statik.aiff");
});

Deno.test("tag source confidence: a file missing its title tag goes to review", async () => {
  const dir = await Deno.makeTempDir() + "/";
  await tone(`${dir}01 Title.m4a`, { artist: "Artist", album: "Album" });

  const [file] = await readSourceTags([{ source: "itunes", src: "01 Title.m4a", dir }]);
  const song = buildSong("itunes", file.src, dir, file.tags);
  const result = scoreConfidence(song, file.src, { source: "itunes", tags: file.tags });

  assertEquals(result.decision, "review");
});

Deno.test("readSourceTags: an unreadable tag file reports tagError instead of throwing", async () => {
  const dir = await Deno.makeTempDir() + "/";
  await Deno.writeTextFile(`${dir}broken.m4a`, "not audio");

  const [file, passthrough] = await readSourceTags([
    { source: "itunes", src: "broken.m4a", dir },
    { source: "downloaded", src: "A - B.wav", dir },
  ]);
  assertEquals(file.tags, undefined);
  assertEquals(typeof file.tagError, "string");
  assertEquals(passthrough, { source: "downloaded", src: "A - B.wav", dir });
});

Deno.test("buildSong: a slash in the artist tag can't reach the file name", () => {
  const song = buildSong("itunes", "AC_DC/B/01 T.m4a", "/i/", { artist: "AC/DC", album: "B", title: "T" });
  assertEquals(song.finalFilename, "AC x DC - B - T.m4a");
});

Deno.test("listSourceFiles: an itunes folder inside the Downloaded root isn't reported as ignored", async () => {
  const downloaded = `${await Deno.makeTempDir()}/`;
  await touch(`${downloaded}itunes/Music/A/B/01 T.m4a`);
  const listing = await listSourceFiles({ downloaded, itunes: `${downloaded}itunes/Music/` });
  assertEquals(listing.ignoredFolders, []);
  assertEquals(listing.files.map((f) => f.src), ["A/B/01 T.m4a"]);
});

Deno.test("listSourceFiles: an iTunes folder overlapping a scanned folder is refused", async () => {
  const downloaded = `${await Deno.makeTempDir()}/`;
  for (const itunes of [downloaded, `${downloaded}bandcamp/`, `${downloaded}bandcamp/x/`]) {
    await assertRejects(() => listSourceFiles({ downloaded, itunes }), Error, "overlaps");
  }
});

Deno.test("buildSong: an iTunes version label is not a remixer", () => {
  const tags = { artist: "Hypho", album: "Low Down Deep - Single", title: "Low Down Deep (Dub Edit)" };
  const song = buildSong("itunes", "Hypho/Low Down Deep - Single/02 Low Down Deep (Dub Edit).m4a", "/i/", tags);
  assertEquals(song.finalFilename, "Hypho - Low Down Deep.m4a");
});

Deno.test("buildSong: & stays in an iTunes album title", () => {
  const tags = { artist: "Molecular", album: "Heritage & Sound", title: "Next Level" };
  const song = buildSong("itunes", "Molecular/Heritage & Sound/10 Next Level.m4a", "/i/", tags);
  assertEquals(song.finalFilename, "Molecular - Heritage & Sound - Next Level.m4a");
});

Deno.test("buildSong: other version labels aren't remixers either", () => {
  const tags = { artist: "Hypho", album: "EP", title: "Track (Clean Edit)" };
  assertEquals(buildSong("itunes", "Hypho/EP/01 Track (Clean Edit).m4a", "/i/", tags).finalFilename, "Hypho - EP - Track.m4a");
});
