import { assertEquals } from "jsr:@std/assert@^1";
import { isProcessable } from "./common.ts";

function file(name: string): Deno.DirEntry {
  return { name, isFile: true, isDirectory: false, isSymlink: false };
}

Deno.test("isProcessable skips macOS AppleDouble files", () => {
  assertEquals(isProcessable(file("._Artist - Title.wav")), false);
  assertEquals(isProcessable(file("Artist - Title.wav")), true);
});
