import { assertEquals, assertRejects, assertThrows } from "jsr:@std/assert@^1";
import { entryKey, Manifest, readManifest, sourceDirFor, writeManifest } from "./manifest.ts";

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
  source_dirs: { downloaded: "/tmp/source/" },
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

Deno.test("readManifest keeps a well-formed soundcloud field and rejects a malformed one", async () => {
  const soundcloud = {
    url: "https://soundcloud.com/mousai/ball-so-hard",
    title: "BALL SO HARD (Mousai & UrBoiN8)",
    uploader: "MOUSAI",
    metadata_artist: "MOUSAI & Urboin8",
    label_name: null,
  };
  await withTempFile(async (path) => {
    const good = { ...sampleManifest, entries: [{ ...sampleManifest.entries[0], soundcloud }] };
    await Deno.writeTextFile(path, JSON.stringify(good));
    assertEquals((await readManifest(path)).entries[0].soundcloud, soundcloud);

    const bad = { ...sampleManifest, entries: [{ ...sampleManifest.entries[0], soundcloud: { ...soundcloud, url: 1 } }] };
    await Deno.writeTextFile(path, JSON.stringify(bad));
    await assertRejects(() => readManifest(path), Error, "soundcloud");
  });
});

Deno.test("a manifest entry whose name is a path is rejected before anything moves", async () => {
  const dir = await Deno.makeTempDir();
  for (const [field, value] of [["src", "../Blosso - Galvanize.wav"], ["proposed", "sub/Blosso - Galvanize.wav"]]) {
    const path = `${dir}/${field}.json`;
    const entry = {
      src: "Blosso - Galvanize.wav",
      proposed: "Blosso - Galvanize.wav",
      confidence: "high",
      reasons: [],
      decision: "apply",
      [field]: value,
    };
    await Deno.writeTextFile(path, JSON.stringify({ version: 1, generated_at: "", source_dir: dir, move_dir: dir, cache_dir: dir, entries: [entry] }));
    await assertRejects(() => readManifest(path), Error, "must be a plain filename");
  }
});

async function readRaw(raw: unknown): Promise<Manifest> {
  const path = await Deno.makeTempFile({ suffix: ".json" });
  try {
    await Deno.writeTextFile(path, JSON.stringify(raw));
    return await readManifest(path);
  } finally {
    await Deno.remove(path).catch(() => {});
  }
}

const rawEntry = {
  src: "Blosso - Galvanize.wav",
  proposed: "Blosso - Galvanize.wav",
  confidence: "high",
  reasons: [],
  decision: "apply",
};

const rawManifest = (entry: Record<string, unknown>, extra: Record<string, unknown> = {}) => ({
  version: 1,
  generated_at: "",
  source_dir: "/tmp/dl/",
  move_dir: "/tmp/dest/",
  cache_dir: "/tmp/cache/",
  entries: [{ ...rawEntry, ...entry }],
  ...extra,
});

Deno.test("an old manifest reads as downloaded, its folder from source_dir, with no source_dirs added", async () => {
  const loaded = await readRaw(rawManifest({}));
  assertEquals("source_dirs" in loaded, false);
  assertEquals(entryKey(loaded.entries[0]), "downloaded/Blosso - Galvanize.wav");
  assertEquals(sourceDirFor(loaded, loaded.entries[0]), "/tmp/dl/");
});

Deno.test("an empty proposed name is rejected", async () => {
  await assertRejects(() => readRaw(rawManifest({ proposed: "" })), Error, "plain filename");
});

Deno.test("source_dirs, source and tags survive a read", async () => {
  const tags = { artist: "A", album: "B", title: "C" };
  const source_dirs = { downloaded: "/tmp/dl/", itunes: "/tmp/it/" };
  const loaded = await readRaw(
    rawManifest({ src: "A/B/01 C.m4a", source: "itunes", tags }, { source_dirs }),
  );
  assertEquals(loaded.source_dirs, source_dirs);
  assertEquals(loaded.entries[0].tags, tags);
  assertEquals(entryKey(loaded.entries[0]), "itunes/A/B/01 C.m4a");
  assertEquals(sourceDirFor(loaded, loaded.entries[0]), "/tmp/it/");
});

Deno.test("only itunes may have a nested src", async () => {
  const source_dirs = { downloaded: "/tmp/dl/", itunes: "/tmp/it/", bandcamp: "/tmp/bc/" };
  await readRaw(rawManifest({ src: "A/B/01 C.m4a", source: "itunes" }, { source_dirs }));
  for (const source of [undefined, "soundcloud", "bandcamp", "beatport"]) {
    await assertRejects(
      () => readRaw(rawManifest({ src: "sub/x.wav", source }, { source_dirs })),
      Error,
      "plain filename",
    );
  }
});

Deno.test("an unsafe src is rejected for every source", async () => {
  for (const source of ["downloaded", "itunes", "bandcamp"]) {
    for (const src of ["/etc/passwd.wav", "../x.wav", "A/../x.m4a", "./x.wav", "A//x.m4a", "x\0.wav", ""]) {
      await assertRejects(() => readRaw(rawManifest({ src, source })), Error, "Manifest entry 0");
    }
  }
});

Deno.test("an unknown source or malformed tags are rejected", async () => {
  await assertRejects(() => readRaw(rawManifest({ source: "napster" })), Error, "source");
  await assertRejects(
    () => readRaw(rawManifest({ source: "itunes", tags: { artist: "A", title: "C" } })),
    Error,
    "tags",
  );
  await assertRejects(
    () => readRaw(rawManifest({}, { source_dirs: { napster: "/x/" } })),
    Error,
    "source_dirs",
  );
});

Deno.test("sourceDirFor throws for a source with no dir instead of falling back", async () => {
  const loaded = await readRaw(rawManifest({ source: "bandcamp" }));
  assertThrows(() => sourceDirFor(loaded, loaded.entries[0]), Error, "bandcamp");
});
