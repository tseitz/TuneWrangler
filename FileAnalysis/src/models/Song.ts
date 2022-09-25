import * as path from "https://deno.land/std@0.157.0/path/mod.ts";

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
  tags: Tags;

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
    if (
      second.trim() === "Topic" &&
      !this.filename.includes("Various Artists")
    ) {
      second = this.grabFirst();
    }

    return second;
  }

  grabThird(): string {
    return this.filename.split(" - ")[2];
  }

  grabLast(): string {
    return this.filename
      .slice(
        this.filename.lastIndexOf(" - ") + 3,
        this.filename.lastIndexOf(".")
      )
      .trim();
  }
}

export class LocalSong extends Song {
  constructor(filename: string, directory: string) {
    super(filename, directory);

    // this.artist = this.grabFirst();
    // this.album = this.grabSecond();
    // this.title = this.grabThird();
    // this.rating = parseInt(this.grabLast(), 10) || 0;

    if (this.getDashCount() === 1) {
      this.artist = this.grabFirst();
      this.title = this.grabSecond();
    } else if (this.getDashCount() > 1) {
      this.artist = this.grabSecond();
      this.album = this.grabFirst();
      this.title = this.grabLast();
    }
  }
}

export class DownloadedSong extends Song {
  constructor(filename: string, directory: string) {
    super(filename, directory);

    if (this.getDashCount() === 0) {
      console.log("Bad Request: No dashes in filename");
      return;
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

interface Tags {
  artist: string;
  album: string;
  title: string;
}
