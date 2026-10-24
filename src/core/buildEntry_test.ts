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
