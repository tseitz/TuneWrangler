import { assertEquals } from "jsr:@std/assert@^1";
import { join } from "@std/path";
import { readTags, tagsFromFilename, writeTagsInPlace } from "./tagging.ts";
import { planRetag } from "../processors/retagFromFilename.ts";
import { DownloadedSong } from "./models/Song.ts";
import { renameAndMove } from "./utils/common.ts";

async function ffmpeg(...args: string[]): Promise<void> {
  const out = await new Deno.Command("ffmpeg", { args: ["-v", "error", ...args, "-y"] }).output();
  if (!out.success) throw new Error(new TextDecoder().decode(out.stderr));
}

const tone = ["-f", "lavfi", "-i", "sine=frequency=440:duration=0.2"];

Deno.test("a three-part name splits into artist, album and title", () => {
  assertEquals(tagsFromFilename("Blosso - Tim Deluxe - It Just Won't Do.aiff"), {
    artist: "Blosso",
    album: "Tim Deluxe",
    title: "It Just Won't Do",
  });
});

Deno.test("a two-part name has no album, and a title containing a dash stays whole", () => {
  assertEquals(tagsFromFilename("CCIV x Portals - Discombobulated.aiff"), {
    artist: "CCIV x Portals",
    album: "",
    title: "Discombobulated",
  });
  assertEquals(tagsFromFilename("A - B - Part 1 - Intro.mp3").title, "Part 1 - Intro");
});

Deno.test("an Unknown placeholder in the name is a blank field, not a value", () => {
  assertEquals(tagsFromFilename("Krischvn - Unknown - Baked.mp3"), { artist: "Krischvn", album: "", title: "Baked" });
});

Deno.test("retag fills missing tags but keeps a set one unless told to overwrite", () => {
  const current = { artist: "", album: "", title: "Wrong Title" };
  const fill = planRetag("Rayment - STPTBOOTS - Wicked & Dark.aiff", current, false);
  assertEquals(fill.next, { artist: "Rayment", album: "STPTBOOTS", title: "Wrong Title" });
  assertEquals(fill.kept.length, 1);

  const overwrite = planRetag("Rayment - STPTBOOTS - Wicked & Dark.aiff", current, true);
  assertEquals(overwrite.next.title, "Wicked & Dark");
});

Deno.test("retagging an AIFF stores artist and album where a reader can find them", async () => {
  const dir = await Deno.makeTempDir();
  const file = join(dir, "Rayment - STPTBOOTS - Wicked & Dark.aiff");
  await ffmpeg(...tone, "-metadata", "title=Wicked & Dark", file);

  await writeTagsInPlace(file, tagsFromFilename("Rayment - STPTBOOTS - Wicked & Dark.aiff"));

  assertEquals(await readTags(file), { artist: "Rayment", album: "STPTBOOTS", title: "Wicked & Dark" });
});

Deno.test("converting a download to AIFF keeps its artist and album tags", async () => {
  const src = await Deno.makeTempDir();
  const out = await Deno.makeTempDir();
  await ffmpeg(...tone, join(src, "Blosso - Galvanize.wav"));
  const song = new DownloadedSong("Blosso - Galvanize.wav", `${src}/`);
  Object.assign(song, { artist: "Blosso", album: "Tim Deluxe", title: "Galvanize" });
  song.finalFilename = "Blosso - Tim Deluxe - Galvanize.wav";

  await renameAndMove(`${out}/`, song);

  assertEquals(await readTags(join(out, "Blosso - Tim Deluxe - Galvanize.aiff")), {
    artist: "Blosso",
    album: "Tim Deluxe",
    title: "Galvanize",
  });
});
