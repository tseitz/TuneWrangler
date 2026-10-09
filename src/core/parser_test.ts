import { assertEquals, assertNotEquals, assertThrows } from "jsr:@std/assert@^1";
import { parseFilename } from "./corpus.ts";
import { DownloadedSong } from "./models/Song.ts";
import { parseBandcampSong } from "./parser.ts";

const cases: [string, string, string][] = [
  // Bracket remixer with extra words, posted by the remixer: the uploader's spelling wins.
  ["remixer spelling", "MORTY - Korn - Freak On a Leash (Morty UKG Bootleg).wav", "MORTY - Korn - Freak On a Leash.wav"],
  ["remixer spelling", "strange language - Gucci Mane - Pillz (STRANGE LANGUAGE 5K FLIP).wav", "strange language - Gucci Mane - Pillz.wav"],
  ["remixer spelling", "DAZEYLANES - Flight Facilities - CRAVE YOU (DAZEY UKG BOOTLEG).wav", "DAZEYLANES - Flight Facilities - CRAVE YOU.wav"],
  // A remix word checkRemix doesn't know, with the uploader named in the bracket.
  ["unknown remix word", "Blosso - Tim Deluxe - It Just Won't Do (Blosso Edition).wav", "Blosso - Tim Deluxe - It Just Won't Do.wav"],
  ["unknown remix word", "Gunpoint - Taiki Nulight - Style (Gunpoint Reload).wav", "Gunpoint - Taiki Nulight - Style.wav"],
  ["unknown remix word", "THE BUZZ - JG DUBZ - KILL BABYLON [THE BUZZ SPESH].wav", "THE BUZZ - JG DUBZ - KILL BABYLON.wav"],
  // The uploader repeated inside the collab.
  ["repeated uploader", "CCIV - CCIV x Portals - Discombobulated.wav", "CCIV x Portals - Discombobulated.wav"],
  ["repeated uploader", "LOWER [SKANK GANG] - LOWER & JADHA - ON MY LEVEL.wav", "LOWER x JADHA - ON MY LEVEL.wav"],
  ["repeated uploader", "Fossils - FOSSILS - PULL UP.wav", "FOSSILS - PULL UP.wav"],
  ["repeated uploader", "statiq. - statiq. niko - guns of fury.wav", "statiq. x niko - guns of fury.wav"],
  // A self-remix names one artist once.
  ["self-remix", "ALIAS - I CRY, JUST A LITTLE (ALIAS UKG FLIP).wav", "ALIAS - I CRY, JUST A LITTLE.wav"],
  // Guards: none of the rules may fire here.
  ["guard: collab remixer", "HAMMAH - Kanye West - Mercy (HAMMAH & JBG Flip).mp3", "HAMMAH x JBG - Kanye West - Mercy.mp3"],
  ["guard: unrelated remixer", "Only Bangs - Blaze - Lovlee Dae (sevenseven Edit).wav", "sevenseven - Blaze - Lovlee Dae.wav"],
  ["guard: same spelling", "cozy kev - A$AP ROCKY - LONG LIVE A$AP (COZY KEV REMIX).wav", "COZY KEV - A$AP ROCKY - LONG LIVE A$AP.wav"],
  ["guard: label up front", "STPTBOOTS - Rayment - Wicked & Dark.wav", "Rayment - STPTBOOTS - Wicked & Dark.wav"],
  ["guard: bracket not the uploader", "Kvolx - San Pacho - Bootay (Remastered).wav", "San Pacho - Kvolx - Bootay.wav"],
  // A listed duo keeps its `&`; every other `&` still becomes ` x `.
  [
    "ampersand duo",
    "Joey Valence & Brae, Ayesha Erotica - The Baddest (Badder) (Phrva Flip).wav",
    "Phrva - Joey Valence & Brae x Ayesha Erotica - The Baddest.wav",
  ],
];

for (const [rule, src, want] of cases) {
  Deno.test(`parser ${rule}: ${src}`, () => assertEquals(parseFilename(src), want));
}

const bandcampCases: [string, string][] = [
  ["ILL GROOVE SOCIETY - Duality - Fallin'.aiff", "Duality - ILL GROOVE SOCIETY - Fallin'.aiff"],
  ["fez the kid - D.Tee - As we enter.aiff", "D.Tee - fez the kid - As we enter.aiff"],
  ["fez the kid - Fez the kid - Keep the fire burning.aiff", "Fez the kid - Keep the fire burning.aiff"],
  ["Jaz Imsky, En-vy - Codebreaker - 01 Codebreaker.aiff", "Jaz Imsky x En-vy - Codebreaker.aiff"],
  ["Gaszia - Ninajirachi - Fuck My Computer (Gaszia Edit).aiff", "Gaszia - Ninajirachi - Fuck My Computer.aiff"],
  ["D-FORM - BURN EP - 01 Statik.aiff", "D-FORM - BURN EP - Statik.aiff"],
  ["Cardvell - Bang Laser.aiff", "Cardvell - Bang Laser.aiff"],
  [
    "Bukez Finezt - BUKEZ BOOTLEGZ #1 - 02 Cam'Ron - Oh Boy (Bukez Finezt Jersey Club Bootleg Remix).aiff",
    "Bukez Finezt - Cam'Ron - Oh Boy.aiff",
  ],
  ["Alex Unger - Jet Fuel (feat. parkbreezy).aiff", "Alex Unger x parkbreezy - Jet Fuel.aiff"],
];

for (const [src, want] of bandcampCases) {
  Deno.test(`parser bandcamp: ${src}`, () => assertEquals(parseFilename(src, "bandcamp"), want));
}

Deno.test("parser bandcamp order differs from downloaded for a 3-part name", () => {
  const src = "D-FORM - BURN EP - 01 Statik.aiff";
  assertNotEquals(parseFilename(src, "bandcamp"), parseFilename(src));
});

Deno.test("parser bandcamp rejects a name with no dash", () => {
  assertThrows(() => parseBandcampSong(Object.assign(new DownloadedSong("Cardvell - X.aiff", "/tmp/"), { dashCount: 0 })));
});

Deno.test("parser bandcamp: a remix credited to the release's own artist is still a remix", () => {
  assertEquals(parseFilename("Acct - Album - 01 Artist2 - Title (Acct Remix).mp3", "bandcamp"), "Acct - Artist2 - Title.mp3");
});
