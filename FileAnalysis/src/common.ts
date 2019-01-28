import { LocalSong, Song } from './models/Song';

export function checkOS(type: string): string {
  switch (type) {
    case 'transfer':
      return process.env.OS === 'Windows_NT' ? 'F:\\Dropbox\\TransferMusic\\' : '/Users/tseitz10/Dropbox/TransferMusic/';
    case 'music':
      return process.env.OS === 'Windows_NT' ? 'F:\\Dropbox\\Music\\' : '/Users/tseitz10/Dropbox/Music/';
    case 'downloads':
      return process.env.OS === 'Windows_NT' ? 'C:\\Users\\Scooter\\Downloads\\' : '/Users/tseitz10/Downloads/';
    case 'playlists':
      return process.env.OS === 'Windows_NT' ? 'F:\\Dropbox\\MediaMonkeyPlaylists\\' : '/Users/tseitz10/Dropbox/MediaMonkeyPlaylists/';
    default:
      return '';
  }
}

export function cacheMusic(files: string[], dir: string): LocalSong[] {
  const cache: LocalSong[] = [];

  for (let i = 0, len = files.length; i < len; i++) {
    const song = new LocalSong(files[i], dir);
    cache.push(song);
  }

  return cache;
}

export function splitArtist(artist: string): string[] {
  return artist.split ? artist.split(' x ') : [];
}

export function removeBadCharacters(song: Song): Song {
  const origFilename = song.filename;

  // Unicode
  song.filename = song.filename.replace(/\u3010/g, '['); // 【
  song.filename = song.filename.replace(/\u3011/g, '] '); // 】
  song.filename = song.filename.replace(/\u2768/g, '['); // ❨
  song.filename = song.filename.replace(/\u2769/g, ']'); // ❩
  song.filename = song.filename.replace(/\u2770/g, '['); // ❰
  song.filename = song.filename.replace(/\u2771/g, ']'); // ❱
  song.filename = song.filename.replace(/\u2716/g, 'x'); // ✖
  song.filename = song.filename.replace(/\u2718/g, 'x');
  song.filename = song.filename.replace(/\u00D8/g, 'o'); // Ø
  song.filename = song.filename.replace(/\u00f8/g, 'o'); // ø
  song.filename = song.filename.replace(/[\u201C-\u201D]/g, '"');

  song.filename = song.filename.replace(/\u2014/g, '-'); // —
  song.dashCount = song.getDashCount();

  // Name fixes
  song.filename = song.filename.replace(/ʟᴜᴄᴀ ʟᴜsʜ/g, 'LUCA LUSH');
  song.filename = song.filename.replace('Re-Sauce', 'Remix');
  song.filename = song.filename.replace('Re-Crank', 'Remix');
  song.filename = song.filename.replace('Mixmag - Premiere-', 'Mixmag - ');
  song.filename = song.filename.replace('1985  -  Music', '1985 Music');

  // Channels
  if (song.filename.toUpperCase().includes('[FIRE')) {
    song.filename = song.filename.substring(0, song.filename.toUpperCase().indexOf('[FIRE') - 1).concat('.mp3');
  }
  if (song.filename.includes('NEVER SAY DIE - BLACK LABEL')) {
    song.filename = song.filename.replace('Never Say Die - Black Label', 'Never Say Die Black Label');
  }
  if (song.filename.toUpperCase().includes('INSOMNIAC') && song.filename.toUpperCase().includes('TRACK OF THE DAY')) {
    song.filename = song.filename.slice(0, song.filename.toUpperCase().indexOf('TRACK OF'))
      .concat(song.filename.slice(song.filename.toUpperCase().indexOf('OF THE DAY ') + 11));
    song.filename = song.filename.replace(/\"/, '- '); // replace first instance of " with -
    song.filename = song.filename.replace(/\"/, ''); // then remove the second one
    song.dashCount = song.getDashCount();
  } else if (song.filename.toUpperCase().includes('DJMAG') && song.filename.toUpperCase().includes('PREMIERE')) {
    song.filename = song.filename.slice(0, song.filename.toUpperCase().indexOf('PREMIERE'))
      .concat(song.filename.slice(song.filename.toUpperCase().indexOf('PREMIERE ') + 9));
    song.filename = song.filename.replace(/\'/, '- ');
    song.filename = song.filename.replace(/\'/, '');
    song.dashCount = song.getDashCount();
  }

  if (origFilename !== song.filename) {
    song.changed = true;
  }

  return song;
}

export function checkRemix(song: Song): Song {
  const origArtist = song.artist;
  const filename = song.filename;

  // regex: ( or [ not followed by another ) or ] followed by REMIX etc.   So: Title (... Remix)   NOT: Title (Feat. ...) (... Remix)
  if (/(\(|\[)[^\)]+ REMIX/ig.test(filename)) {
    const filenameRegex = /(\(|\[)[^\)]+ REMIX(\)|\])/ig.exec(filename);
    song.artist = filename.slice(/(\(|\[)[^\)]+ REMIX/ig.exec(filename)!.index + 1, / REMIX/ig.exec(filename)!.index).trim();
    song.filename = filename.slice(0, filenameRegex!.index).trim().concat(song.extension);
  } else if (/(\(|\[)[^\)]+ REFIX\)/ig.test(filename)) {
    song.artist = filename.slice(/(\(|\[)[^\)]+ REFIX\)/ig.exec(filename)!.index + 1, / REFIX/ig.exec(filename)!.index).trim();
    song.filename = filename.slice(0, /(\(|\[)[^\)]+ REFIX\)/ig.exec(filename)!.index).trim().concat(song.extension);
  } else if (/(\(|\[)[^\)]+ FLIP(\)|\])/ig.test(filename)) {
    song.artist = filename.slice(/(\(|\[)[^\)]+ FLIP(\)|\])/ig.exec(filename)!.index + 1, / FLIP/ig.exec(filename)!.index).trim();
    song.filename = filename.slice(0, /(\(|\[)[^\)]+ FLIP(\)|\])/ig.exec(filename)!.index).trim().concat(song.extension);
  } else if (/(\(|\[)[^\)]+ EDIT(\)|\])/ig.test(filename)) {
    song.artist = filename.slice(/(\(|\[)[^\)]+ EDIT(\)|\])/ig.exec(filename)!.index + 1, / EDIT/ig.exec(filename)!.index).trim();
    song.filename = filename.slice(0, /(\(|\[)[^\)]+ EDIT(\)|\])/ig.exec(filename)!.index).trim().concat(song.extension);
  } else if (/(\(|\[)[^\)]+ BOOTLEG\)/ig.test(filename)) {
    song.artist = filename.slice(/(\(|\[)[^\)]+ BOOTLEG\)/ig.exec(filename)!.index + 1, / BOOTLEG/ig.exec(filename)!.index).trim();
    song.filename = filename.slice(0, /(\(|\[)[^\)]+ BOOTLEG\)/ig.exec(filename)!.index).trim().concat(song.extension);
  }
  // else if (/(\(|\[)[^\)]+ EDITION\)/ig.test(filename)) {
  //   song.artist = filename.slice(/(\(|\[)[^\)]+ EDITION\)/ig.exec(filename).index + 1, / EDITION/ig.exec(filename).index).trim();
  //   song.filename = filename.slice(0, /(\(|\[)[^\)]+ EDITION\)/ig.exec(filename).index - 1).concat(song.extension);
  // }

  if (origArtist !== song.artist) {
    song.remix = true;
    song.changed = true;
  }

  return song;
}

export function removeAnd(song: Song, ...types: Array<'artist' | 'album'>): Song {
  types.forEach((type) => {
    const origLabel = song[type];

    song[type] = song[type].replace(/ & /g, ' x ');
    song[type] = song[type].replace(/ %26 /g, ' x ');
    song[type] = song[type].replace(/, /g, ' x ');
    song[type] = song[type].replace(/ X /ig, ' x ');
    song[type] = song[type].replace(/ and /ig, ' x ');
    song[type] = song[type].replace(/ \+ /ig, ' x ');

    if (origLabel !== song[type]) {
      song.changed = true;
    }
  });

  return song;
}

export function removeClip(title: string): string {
  title = title.replace(/(\(|\[).?CLIP.?(\)|\])/ig, '').trim();

  return title;
}

export function checkDuplicate(song: Song, musicArr: Song[] = []): boolean {
  console.time('start');
  for (let i = 0, len = musicArr.length; i < len; i++) {
    const compare = musicArr[i];
    const songArtist = song.artist || '';
    const songTitle = song.title || '';
    const compareArtist = compare.artist || '';
    const compareTitle = compare.title || '';

    // remove clip to check if we have full version
    if (compareTitle.toUpperCase().includes('CLIP')) {
      compare.title = removeClip(compareTitle);
    }

    if (compare !== song && // when comparing local to itself, make sure the files don't exactly match
        songArtist.toUpperCase() === compareArtist.toUpperCase()  &&
        songTitle.toUpperCase() === compareTitle.toUpperCase()) {
      console.log(`***Duplicate: ${song.artist} - ${song.title}***
        ------------------------------`);
      return true;
    }
  }
  return false;
  console.time('end');
}

export function checkWith(song: Song): Song {
  // W- is usually an artist. Add it to artist with an x
  const origArtist = song.artist;
  const filename = song.filename;

  if (song.artist.length > 0) {
    if (filename.toUpperCase().includes('(W-')) {
      song.artist += ` x ${filename.slice(filename.toUpperCase().indexOf('(W- ') + 4, filename.lastIndexOf(song.extension) - 1)}`;
      song.filename = filename.slice(0, filename.toUpperCase().indexOf('(W-')).trim().concat(song.extension);
    } else if (filename.toUpperCase().includes('(WITH ')) {
      song.artist += ` x ${filename.slice(filename.toUpperCase().indexOf('(WITH ') + 6, filename.lastIndexOf(song.extension) - 1)}`;
      song.filename = filename.slice(0, filename.toUpperCase().indexOf('(WITH')).trim().concat(song.extension);
    } else if (filename.toUpperCase().includes('(W_')) {
      song.artist += ` x ${filename.slice(filename.toUpperCase().indexOf('(W_ ') + 4, filename.lastIndexOf(song.extension) - 1)}`;
      song.filename = filename.slice(0, filename.toUpperCase().indexOf('(W_')).trim().concat(song.extension);
    } else if (filename.toUpperCase().includes('W-')) {
      song.artist += ` x ${filename.slice(filename.toUpperCase().indexOf('W- ') + 3, filename.lastIndexOf(song.extension))}`;
      song.filename = filename.slice(0, filename.toUpperCase().indexOf('W-')).trim().concat(song.extension);
    } else if (filename.toUpperCase().includes('W_')) {
      song.artist += ` x ${filename.slice(filename.toUpperCase().indexOf('W_ ') + 3, filename.lastIndexOf(song.extension))}`;
      song.filename = filename.slice(0, filename.toUpperCase().indexOf('W_')).trim().concat(song.extension);
    } else if (filename.toUpperCase().includes(' W ')) {
      song.artist += ` x ${filename.slice(filename.toUpperCase().indexOf(' W ') + 3, filename.lastIndexOf(song.extension))}`;
      song.filename = filename.slice(0, filename.toUpperCase().indexOf(' W ')).trim().concat(song.extension);
    }
  }

  if (song.artist !== origArtist) {
    song.changed = true;
  }

  return song;
}

// tslint:disable-next-line:cyclomatic-complexity
export function checkFeat(song: Song): Song {
  const origArtist = song.artist;
  const origTitle = song.title;
  const origAlbum = song.album || '';
  let featuringArtist: string | undefined;

  // slice the find index, plus the length of the first capturing group and the second capturing group
  // (FEAT.  (FT.  [FEAT.  [FT.  FEAT.  FT.  FEAT  FT
  if (/(\(|\[|\s)(FEAT|FT)(\.?)\s.+(\)|\]|$)/ig.test(origArtist)) {
    const exec = /(\(|\[|\s)(FEAT|FT)(\.?)\s.+(\)|\]|$)/ig.exec(origArtist);
    featuringArtist = origArtist.slice(exec!.index + exec![1].length + exec![2].length + exec![3].length, /(\)|\]|$)/ig.exec(origArtist)!.index).trim();
    song.artist = origArtist.slice(0, exec!.index).trim();
  }
  if (/(\(|\[|\s)(FEAT|FT)(\.?)\s.+(\)|\]|$)/ig.test(origTitle)) {
    const exec = /(\(|\[|\s)(FEAT|FT)(\.?)\s.+(\)|\]|$)/ig.exec(origTitle);
    featuringArtist = origTitle.slice(exec!.index + exec![1].length + exec![2].length + exec![3].length, /(\)|\]|$)/ig.exec(origTitle)!.index).trim();
    song.title = origTitle.slice(0, exec!.index).trim();
  }
  if (/(\(|\[|\s)(FEAT|FT)(\.?)\s.+(\)|\]|$)/ig.test(origAlbum)) {
    const exec = /(\(|\[|\s)(FEAT|FT)(\.?)\s.+(\)|\]|$)/ig.exec(origAlbum);
    featuringArtist = origAlbum.slice(exec!.index + exec![1].length + exec![2].length + exec![3].length, /(\)|\]|$)/ig.exec(origAlbum)!.index).trim();
    song.album = origAlbum.slice(0, exec!.index).trim();
  }

  // (PROD. and [PROD
  if (/(\(|\[)PROD\.?\s/ig.test(origArtist)) {
    featuringArtist = origArtist.slice(/(\(|\[)PROD\.?\s/ig.exec(origArtist)!.index + 7, origArtist.lastIndexOf(')')).trim();
    song.artist = origArtist.slice(0, /(\(|\[)PROD\.?\s/ig.exec(origArtist)!.index).trim();
  }
  if (/(\(|\[)PROD\.?\s/ig.test(origTitle)) {
    featuringArtist = origTitle.slice(/(\(|\[)PROD\.?\s/ig.exec(origTitle)!.index + 7, origTitle.lastIndexOf(')')).trim();
    song.title = origTitle.slice(0, /(\(|\[)PROD\.?\s/ig.exec(origTitle)!.index).trim();
  }

  if (song.artist !== origArtist || song.title !== origTitle || song.album !== origAlbum) {
    song.changed = true;
    console.log(`Feat: ${featuringArtist}`);

    // if it's a remix, the featuring artist belongs to the original artist (which we label as album)
    if (featuringArtist && song.remix) {
      song.album += ` x ${featuringArtist}`;
    } else if (song.artist !== origArtist) {
      song.artist += ` x ${featuringArtist}`;
    } else if (song.title !== origTitle) {
      song.artist += ` x ${featuringArtist}`;
    } else if (song.album !== origAlbum) {
      song.album += ` x ${featuringArtist}`;
    }
  }

  return song;
}

export function lastCheck(song: Song): Song {
  const title = song.title;
  const artist = song.artist;
  const album = song.album;

  if (song.filename.includes('Track of the Day- ')) {
    song.album = song.artist;
    song.artist = song.filename.slice(song.filename.lastIndexOf('- ') + 2, song.filename.indexOf('"')).trim();
    song.title = song.filename.slice(song.filename.indexOf('"') + 1, song.filename.lastIndexOf('"')).trim();
    song.dashCount = 2;
  }

  if (/(\(|\[)/g.test(title) &&
    !title.toUpperCase().includes('VIP') &&
    !title.toUpperCase().includes('WIP') &&
    !title.toUpperCase().includes('CLIP') &&
    !title.toUpperCase().includes('INSTRUMENTAL')
  ) {
    console.log(`Title: ${title}`);
    song.title = title.slice(0, /(\(|\[)/g.exec(title)!.index).trim();
  }

  if (/(\(|\[)/g.test(artist)) {
    console.log(`Artist: ${artist}`);
    song.artist = artist.slice(0, /(\(|\[)/g.exec(artist)!.index).trim();
  }

  if (/(\(|\[)/g.test(album)) {
    console.log(`Album: ${album}`);
    song.album = album.slice(0, /(\(|\[)/g.exec(album)!.index).trim();
  }

  return song;
}
