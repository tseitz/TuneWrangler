import * as path from 'path';

export class Song {
  artist: string = '';
  album: string = '';
  title: string = '';
  extension: string = '';
  count: number = 0;
  filename: string = '';
  directory: string = '';
  remix: boolean = false;
  changed: boolean = false;
  duplicate: boolean = false;
  rating: number = 0;

  constructor(filename: string, directory: string) {
    this.extension = this.grabExtension();
    this.count = this.countDash();
    this.filename = filename;
    this.directory = directory;
    this.count = this.countDash();
  }

  get fullFilename() {
    return `${this.directory}${this.filename}`;
  }

  countDash(): number {
    return this.filename.split(' - ').length - 1;
  }

  grabFirst(): string {
    return this.filename.split(' - ')[0].trim().trimLeft();
  }
  
  grabSecond(): string {
    let second = '';
    
    if (this.filename.split(' - ')[1]) {
      second = this.filename.split(' - ')[1].trim().trimLeft();
    }

    // YouTube naming Artist - Topic
    if (second.trim().trimLeft() === 'Topic' && !this.filename.includes('Various Artists')) {
      second = this.grabFirst();
    }
  
    return second;
  }
  
  grabThird(): string {
    return this.filename.split(' - ')[2];
  }
  
  grabLast(): string {  
    return this.filename.slice(this.filename.lastIndexOf(' - ') + 3, this.filename.lastIndexOf('.')).trim().trimLeft();
  }
  
  grabExtension(): string {
    return path.extname(this.filename) || undefined;
  }
}

export class LocalSong extends Song {
  constructor(filename: string, directory: string) {
    super(filename, directory);

    this.artist = this.grabFirst();
    this.album = this.grabSecond();
    this.title = this.grabThird();
    this.rating = parseInt(this.grabLast(), 10) || 0;
  }
}

export class DownloadedSong extends Song {
  constructor(filename: string, directory: string) {
    super(filename, directory);

    this.artist = this.grabSecond();
    this.album = this.grabFirst();
    this.title = this.grabLast();
  }
}