import { ConfidenceLevel, Decision } from "./confidence.ts";

export interface ManifestEntry {
  src: string;
  proposed: string;
  confidence: ConfidenceLevel;
  reasons: string[];
  decision: Decision;
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
}
