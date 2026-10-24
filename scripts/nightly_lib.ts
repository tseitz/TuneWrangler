export const STAGES = ["download", "rename", "prune", "tag"] as const;
export type StageName = typeof STAGES[number];

export const MAX_ATTEMPTS = 3;
/** 4 hours of polls. Tag has no cap: Rekordbox may be open all day, and the notice doesn't wait for it. */
export const MAX_DEFERRALS: Record<StageName, number> = { download: 8, rename: 8, prune: 8, tag: Infinity };
export const TRY_LATER = 75;

export interface StageState {
  status: "pending" | "done" | "gave_up";
  attempts: number;
  deferrals: number;
  lastExit: number | null;
  detail: string | null;
}

export interface NightlyState {
  version: 1;
  date: string;
  stages: Record<StageName, StageState>;
  /** The title last notified, so a stage that fails after the notice gets a second one. */
  notified: string | null;
  renameManifest: string | null;
  tagManifest: string | null;
  tagApplyLog: string | null;
  /** Absent in state files from before the check existed, and until a run settles. */
  namesDrift?: NamesDrift;
}

export interface NamesDrift {
  exit: 0 | 1;
  drift: number | null;
  held: number;
}

export function freshState(date: string, previous?: NightlyState): NightlyState {
  if (previous?.date === date) return previous;
  const stages = Object.fromEntries(
    STAGES.map((s) => [s, { status: "pending", attempts: 0, deferrals: 0, lastExit: null, detail: null }]),
  ) as Record<StageName, StageState>;
  return {
    version: 1,
    date,
    stages,
    notified: null,
    renameManifest: null,
    tagManifest: null,
    tagApplyLog: null,
  };
}

/** "retry" costs no attempt: the stage couldn't start (drive, lock, Rekordbox open). */
export type Outcome = "done" | "retry" | "failed";

export function settle(
  stage: StageState,
  outcome: Outcome,
  exit: number | null,
  detail: string | null,
  maxDeferrals = Infinity,
): StageState {
  if (outcome === "done") return { ...stage, status: "done", attempts: stage.attempts + 1, lastExit: exit, detail };
  if (outcome === "retry") {
    const deferrals = stage.deferrals + 1;
    return { ...stage, status: deferrals >= maxDeferrals ? "gave_up" : "pending", deferrals, lastExit: exit, detail };
  }
  const attempts = stage.attempts + 1;
  return { ...stage, status: attempts >= MAX_ATTEMPTS ? "gave_up" : "pending", attempts, lastExit: exit, detail };
}

/** rM also exits 1 after an apply with some failures; a crash exits 1 too, but prints no summary. */
export function renameOutcome(exit: number, printedSummary: boolean): Outcome {
  if (exit === 0 || (exit === 1 && printedSummary)) return "done";
  return exit === TRY_LATER ? "retry" : "failed";
}

/** embed exits 1 when some tracks failed; a crash exits 1 too, but prints no summary. */
export function embedUsable(exit: number, printedSummary: boolean): boolean {
  return exit === 0 || (exit === 1 && printedSummary);
}

export interface LastRun {
  run_started_at: string;
  finished: boolean;
  stopped_early: boolean;
  error: string | null;
  counts: Record<string, number>;
  needs_attention: unknown[];
}

/** The downloader exits 0 even when it stopped early, so its run record decides. */
export function downloadOutcome(exit: number, lastRun: LastRun | null, startedAt: Date): Outcome {
  if (exit !== 0 || !lastRun) return "failed";
  if (new Date(lastRun.run_started_at).getTime() < startedAt.getTime() - 1000) return "failed";
  return lastRun.finished && !lastRun.stopped_early && !lastRun.error ? "done" : "failed";
}

export function settled(stage: StageState): boolean {
  return stage.status !== "pending";
}

/** Stages this poll should run, in order. Prune and tag wait for rename. */
export function runnable(state: NightlyState): StageName[] {
  const { stages } = state;
  return STAGES.filter((s) => {
    if (settled(stages[s])) return false;
    if (s === "prune" || s === "tag") return settled(stages.rename);
    return true;
  });
}

/** Tag can wait on Rekordbox closing all day, so the notification doesn't wait for it. */
export function coreSettled(state: NightlyState): boolean {
  return settled(state.stages.download) && settled(state.stages.rename) && settled(state.stages.prune);
}

/** Runs only on AC power (Tegan, 2026-10-10). On AC a closed lid is a desk setup. */
export function onBattery(pmsetBatt: string): boolean {
  return !pmsetBatt.includes("'AC Power'");
}

export function lineAfter(output: string, prefix: string): string | null {
  for (const line of output.split("\n")) {
    const trimmed = line.trim();
    if (trimmed.startsWith(prefix)) return trimmed.slice(prefix.length).trim();
  }
  return null;
}

export function lineWith(output: string, needle: string): string | null {
  return output.split("\n").find((l) => l.includes(needle))?.trim() ?? null;
}

/** The `drift: N tracks (H held)` line that `rb sync-names` ends its report with. */
export function parseDrift(output: string): { drift: number; held: number } | null {
  const m = lineAfter(output, "drift:")?.match(/^(\d+) tracks? \((\d+) held\)/);
  return m ? { drift: Number(m[1]), held: Number(m[2]) } : null;
}

export interface LastPrune {
  run_started_at: string;
  error: string | null;
  removed: number;
  returned: number;
  kept: number | null;
  mass_return: boolean;
}

/** A record from before today is a run that died before writing its own. */
export function fromToday<T extends { run_started_at: string }>(record: T | null, date: string): T | null {
  return record && record.run_started_at.slice(0, 10) === date ? record : null;
}

export interface ReportInput {
  state: NightlyState;
  lastRun: LastRun | null;
  lastPrune: LastPrune | null;
  holding: number;
  namesDrift?: NamesDrift;
}

const LABEL: Record<StageState["status"], string> = { pending: "waiting", done: "ok", gave_up: "FAILED" };

export function reportLines({ state, holding, namesDrift, ...records }: ReportInput): string[] {
  const { stages } = state;
  const lastRun = fromToday(records.lastRun, state.date);
  const lastPrune = fromToday(records.lastPrune, state.date);
  const lines: string[] = [];
  const dl = stages.download;
  let dlDetail = dl.detail ?? "";
  if (lastRun) {
    const attention = lastRun.needs_attention.length;
    dlDetail = `${lastRun.counts.done ?? 0} downloaded, ${attention} need attention` +
      (lastRun.error ? ` (${lastRun.error})` : "");
  }
  lines.push(`download: ${LABEL[dl.status]} — ${dlDetail}`);
  lines.push(`rename: ${LABEL[stages.rename.status]} — ${stages.rename.detail ?? ""}`);
  let pruneDetail = stages.prune.detail ?? "";
  if (lastPrune) {
    pruneDetail = lastPrune.error ??
      `removed ${lastPrune.removed}, kept ${lastPrune.kept ?? "?"}, came back ${lastPrune.returned}`;
  }
  lines.push(`prune: ${LABEL[stages.prune.status]} — ${pruneDetail}`);
  if (lastPrune?.mass_return) {
    lines.push("prune: many pruned tracks came back — check recent additions are still on the playlist");
  }
  lines.push(`tag: ${LABEL[stages.tag.status]} — ${stages.tag.detail ?? ""}`);
  if (namesDrift?.drift === null) {
    lines.push(`names: drift check failed (exit ${namesDrift.exit})`);
  } else if (namesDrift && namesDrift.drift > 0) {
    lines.push(
      `names: ${namesDrift.drift} tracks out of sync with Rekordbox (${namesDrift.held} held) — deno task rb sync-names`,
    );
  }
  if (holding > 0) lines.push(`${holding} downloads waiting in logs/soundcloud_dl/downloads/`);
  return lines;
}

export function notificationTitle(state: NightlyState): string {
  const failed = STAGES.filter((s) => state.stages[s].status === "gave_up");
  return failed.length ? `TuneWrangler: ${failed.join(", ")} failed` : "TuneWrangler ✓";
}
