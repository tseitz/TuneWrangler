import { assertEquals, assertRejects } from "jsr:@std/assert@^1";
import { join } from "@std/path";
import { isProcessable, MusicCache, renameAndMove } from "./common.ts";
import { DownloadedSong } from "../models/Song.ts";

async function tone(path: string): Promise<void> {
  const args = ["-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2", "-y", path];
  const out = await new Deno.Command("ffmpeg", { args }).output();
  if (!out.success) throw new Error(new TextDecoder().decode(out.stderr));
}

async function listNames(dir: string): Promise<string[]> {
  return (await Array.fromAsync(Deno.readDir(dir))).map((e) => e.name).sort();
}

async function download(dir: string, name: string, finalFilename: string): Promise<DownloadedSong> {
  await tone(join(dir, name));
  const song = new DownloadedSong(name, `${dir}/`);
  const [artist, title] = finalFilename.replace(/\.\w+$/, "").split(" - ");
  Object.assign(song, { artist, album: "", title, finalFilename });
  return song;
}

function file(name: string): Deno.DirEntry {
  return { name, isFile: true, isDirectory: false, isSymlink: false };
}

Deno.test("isProcessable skips macOS AppleDouble files", () => {
  assertEquals(isProcessable(file("._Artist - Title.wav")), false);
  assertEquals(isProcessable(file("Artist - Title.wav")), true);
});

Deno.test("the duplicate check treats accented and plain spellings as the same track", () => {
  const cache = new MusicCache();
  const inCollection = new DownloadedSong("Reece Rosé x WAVHART - Strange.aiff", "/tmp/");
  Object.assign(inCollection, { artist: "Reece Rosé x WAVHART", title: "Strange" });
  cache.add(inCollection);

  const download = new DownloadedSong("Reece Rose x WAVHART - Strange.wav", "/tmp/");
  Object.assign(download, { artist: "Reece Rose x WAVHART", title: "Strange" });
  assertEquals(cache.has(download), true);

  const decomposed = new DownloadedSong("a - x.wav", "/tmp/");
  Object.assign(decomposed, { artist: "ØNLYBASH x Reece Rosé", title: "Bloody Money" });
  const plain = new DownloadedSong("a - y.wav", "/tmp/");
  Object.assign(plain, { artist: "ONLYBASH x Reece Rose", title: "Bloody Money" });
  cache.add(decomposed);
  assertEquals(cache.has(plain), true);
});

Deno.test("a move never overwrites a file already at the destination", async () => {
  const src = await Deno.makeTempDir();
  const out = await Deno.makeTempDir();
  const song = await download(src, "Blosso - Galvanize.wav", "Blosso - Galvanize.wav");
  await Deno.writeTextFile(join(out, "Blosso - Galvanize.aiff"), "already collected");

  await assertRejects(() => renameAndMove(`${out}/`, song, undefined, true), Error, "refusing to overwrite");

  assertEquals(await Deno.readTextFile(join(out, "Blosso - Galvanize.aiff")), "already collected");
  assertEquals(await listNames(out), ["Blosso - Galvanize.aiff"]);
  assertEquals(await listNames(src), ["Blosso - Galvanize.wav"]);
});

Deno.test("two moves to names that differ only in case: one lands, the other is refused", async () => {
  const src = await Deno.makeTempDir();
  const out = await Deno.makeTempDir();
  const first = await download(src, "One - A.wav", "Blosso - Galvanize.wav");
  const second = await download(src, "Two - B.wav", "blosso - galvanize.wav");

  const results = await Promise.allSettled([
    renameAndMove(`${out}/`, first, undefined, true),
    renameAndMove(`${out}/`, second, undefined, true),
  ]);

  assertEquals(results.map((r) => r.status).sort(), ["fulfilled", "rejected"]);
  assertEquals((await listNames(out)).length, 1);
  assertEquals((await listNames(src)).length, 1);
});

Deno.test("a finished move leaves only the final file behind", async () => {
  const src = await Deno.makeTempDir();
  const out = await Deno.makeTempDir();
  const song = await download(src, "Blosso - Galvanize.wav", "Blosso - Galvanize.wav");

  await renameAndMove(`${out}/`, song, undefined, true);

  assertEquals(await listNames(out), ["Blosso - Galvanize.aiff"]);
  assertEquals(await listNames(src), []);
});
