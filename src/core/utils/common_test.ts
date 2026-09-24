import { assertEquals } from "jsr:@std/assert@^1";
import { isProcessable, MusicCache } from "./common.ts";
import { DownloadedSong } from "../models/Song.ts";

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
