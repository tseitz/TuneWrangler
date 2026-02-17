import * as path from "@std/path";
import { normalizeUnicode, normalizeFilename } from "../utils/unicode.ts";

export class Song {
  artist = "";
  album = "";
  title = "";
  extension: string;
  fullFilename = "";
  finalFilename = "";
  dashCount = 0;
  rating = 0;
  remix = false;
  changed = false;
  duplicate = false;
  tags: Tags | undefined;

  constructor(public filename: string, public directory: string) {
    this.fullFilename = `${directory}${filename}`;
    this.extension = path.extname(filename);
    this.dashCount = this.getDashCount();
  }

  getDashCount(): number {
    return this.filename.split(" - ").length - 1;
  }

  grabFirst(): string {
    return this.filename.split(" - ")[0].trim();
  }

  grabSecond(): string {
    let second = "";

    if (this.filename.split(" - ")[1]) {
      second = this.filename.split(" - ")[1].trim();
    }

    // YouTube naming Artist - Topic
    if (second.trim() === "Topic" && !this.filename.includes("Various Artists")) {
      second = this.grabFirst();
    }

    return second;
  }

  grabThird(): string {
    return this.filename.split(" - ")[2];
  }

  grabLast(): string {
    if (this.filename.lastIndexOf(".") === -1) {
      return this.filename.slice(this.filename.lastIndexOf(" - ") + 3).trim();
    } else {
      return this.filename.slice(this.filename.lastIndexOf(" - ") + 3, this.filename.lastIndexOf(".")).trim();
    }
  }

  splitArtist(): string[] {
    return this.artist.split ? this.artist.split(" x ") : [];
  }

  removeBadCharacters(): Song {
    const origFilename = this.filename;

    // First, normalize all Unicode characters to ASCII equivalents
    this.filename = normalizeFilename(this.filename);

    // Specific Unicode character replacements for music files
    // These are in addition to the comprehensive normalization
    this.filename = this.filename.replace(/\u3010/g, "["); // 【
    this.filename = this.filename.replace(/\u3011/g, "] "); // 】
    this.filename = this.filename.replace(/\u2768/g, "["); // ❨
    this.filename = this.filename.replace(/\u2769/g, "]"); // ❩
    this.filename = this.filename.replace(/\u2770/g, "["); // ❰
    this.filename = this.filename.replace(/\u2771/g, "]"); // ❱
    this.filename = this.filename.replace(/\u2716/g, "x"); // ✖
    this.filename = this.filename.replace(/\u2718/g, "x"); // ✘

    // Music-specific name fixes
    this.filename = this.filename.replace(/ʟᴜᴄᴀ ʟᴜsʜ/g, "LUCA LUSH");
    this.filename = this.filename.replace("Re-Sauce", "Remix");
    this.filename = this.filename.replace("Re-Crank", "Remix");
    this.filename = this.filename.replace("Mixmag - Premiere-", "Mixmag - ");
    this.filename = this.filename.replace("1985  -  Music", "1985 Music");
    this.filename = this.filename.replace(/free download/gi, "");
    this.filename = this.filename.replace(/featuring/gi, "feat.");

    // Update dash count after all transformations
    this.dashCount = this.getDashCount();

    if (origFilename !== this.filename) {
      this.changed = true;
    }

    return this;
  }

  /**
   * Normalizes Unicode characters in artist, album, and title fields.
   * This method should be called after parsing the filename to ensure
   * all metadata fields use ASCII equivalents.
   */
  normalizeMetadata(): Song {
    const origArtist = this.artist;
    const origAlbum = this.album;
    const origTitle = this.title;

    // Normalize Unicode characters in all metadata fields
    this.artist = normalizeUnicode(this.artist);
    this.album = normalizeUnicode(this.album);
    this.title = normalizeUnicode(this.title);

    // Mark as changed if any field was modified
    if (origArtist !== this.artist || origAlbum !== this.album || origTitle !== this.title) {
      this.changed = true;
    }

    return this;
  }

  checkRemix(): Song {
    const origArtist = this.artist;
    const filename = this.filename;

    // regex: ( or [ not followed by another ) or ] followed by REMIX etc.   So: Title (... Remix)   NOT: Title (Feat. ...) (... Remix)
    // also checks there isn't an album called REMIXES. So we expect non word character after REMIX (\W)
    if (/(\(|\[)[^\)]+ REMIX\W/gi.test(filename)) {
      const filenameRegex = /(\(|\[)[^\)]+ REMIX\W/gi.exec(filename); // /(\(|\[)[^\)]+ REMIX(\)|\])/ig.exec(filename);
      this.artist = filename
        .slice(/(\(|\[)[^\)]+ REMIX\W/gi.exec(filename)!.index + 1, / REMIX\W/gi.exec(filename)!.index)
        .trim();
      this.filename = filename.slice(0, filenameRegex!.index).trim().concat(this.extension);
    } else if (/(\(|\[)[^\)]+ REFIX\W/gi.test(filename)) {
      this.artist = filename
        .slice(/(\(|\[)[^\)]+ REFIX\W/gi.exec(filename)!.index + 1, / REFIX\W/gi.exec(filename)!.index)
        .trim();
      this.filename = filename
        .slice(0, /(\(|\[)[^\)]+ REFIX\W/gi.exec(filename)!.index)
        .trim()
        .concat(this.extension);
    } else if (/(\(|\[)[^\)]+ FLIP\W/gi.test(filename)) {
      this.artist = filename
        .slice(/(\(|\[)[^\)]+ FLIP\W/gi.exec(filename)!.index + 1, / FLIP\W/gi.exec(filename)!.index)
        .trim();
      this.filename = filename
        .slice(0, /(\(|\[)[^\)]+ FLIP\W/gi.exec(filename)!.index)
        .trim()
        .concat(this.extension);
    } else if (/(\(|\[)[^\)]+ EDIT\W/gi.test(filename)) {
      this.artist = filename
        .slice(/(\(|\[)[^\)]+ EDIT\W/gi.exec(filename)!.index + 1, / EDIT\W/gi.exec(filename)!.index)
        .trim();
      this.filename = filename
        .slice(0, /(\(|\[)[^\)]+ EDIT\W/gi.exec(filename)!.index)
        .trim()
        .concat(this.extension);
    } else if (/(\(|\[)[^\)]+ BOOTLEG\W/gi.test(filename)) {
      this.artist = filename
        .slice(/(\(|\[)[^\)]+ BOOTLEG\W/gi.exec(filename)!.index + 1, / BOOTLEG\W/gi.exec(filename)!.index)
        .trim();
      this.filename = filename
        .slice(0, /(\(|\[)[^\)]+ BOOTLEG\W/gi.exec(filename)!.index)
        .trim()
        .concat(this.extension);
    } else if (/(\(|\[)[^\)]+ REBOOT\W/gi.test(filename)) {
      this.artist = filename
        .slice(/(\(|\[)[^\)]+ REBOOT\W/gi.exec(filename)!.index + 1, / REBOOT\W/gi.exec(filename)!.index)
        .trim();
      this.filename = filename.slice(0, /(\(|\[)[^\)]+ REBOOT\W/gi.exec(filename)!.index - 1).concat(this.extension);
    } else if (/(\(|\[)[^\)]+ DUB\W/gi.test(filename)) {
      this.artist = filename
        .slice(/(\(|\[)[^\)]+ DUB\W/gi.exec(filename)!.index + 1, / DUB\W/gi.exec(filename)!.index)
        .trim();
      this.filename = filename.slice(0, /(\(|\[)[^\)]+ DUB\W/gi.exec(filename)!.index - 1).concat(this.extension);
    }

    if (origArtist !== this.artist) {
      this.remix = true;
      this.changed = true;
    }

    return this;
  }

  removeAnd(...types: Array<"artist" | "album">): Song {
    types.forEach((type) => {
      const origLabel = this[type];

      this[type] = this[type].replace(/ & /g, " x ");
      this[type] = this[type].replace(/ %26 /g, " x ");
      this[type] = this[type].replace(/, /g, " x ");
      this[type] = this[type].replace(/ X /gi, " x ");
      this[type] = this[type].replace(/ and /gi, " x ");
      this[type] = this[type].replace(/ \+ /gi, " x ");

      if (origLabel !== this[type]) {
        this.changed = true;
      }
    });

    return this;
  }

  checkWith(): Song {
    // W- is usually an artist. Add it to artist with an x
    const origArtist = this.artist;
    const filename = this.filename;

    if (this.artist.length > 0) {
      if (filename.toUpperCase().includes("(W-")) {
        this.artist += ` x ${filename.slice(
          filename.toUpperCase().indexOf("(W- ") + 4,
          filename.lastIndexOf(this.extension) - 1
        )}`;
        this.filename = filename.slice(0, filename.toUpperCase().indexOf("(W-")).trim().concat(this.extension);
      } else if (filename.toUpperCase().includes("(WITH ")) {
        this.artist += ` x ${filename.slice(
          filename.toUpperCase().indexOf("(WITH ") + 6,
          filename.lastIndexOf(this.extension) - 1
        )}`;
        this.filename = filename.slice(0, filename.toUpperCase().indexOf("(WITH")).trim().concat(this.extension);
      } else if (filename.toUpperCase().includes("(W_")) {
        this.artist += ` x ${filename.slice(
          filename.toUpperCase().indexOf("(W_ ") + 4,
          filename.lastIndexOf(this.extension) - 1
        )}`;
        this.filename = filename.slice(0, filename.toUpperCase().indexOf("(W_")).trim().concat(this.extension);
      } else if (filename.toUpperCase().includes("W-")) {
        this.artist += ` x ${filename.slice(
          filename.toUpperCase().indexOf("W- ") + 3,
          filename.lastIndexOf(this.extension)
        )}`;
        this.filename = filename.slice(0, filename.toUpperCase().indexOf("W-")).trim().concat(this.extension);
      } else if (filename.toUpperCase().includes("W_")) {
        this.artist += ` x ${filename.slice(
          filename.toUpperCase().indexOf("W_ ") + 3,
          filename.lastIndexOf(this.extension)
        )}`;
        this.filename = filename.slice(0, filename.toUpperCase().indexOf("W_")).trim().concat(this.extension);
      } else if (filename.toUpperCase().includes(" W ")) {
        this.artist += ` x ${filename.slice(
          filename.toUpperCase().indexOf(" W ") + 3,
          filename.lastIndexOf(this.extension)
        )}`;
        this.filename = filename.slice(0, filename.toUpperCase().indexOf(" W ")).trim().concat(this.extension);
      }
    }

    if (this.artist !== origArtist) {
      this.changed = true;
    }

    return this;
  }

  // tslint:disable-next-line:cyclomatic-complexity
  checkFeat(): Song {
    const origArtist = this.artist;
    const origTitle = this.title;
    const origAlbum = this.album || "";
    let featuringArtist: string | undefined;

    // slice the find index, plus the length of the first capturing group and the second capturing group
    // (FEAT.  (FT.  [FEAT.  [FT.  FEAT.  FT.  FEAT  FT
    if (/(\(|\[|\s)(FEAT|FT)(\.?)\s.+(\)|\]|$)/gi.test(origArtist)) {
      const exec = /(\(|\[|\s)(FEAT|FT|FEATURING)(\.?)\s.+(\)|\]|$)/gi.exec(origArtist);
      featuringArtist = origArtist
        .slice(exec!.index + exec![1].length + exec![2].length + exec![3].length, /(\)|\]|$)/gi.exec(origArtist)!.index)
        .trim();
      this.artist = origArtist.slice(0, exec!.index).trim();
    }
    if (/(\(|\[|\s)(FEAT|FT)(\.?)\s.+(\)|\]|$)/gi.test(origTitle)) {
      const exec = /(\(|\[|\s)(FEAT|FT|FEATURING)(\.?)\s.+(\)|\]|$)/gi.exec(origTitle);
      featuringArtist = origTitle
        .slice(exec!.index + exec![1].length + exec![2].length + exec![3].length, /(\)|\]|$)/gi.exec(origTitle)!.index)
        .trim();
      this.title = origTitle.slice(0, exec!.index).trim();
    }
    if (/(\(|\[|\s)(FEAT|FT)(\.?)\s.+(\)|\]|$)/gi.test(origAlbum)) {
      const exec = /(\(|\[|\s)(FEAT|FT|FEATURING)(\.?)\s.+(\)|\]|$)/gi.exec(origAlbum);
      featuringArtist = origAlbum
        .slice(exec!.index + exec![1].length + exec![2].length + exec![3].length, /(\)|\]|$)/gi.exec(origAlbum)!.index)
        .trim();
      this.album = origAlbum.slice(0, exec!.index).trim();
    }

    // (PROD. and [PROD
    if (/(\(|\[)PROD\.?\s/gi.test(origArtist)) {
      featuringArtist = origArtist
        .slice(/(\(|\[)PROD\.?\s/gi.exec(origArtist)!.index + 7, origArtist.lastIndexOf(")"))
        .trim();
      this.artist = origArtist.slice(0, /(\(|\[)PROD\.?\s/gi.exec(origArtist)!.index).trim();
    }
    if (/(\(|\[)PROD\.?\s/gi.test(origTitle)) {
      featuringArtist = origTitle
        .slice(/(\(|\[)PROD\.?\s/gi.exec(origTitle)!.index + 7, origTitle.lastIndexOf(")"))
        .trim();
      this.title = origTitle.slice(0, /(\(|\[)PROD\.?\s/gi.exec(origTitle)!.index).trim();
    }

    if (this.artist !== origArtist || this.title !== origTitle || this.album !== origAlbum) {
      this.changed = true;
      console.log(`Feat: ${featuringArtist}`);

      // if it's a remix, the featuring artist belongs to the original artist (which we label as album)
      if (featuringArtist && this.remix) {
        this.album += ` x ${featuringArtist}`;
      } else if (this.artist !== origArtist) {
        this.artist += ` x ${featuringArtist}`;
      } else if (this.title !== origTitle) {
        this.artist += ` x ${featuringArtist}`;
      } else if (this.album !== origAlbum) {
        this.album += ` x ${featuringArtist}`;
      }
    }

    return this;
  }

  lastCheck(): Song {
    const title = this.title;
    const artist = this.artist;
    const album = this.album;

    if (
      /(\(|\[)/g.test(title) &&
      !title.toUpperCase().includes("VIP") &&
      !title.toUpperCase().includes("WIP") &&
      !title.toUpperCase().includes("INSTRUMENTAL") &&
      !title.toUpperCase().includes("EXTENDED")
    ) {
      console.log(`Title: ${title}`);
      this.title = title.slice(0, /(\(|\[)/g.exec(title)!.index).trim();
    }

    if (/(\(|\[)/g.test(artist)) {
      console.log(`Artist: ${artist}`);
      this.artist = artist.slice(0, /(\(|\[)/g.exec(artist)!.index).trim();
    }

    if (/(\(|\[)/g.test(album)) {
      console.log(`Album: ${album}`);
      this.album = album.slice(0, /(\(|\[)/g.exec(album)!.index).trim();
    }

    return this;
  }
}

export class FormattedSong extends Song {
  constructor(filename: string, directory: string) {
    super(filename, directory);

    this.artist = this.grabFirst();
    this.album = this.grabSecond();
    this.title = this.grabThird();
    this.rating = parseInt(this.grabLast(), 10) || 0;
  }
}

export class LocalSong extends Song {
  constructor(filename: string, directory: string) {
    super(filename, directory);

    this.extension = path.extname(filename);

    if (this.getDashCount() === 1) {
      this.artist = this.grabFirst();
      this.title = this.grabSecond();
    } else if (this.getDashCount() > 1) {
      this.artist = this.grabFirst();
      this.album = this.grabSecond();
      this.title = this.grabLast();
    }

    if (this.title.includes(this.extension)) {
      this.title = this.title.slice(0, this.title.lastIndexOf(this.extension));
    }
  }
}

export class DownloadedSong extends Song {
  constructor(filename: string, directory: string) {
    super(filename, directory);

    if (this.getDashCount() === 0) {
      this.checkRemix();
      this.checkFeat();
      this.lastCheck();
      this.removeAnd("artist", "album");
      if (this.artist === "") {
        throw "No artist found";
      } else {
        this.title = this.filename.slice(0, this.filename.lastIndexOf("."));
      }
    }
    if (this.getDashCount() === 1) {
      this.artist = this.grabFirst();
      this.title = this.grabSecond();
    } else if (this.getDashCount() === 2) {
      this.artist = this.grabSecond();
      this.album = this.grabFirst();
      this.title = this.grabLast();
    }
  }
}

export class PlaylistSong extends Song {
  constructor(filename: string, directory: string) {
    super(filename, directory);

    this.artist = this.grabFirst();
    this.title = this.grabSecond();
  }
}

export interface Tags {
  artist: string;
  album: string;
  title: string;
  performerInfo?: string;
}
