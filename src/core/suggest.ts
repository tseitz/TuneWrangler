import { extname } from "@std/path";
import type { EntryTags, ManifestEntry, Source } from "./manifest.ts";
import { normalizeFilename, normalizeUnicode } from "./utils/unicode.ts";
import { missingCredits } from "./soundcloudFacts.ts";
import { NAMES_WITH_AMPERSAND } from "../config/artistNames.ts";

export const EXAMPLES_PATH = new URL("./suggest-examples.txt", import.meta.url);

const DEFAULT_MODEL = "sonnet";
const DEFAULT_BATCH = 25;
const DEFAULT_MAX_USD = 0.25;
/** A nightly run holds the rename lock; a stalled call must not hold it forever. */
const CALL_TIMEOUT_MS = 180_000;
const AUTH_TIMEOUT_MS = 30_000;

const SYSTEM_PROMPT =
  "You name DJ music files to one owner's exact convention. Reply only through the structured output.";

export interface SuggestInput {
  source: Source;
  /** File name only, no folders. */
  filename: string;
  tags?: EntryTags;
  /** Who SoundCloud credits, for a file soundcloud_dl downloaded. */
  credits?: string;
  parserName: string;
}

export interface SuggestOutput {
  index: number;
  /** Without extension. */
  name: string;
  confident: boolean;
  why: string;
}

export interface ClaudeResult {
  outputs: SuggestOutput[];
  costUsd: number;
  model: string;
  error?: string;
}

export type ClaudeRunner = (prompt: string, schema: object) => Promise<ClaudeResult>;

export const SUGGEST_SCHEMA = {
  type: "object",
  properties: {
    names: {
      type: "array",
      items: {
        type: "object",
        properties: {
          index: { type: "integer" },
          name: { type: "string" },
          confident: { type: "boolean" },
          why: { type: "string" },
        },
        required: ["index", "name", "confident", "why"],
      },
    },
  },
  required: ["names"],
};

export function getSuggestModel(): string {
  return Deno.env.get("TUNEWRANGLER_SUGGEST_MODEL")?.trim() || DEFAULT_MODEL;
}

export function getSuggestBatch(): number {
  const parsed = parseInt(Deno.env.get("TUNEWRANGLER_SUGGEST_BATCH") ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_BATCH;
}

export function getSuggestMaxUsd(): number {
  const parsed = parseFloat(Deno.env.get("TUNEWRANGLER_SUGGEST_MAX_USD") ?? "");
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_MAX_USD;
}

export function buildPrompt(examples: string, inputs: SuggestInput[]): string {
  const lines = inputs.map((input, index) => {
    const tags = input.tags
      ? `\ttags: artist="${input.tags.artist}" album="${input.tags.album}" title="${input.tags.title}"`
      : "";
    const credits = input.credits ? `\tsoundcloud credits: ${input.credits}` : "";
    return `${index}\t${input.source}\t${input.filename}\tparser: ${input.parserName}${tags}${credits}`;
  });
  return [
    "Name each music file below to the owner's convention, shown by these rules and examples.",
    "",
    examples.trim(),
    `- These act names contain "&" and stay whole: ${NAMES_WITH_AMPERSAND.join("; ")}.`,
    "",
    "# Files",
    "Each line: index, where it was downloaded from, its file name, the name a regex parser proposed,",
    "and for iTunes/Beatport the file's tags (more reliable than the file name there).",
    "SoundCloud credits list every artist on the track; a credited artist missing from the name",
    "belongs in it (the uploader alone may be a label).",
    "The parser is usually right; change its name only where it breaks the convention.",
    "Return the name without a file extension. Set confident=false when the file name doesn't",
    "say which part is the artist, album or title. Keep `why` to one short sentence.",
    "",
    ...lines,
  ].join("\n");
}

function childEnv(): Record<string, string> {
  const env: Record<string, string> = {};
  for (const key of ["HOME", "PATH", "USER", "LOGNAME", "TMPDIR", "LANG", "SHELL"]) {
    const value = Deno.env.get(key);
    if (value !== undefined) env[key] = value;
  }
  return env;
}

/** Where the claude binary is: launchd's PATH lacks ~/.local/bin, so look there too. */
export async function resolveClaudeBin(): Promise<string | undefined> {
  const configured = Deno.env.get("TUNEWRANGLER_CLAUDE_BIN")?.trim();
  const home = Deno.env.get("HOME") ?? "";
  for (const candidate of [configured, "claude", `${home}/.local/bin/claude`]) {
    if (!candidate) continue;
    try {
      const out = await new Deno.Command(candidate, { args: ["--version"], stdout: "null", stderr: "null" })
        .output();
      if (out.success) return candidate;
    } catch (error) {
      if (!(error instanceof Deno.errors.NotFound)) throw error;
    }
  }
  return undefined;
}

/** Why claude can't be used right now, or undefined when it can. Never throws. */
export async function claudeUnavailable(bin: string | undefined): Promise<string | undefined> {
  if (!bin) return "claude CLI not found (set TUNEWRANGLER_CLAUDE_BIN)";
  try {
    const out = await new Deno.Command(bin, {
      args: ["auth", "status"],
      clearEnv: true,
      env: childEnv(),
      stderr: "piped",
      signal: AbortSignal.timeout(AUTH_TIMEOUT_MS),
    }).output();
    const status = JSON.parse(new TextDecoder().decode(out.stdout));
    return status.loggedIn === true ? undefined : "claude CLI is not logged in (run `claude auth login`)";
  } catch (error) {
    return error instanceof SyntaxError ? "could not read `claude auth status` output" : `could not check claude login: ${error}`;
  }
}

/** None of the user's setup may load (empty folder, safe mode, no settings/tools/MCP): it multiplies the cost. */
export function claudeRunner(bin: string, model: string, maxUsd: number): ClaudeRunner {
  return async (prompt, schema) => {
    const cwd = await Deno.makeTempDir({ prefix: "tw-suggest-" });
    try {
      const child = new Deno.Command(bin, {
        args: [
          "-p",
          "--safe-mode",
          "--model", model,
          "--tools", "",
          "--setting-sources", "",
          "--strict-mcp-config",
          "--system-prompt", SYSTEM_PROMPT,
          "--no-session-persistence",
          "--output-format", "json",
          "--json-schema", JSON.stringify(schema),
          "--max-budget-usd", String(maxUsd),
        ],
        cwd,
        // An ANTHROPIC_API_KEY in .env would bill the API instead of the logged-in subscription.
        clearEnv: true,
        env: childEnv(),
        signal: AbortSignal.timeout(CALL_TIMEOUT_MS),
        stdin: "piped",
        stdout: "piped",
        stderr: "piped",
      }).spawn();
      const writer = child.stdin.getWriter();
      try {
        await writer.write(new TextEncoder().encode(prompt));
        await writer.close();
      } catch (error) {
        child.kill();
        await child.output().catch(() => undefined);
        return { outputs: [], costUsd: 0, model, error: `could not send the prompt: ${error instanceof Error ? error.message : error}` };
      }
      const out = await child.output();
      return parseClaudeOutput(new TextDecoder().decode(out.stdout), new TextDecoder().decode(out.stderr), model);
    } finally {
      await Deno.remove(cwd, { recursive: true }).catch((error) => console.error(`Could not remove ${cwd}: ${error}`));
    }
  };
}

/** Reads stdout even for a failed call: it still reports what the call cost. */
export function parseClaudeOutput(stdout: string, stderr: string, model: string): ClaudeResult {
  let json: Record<string, unknown>;
  try {
    json = JSON.parse(stdout);
  } catch {
    return { outputs: [], costUsd: 0, model, error: `claude printed no JSON: ${(stderr || stdout).trim().slice(0, 300)}` };
  }
  const costUsd = typeof json.total_cost_usd === "number" ? json.total_cost_usd : 0;
  const names = (json.structured_output as { names?: unknown } | undefined)?.names;
  if (json.is_error || json.subtype !== "success" || !Array.isArray(names)) {
    return { outputs: [], costUsd, model, error: `claude call failed: ${json.subtype ?? "no structured output"}` };
  }
  const outputs = names.filter((n): n is SuggestOutput =>
    !!n && typeof n === "object" && Number.isInteger((n as SuggestOutput).index) &&
    typeof (n as SuggestOutput).name === "string" && typeof (n as SuggestOutput).confident === "boolean" &&
    typeof (n as SuggestOutput).why === "string"
  );
  return { outputs, costUsd, model };
}

export interface BatchResult {
  /** Same length and order as the inputs; undefined where claude returned nothing usable. */
  outputs: (SuggestOutput | undefined)[];
  errors: (string | undefined)[];
  costUsd: number;
}

/** One call per batch, in order. Stops calling once the run's spend reaches `runMaxUsd`. */
export async function suggestNames(
  inputs: SuggestInput[],
  { run, examples, batchSize, perCallMaxUsd, runMaxUsd }: {
    run: ClaudeRunner;
    examples: string;
    batchSize: number;
    perCallMaxUsd: number;
    runMaxUsd: number;
  },
): Promise<BatchResult> {
  const outputs: (SuggestOutput | undefined)[] = new Array(inputs.length).fill(undefined);
  const errors: (string | undefined)[] = new Array(inputs.length).fill(undefined);
  let costUsd = 0;

  for (let start = 0; start < inputs.length; start += batchSize) {
    const batch = inputs.slice(start, start + batchSize);
    if (costUsd + perCallMaxUsd > runMaxUsd) {
      batch.forEach((_, i) => errors[start + i] = `run budget of $${runMaxUsd} spent`);
      continue;
    }
    let result: ClaudeResult;
    try {
      result = await run(buildPrompt(examples, batch), SUGGEST_SCHEMA);
    } catch (error) {
      result = { outputs: [], costUsd: 0, model: "", error: `claude call threw: ${error instanceof Error ? error.message : error}` };
    }
    // A call that reported no cost may still have spent up to its cap.
    costUsd += result.error && result.costUsd === 0 ? perCallMaxUsd : result.costUsd;
    const byIndex = new Map(result.outputs.map((o) => [o.index, o]));
    batch.forEach((_, i) => {
      const output = byIndex.get(i);
      if (output) outputs[start + i] = output;
      else errors[start + i] = result.error ?? "claude returned no name for this file";
    });
  }
  return { outputs, errors, costUsd };
}

/** Equal once the differences the user doesn't care about are folded away (extension, case, accents, joins). */
export function sameName(a: string, b: string): boolean {
  return foldForCompare(a) === foldForCompare(b);
}

function foldForCompare(name: string): string {
  const stem = /\.(mp3|wav|aiff?|flac|m4a|ogg|opus|alac)$/i.test(name) ? name.slice(0, name.lastIndexOf(".")) : name;
  return normalizeUnicode(stem.normalize("NFC"))
    .toLowerCase()
    .replace(/\s*(?:&|,|\bfeat\.?|\bft\.?|\band\b|\+)\s*/g, " x ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Why a name claude returned can't be used as a file name, or undefined when it can. */
export function unsafeName(stem: string): string | undefined {
  if (!stem.trim()) return "empty name";
  if (/[/\\\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]/.test(stem)) {
    return "name has a slash, a control or an invisible character";
  }
  if (stem.trim().startsWith(".")) return "name starts with a dot";
  // The move writes a temp file with a ~40-byte prefix; APFS stops at 255 bytes.
  if (new TextEncoder().encode(stem).length > 200) return "name is too long";
  if (AUDIO_EXTENSION.test(stem.replace(AUDIO_EXTENSION, ""))) return "name has a doubled extension";
  return undefined;
}

const AUDIO_EXTENSION = /\.(mp3|wav|aiff?|flac|m4a|ogg|opus)$/i;

/** Parser downgrades claude may not overrule: an opt-in Jev verdict, a SoundCloud credit check. */
function heldForReview(entry: ManifestEntry, name: string): boolean {
  if (entry.reasons.some((r) => r.startsWith("jev:"))) return true;
  return !!entry.soundcloud && missingCredits(entry.soundcloud, name).length > 0;
}

/**
 * Folds claude's answer onto an entry. Claude decides when it disagrees and is confident: its
 * name becomes `proposed` (the parser's stays in `parser_output`, which the corpus counts as a
 * parser bug to fix). Agreeing or confident renaming settles a parser `review` as `apply`. An
 * unsure answer or a failure leaves the parser's name and decision as they were.
 */
/**
 * True when `name` has a word that isn't in the file's own name, tags or credits. Claude may only
 * reorder, drop or clean up what's there; a new word is either a guess or text a file name injected.
 */
export function inventsWords(name: string, sourceText: string): boolean {
  const have = new Set(words(sourceText));
  return words(name).some((word) => !have.has(word));
}

function words(text: string): string[] {
  return normalizeUnicode(text.normalize("NFC")).toLowerCase().replace(AUDIO_EXTENSION, "")
    .split(/[^\p{L}\p{N}]+/u).filter((w) => w && w !== "x");
}

export function applySuggestion(
  entry: ManifestEntry,
  output: SuggestOutput | undefined,
  error: string | undefined,
  model: string,
  sourceText: string,
): ManifestEntry {
  const parser_name = entry.proposed;
  const failed = (message: string, extra = {}): ManifestEntry => ({
    ...entry,
    reasons: [...entry.reasons, `claude: could not suggest (${message})`],
    suggestion: { ...extra, outcome: "failed", parser_name, model, error: message },
  });
  if (!output) return failed(error ?? "no answer");

  const base = { confident: output.confident, why: output.why };
  const raw = output.name.normalize("NFC").replace(/\s+/g, " ").trim().replace(AUDIO_EXTENSION, "");
  const unsafe = unsafeName(output.name) ?? unsafeName(raw);
  if (unsafe) return failed(`${unsafe}: "${output.name}"`, base);

  const sameAsParser = sameName(raw, parser_name);
  const parts = raw.split(" - ").length;
  const odd = !sameAsParser && (parts < 2 || parts > 3 || inventsWords(raw, `${sourceText} ${parser_name}`));
  if (!output.confident || odd) {
    const said = sameAsParser ? "unsure too" : `unsure, suggested "${raw}" — kept the parser's name`;
    return {
      ...entry,
      reasons: [...entry.reasons, `claude: ${said}`],
      suggestion: { ...base, outcome: "unsure", parser_name, model, name: `${raw}${extname(parser_name)}` },
    };
  }

  // The same cleanup the parser's names get: ASCII letters, no characters a file system rejects.
  const name = sameAsParser ? parser_name : `${normalizeFilename(raw)}${extname(parser_name)}`;
  const decision = entry.decision === "review" && !heldForReview(entry, name) ? "apply" : entry.decision;
  const suggestion = { ...base, parser_name, model, name };
  if (sameAsParser) {
    return { ...entry, decision, reasons: [...entry.reasons, "claude: agrees"], suggestion: { ...suggestion, outcome: "agreed" } };
  }
  return {
    ...entry,
    proposed: name,
    decision,
    reasons: [...entry.reasons, `claude: renamed from "${parser_name}" — ${output.why}`],
    suggestion: { ...suggestion, outcome: "renamed" },
  };
}
