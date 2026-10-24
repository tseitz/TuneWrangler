import { assertEquals, assertThrows } from "jsr:@std/assert@^1";

import { selectNames } from "./retagFromFilename.ts";

const present = ["A - B - C.mp3", "Don't & Stop - X - Y.aiff", "z.flac"];

Deno.test("selectNames: no --only keeps everything", () => {
  assertEquals(selectNames(present, []), present);
});

Deno.test("selectNames: restricts to exact names, keeping folder order", () => {
  assertEquals(selectNames(present, ["z.flac", "Don't & Stop - X - Y.aiff"]), [
    present[1],
    present[2],
  ]);
});

Deno.test("selectNames: duplicates in --only are harmless", () => {
  assertEquals(selectNames(present, ["z.flac", "z.flac"]), ["z.flac"]);
});

Deno.test("selectNames: a missing name throws, naming it", () => {
  assertThrows(
    () => selectNames(present, ["z.flac", "nope.mp3"]),
    Error,
    "nope.mp3",
  );
});

Deno.test("selectNames: match is exact, not case-folded", () => {
  assertThrows(() => selectNames(present, ["a - b - c.mp3"]), Error);
});
