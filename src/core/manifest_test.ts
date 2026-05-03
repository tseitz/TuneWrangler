import { assertEquals, assertRejects } from "jsr:@std/assert@^1";
import { Manifest, readManifest, writeManifest } from "./manifest.ts";

async function withTempFile(fn: (path: string) => Promise<void>) {
  const path = await Deno.makeTempFile({ suffix: ".json" });
  try {
    await fn(path);
  } finally {
    await Deno.remove(path).catch(() => {});
  }
}

const sampleManifest: Manifest = {
  version: 1,
  generated_at: "2026-05-03T12:00:00Z",
  source_dir: "/tmp/source/",
  move_dir: "/tmp/dest/",
  cache_dir: "/tmp/cache/",
  entries: [
    {
      src: "BUGGY - Pillage Dub.wav",
      proposed: "BUGGY - Pillage Dub.wav",
      parser_output: "BUGGY - Pillage Dub.wav",
      confidence: "high",
      reasons: ["clean parse"],
      decision: "apply",
    },
    {
      src: "Halsey - Gasoline - Fang Shui Flip.wav",
      proposed: "Fang Shui - Halsey - Gasoline.wav",
      parser_output: "Gasoline - Halsey - Fang Shui Flip.wav",
      confidence: "low",
      reasons: ["bare remix keyword in last segment"],
      decision: "review",
    },
  ],
};

Deno.test("write then read roundtrip preserves all fields", async () => {
  await withTempFile(async (path) => {
    await writeManifest(path, sampleManifest);
    const loaded = await readManifest(path);
    assertEquals(loaded, sampleManifest);
  });
});

Deno.test("readManifest rejects malformed JSON", async () => {
  await withTempFile(async (path) => {
    await Deno.writeTextFile(path, "{not valid json");
    await assertRejects(() => readManifest(path), Error);
  });
});

Deno.test("readManifest rejects manifest without entries array", async () => {
  await withTempFile(async (path) => {
    await Deno.writeTextFile(path, JSON.stringify({ version: 1 }));
    await assertRejects(() => readManifest(path), Error, "entries");
  });
});

Deno.test("readManifest rejects entry with invalid decision value", async () => {
  await withTempFile(async (path) => {
    const bad = {
      ...sampleManifest,
      entries: [{ ...sampleManifest.entries[0], decision: "yolo" }],
    };
    await Deno.writeTextFile(path, JSON.stringify(bad));
    await assertRejects(() => readManifest(path), Error, "decision");
  });
});

Deno.test("readManifest rejects entry with invalid confidence value", async () => {
  await withTempFile(async (path) => {
    const bad = {
      ...sampleManifest,
      entries: [{ ...sampleManifest.entries[0], confidence: "really high" }],
    };
    await Deno.writeTextFile(path, JSON.stringify(bad));
    await assertRejects(() => readManifest(path), Error, "confidence");
  });
});

Deno.test("readManifest defaults parser_output to proposed when missing (backwards compat)", async () => {
  await withTempFile(async (path) => {
    const { parser_output: _, ...withoutParserOutput } = sampleManifest.entries[0];
    const compat = { ...sampleManifest, entries: [withoutParserOutput] };
    await Deno.writeTextFile(path, JSON.stringify(compat));
    const loaded = await readManifest(path);
    assertEquals(loaded.entries[0].parser_output, loaded.entries[0].proposed);
  });
});

Deno.test("writeManifest creates pretty-printed JSON for human editing", async () => {
  await withTempFile(async (path) => {
    await writeManifest(path, sampleManifest);
    const text = await Deno.readTextFile(path);
    assertEquals(text.includes("\n  "), true, "expected indented output");
  });
});
