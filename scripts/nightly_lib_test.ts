import { assertEquals } from "jsr:@std/assert@^1";
import {
  coreSettled,
  downloadOutcome,
  embedUsable,
  freshState,
  type LastRun,
  lineAfter,
  MAX_DEFERRALS,
  notificationTitle,
  onBattery,
  parseDrift,
  renameOutcome,
  reportLines,
  runnable,
  settle,
} from "./nightly_lib.ts";

const started = new Date("2026-10-09T03:00:00Z");

function lastRun(over: Partial<LastRun> = {}): LastRun {
  return {
    run_started_at: "2026-10-09T03:00:01Z",
    finished: true,
    stopped_early: false,
    error: null,
    counts: { done: 2 },
    needs_attention: [],
    ...over,
  };
}

Deno.test("a new day starts every stage over; the same day keeps its progress", () => {
  const today = freshState("2026-10-09");
  today.stages.download = settle(today.stages.download, "done", 0, null);
  assertEquals(freshState("2026-10-09", today).stages.download.status, "done");
  assertEquals(freshState("2026-10-10", today).stages.download.status, "pending");
});

Deno.test("a failing stage is given up on after 3 attempts; a retry costs none", () => {
  let stage = freshState("d").stages.rename;
  stage = settle(stage, "retry", 75, null);
  assertEquals([stage.status, stage.attempts], ["pending", 0]);
  for (let i = 0; i < 2; i++) stage = settle(stage, "failed", 2, null);
  assertEquals(stage.status, "pending");
  stage = settle(stage, "failed", 2, null);
  assertEquals([stage.status, stage.attempts], ["gave_up", 3]);
});

Deno.test("rM exit 1 counts as done only when it printed its apply summary; 75 is a retry", () => {
  assertEquals([0, 1, 75, 2].map((c) => renameOutcome(c, true)), ["done", "done", "retry", "failed"]);
  assertEquals(renameOutcome(1, false), "failed");
});

Deno.test("embed exit 1 is usable only when it printed its summary", () => {
  assertEquals([embedUsable(0, false), embedUsable(1, true), embedUsable(1, false), embedUsable(2, true)], [
    true,
    true,
    false,
    false,
  ]);
});

Deno.test("download and rename give up after a day's worth of deferrals; tag never does", () => {
  let stage = freshState("d").stages.download;
  for (let i = 0; i < MAX_DEFERRALS.download; i++) stage = settle(stage, "retry", null, null, MAX_DEFERRALS.download);
  assertEquals([stage.status, stage.attempts], ["gave_up", 0]);
  let tag = freshState("d").stages.tag;
  for (let i = 0; i < 100; i++) tag = settle(tag, "retry", 75, null, MAX_DEFERRALS.tag);
  assertEquals(tag.status, "pending");
});

Deno.test("the downloader's exit 0 is only done when its run record says it finished", () => {
  assertEquals(downloadOutcome(0, lastRun(), started), "done");
  assertEquals(downloadOutcome(0, lastRun({ stopped_early: true }), started), "failed");
  assertEquals(downloadOutcome(0, lastRun({ error: "login required" }), started), "failed");
  assertEquals(downloadOutcome(0, null, started), "failed");
  assertEquals(downloadOutcome(0, lastRun({ run_started_at: "2026-10-08T03:00:00Z" }), started), "failed");
  assertEquals(downloadOutcome(1, lastRun(), started), "failed");
});

Deno.test("prune and tag wait for rename to settle, even when it gave up", () => {
  const state = freshState("d");
  assertEquals(runnable(state), ["download", "rename"]);
  state.stages.rename = { status: "gave_up", attempts: 3, deferrals: 0, lastExit: 2, detail: null };
  assertEquals(runnable(state), ["download", "prune", "tag"]);
});

Deno.test("the notification doesn't wait on tagging, which waits for Rekordbox to close", () => {
  const state = freshState("d");
  for (const s of ["download", "rename", "prune"] as const) state.stages[s] = settle(state.stages[s], "done", 0, null);
  assertEquals(coreSettled(state), true);
  assertEquals(notificationTitle(state), "TuneWrangler ✓");
  state.stages.prune = { status: "gave_up", attempts: 3, deferrals: 0, lastExit: 1, detail: null };
  assertEquals(notificationTitle(state), "TuneWrangler: prune failed");
});

Deno.test("power: run on AC whatever the lid, never on battery", () => {
  assertEquals(onBattery("Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t100%; charged"), false);
  assertEquals(onBattery("Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t95%; discharging"), true);
});

Deno.test("output lines are matched at the start of a line only", () => {
  const out = "INFO wrote the manifest: elsewhere\nmanifest: /x/tag-manifest.json\n";
  assertEquals(lineAfter(out, "manifest:"), "/x/tag-manifest.json");
});

Deno.test("the report names stuck downloads, a mass return and held downloads", () => {
  const state = freshState("2026-10-09");
  const lines = reportLines({
    state,
    lastRun: lastRun({ needs_attention: [{}, {}] }),
    lastPrune: {
      run_started_at: "2026-10-09T03:10:00-0500",
      error: null,
      removed: 3,
      returned: 6,
      kept: 1,
      mass_return: true,
    },
    holding: 2,
  });
  assertEquals(lines[0], "download: waiting — 2 downloaded, 2 need attention");
  assertEquals(lines.some((l) => l.includes("came back 6")), true);
  assertEquals(lines.some((l) => l.includes("check recent additions")), true);
  assertEquals(lines.at(-1), "2 downloads waiting in logs/soundcloud_dl/downloads/");
});

Deno.test("the report ignores run records from an earlier day", () => {
  const lines = reportLines({
    state: freshState("2026-10-10"),
    lastRun: lastRun(),
    lastPrune: { run_started_at: "2026-10-09T03:10:00-0500", error: null, removed: 9, returned: 0, kept: 0, mass_return: false },
    holding: 0,
  });
  assertEquals(lines[0], "download: waiting — ");
  assertEquals(lines.some((l) => l.includes("removed 9")), false);
});

Deno.test("parseDrift reads the closing drift line and is null without one", () => {
  assertEquals(parseDrift("scanned: 9 tracks\ndrift: 4 tracks (2 held)\n"), { drift: 4, held: 2 });
  assertEquals(parseDrift("scanned: 9 tracks\n"), null);
});

Deno.test("the report adds a names line only when tracks drifted or the check failed", () => {
  const base = { state: freshState("2026-10-09"), lastRun: null, lastPrune: null, holding: 0 };
  const names = (namesDrift?: Parameters<typeof reportLines>[0]["namesDrift"]) =>
    reportLines({ ...base, namesDrift }).filter((l) => l.startsWith("names:"));
  assertEquals(names({ exit: 0, drift: 3, held: 1 }), [
    "names: 3 tracks out of sync with Rekordbox (1 held) — deno task rb sync-names",
  ]);
  assertEquals(names({ exit: 0, drift: 0, held: 0 }), []);
  assertEquals(names(), []);
  assertEquals(names({ exit: 1, drift: null, held: 0 }), ["names: drift check failed (exit 1)"]);
});
