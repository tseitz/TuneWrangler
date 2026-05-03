import { DownloadedSong } from "./models/Song.ts";

export type ConfidenceLevel = "high" | "medium" | "low";
export type Decision = "apply" | "review" | "skip";

export interface ConfidenceResult {
  level: ConfidenceLevel;
  reasons: string[];
  decision: Decision;
}

/**
 * Scores how confident we are that the parsed Song reflects what the user wants.
 *
 * "high"   → trivially clean: 1-2 dashes, all fields populated, no remix logic ran
 * "medium" → remix/feat detected, parse looks clean
 * "low"    → ambiguous structure (3+ dashes), empty fields, mangled output, or
 *            duplicated artist names that suggest a self-remix or parser confusion
 *
 * Default decisions: high+medium → apply, low → review.
 * The user can override any decision by editing the manifest before --apply.
 */
export function scoreConfidence(song: DownloadedSong, sourceFilename: string): ConfidenceResult {
  const reasons: string[] = [];
  let level: ConfidenceLevel = "high";

  // --- Hard signals: low confidence ---

  if (hasMangledExtension(song.finalFilename)) {
    reasons.push("finalFilename appears mangled (duplicate extension or extra characters past the first extension)");
    level = "low";
  }

  if (!song.artist.trim()) {
    reasons.push("artist field is empty after parsing");
    level = "low";
  }

  if (!song.title.trim()) {
    reasons.push("title field is empty after parsing");
    level = "low";
  }

  if (hasBareRemixTagInLastSegment(sourceFilename)) {
    reasons.push("last segment of source filename ends in a bare remix keyword (FLIP/EDIT/REMIX/etc.) — likely 'artist - title - remixer' structure rather than 'album - artist - title'");
    level = "low";
  }

  if (artistAppearsTwice(song)) {
    reasons.push("artist name appears in both artist and album fields (likely self-remix or parser confusion)");
    level = "low";
  }

  if (titleHasNonAscii(song.title) === false && sourceTitleHadNonAscii(sourceFilename) === true) {
    reasons.push("non-ASCII characters in source title were stripped entirely — title may have lost meaning");
    level = "low";
  }

  if (level === "low") {
    return { level, reasons, decision: "review" };
  }

  // --- Soft signals: medium confidence ---

  if (song.remix) {
    reasons.push("remix/edit/flip detected — parse depends on regex matching");
    level = "medium";
  }

  if (song.dashCount >= 2) {
    reasons.push(`source has ${song.dashCount} dash separators — assumed album-artist-title structure`);
    if (level === "high") level = "medium";
  }

  // --- Default ---

  if (level === "high" && reasons.length === 0) {
    reasons.push("clean parse, no transformations needed");
  }

  return {
    level,
    reasons,
    decision: "apply",
  };
}

const BARE_REMIX_KEYWORDS = ["FLIP", "EDIT", "REMIX", "REFIX", "BOOTLEG", "REBOOT", "DUB", "MIX", "VIP"];

function hasBareRemixTagInLastSegment(sourceFilename: string): boolean {
  const parts = sourceFilename.split(" - ");
  if (parts.length < 3) return false;
  const last = parts[parts.length - 1].toUpperCase();
  // Strip extension
  const lastClean = last.replace(/\.[A-Z0-9]{2,4}$/i, "").trim();
  // Match if the last segment ends with a bare remix keyword (no enclosing parens/brackets in that segment)
  if (/[()\[\]]/.test(lastClean)) return false;
  for (const kw of BARE_REMIX_KEYWORDS) {
    if (lastClean.endsWith(` ${kw}`) || lastClean === kw) return true;
  }
  return false;
}

function hasMangledExtension(finalFilename: string): boolean {
  // Match audio extensions only at token boundaries (followed by space, dash, dot, or end-of-string).
  // The lookahead prevents matching .aif inside .aiff. Case-sensitive matching means a band name
  // like "Hemi.Wav" with a real ".wav" extension doesn't false-positive.
  const matches = finalFilename.match(/\.(wav|mp3|aiff|aif|flac|m4a|ogg|opus)(?=[\s\-.]|$)/g);
  if (!matches || matches.length < 2) return false;

  const counts: Record<string, number> = {};
  for (const m of matches) counts[m] = (counts[m] ?? 0) + 1;
  return Object.values(counts).some((c) => c > 1);
}

function artistAppearsTwice(song: DownloadedSong): boolean {
  if (!song.artist || !song.album) return false;
  const a = song.artist.toUpperCase();
  const b = song.album.toUpperCase();
  if (a === b) return true;
  // Catch the "OVEREAZY x ROTO" / "OVEREAZY" case — artist is a superset of album, or vice-versa
  return a.includes(b) || b.includes(a);
}

function titleHasNonAscii(s: string): boolean {
  return /[^\x00-\x7F]/.test(s);
}

function sourceTitleHadNonAscii(sourceFilename: string): boolean {
  // The "title" portion is everything after the last " - "
  const lastDash = sourceFilename.lastIndexOf(" - ");
  if (lastDash === -1) return /[^\x00-\x7F]/.test(sourceFilename);
  return /[^\x00-\x7F]/.test(sourceFilename.slice(lastDash + 3));
}
