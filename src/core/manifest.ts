import { ConfidenceLevel, Decision } from "./confidence.ts";

/** Jev's advisory verdict on a manifest entry. Never upgrades a decision, only downgrades. */
export interface EntryJudgement {
  nouls: Record<string, number>;
  /** The proposed string actually graded. If it no longer matches entry.proposed, the user edited it since judging. */
  judged_proposed: string;
  model: string;
  judged_at: string;
  error?: string;
}

/** What SoundCloud reported for the file when soundcloud_dl downloaded it. */
export interface SoundcloudFacts {
  url: string;
  title: string | null;
  uploader: string | null;
  metadata_artist: string | null;
  label_name: string | null;
}

export interface ManifestEntry {
  src: string;
  /** What the user approved (may be edited from parser_output before --apply). */
  proposed: string;
  /** Immutable: what the parser originally produced. Never edited by the user. */
  parser_output: string;
  confidence: ConfidenceLevel;
  reasons: string[];
  decision: Decision;
  /** Set only when run with --judge. Absent means the entry was never judged. */
  judgement?: EntryJudgement;
  /** Absent for any file soundcloud_dl did not download. */
  soundcloud?: SoundcloudFacts;
}

export interface Manifest {
  version: 1;
  generated_at: string;
  source_dir: string;
  move_dir: string;
  cache_dir: string;
  entries: ManifestEntry[];
}

const VALID_CONFIDENCE: ConfidenceLevel[] = ["high", "medium", "low"];
const VALID_DECISION: Decision[] = ["apply", "review", "skip"];

export async function writeManifest(path: string, manifest: Manifest): Promise<void> {
  await Deno.writeTextFile(path, JSON.stringify(manifest, null, 2));
}

export async function readManifest(path: string): Promise<Manifest> {
  const text = await Deno.readTextFile(path);
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch (e) {
    throw new Error(`Failed to parse manifest JSON at ${path}: ${(e as Error).message}`);
  }
  return validateManifest(raw, path);
}

function validateManifest(raw: unknown, path: string): Manifest {
  if (!raw || typeof raw !== "object") {
    throw new Error(`Manifest at ${path} must be a JSON object`);
  }
  const obj = raw as Record<string, unknown>;

  if (!Array.isArray(obj.entries)) {
    throw new Error(`Manifest at ${path} is missing 'entries' array`);
  }

  for (const [i, entry] of obj.entries.entries()) {
    validateEntry(entry, i, path);
  }

  return {
    version: 1,
    generated_at: typeof obj.generated_at === "string" ? obj.generated_at : "",
    source_dir: typeof obj.source_dir === "string" ? obj.source_dir : "",
    move_dir: typeof obj.move_dir === "string" ? obj.move_dir : "",
    cache_dir: typeof obj.cache_dir === "string" ? obj.cache_dir : "",
    entries: obj.entries as ManifestEntry[],
  };
}

function validateEntry(entry: unknown, index: number, path: string): void {
  if (!entry || typeof entry !== "object") {
    throw new Error(`Manifest entry ${index} at ${path} must be an object`);
  }
  const e = entry as Record<string, unknown>;

  if (typeof e.src !== "string" || typeof e.proposed !== "string") {
    throw new Error(`Manifest entry ${index} at ${path} requires string src and proposed`);
  }
  // parser_output was added in a later version; default to proposed for older manifests
  if (e.parser_output !== undefined && typeof e.parser_output !== "string") {
    throw new Error(`Manifest entry ${index} at ${path} has invalid parser_output (must be a string)`);
  }
  if (e.parser_output === undefined) {
    e.parser_output = e.proposed;
  }
  if (typeof e.confidence !== "string" || !VALID_CONFIDENCE.includes(e.confidence as ConfidenceLevel)) {
    throw new Error(
      `Manifest entry ${index} at ${path} has invalid confidence "${e.confidence}" (must be one of: ${VALID_CONFIDENCE.join(", ")})`
    );
  }
  if (typeof e.decision !== "string" || !VALID_DECISION.includes(e.decision as Decision)) {
    throw new Error(
      `Manifest entry ${index} at ${path} has invalid decision "${e.decision}" (must be one of: ${VALID_DECISION.join(", ")})`
    );
  }
  if (!Array.isArray(e.reasons)) {
    throw new Error(`Manifest entry ${index} at ${path} requires 'reasons' array`);
  }
  if (e.judgement !== undefined) {
    validateJudgement(e.judgement, index, path);
  }
  if (e.soundcloud !== undefined && !isSoundcloudFacts(e.soundcloud)) {
    throw new Error(`Manifest entry ${index} at ${path} has invalid soundcloud (needs a string url; other fields string or null)`);
  }
}

const OPTIONAL_FACTS = ["title", "uploader", "metadata_artist", "label_name"] as const;

export function isSoundcloudFacts(value: unknown): value is SoundcloudFacts {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const v = value as Record<string, unknown>;
  return typeof v.url === "string" &&
    OPTIONAL_FACTS.every((key) => v[key] === null || typeof v[key] === "string");
}

function validateJudgement(judgement: unknown, index: number, path: string): void {
  if (!judgement || typeof judgement !== "object") {
    throw new Error(`Manifest entry ${index} at ${path} has invalid judgement (must be an object)`);
  }
  const j = judgement as Record<string, unknown>;

  if (!j.nouls || typeof j.nouls !== "object" || Array.isArray(j.nouls)) {
    throw new Error(`Manifest entry ${index} at ${path} has invalid judgement.nouls (must be an object)`);
  }
  for (const value of Object.values(j.nouls as Record<string, unknown>)) {
    if (typeof value !== "number") {
      throw new Error(`Manifest entry ${index} at ${path} has a non-numeric judgement.nouls value`);
    }
  }
  if (typeof j.judged_proposed !== "string") {
    throw new Error(`Manifest entry ${index} at ${path} has invalid judgement.judged_proposed (must be a string)`);
  }
  if (typeof j.model !== "string") {
    throw new Error(`Manifest entry ${index} at ${path} has invalid judgement.model (must be a string)`);
  }
  if (typeof j.judged_at !== "string") {
    throw new Error(`Manifest entry ${index} at ${path} has invalid judgement.judged_at (must be a string)`);
  }
  if (j.error !== undefined && typeof j.error !== "string") {
    throw new Error(`Manifest entry ${index} at ${path} has invalid judgement.error (must be a string)`);
  }
}
