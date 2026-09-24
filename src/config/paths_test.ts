import { assertEquals, assertThrows } from "jsr:@std/assert@^1";
import { getFolder } from "../core/utils/common.ts";
import { ConfigurationError } from "../core/utils/errors.ts";

function withEnv(name: string, value: string | undefined, fn: () => void): void {
  const before = Deno.env.get(name);
  if (value === undefined) Deno.env.delete(name);
  else Deno.env.set(name, value);
  try {
    fn();
  } finally {
    if (before === undefined) Deno.env.delete(name);
    else Deno.env.set(name, before);
  }
}

Deno.test("an unset path variable fails naming it, rather than falling back to a guess", () => {
  withEnv("TUNEWRANGLER_DOWNLOADED_PATH", undefined, () => {
    assertThrows(() => getFolder("downloaded"), ConfigurationError, "TUNEWRANGLER_DOWNLOADED_PATH");
  });
});

Deno.test("a path without a trailing slash gets one", () => {
  withEnv("TUNEWRANGLER_RENAME_PATH", "/music/renamed", () => {
    assertEquals(getFolder("rename"), "/music/renamed/");
  });
});
