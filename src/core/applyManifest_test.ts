import { assertEquals } from "jsr:@std/assert@^1";
import { join } from "@std/path";
import { applyManifest } from "./applyManifest.ts";
import { Manifest, ManifestEntry } from "./manifest.ts";

async function tone(path: string): Promise<void> {
  const args = ["-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2", "-y", path];
  const out = await new Deno.Command("ffmpeg", { args }).output();
  if (!out.success) throw new Error(new TextDecoder().decode(out.stderr));
}

async function listNames(dir: string): Promise<string[]> {
  return (await Array.fromAsync(Deno.readDir(dir))).map((e) => e.name).sort();
}

function entry(src: string, decision: ManifestEntry["decision"]): ManifestEntry {
  return { src, proposed: src, parser_output: src, confidence: "high", reasons: [], decision };
}

Deno.test("apply moves only the approved entries, into the manifest's destination", async () => {
  const [source, collection, backup] = await Promise.all([Deno.makeTempDir(), Deno.makeTempDir(), Deno.makeTempDir()]);
  for (const name of ["Blosso - Galvanize.wav", "Dmtree - On My Mind.wav", "NEO_G - SIGNAL_01.wav"]) {
    await tone(join(source, name));
  }
  const manifest: Manifest = {
    version: 1,
    generated_at: new Date().toISOString(),
    source_dir: source,
    move_dir: collection,
    cache_dir: collection,
    entries: [
      entry("Blosso - Galvanize.wav", "apply"),
      entry("Dmtree - On My Mind.wav", "review"),
      entry("NEO_G - SIGNAL_01.wav", "skip"),
    ],
  };

  const result = await applyManifest(manifest, { backupDir: backup });

  assertEquals([result.applied, result.skipped, result.failures.length], [1, 2, 0]);
  assertEquals(await listNames(collection), ["Blosso - Galvanize.aiff"]);
  assertEquals(await listNames(source), ["Dmtree - On My Mind.wav", "NEO_G - SIGNAL_01.wav"]);
  assertEquals(await listNames(result.runBackupDir!), ["Blosso - Galvanize.wav"]);
});

Deno.test("a run with nothing to move leaves no backup folder", async () => {
  const [source, collection, backup] = await Promise.all([Deno.makeTempDir(), Deno.makeTempDir(), Deno.makeTempDir()]);
  await tone(join(source, "Dmtree - On My Mind.wav"));
  const manifest: Manifest = {
    version: 1,
    generated_at: new Date().toISOString(),
    source_dir: source,
    move_dir: collection,
    cache_dir: collection,
    entries: [entry("Dmtree - On My Mind.wav", "review")],
  };

  const result = await applyManifest(manifest, { backupDir: backup });

  assertEquals(result.runBackupDir, null);
  assertEquals(await listNames(backup), []);
});

async function taggedTone(path: string, tags: { artist: string; album: string; title: string }): Promise<void> {
  await Deno.mkdir(join(path, ".."), { recursive: true });
  const meta = Object.entries(tags).flatMap(([k, v]) => ["-metadata", `${k}=${v}`]);
  const args = ["-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2", ...meta, "-y", path];
  const out = await new Deno.Command("ffmpeg", { args }).output();
  if (!out.success) throw new Error(new TextDecoder().decode(out.stderr));
}

async function sourcesManifest(entries: ManifestEntry[]) {
  const [downloaded, itunes, collection, backup] = await Promise.all(
    [0, 1, 2, 3].map(() => Deno.makeTempDir()),
  );
  const bandcamp = join(downloaded, "bandcamp");
  await Deno.mkdir(bandcamp);
  const manifest: Manifest = {
    version: 1,
    generated_at: new Date().toISOString(),
    source_dir: downloaded,
    source_dirs: { downloaded: `${downloaded}/`, bandcamp: `${bandcamp}/`, itunes: `${itunes}/` },
    move_dir: collection,
    cache_dir: collection,
    entries,
  };
  return { manifest, downloaded, bandcamp, itunes, collection, backup };
}

Deno.test("apply takes each entry from its own source folder, incl. a nested itunes path with no dash", async () => {
  const tags = { artist: "AFTER MIDNIGHT", album: "AF_MN", title: "Hat & Shades" };
  const { manifest, bandcamp, itunes, collection, backup } = await sourcesManifest([
    { ...entry("D-FORM - BURN EP - 01 Statik.wav", "apply"), source: "bandcamp", proposed: "D-FORM - BURN EP - Statik.wav" },
    { ...entry("AFTER MIDNIGHT/AF_MN/05 Hat & Shades.m4a", "apply"), source: "itunes", tags, proposed: "AFTER MIDNIGHT - AF_MN - Hat & Shades.m4a" },
  ]);
  await tone(join(bandcamp, "D-FORM - BURN EP - 01 Statik.wav"));
  await taggedTone(join(itunes, "AFTER MIDNIGHT/AF_MN/05 Hat & Shades.m4a"), tags);

  const result = await applyManifest(manifest, { backupDir: backup });

  assertEquals(result.failures, []);
  assertEquals(result.applied, 2);
  assertEquals(await listNames(collection), ["AFTER MIDNIGHT - AF_MN - Hat & Shades.aiff", "D-FORM - BURN EP - Statik.aiff"]);
  assertEquals(await listNames(bandcamp), []);
  assertEquals(await listNames(join(itunes, "AFTER MIDNIGHT/AF_MN")), []);
  assertEquals(await listNames(join(result.runBackupDir!, "itunes/AFTER MIDNIGHT/AF_MN")), ["05 Hat & Shades.m4a"]);
  assertEquals(await listNames(join(result.runBackupDir!, "bandcamp")), ["D-FORM - BURN EP - 01 Statik.wav"]);
});

Deno.test("two itunes tracks with the same file name are both backed up", async () => {
  const one = { artist: "Zero", album: "One - Single", title: "Intro" };
  const two = { artist: "Pryzms", album: "Two - Single", title: "Intro" };
  const { manifest, itunes, backup } = await sourcesManifest([
    { ...entry("Zero/One - Single/01 Intro.m4a", "apply"), source: "itunes", tags: one, proposed: "Zero - One - Intro.m4a" },
    { ...entry("Pryzms/Two - Single/01 Intro.m4a", "apply"), source: "itunes", tags: two, proposed: "Pryzms - Two - Intro.m4a" },
  ]);
  await taggedTone(join(itunes, "Zero/One - Single/01 Intro.m4a"), one);
  await taggedTone(join(itunes, "Pryzms/Two - Single/01 Intro.m4a"), two);

  const result = await applyManifest(manifest, { backupDir: backup });

  assertEquals([result.applied, result.failures.length], [2, 0]);
  assertEquals(await listNames(join(result.runBackupDir!, "itunes/Zero/One - Single")), ["01 Intro.m4a"]);
  assertEquals(await listNames(join(result.runBackupDir!, "itunes/Pryzms/Two - Single")), ["01 Intro.m4a"]);
});

Deno.test("an entry that can't be built fails alone; the rest still apply", async () => {
  const { manifest, downloaded, collection, backup } = await sourcesManifest([
    { ...entry("No Dash Here.wav", "apply"), source: "bandcamp" },
    { ...entry("Something.m4a", "apply"), source: "itunes" },
    entry("Blosso - Galvanize.wav", "apply"),
  ]);
  await tone(join(downloaded, "Blosso - Galvanize.wav"));

  const result = await applyManifest(manifest, { backupDir: backup });

  assertEquals(result.applied, 1);
  assertEquals(result.failures.map((f) => f.src), ["bandcamp/No Dash Here.wav", "itunes/Something.m4a"]);
  assertEquals(await listNames(collection), ["Blosso - Galvanize.aiff"]);
});

Deno.test("an entry whose source has no folder in the manifest fails instead of using another folder", async () => {
  const { manifest, downloaded, collection, backup } = await sourcesManifest([
    { ...entry("Blosso - Galvanize.wav", "apply"), source: "soundcloud" },
  ]);
  await tone(join(downloaded, "Blosso - Galvanize.wav"));

  const result = await applyManifest(manifest, { backupDir: backup });

  assertEquals([result.applied, result.failures.length], [0, 1]);
  assertEquals(await listNames(collection), []);
  assertEquals(await listNames(downloaded), ["Blosso - Galvanize.wav", "bandcamp"]);
});

Deno.test("apply refuses a src that reaches outside its folder through a symlink", async () => {
  const outside = await Deno.makeTempDir();
  await tone(join(outside, "Blosso - Galvanize.wav"));
  const { manifest, itunes, collection, backup } = await sourcesManifest([
    { ...entry("Link/Blosso - Galvanize.wav", "apply"), source: "itunes", tags: { artist: "Blosso", album: "", title: "Galvanize" }, proposed: "Blosso - Galvanize.wav" },
  ]);
  await Deno.symlink(outside, join(itunes, "Link"));

  const result = await applyManifest(manifest, { backupDir: backup });

  assertEquals([result.applied, result.failures.length], [0, 1]);
  assertEquals(await listNames(outside), ["Blosso - Galvanize.wav"]);
  assertEquals(await listNames(collection), []);
});
