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
