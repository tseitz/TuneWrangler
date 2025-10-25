/**
 * Unicode normalization utilities for converting accented and special characters
 * to their closest ASCII equivalents while preserving case.
 */

/**
 * Comprehensive mapping of Unicode characters to their ASCII equivalents.
 * This includes common accented characters, special symbols, and other Unicode variants.
 */
const UNICODE_MAP: Record<string, string> = {
  // Latin Extended-A
  À: "A",
  Á: "A",
  Â: "A",
  Ã: "A",
  Ä: "A",
  Å: "A",
  Æ: "AE",
  Ç: "C",
  È: "E",
  É: "E",
  Ê: "E",
  Ë: "E",
  Ì: "I",
  Í: "I",
  Î: "I",
  Ï: "I",
  Ð: "D",
  Ñ: "N",
  Ò: "O",
  Ó: "O",
  Ô: "O",
  Õ: "O",
  Ö: "O",
  Ø: "O",
  Ù: "U",
  Ú: "U",
  Û: "U",
  Ü: "U",
  Ý: "Y",
  Þ: "TH",
  ß: "ss",

  à: "a",
  á: "a",
  â: "a",
  ã: "a",
  ä: "a",
  å: "a",
  æ: "ae",
  ç: "c",
  è: "e",
  é: "e",
  ê: "e",
  ë: "e",
  ì: "i",
  í: "i",
  î: "i",
  ï: "i",
  ð: "d",
  ñ: "n",
  ò: "o",
  ó: "o",
  ô: "o",
  õ: "o",
  ö: "o",
  ø: "o",
  ù: "u",
  ú: "u",
  û: "u",
  ü: "u",
  ý: "y",
  þ: "th",
  ÿ: "y",

  // Latin Extended-B
  Ā: "A",
  ā: "a",
  Ă: "A",
  ă: "a",
  Ą: "A",
  ą: "a",
  Ć: "C",
  ć: "c",
  Ĉ: "C",
  ĉ: "c",
  Ċ: "C",
  ċ: "c",
  Č: "C",
  č: "c",
  Ď: "D",
  ď: "d",
  Đ: "D",
  đ: "d",
  Ē: "E",
  ē: "e",
  Ĕ: "E",
  ĕ: "e",
  Ė: "E",
  ė: "e",
  Ę: "E",
  ę: "e",
  Ě: "E",
  ě: "e",
  Ĝ: "G",
  ĝ: "g",
  Ğ: "G",
  ğ: "g",
  Ġ: "G",
  ġ: "g",
  Ģ: "G",
  ģ: "g",
  Ĥ: "H",
  ĥ: "h",
  Ħ: "H",
  ħ: "h",
  Ĩ: "I",
  ĩ: "i",
  Ī: "I",
  ī: "i",
  Ĭ: "I",
  ĭ: "i",
  Į: "I",
  į: "i",
  İ: "I",
  ı: "i",
  Ĵ: "J",
  ĵ: "j",
  Ķ: "K",
  ķ: "k",
  ĸ: "k",
  Ĺ: "L",
  ĺ: "l",
  Ļ: "L",
  ļ: "l",
  Ľ: "L",
  ľ: "l",
  Ŀ: "L",
  ŀ: "l",
  Ł: "L",
  ł: "l",
  Ń: "N",
  ń: "n",
  Ņ: "N",
  ņ: "n",
  Ň: "N",
  ň: "n",
  ŉ: "n",
  Ŋ: "N",
  ŋ: "n",
  Ō: "O",
  ō: "o",
  Ŏ: "O",
  ŏ: "o",
  Ő: "O",
  ő: "o",
  Œ: "OE",
  œ: "oe",
  Ŕ: "R",
  ŕ: "r",
  Ŗ: "R",
  ŗ: "r",
  Ř: "R",
  ř: "r",
  Ś: "S",
  ś: "s",
  Ŝ: "S",
  ŝ: "s",
  Ş: "S",
  ş: "s",
  Š: "S",
  š: "s",
  Ţ: "T",
  ţ: "t",
  Ť: "T",
  ť: "t",
  Ŧ: "T",
  ŧ: "t",
  Ũ: "U",
  ũ: "u",
  Ū: "U",
  ū: "u",
  Ŭ: "U",
  ŭ: "u",
  Ů: "U",
  ů: "u",
  Ű: "U",
  ű: "u",
  Ų: "U",
  ų: "u",
  Ŵ: "W",
  ŵ: "w",
  Ŷ: "Y",
  ŷ: "y",
  Ÿ: "Y",
  Ź: "Z",
  ź: "z",
  Ż: "Z",
  ż: "z",
  Ž: "Z",
  ž: "z",

  // Greek letters commonly used in music
  Α: "A",
  Β: "B",
  Γ: "G",
  Δ: "D",
  Ε: "E",
  Ζ: "Z",
  Η: "H",
  Θ: "TH",
  Ι: "I",
  Κ: "K",
  Λ: "L",
  Μ: "M",
  Ν: "N",
  Ξ: "X",
  Ο: "O",
  Π: "P",
  Ρ: "R",
  Σ: "S",
  Τ: "T",
  Υ: "Y",
  Φ: "F",
  Χ: "CH",
  Ψ: "PS",
  Ω: "O",

  α: "a",
  β: "b",
  γ: "g",
  δ: "d",
  ε: "e",
  ζ: "z",
  η: "h",
  θ: "th",
  ι: "i",
  κ: "k",
  λ: "l",
  μ: "m",
  ν: "n",
  ξ: "x",
  ο: "o",
  π: "p",
  ρ: "r",
  σ: "s",
  ς: "s",
  τ: "t",
  υ: "y",
  φ: "f",
  χ: "ch",
  ψ: "ps",
  ω: "o",

  // Cyrillic (common ones)
  А: "A",
  Б: "B",
  В: "V",
  Г: "G",
  Д: "D",
  Е: "E",
  Ё: "YO",
  Ж: "ZH",
  З: "Z",
  И: "I",
  Й: "Y",
  К: "K",
  Л: "L",
  М: "M",
  Н: "N",
  О: "O",
  П: "P",
  Р: "R",
  С: "S",
  Т: "T",
  У: "U",
  Ф: "F",
  Х: "KH",
  Ц: "TS",
  Ч: "CH",
  Ш: "SH",
  Щ: "SCH",
  Ъ: "",
  Ы: "Y",
  Ь: "",
  Э: "E",
  Ю: "YU",
  Я: "YA",

  а: "a",
  б: "b",
  в: "v",
  г: "g",
  д: "d",
  е: "e",
  ё: "yo",
  ж: "zh",
  з: "z",
  и: "i",
  й: "y",
  к: "k",
  л: "l",
  м: "m",
  н: "n",
  о: "o",
  п: "p",
  р: "r",
  с: "s",
  т: "t",
  у: "u",
  ф: "f",
  х: "kh",
  ц: "ts",
  ч: "ch",
  ш: "sh",
  щ: "sch",
  ъ: "",
  ы: "y",
  ь: "",
  э: "e",
  ю: "yu",
  я: "ya",

  // Special punctuation and symbols (no duplicates)
  "\u2018": "'",
  "\u2019": "'",
  "\u201C": '"',
  "\u201D": '"',
  "\u2013": "-",
  "\u2014": "-",
  "\u2026": "...",
  "•": "*",
  "‚": ",",
  "„": '"',
  "‹": "<",
  "›": ">",
  "«": '"',
  "»": '"',

  // Mathematical and other symbols
  "×": "x",
  "÷": "/",
  "±": "+/-",
  "≈": "~",
  "≠": "!=",
  "≤": "<=",
  "≥": ">=",
  "∞": "infinity",
  "∑": "sum",
  "∏": "product",
  "∆": "delta",
  "∇": "nabla",

  // Currency symbols
  "€": "EUR",
  "£": "GBP",
  "¥": "JPY",
  "¢": "cent",
  "¤": "currency",

  // Fractions
  "½": "1/2",
  "⅓": "1/3",
  "⅔": "2/3",
  "¼": "1/4",
  "¾": "3/4",
  "⅛": "1/8",
  "⅜": "3/8",
  "⅝": "5/8",
  "⅞": "7/8",

  // Superscripts and subscripts
  "⁰": "0",
  "¹": "1",
  "²": "2",
  "³": "3",
  "⁴": "4",
  "⁵": "5",
  "⁶": "6",
  "⁷": "7",
  "⁸": "8",
  "⁹": "9",
  "₀": "0",
  "₁": "1",
  "₂": "2",
  "₃": "3",
  "₄": "4",
  "₅": "5",
  "₆": "6",
  "₇": "7",
  "₈": "8",
  "₉": "9",

  // Common music-related symbols
  "♪": "note",
  "♫": "notes",
  "♬": "notes",
  "♭": "b",
  "♯": "#",
  "♮": "natural",

  // Arrows
  "←": "<-",
  "→": "->",
  "↑": "^",
  "↓": "v",
  "↔": "<->",
  "↕": "^v",

  // Box drawing and other special characters
  "│": "|",
  "─": "-",
  "┌": "+",
  "┐": "+",
  "└": "+",
  "┘": "+",
  "├": "+",
  "┤": "+",
  "┬": "+",
  "┴": "+",
  "┼": "+",
};

/**
 * Normalizes Unicode characters to their closest ASCII equivalents.
 * Uses both a comprehensive character map and Unicode normalization.
 *
 * @param text - The text to normalize
 * @returns The normalized text with ASCII equivalents
 *
 * @example
 * ```typescript
 * normalizeUnicode("Café"); // "Cafe"
 * normalizeUnicode("Naïve"); // "Naive"
 * normalizeUnicode("Zürich"); // "Zurich"
 * normalizeUnicode("Björk"); // "Bjork"
 * normalizeUnicode("Sigur Rós"); // "Sigur Ros"
 * ```
 */
export function normalizeUnicode(text: string): string {
  if (!text) return text;

  // First, try to normalize using the comprehensive character map
  let result = text;

  // Replace characters using our comprehensive map
  for (const [unicode, ascii] of Object.entries(UNICODE_MAP)) {
    result = result.replaceAll(unicode, ascii);
  }

  // Use Unicode normalization as a fallback for any remaining accented characters
  // NFD (Normalization Form Decomposed) separates base characters from combining marks
  result = result.normalize("NFD");

  // Remove combining diacritical marks (accents, etc.)
  // This regex matches all combining diacritical marks in Unicode
  result = result.replace(/[\u0300-\u036f]/g, "");

  // Clean up any remaining problematic characters by replacing with closest ASCII
  // This catches any edge cases not covered by the map
  // deno-lint-ignore no-control-regex
  result = result.replace(/[^\x00-\x7F]/g, (char) => {
    // If we have a specific mapping, use it
    if (UNICODE_MAP[char]) {
      return UNICODE_MAP[char];
    }

    // For unmapped characters, try to find a reasonable ASCII substitute
    const code = char.charCodeAt(0);

    // Handle various Unicode blocks
    if (code >= 0x0100 && code <= 0x017f) {
      // Latin Extended-A
      return char.toLowerCase();
    } else if (code >= 0x0180 && code <= 0x024f) {
      // Latin Extended-B
      return char.toLowerCase();
    } else if (code >= 0x1e00 && code <= 0x1eff) {
      // Latin Extended Additional
      return char.toLowerCase();
    }

    // If no reasonable substitute found, remove the character
    return "";
  });

  // Clean up any double spaces or other artifacts
  result = result.replace(/\s+/g, " ").trim();

  return result;
}

/**
 * Normalizes Unicode characters in a filename-safe way.
 * Similar to normalizeUnicode but also handles filename-specific concerns.
 *
 * @param filename - The filename to normalize
 * @returns The normalized filename safe for filesystem use
 *
 * @example
 * ```typescript
 * normalizeFilename("Café Müller - Naïve.mp3"); // "Cafe Muller - Naive.mp3"
 * normalizeFilename("Björk – Jóga.flac"); // "Bjork - Joga.flac"
 * ```
 */
export function normalizeFilename(filename: string): string {
  if (!filename) return filename;

  // First normalize Unicode characters
  let result = normalizeUnicode(filename);

  // Handle filename-specific character replacements
  result = result
    .replace(/[<>:"/\\|?*]/g, "") // Remove invalid filename characters
    .replace(/\s+/g, " ") // Normalize whitespace
    .trim();

  return result;
}

/**
 * Checks if a string contains any non-ASCII characters.
 *
 * @param text - The text to check
 * @returns True if the text contains non-ASCII characters
 *
 * @example
 * ```typescript
 * hasUnicodeCharacters("Hello"); // false
 * hasUnicodeCharacters("Café"); // true
 * hasUnicodeCharacters("Björk"); // true
 * ```
 */
export function hasUnicodeCharacters(text: string): boolean {
  // deno-lint-ignore no-control-regex
  return /[^\x00-\x7F]/.test(text);
}

/**
 * Gets a list of all non-ASCII characters in a string.
 * Useful for debugging or reporting which characters need normalization.
 *
 * @param text - The text to analyze
 * @returns Array of unique non-ASCII characters found
 *
 * @example
 * ```typescript
 * getUnicodeCharacters("Café Müller"); // ["é", "ü"]
 * getUnicodeCharacters("Björk & Sigur Rós"); // ["ö", "ó"]
 * ```
 */
export function getUnicodeCharacters(text: string): string[] {
  const unicodeChars = new Set<string>();

  for (const char of text) {
    if (char.charCodeAt(0) > 127) {
      unicodeChars.add(char);
    }
  }

  return Array.from(unicodeChars);
}
