import { extname } from "@std/path";

import { isSoundcloudFacts, ManifestEntry, SoundcloudFacts } from "./manifest.ts";
import { foldName } from "./utils/unicode.ts";

export const SOUNDCLOUD_INDEX_PATH = "./logs/soundcloud_dl/track_index.json";

/** SoundCloud's credits separate names every way it can: `,` `&` ` x ` `|`. */
const CREDIT_SEPARATOR = /\s*(?:,|&|\||\s+x\s+)\s*/i;
const MIN_NAME = 3;

export type SoundcloudIndex = Map<string, SoundcloudFacts>;

/** The index soundcloud_dl writes as it downloads. No file yet means nothing was recorded. */
export async function loadSoundcloudIndex(path = SOUNDCLOUD_INDEX_PATH): Promise<SoundcloudIndex> {
  let raw: string;
  try {
    raw = await Deno.readTextFile(path);
  } catch (error) {
    if (error instanceof Deno.errors.NotFound) return new Map();
    throw error;
  }
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch (error) {
    throw new Error(`SoundCloud track index at ${path} is not valid JSON: ${error}`);
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error(`SoundCloud track index at ${path} must be an object keyed by filename`);
  }
  const index: SoundcloudIndex = new Map();
  for (const [name, facts] of Object.entries(data)) {
    if (isSoundcloudFacts(facts)) index.set(name.normalize("NFC"), facts);
  }
  return index;
}

/** Looks a file up by its name without the extension, the key soundcloud_dl saved it under. */
export function factsFor(index: SoundcloudIndex, src: string): SoundcloudFacts | undefined {
  const stem = src.slice(0, src.length - extname(src).length);
  return index.get(stem.normalize("NFC"));
}

/** Names SoundCloud credits that the proposed filename leaves out. The uploader is not
 * counted: a label posting someone else's track is rightly dropped from the name. */
export function missingCredits(facts: SoundcloudFacts, proposed: string): string[] {
  if (!facts.metadata_artist) return [];
  const have = foldName(proposed);
  const uploader = foldName(facts.uploader ?? "");
  const missing: string[] = [];
  const seen = new Set<string>();
  for (const name of facts.metadata_artist.split(CREDIT_SEPARATOR)) {
    const folded = foldName(name);
    if (folded.length < MIN_NAME || folded === uploader || seen.has(folded)) continue;
    seen.add(folded);
    // Word by word too: "statiq. niko" is credited as one name and filed as "statiq. x niko".
    // A short word ("Jay Z") matches too much by accident to count on its own.
    const words = name.split(/\s+/).map(foldName).filter(Boolean);
    const wordsPresent = words.every((word) => word.length >= MIN_NAME && have.includes(word));
    if (!have.includes(folded) && !wordsPresent) missing.push(name.trim());
  }
  return missing;
}

/** Attaches the facts, and sends an entry to review when its name drops a credited artist.
 * Never raises a decision: skip and review stay as they are. */
export function applySoundcloudCredits(entry: ManifestEntry, facts: SoundcloudFacts): ManifestEntry {
  const missing = missingCredits(facts, entry.proposed);
  if (missing.length === 0) return { ...entry, soundcloud: facts };
  return {
    ...entry,
    soundcloud: facts,
    reasons: [...entry.reasons, ...missing.map((name) => `soundcloud credits ${name}, missing from the name`)],
    decision: entry.decision === "apply" ? "review" : entry.decision,
  };
}
