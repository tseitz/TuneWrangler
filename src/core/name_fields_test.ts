import { assertEquals } from "jsr:@std/assert@^1";
import { tagsFromFilename } from "./tagging.ts";

// rekordbox sync-names splits names with its own port of tagsFromFilename; both read this fixture.
const FIXTURE = new URL("../../rekordbox/tests/fixtures/name_fields.json", import.meta.url);

Deno.test("tagsFromFilename matches the shared name fixture", async () => {
  const cases: { stem: string; artist: string; album: string; title: string }[] = JSON.parse(
    await Deno.readTextFile(FIXTURE),
  );
  for (const { stem, ...want } of cases) assertEquals(tagsFromFilename(`${stem}.mp3`), want, stem);
});
