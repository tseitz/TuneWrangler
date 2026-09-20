import type { TypeSafeClient as TypeSafeClientClass } from "@typesafe-ai/sdk";
import { ConfigurationError } from "./utils/errors.ts";
import { EntryJudgement, ManifestEntry } from "./manifest.ts";
import { DownloadedSong } from "./models/Song.ts";

export interface JudgeCandidate {
  entry: ManifestEntry;
  song: DownloadedSong;
}

const DEFAULT_THRESHOLD = 0.5;
const DEFAULT_CONCURRENCY = 8;

// The parser drops these tokens on purpose. Without naming them, nothing_lost fires on most
// of a batch and the feature gets switched off after one run.
const NOTHING_LOST_CARVE_OUTS = [
  '"free download" is stripped entirely',
  '"featuring" is normalized to "feat."',
  "everything from a remix/refix/flip/edit/bootleg/reboot/dub bracket onward is truncated out " +
    "of the title into a separate remix credit",
  '"- Single" / "- EP" suffixes and commas are removed',
  '"&" is normalized to "x"',
].join("; ");

let clientPromise: Promise<TypeSafeClientClass> | undefined;

async function getClient(): Promise<TypeSafeClientClass> {
  if (!clientPromise) {
    clientPromise = (async () => {
      const { TypeSafeClient } = await import("@typesafe-ai/sdk");
      return new TypeSafeClient();
    })();
  }
  return clientPromise;
}

/**
 * Validates TYPESAFE_API_KEY is usable by constructing the client. Call this before any IO
 * when --judge is set, so a missing key fails in the first second instead of after parsing
 * the whole downloads directory.
 */
export async function assertJudgeAvailable(): Promise<void> {
  try {
    await getClient();
  } catch (error) {
    throw new ConfigurationError(
      `--judge requires a usable TYPESAFE_API_KEY: ${error instanceof Error ? error.message : String(error)}`,
      "TYPESAFE_API_KEY",
    );
  }
}

export function getJudgeThreshold(): number {
  const raw = Deno.env.get("TUNEWRANGLER_JUDGE_THRESHOLD");
  const parsed = raw ? parseFloat(raw) : NaN;
  return Number.isFinite(parsed) ? parsed : DEFAULT_THRESHOLD;
}

function getJudgeConcurrency(): number {
  const raw = Deno.env.get("TUNEWRANGLER_JUDGE_CONCURRENCY");
  const parsed = raw ? parseInt(raw, 10) : NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_CONCURRENCY;
}

async function judgeOne(client: TypeSafeClientClass, candidate: JudgeCandidate): Promise<EntryJudgement> {
  const { noul } = await import("@typesafe-ai/sdk");
  const { song, entry } = candidate;

  const response = await client.systemOne({
    state: {
      source_filename: entry.src,
      proposed: {
        artist: song.artist,
        album: song.album,
        title: song.title,
        remix: song.remix,
      },
    },
    questions: {
      nothing_lost: noul(
        "Every meaningful token in `source_filename` survived into one of the fields in `proposed`. " +
          `The parser deliberately drops some tokens and this should NOT count as lost: ${NOTHING_LOST_CARVE_OUTS}.`,
      ),
      title_is_a_title: noul(
        "`proposed.title` is the track's own name — no leftover catalogue numbers, artist names, or file cruft.",
      ),
      fields_not_swapped: noul(
        "`proposed.artist` and `proposed.album` each hold what their field name says, rather than each other's content.",
      ),
    },
  });

  return {
    nouls: {
      nothing_lost: response.answers.nothing_lost.noul,
      title_is_a_title: response.answers.title_is_a_title.noul,
      fields_not_swapped: response.answers.fields_not_swapped.noul,
    },
    judged_proposed: entry.proposed,
    model: response.model,
    judged_at: new Date().toISOString(),
  };
}

/** Judges each candidate, keyed by entry.src. A failed request records a fail-closed error entry rather than a pass. */
export async function judgeEntries(candidates: JudgeCandidate[]): Promise<Map<string, EntryJudgement>> {
  const client = await getClient();
  const concurrency = Math.min(getJudgeConcurrency(), candidates.length) || 1;
  const results = new Map<string, EntryJudgement>();

  let next = 0;
  async function worker(): Promise<void> {
    while (next < candidates.length) {
      const candidate = candidates[next++];
      try {
        results.set(candidate.entry.src, await judgeOne(client, candidate));
      } catch (error) {
        results.set(candidate.entry.src, {
          nouls: {},
          judged_proposed: candidate.entry.proposed,
          model: "",
          judged_at: new Date().toISOString(),
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
  }

  await Promise.all(Array.from({ length: concurrency }, worker));
  return results;
}

/**
 * Pure fold from a judgement onto an entry. Downgrade-only: the returned decision is either
 * unchanged or "review" — never "apply". A missing judgement (undefined) is a failure verdict,
 * not a pass, so a silently dropped entry still ends up needing review.
 */
export function applyJudgement(
  entry: ManifestEntry,
  judgement: EntryJudgement | undefined,
  threshold: number,
): ManifestEntry {
  if (!judgement) {
    return {
      ...entry,
      decision: "review",
      reasons: [...entry.reasons, "jev: could not be judged (no result recorded)"],
      judgement: {
        nouls: {},
        judged_proposed: entry.proposed,
        model: "",
        judged_at: new Date().toISOString(),
        error: "no judgement recorded for this entry",
      },
    };
  }

  if (judgement.error) {
    return {
      ...entry,
      decision: "review",
      reasons: [...entry.reasons, `jev: could not be judged (${judgement.error})`],
      judgement,
    };
  }

  const failed = Object.entries(judgement.nouls).filter(([, probability]) => probability < threshold);
  if (failed.length === 0) {
    return { ...entry, judgement };
  }

  const reasons = failed.map(([key, probability]) => `jev: ${key}=${probability.toFixed(2)} below threshold ${threshold}`);
  return {
    ...entry,
    decision: "review",
    reasons: [...entry.reasons, ...reasons],
    judgement,
  };
}
