import { assertEquals } from "jsr:@std/assert@^1";
import {
  applySuggestion,
  buildPrompt,
  type ClaudeRunner,
  inventsWords,
  parseClaudeOutput,
  sameName,
  suggestNames,
} from "./suggest.ts";
import type { ManifestEntry } from "./manifest.ts";

function entry(proposed: string, decision: ManifestEntry["decision"] = "apply"): ManifestEntry {
  return { src: proposed, proposed, parser_output: proposed, confidence: "medium", reasons: [], decision };
}

const output = (name: string, confident = true) => ({ index: 0, name, confident, why: "because" });

/** The source text defaults to the entry's own file name. */
function fold(e: ManifestEntry, name: string, { confident = true, source = e.src } = {}) {
  return applySuggestion(e, output(name, confident), undefined, "sonnet", source);
}

Deno.test("sameName ignores extension, case, accents and how artists are joined", () => {
  assertEquals(sameName("CONTRA x Saturna - What I Can Do.wav", "CØNTRA & Saturna - what i can do"), true);
  assertEquals(sameName("A - B.wav", "A - C"), false);
});

Deno.test("a cosmetic difference counts as agreeing and keeps the parser's name", () => {
  const result = fold(entry("CONTRA - Nirali.aiff"), "CØNTRA - Nirali.aiff");
  assertEquals([result.proposed, result.suggestion?.outcome], ["CONTRA - Nirali.aiff", "agreed"]);
});

Deno.test("a confident rename replaces proposed, keeps parser_output and the source's extension", () => {
  const result = fold(entry("BACK HURT x MIGOS - ASAP FERG.wav"), "ASAP FERG x MIGOS - BACK HURT.aiff");
  assertEquals(result.proposed, "ASAP FERG x MIGOS - BACK HURT.wav");
  assertEquals(result.parser_output, "BACK HURT x MIGOS - ASAP FERG.wav");
  assertEquals([result.decision, result.suggestion?.outcome], ["apply", "renamed"]);
});

Deno.test("a renamed name gets the parser's cleanup: ASCII letters, no characters a file system rejects", () => {
  const source = "Fred Again - Jungle (Jimmy Pé RMX).wav";
  const result = fold(entry("Fred Again - Jungle.wav"), "Jimmy Pé - Fred Again: Jungle?", { source });
  assertEquals(result.proposed, "Jimmy Pe - Fred Again Jungle.wav");
});

Deno.test("a rename may only use words the file already has", () => {
  assertEquals(inventsWords("Jimmy Pe - Fred Again - Jungle", "Fred Again - Jungle (Jimmy Pé RMX).wav"), false);
  assertEquals(inventsWords("Evil - Payload - Now", "A - B.wav"), true);
  const injected = fold(entry("A - B.wav"), "Evil - Payload - Now");
  assertEquals([injected.proposed, injected.suggestion?.outcome], ["A - B.wav", "unsure"]);
});

Deno.test("a rename into one part or four parts isn't taken", () => {
  for (const name of ["B A", "B - A - C - D"]) {
    const result = fold(entry("A - B - C - D.wav"), name, { source: "A - B - C - D" });
    assertEquals([result.proposed, result.suggestion?.outcome], ["A - B - C - D.wav", "unsure"], name);
  }
});

Deno.test("agreeing or renaming settles a parser review as apply", () => {
  assertEquals(fold(entry("A - B.wav", "review"), "A - B").decision, "apply");
  assertEquals(fold(entry("A - B.wav", "review"), "B - A").decision, "apply");
});

Deno.test("claude can't overrule a Jev downgrade or a missing SoundCloud credit", () => {
  const judged = { ...entry("A - B.wav", "review"), reasons: ["jev: nothing_lost=0.10 below threshold 0.5"] };
  assertEquals(fold(judged, "A - B").decision, "review");

  const soundcloud = { url: "u", title: null, uploader: "Label", metadata_artist: "A, Missing Artist", label_name: null };
  const uncredited = { ...entry("A - B.wav", "review"), soundcloud };
  assertEquals(fold(uncredited, "A - B").decision, "review");
  const credited = fold(uncredited, "A x Missing Artist - B", { source: "A - B Missing Artist" });
  assertEquals([credited.proposed, credited.decision], ["A x Missing Artist - B.wav", "apply"]);
});

Deno.test("an unsure answer keeps the parser's name and decision, even when it repeats the parser's name", () => {
  for (const name of ["B - A", "A - B"]) {
    const result = fold(entry("A - B.wav", "review"), name, { confident: false });
    assertEquals([result.proposed, result.decision, result.suggestion?.outcome], ["A - B.wav", "review", "unsure"], name);
  }
});

Deno.test("a failed call or an unsafe name keeps the parser's name and decision", () => {
  const failed = applySuggestion(entry("A - B.wav", "review"), undefined, "claude call failed", "sonnet", "A - B");
  assertEquals([failed.proposed, failed.decision, failed.suggestion?.outcome], ["A - B.wav", "review", "failed"]);
  for (const name of ["../x - y", "A\n- B", ".hidden - x", "  ", "A - B‮", "A - B.mp3.mp3", `A - ${"b".repeat(201)}`]) {
    const unsafe = fold(entry("A - B.wav"), name);
    assertEquals([unsafe.proposed, unsafe.suggestion?.outcome], ["A - B.wav", "failed"], name);
  }
});

Deno.test("suggestNames maps answers back by index and stops before the run budget", async () => {
  const prompts: string[] = [];
  const run: ClaudeRunner = (prompt) => {
    prompts.push(prompt);
    return Promise.resolve({ outputs: [{ index: 1, name: "second", confident: true, why: "" }], costUsd: 0.4, model: "m" });
  };
  const inputs = Array.from({ length: 6 }, (_, i) => ({ source: "downloaded" as const, filename: `f${i}.wav`, parserName: `p${i}` }));

  const result = await suggestNames(inputs, { run, examples: "", batchSize: 2, perCallMaxUsd: 0.5, runMaxUsd: 1 });

  assertEquals(prompts.length, 2);
  assertEquals(result.outputs.map((o) => o?.name), [undefined, "second", undefined, "second", undefined, undefined]);
  assertEquals(result.errors[0], "claude returned no name for this file");
  assertEquals(result.errors[4], "run budget of $1 spent");
});

Deno.test("a call that throws or reports no cost fails its batch and counts its cap against the budget", async () => {
  let calls = 0;
  const run: ClaudeRunner = () => {
    calls++;
    return calls === 1 ? Promise.reject(new Error("spawn failed")) : Promise.resolve({ outputs: [], costUsd: 0, model: "m", error: "no JSON" });
  };
  const inputs = Array.from({ length: 6 }, (_, i) => ({ source: "downloaded" as const, filename: `f${i}.wav`, parserName: `p${i}` }));

  const result = await suggestNames(inputs, { run, examples: "", batchSize: 2, perCallMaxUsd: 0.5, runMaxUsd: 1 });

  assertEquals(calls, 2);
  assertEquals(result.errors[0]?.includes("spawn failed"), true);
  assertEquals(result.errors[2], "no JSON");
  assertEquals(result.errors[4], "run budget of $1 spent");
});

Deno.test("parseClaudeOutput keeps the cost of a failed call", () => {
  const failed = parseClaudeOutput(JSON.stringify({ subtype: "error_max_budget_usd", is_error: true, total_cost_usd: 0.79 }), "", "m");
  assertEquals([failed.costUsd, failed.outputs.length, failed.error?.includes("error_max_budget_usd")], [0.79, 0, true]);
  assertEquals(parseClaudeOutput("not json", "boom", "m").error?.includes("boom"), true);
});

Deno.test("the prompt carries tags, SoundCloud credits and the &-names list", () => {
  const prompt = buildPrompt("RULES", [{
    source: "itunes",
    filename: "01 T.m4a",
    tags: { artist: "A", album: "B", title: "T" },
    credits: "artist A x C",
    parserName: "A - B - T.m4a",
  }]);
  assertEquals(["RULES", 'artist="A"', "soundcloud credits: artist A x C", "Joey Valence & Brae"].every((s) => prompt.includes(s)), true);
});
