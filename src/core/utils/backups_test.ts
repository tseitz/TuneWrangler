import { assertEquals, assertRejects } from "jsr:@std/assert@^1";
import { join } from "@std/path";
import { listBackupRuns, pruneBackups, startBackupRun } from "./backups.ts";

async function exists(path: string): Promise<boolean> {
  try {
    await Deno.stat(path);
    return true;
  } catch {
    return false;
  }
}

Deno.test("a second run gets its own folder and leaves the first run's originals alone", async () => {
  const root = await Deno.makeTempDir();
  const first = await startBackupRun(root, "rename-music", new Date("2026-09-24T07:00:00Z"));
  await Deno.writeTextFile(join(first, "song.wav"), "original");
  const second = await startBackupRun(root, "rename-music", new Date("2026-09-24T08:00:00Z"));

  assertEquals(first === second, false);
  assertEquals(await Deno.readTextFile(join(first, "song.wav")), "original");
});

Deno.test("prune keeps the newest runs and never touches loose files or other folders", async () => {
  const root = await Deno.makeTempDir();
  for (const hour of ["05", "06", "07"]) {
    await startBackupRun(root, "rename-music", new Date(`2026-09-24T${hour}:00:00Z`));
  }
  await Deno.writeTextFile(join(root, "loose.wav"), "x");
  await Deno.mkdir(join(root, "keep-me"));

  const listed = await pruneBackups(root, 1, { apply: false });
  assertEquals(listed, ["2026-09-24_05-00-00_rename-music", "2026-09-24_06-00-00_rename-music"]);
  assertEquals((await listBackupRuns(root)).length, 3);

  await pruneBackups(root, 1, { apply: true });
  assertEquals(await listBackupRuns(root), ["2026-09-24_07-00-00_rename-music"]);
  assertEquals(await exists(join(root, "loose.wav")), true);
  assertEquals(await exists(join(root, "keep-me")), true);
});

Deno.test("prune refuses to keep zero runs", async () => {
  const root = await Deno.makeTempDir();
  await assertRejects(() => pruneBackups(root, 0, { apply: true }), Error, "--keep");
});
