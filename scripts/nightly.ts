/**
 * Nightly job: download → rename → prune → auto-tag. launchd polls this every 30 minutes and
 * on every volume mount; the gate decides whether anything runs.
 *
 *   deno task nightly            one poll (what launchd runs)
 *   deno task nightly --force    run today's stages again, ignoring the power gate
 *
 * Stop it with `touch logs/nightly/pause`. Per-day state is in logs/nightly/state.json.
 */
import { join } from "@std/path";
import { acquireRunLock } from "../src/core/utils/runLock.ts";
import { TryLaterError } from "../src/core/utils/errors.ts";
import {
  coreSettled,
  downloadOutcome,
  embedUsable,
  freshState,
  type LastPrune,
  type LastRun,
  lineAfter,
  lineWith,
  MAX_DEFERRALS,
  type NightlyState,
  notificationTitle,
  type Outcome,
  onBattery,
  renameOutcome,
  reportLines,
  runnable,
  settle,
  type StageName,
  STAGES,
  TRY_LATER,
} from "./nightly_lib.ts";

const REPO = new URL("..", import.meta.url).pathname;
const LOG_DIR = join(REPO, "logs/nightly");
const STATE_FILE = join(LOG_DIR, "state.json");
const SC_LOGS = join(REPO, "logs/soundcloud_dl");
const KEEP_LOG_DAYS = 30;

const force = Deno.args.includes("--force");
const today = localDate(new Date());

function localDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

async function gate(reason: string): Promise<never> {
  await Deno.writeTextFile(join(LOG_DIR, "gate.txt"), `${new Date().toISOString()}  skipped: ${reason}\n`);
  Deno.exit(0);
}

async function readJson<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await Deno.readTextFile(path)) as T;
  } catch (e) {
    if (e instanceof Deno.errors.NotFound) return null;
    throw new Error(`Could not read ${path}: ${e}`);
  }
}

async function saveState(state: NightlyState): Promise<void> {
  const tmp = `${STATE_FILE}.tmp`;
  await Deno.writeTextFile(tmp, JSON.stringify(state, null, 2));
  await Deno.rename(tmp, STATE_FILE);
}

async function capture(cmd: string, args: string[]): Promise<string> {
  const { stdout } = await new Deno.Command(cmd, { args, stdout: "piped", stderr: "null" }).output();
  return new TextDecoder().decode(stdout);
}

function appleScriptString(s: string): string {
  return `"${s.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

async function notify(title: string, body: string): Promise<boolean> {
  const script = `display notification ${appleScriptString(body)} with title ${appleScriptString(title)}`;
  const { code } = await new Deno.Command("/usr/bin/osascript", { args: ["-e", script] }).output();
  if (code !== 0) console.error(`osascript exited ${code}; notification not shown: ${title}`);
  return code === 0;
}

/** NotFound is an unplugged drive (skip quietly); anything else is a real problem. */
async function driveProblem(folder: string): Promise<"absent" | string | null> {
  try {
    for await (const _ of Deno.readDir(folder)) break;
    return null;
  } catch (e) {
    if (e instanceof Deno.errors.NotFound) return "absent";
    if (e instanceof Deno.errors.PermissionDenied) {
      return `macOS blocked reading ${folder}. Grant Full Disk Access to ${Deno.execPath()}.`;
    }
    return `Could not read ${folder}: ${e}`;
  }
}

async function chromeBusy(): Promise<boolean> {
  const port = Deno.env.get("TUNEWRANGLER_SC_CHROME_DEBUG_PORT") ?? "9222";
  try {
    const res = await fetch(`http://127.0.0.1:${port}/json/version`, { signal: AbortSignal.timeout(1000) });
    await res.body?.cancel();
    return true;
  } catch {
    return false;
  }
}

interface RunResult {
  code: number;
  output: string;
}

const HOUR = 3_600_000;

/** A wedged child would hold the run lock, and every later poll would skip, forever. */
async function task(log: Deno.FsFile, args: string[], timeoutMs: number): Promise<RunResult> {
  const enc = new TextEncoder();
  await log.write(enc.encode(`\n$ deno task ${args.join(" ")}   (${new Date().toISOString()})\n`));
  const child = new Deno.Command(Deno.execPath(), {
    args: ["task", ...args],
    cwd: REPO,
    stdin: "null",
    stdout: "piped",
    stderr: "piped",
  }).spawn();
  const timer = setTimeout(() => {
    log.writeSync(enc.encode(`[timed out after ${timeoutMs / 60_000} min; killing]\n`));
    child.kill("SIGTERM");
  }, timeoutMs);
  const pump = async (stream: ReadableStream<Uint8Array>) => {
    const dec = new TextDecoder();
    let text = "";
    for await (const chunk of stream) {
      await log.write(chunk);
      text += dec.decode(chunk, { stream: true });
    }
    return text;
  };
  const [out, err] = await Promise.all([pump(child.stdout), pump(child.stderr)]);
  const { code } = await child.status;
  clearTimeout(timer);
  await log.write(enc.encode(`[exit ${code}]\n`));
  return { code, output: `${out}\n${err}` };
}

type StageResult = [Outcome, number | null, string | null];

async function download(log: Deno.FsFile): Promise<StageResult> {
  if (await chromeBusy()) return ["retry", null, "Chrome debug port busy (a manual run?)"];
  const startedAt = new Date();
  const { code } = await task(log, ["py", "--sc-actions"], 3 * HOUR);
  const lastRun = await readJson<LastRun>(join(SC_LOGS, "last_run.json"));
  return [downloadOutcome(code, lastRun, startedAt), code, lastRun?.error ?? null];
}

async function rename(log: Deno.FsFile, state: NightlyState): Promise<StageResult> {
  const { code, output } = await task(log, ["rM", "--auto"], HOUR);
  state.renameManifest = lineAfter(output, "Manifest written:") ?? state.renameManifest;
  const applied = lineAfter(output, "Applied:");
  const claudeSkipped = lineWith(output, "claude second opinion skipped");
  const detail = [applied ? `applied ${applied}` : null, claudeSkipped].filter(Boolean).join("; ");
  return [renameOutcome(code, applied !== null), code, detail || null];
}

async function prune(log: Deno.FsFile): Promise<StageResult> {
  const { code } = await task(log, ["py", "--prune-playlist", "--apply"], HOUR / 4);
  return [code === 0 ? "done" : "failed", code, null];
}

async function tag(log: Deno.FsFile, state: NightlyState): Promise<StageResult> {
  let note = "";
  if (!state.tagManifest) {
    const embed = await task(log, ["rb:tag", "embed"], 4 * HOUR);
    if (!embedUsable(embed.code, lineAfter(embed.output, "failed now:") !== null)) {
      return ["failed", embed.code, "embed failed"];
    }
    if (embed.code === 1) note = " (some tracks failed to embed)";
    const suggest = await task(
      log,
      ["rb:tag", "suggest", "--new-tag-precision", "0.5", "--skip-applied"],
      HOUR / 2,
    );
    if (suggest.code !== 0) return ["failed", suggest.code, "suggest failed"];
    state.tagManifest = lineAfter(suggest.output, "manifest:");
    if (!state.tagManifest) return ["failed", 0, "suggest printed no manifest path"];
    await saveState(state);
  }
  const apply = await task(log, ["rb:tag", "apply", state.tagManifest, "--yes", "--db-keep", "7"], HOUR / 2);
  if (apply.code === TRY_LATER) return ["retry", apply.code, "waiting for Rekordbox to close"];
  if (apply.code !== 0) return ["failed", apply.code, "apply failed"];
  state.tagApplyLog = lineAfter(apply.output, "apply log (for tag undo):");
  return ["done", 0, `${lineWith(apply.output, " tags on ") ?? "applied"}${note}`];
}

async function holdingCount(): Promise<number> {
  let n = 0;
  try {
    for await (const e of Deno.readDir(join(SC_LOGS, "downloads"))) if (e.isFile && !e.name.startsWith(".")) n++;
  } catch (e) {
    if (!(e instanceof Deno.errors.NotFound)) throw e;
  }
  return n;
}

async function writeReport(state: NightlyState): Promise<string[]> {
  const lines = reportLines({
    state,
    lastRun: await readJson<LastRun>(join(SC_LOGS, "last_run.json")),
    lastPrune: await readJson<LastPrune>(join(SC_LOGS, "last_prune.json")),
    holding: await holdingCount(),
  });
  const files = [
    state.renameManifest && `rename manifest: ${state.renameManifest}`,
    state.tagApplyLog && `tag apply log (for rb:tag undo): ${state.tagApplyLog}`,
  ].filter(Boolean);
  await Deno.writeTextFile(
    join(LOG_DIR, `${state.date}.md`),
    `# Nightly ${state.date}\n\n${[...lines, ...files].map((l) => `- ${l}`).join("\n")}\n`,
  );
  return lines;
}

async function pruneOldLogs(): Promise<void> {
  const cutoff = Date.now() - KEEP_LOG_DAYS * 86_400_000;
  for await (const e of Deno.readDir(LOG_DIR)) {
    if (!/^\d{4}-\d{2}-\d{2}\.(log|md)$/.test(e.name)) continue;
    const path = join(LOG_DIR, e.name);
    if ((await Deno.stat(path)).mtime!.getTime() < cutoff) await Deno.remove(path);
  }
}

async function main(): Promise<void> {
  await Deno.mkdir(LOG_DIR, { recursive: true });
  try {
    await Deno.stat(join(LOG_DIR, "pause"));
    await gate("paused — remove logs/nightly/pause to resume");
  } catch (e) {
    if (!(e instanceof Deno.errors.NotFound)) throw e;
  }

  if (!force && Deno.build.os === "darwin" && onBattery(await capture("/usr/bin/pmset", ["-g", "batt"]))) {
    await gate("on battery");
  }

  const downloaded = Deno.env.get("TUNEWRANGLER_DOWNLOADED_PATH");
  if (!downloaded) throw new Error("TUNEWRANGLER_DOWNLOADED_PATH is not set");
  const problem = await driveProblem(downloaded);
  if (problem === "absent") await gate("drive not mounted");
  if (problem) throw new Error(problem);

  let release: () => Promise<void>;
  try {
    release = await acquireRunLock(join(LOG_DIR, "run.lock"));
  } catch (e) {
    if (e instanceof TryLaterError) await gate("another nightly run is in progress");
    throw e;
  }

  // Read under the lock: a run that just finished has saved its state by now.
  const previous = (await readJson<NightlyState>(STATE_FILE)) ?? undefined;
  // --force starts today over, as though the state were from another day.
  const state = freshState(today, force && previous ? { ...previous, date: "" } : previous);
  if (runnable(state).length === 0) {
    await release();
    await gate("today's run is finished");
  }

  // Holds the machine awake while this process lives; it can't wake a sleeping one.
  if (Deno.build.os === "darwin") {
    new Deno.Command("/usr/bin/caffeinate", { args: ["-s", "-i", "-m", "-w", String(Deno.pid)] }).spawn().unref();
  }

  const log = await Deno.open(join(LOG_DIR, `${today}.log`), { create: true, append: true });
  try {
    const stages: Record<StageName, () => Promise<StageResult>> = {
      download: () => download(log),
      rename: () => rename(log, state),
      prune: () => prune(log),
      tag: () => tag(log, state),
    };
    for (const name of STAGES) {
      if (!runnable(state).includes(name)) continue;
      let result: StageResult;
      try {
        result = await stages[name]();
      } catch (e) {
        result = ["failed", null, e instanceof Error ? e.message : String(e)];
      }
      state.stages[name] = settle(state.stages[name], ...result, MAX_DEFERRALS[name]);
      await saveState(state);
    }

    if (coreSettled(state)) {
      const lines = await writeReport(state);
      const title = notificationTitle(state);
      if (state.notified !== title && await notify(title, lines.join("\n"))) state.notified = title;
    }
    await saveState(state);
    await pruneOldLogs();
  } finally {
    log.close();
    await release();
  }
}

try {
  await main();
} catch (e) {
  const message = e instanceof Error ? e.message : String(e);
  console.error(message);
  const marker = join(LOG_DIR, "crash-notified");
  const last = await Deno.readTextFile(marker).catch(() => "");
  if (last.trim() !== today) {
    await notify("TuneWrangler nightly can't run", message);
    await Deno.writeTextFile(marker, today);
  }
  Deno.exit(1);
}
