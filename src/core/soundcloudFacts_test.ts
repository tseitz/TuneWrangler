import { assertEquals, assertRejects } from "jsr:@std/assert@^1";
import { ManifestEntry, SoundcloudFacts } from "./manifest.ts";
import { applySoundcloudCredits, factsFor, loadSoundcloudIndex } from "./soundcloudFacts.ts";

function facts(uploader: string, metadata_artist: string | null): SoundcloudFacts {
  return { url: "https://soundcloud.com/x/y", title: null, uploader, metadata_artist, label_name: null };
}

function entry(proposed: string, decision: ManifestEntry["decision"] = "apply"): ManifestEntry {
  return { src: proposed, proposed, parser_output: proposed, confidence: "high", reasons: [], decision };
}

Deno.test("a collaborator SoundCloud credits but the name drops sends the entry to review", () => {
  const result = applySoundcloudCredits(entry("MOUSAI - BALL SO HARD.wav"), facts("MOUSAI", "MOUSAI & Urboin8"));
  assertEquals(result.decision, "review");
  assertEquals(result.reasons, ["soundcloud credits Urboin8, missing from the name"]);
});

Deno.test("every credited name present leaves the decision alone and attaches the facts", () => {
  const sc = facts("PIERCE", "PIERCE, VIRX");
  const result = applySoundcloudCredits(entry("PIERCE x VIRX - LADY GAGA - JUST DANCE.wav"), sc);
  assertEquals(result.decision, "apply");
  assertEquals(result.reasons, []);
  assertEquals(result.soundcloud, sc);
});

Deno.test("the uploader is not required in the name, even in styled Unicode", () => {
  const result = applySoundcloudCredits(
    entry("Rayment - Wicked & Dark.wav"),
    facts("𝗦𝗧𝗣𝗧𝗕𝗢𝗢𝗧𝗦", "STPTBOOTS, Rayment"),
  );
  assertEquals(result.decision, "apply");
});

Deno.test("a missing credit never raises a skip", () => {
  const result = applySoundcloudCredits(entry("Zei - party & bullshit.wav", "skip"), facts("Zei", "The Notorious B.I.G. x Zei"));
  assertEquals(result.decision, "skip");
  assertEquals(result.reasons, ["soundcloud credits The Notorious B.I.G., missing from the name"]);
});

Deno.test("a decomposed filename finds the entry recorded under the composed name", () => {
  const index = new Map([["Dr. Ushūu - Long Goodbye".normalize("NFC"), facts("Dr. Ushūu", null)]]);
  assertEquals(factsFor(index, "Dr. Ushūu - Long Goodbye.wav".normalize("NFD"))?.uploader, "Dr. Ushūu");
});

Deno.test("no index file yet reads as an empty index; a broken one throws", async () => {
  const dir = await Deno.makeTempDir();
  try {
    assertEquals((await loadSoundcloudIndex(`${dir}/track_index.json`)).size, 0);
    await Deno.writeTextFile(`${dir}/track_index.json`, "{half");
    await assertRejects(() => loadSoundcloudIndex(`${dir}/track_index.json`), Error, "not valid JSON");
  } finally {
    await Deno.remove(dir, { recursive: true });
  }
});

Deno.test("a credit whose words are all in the name, split by a separator, counts as present", () => {
  const result = applySoundcloudCredits(entry("statiq. x niko - guns of fury.wav"), facts("statiq.", "statiq. niko"));
  assertEquals(result.decision, "apply");
});

Deno.test("a short word does not stand in for a whole credit", () => {
  const result = applySoundcloudCredits(entry("DJ Snake x Qwerty - Title.wav"), facts("Remixer", "DJ Q"));
  assertEquals(result.decision, "review");
});
