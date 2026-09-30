import { assertEquals, assertRejects } from "jsr:@std/assert@^1";
import { join } from "@std/path";
import { acquireRunLock } from "./runLock.ts";
import { TryLaterError } from "./errors.ts";
import { requireFolders } from "../../config/paths.ts";

Deno.test("a second run is turned away while the first holds the lock", async () => {
  const lock = join(await Deno.makeTempDir(), "rm.lock");
  const release = await acquireRunLock(lock);

  await assertRejects(() => acquireRunLock(lock, 100), TryLaterError, "holds");

  await release();
  await (await acquireRunLock(lock))();
});

Deno.test("a lock held by a run that crashed is free again", async () => {
  const lock = join(await Deno.makeTempDir(), "rm.lock");
  const holdAndDie = `const f = await Deno.open(${JSON.stringify(lock)}, { create: true, write: true });
    await f.lock(true); console.log("locked"); Deno.exit(1);`;
  const child = await new Deno.Command(Deno.execPath(), { args: ["eval", holdAndDie] }).output();
  assertEquals(new TextDecoder().decode(child.stdout).trim(), "locked");

  await (await acquireRunLock(lock, 100))();
});

Deno.test("an unplugged or blank folder stops the run before it changes anything", async () => {
  const present = await Deno.makeTempDir();
  const missing = join(present, "gone");

  await requireFolders({ HERE: present });
  await assertRejects(() => requireFolders({ HERE: present, GONE: missing }), TryLaterError, "GONE does not exist");
  await assertRejects(() => requireFolders({ BLANK: "" }), TryLaterError, "BLANK is empty");
});
