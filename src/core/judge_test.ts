/**
 * Offline tests for judge.ts. Must run under `deno task test` (--allow-env --allow-read
 * --allow-write, no --allow-net) without ever making a network call.
 *
 * applyJudgement is pure and never touches the TypeSafe SDK, so it's tested directly.
 * assertJudgeAvailable does construct the SDK client, but a missing TYPESAFE_API_KEY throws
 * before any request is made — that's the config-error path this suite pins.
 */
import { assertEquals, assertRejects, assertStringIncludes } from "jsr:@std/assert@^1";
import { applyJudgement, assertJudgeAvailable } from "./judge.ts";
import { EntryJudgement, ManifestEntry } from "./manifest.ts";

function makeEntry(overrides: Partial<ManifestEntry> = {}): ManifestEntry {
  return {
    src: "Some Artist - Some Album - Some Title.mp3",
    proposed: "Some Artist - Some Album - Some Title.mp3",
    parser_output: "Some Artist - Some Album - Some Title.mp3",
    confidence: "high",
    reasons: ["clean parse, no transformations needed"],
    decision: "apply",
    ...overrides,
  };
}

function makeJudgement(overrides: Partial<EntryJudgement> = {}): EntryJudgement {
  return {
    nouls: { nothing_lost: 0.95, title_is_a_title: 0.9, fields_not_swapped: 0.97 },
    judged_proposed: "Some Artist - Some Album - Some Title.mp3",
    model: "jev-latest",
    judged_at: "2026-01-01T00:00:00.000Z",
    ...overrides,
  };
}

Deno.test("applyJudgement: all nouls above threshold leaves decision unchanged", () => {
  const entry = makeEntry({ decision: "apply" });
  const judgement = makeJudgement();
  const result = applyJudgement(entry, judgement, 0.5);
  assertEquals(result.decision, "apply");
  assertEquals(result.judgement, judgement);
});

Deno.test("applyJudgement: a noul below threshold downgrades apply to review, never upgrades", () => {
  const entry = makeEntry({ decision: "apply" });
  const judgement = makeJudgement({ nouls: { nothing_lost: 0.2, title_is_a_title: 0.9, fields_not_swapped: 0.97 } });
  const result = applyJudgement(entry, judgement, 0.5);
  assertEquals(result.decision, "review");
  assertStringIncludes(result.reasons.at(-1)!, "nothing_lost=0.20 below threshold 0.5");
});

Deno.test("applyJudgement: a skip entry that fails judging stays downgraded to review, not re-upgraded", () => {
  const entry = makeEntry({ decision: "skip", reasons: ["duplicate of an existing track in the DJ collection"] });
  const judgement = makeJudgement({ nouls: { nothing_lost: 0.1, title_is_a_title: 0.9, fields_not_swapped: 0.9 } });
  const result = applyJudgement(entry, judgement, 0.5);
  assertEquals(result.decision, "review");
});

Deno.test("applyJudgement: an error verdict downgrades to review and records the error", () => {
  const entry = makeEntry({ decision: "apply" });
  const judgement = makeJudgement({ error: "request timed out" });
  const result = applyJudgement(entry, judgement, 0.5);
  assertEquals(result.decision, "review");
  assertStringIncludes(result.reasons.at(-1)!, "request timed out");
  assertEquals(result.judgement?.error, "request timed out");
});

Deno.test("applyJudgement: a missing (undefined) judgement is a failure verdict, not a pass", () => {
  const entry = makeEntry({ decision: "apply" });
  const result = applyJudgement(entry, undefined, 0.5);
  assertEquals(result.decision, "review");
  assertEquals(result.judgement?.error, "no judgement recorded for this entry");
});

Deno.test("assertJudgeAvailable: throws a ConfigurationError when TYPESAFE_API_KEY is unset", async () => {
  const original = Deno.env.get("TYPESAFE_API_KEY");
  Deno.env.delete("TYPESAFE_API_KEY");
  try {
    await assertRejects(() => assertJudgeAvailable(), Error, "TYPESAFE_API_KEY");
  } finally {
    if (original !== undefined) Deno.env.set("TYPESAFE_API_KEY", original);
  }
});
