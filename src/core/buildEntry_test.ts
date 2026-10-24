import { assertEquals } from "jsr:@std/assert@^1";
import { buildEntry } from "./buildEntry.ts";
import { DUPLICATE_REASON } from "./manifest.ts";
import { cacheMusic, MusicCache } from "./utils/common.ts";

const file = (source: "downloaded" | "soundcloud", src: string) => ({ source, src, dir: "/tmp/" });

Deno.test("a duplicate skip records the Collection file it matched", async () => {
  const collection = await Deno.makeTempDir();
  await Deno.writeTextFile(`${collection}/Artist - Title.aiff`, "");
  const cache = await cacheMusic(`${collection}/`);

  const entry = buildEntry(file("downloaded", "Artist - Title.wav"), cache)?.entry;
  assertEquals(entry?.reasons[0], DUPLICATE_REASON);
  assertEquals(entry?.duplicate_of, { file: "Artist - Title.aiff" });
});

Deno.test("a duplicate of a file earlier in the same run points at that entry", () => {
  const cache = new MusicCache();
  buildEntry(file("downloaded", "Artist - Title.wav"), cache);

  const entry = buildEntry(file("soundcloud", "Artist - Title.wav"), cache)?.entry;
  assertEquals(entry?.decision, "skip");
  assertEquals(entry?.duplicate_of, { entry: "downloaded/Artist - Title.wav" });
});

const itunes = (title: string) => ({
  source: "itunes" as const,
  src: `Ragie Ban/Shake It - Single/${title}.m4a`,
  dir: "/tmp/",
  tags: { artist: "Ragie Ban", album: "Shake It - Single", title },
});

Deno.test("a mix that would collide with its original keeps its version", () => {
  const cache = new MusicCache();
  buildEntry(itunes("Shake It"), cache);

  const dub = buildEntry(itunes("Shake It (Dub Mix)"), cache)?.entry;
  const evil = buildEntry(itunes("Shake It (Evil Mix)"), cache)?.entry;
  assertEquals([dub?.proposed, dub?.decision], ["Ragie Ban - Shake It (Dub Mix).m4a", "apply"]);
  assertEquals(evil?.proposed, "Ragie Ban - Shake It (Evil Mix).m4a");
});

Deno.test("an original mix is still a duplicate of the plain title", () => {
  const cache = new MusicCache();
  buildEntry(itunes("Shake It"), cache);

  const entry = buildEntry(itunes("Shake It (Original Mix)"), cache)?.entry;
  assertEquals([entry?.proposed, entry?.decision], ["Ragie Ban - Shake It.m4a", "skip"]);
});

Deno.test("a mix with nothing to collide with is named as before", () => {
  const entry = buildEntry(itunes("Shake It (Dub Mix)"), new MusicCache())?.entry;
  assertEquals(entry?.proposed, "Ragie Ban - Shake It.m4a");
});
