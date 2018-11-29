// import * as fs from 'fs';
import * as path from 'path';
import { LocalSong, Song } from './models/Song';

export function checkOS(type: string) {
  switch (type) {
    case 'transfer':
      return process.env.OS === 'Windows_NT' ? 'F:\\Dropbox\\TransferMusic\\' : '/Users/tseitz10/Dropbox/TransferMusic/';
    case 'music':
      return process.env.OS === 'Windows_NT' ? 'F:\\Dropbox\\Music\\' : '/Users/tseitz10/Dropbox/Music/';
    case 'downloads':
      return process.env.OS === 'Windows_NT' ? 'C:\\Users\\Scooter\\Downloads\\' : '/Users/tseitz10/Downloads/';
    case 'playlists':
      return process.env.OS === 'Windows_NT' ? 'F:\\Dropbox\\MediaMonkeyPlaylists\\' : '/Users/tseitz10/Dropbox/MediaMonkeyPlaylists/';
  }
}

export function cacheMusic(files: string[], dir: string) {
  const cache: LocalSong[] = [];

  // lots of songs, so fast for loop
  for (let i = 0, len = files.length; i < len; i++) {
    let song = new LocalSong(files[i], dir);
    cache.push(song);
  }

  return cache;
}

export function splitArtist(artist: string) {
  return artist.split ? artist.split(' x ') : [];
}

export function removeBadCharacters(song: Song): Song {
  let origFilename = song.filename;

  song.filename = song.filename.replace('\u3010', '['); // 【
  song.filename = song.filename.replace('\u3011', '] '); // 】
  song.filename = song.filename.replace('\u2768', '['); // ❨
  song.filename = song.filename.replace('\u2769', ']'); // ❩
  song.filename = song.filename.replace('\u2770', '['); // ❰
  song.filename = song.filename.replace('\u2771', ']'); // ❱
  song.filename = song.filename.replace('\u2716', 'x'); // ✖
  song.filename = song.filename.replace('\u2718', 'x');
  song.filename = song.filename.replace(/\u00DC/, 'U'); // Ü
  song.filename = song.filename.replace(/\u00FC/g, 'u'); // ü
  song.filename = song.filename.replace(/\u016B/g, 'u'); // ū
  song.filename = song.filename.replace(/\u014d/g, 'o'); // ō
  song.filename = song.filename.replace(/\u00f3/g, 'o'); // ó
  song.filename = song.filename.replace(/\u00D8/g, 'o'); // Ø
  song.filename = song.filename.replace(/\u00f8/g, 'o'); // ø
  song.filename = song.filename.replace(/\u0126/g, 'H'); // Ħ
  song.filename = song.filename.replace(/\u0127/g, 'H'); // ħ

  song.filename = song.filename.replace(/[\u201C-\u201D]/g, '"');
  song.filename = song.filename.replace('andamp;', '&');
  song.filename = song.filename.replace('#39;', `'`);
  song.filename = song.filename.replace('ʟᴜᴄᴀ ʟᴜsʜ', 'LUCA LUSH');
  song.filename = song.filename.replace('Re-Sauce', 'Remix');
  song.filename = song.filename.replace('Re-Crank', 'Remix');
  song.filename = song.filename.replace('Mixmag - Premiere-', 'Mixmag - ');
  song.filename = song.filename.replace('djmag - Premiere', 'djmag ');
  song.filename = song.filename.replace('1985  -  Music', '1985 Music');
  song.filename = song.filename.replace('+PRIME+', 'PRIME');
  song.filename = song.filename.replace(/[\u1400-\u167F\u1680-\u169F\u16A0-\u16FF\u1700-\u171F\u1720-\u173F\u1740-\u175F\u1760-\u177F\u1780-\u17FF\u1800-\u18AF\u1900-\u194F\u1950-\u197F\u1980-\u19DF\u19E0-\u19FF\u1A00-\u1A1F\u1B00-\u1B7F\u1D00-\u1D7F\u1D80-\u1DBF\u1DC0-\u1DFF\u1E00-\u1EFF\u1F00-\u1FFF\u2000-\u206F\u2070-\u209F\u20A0-\u20CF\u20D0-\u20FF\u2100-\u214F\u2150-\u218F\u2190-\u21FF\u2200-\u22FF\u2300-\u23FF\u2400-\u243F\u2440-\u245F\u2460-\u24FF\u2500-\u257F\u2580-\u259F\u25A0-\u25FF\u2600-\u26FF\u2700-\u27BF\u27C0-\u27EF\u27F0-\u27FF\u2800-\u28FF\u2900-\u297F\u2980-\u29FF\u2A00-\u2AFF\u2B00-\u2BFF\u2C00-\u2C5F\u2C60-\u2C7F\u2C80-\u2CFF\u2D00-\u2D2F\u2D30-\u2D7F\u2D80-\u2DDF\u2E00-\u2E7F\u2E80-\u2EFF\u2F00-\u2FDF\u2FF0-\u2FFF\u3000-\u303F\u3040-\u309F\u30A0-\u30FF\u3100-\u312F\u3130-\u318F\u3190-\u319F\u31A0-\u31BF\u31C0-\u31EF\u31F0-\u31FF\u3200-\u32FF\u3300-\u33FF\u3400-\u4DBF\u4DC0-\u4DFF\u4E00-\u9FFF\uA000-\uA48F\uA490-\uA4CF\uA700-\uA71F\uA720-\uA7FF\uA800-\uA82F\uA840-\uA87F\uAC00-\uD7AF\uD800-\uDB7F\uDB80-\uDBFF\uDC00-\uDFFF\uE000-\uF8FF\uF900-\uFAFF\uFB00-\uFB4F\uFB50-\uFDFF\uFE00-\uFE0F\uFE10-\uFE1F\uFE20-\uFE2F\uFE30-\uFE4F\uFE50-\uFE6F\uFE70-\uFEFF\uFF00-\uFFEF\uFFF0-\uFFFF]/g, '');

  // Channels
  song.filename.toUpperCase().includes('[FIRE') ? song.filename = song.filename.substring(0, song.filename.toUpperCase().indexOf('[FIRE') - 1).concat('.mp3') : song.filename;
  song.filename.toUpperCase().includes('NEVER SAY DIE - BLACK LABEL') ? song.filename = song.filename.replace('Never Say Die - Black Label', 'Never Say Die Black Label') : song.filename;

  song.filename = song.filename.replace(/ \(SUBLMNL .+\)/ig, '');

  song.filename = song.filename.replace(/ \(CIRCUS .+\)/ig, '');
  song.filename = song.filename.replace(/ \[COOKERZ]/ig, '');
  song.filename = song.filename.replace(/ \[.+ CROWSNEST\]/ig, '');
  song.filename = song.filename.replace(/ \[DS FREEBIE\]/ig, '');
  song.filename = song.filename.replace(/ \[ELECTROSTEP .+]/ig, '');
  song.filename = song.filename.replace(/ \(EATBRAIN.+\)/ig, '');
  song.filename = song.filename.replace(/ \[FOOLS GOLD]/ig, '');
  song.filename = song.filename.replace(/ \[GOOD ENUFF RELEASE\]/ig, '');
  song.filename = song.filename.replace(/ \(KILL THE COPYRIGHT RELEASE\)/ig, '');
  song.filename = song.filename.replace(/ \[JD4D .+\]/ig, '');
  song.filename = song.filename.replace(/ \(METHLAB .+\)/ig, '');
  song.filename = song.filename.replace(/ \[MONSTERCAT .+\]/ig, '');
  song.filename = song.filename.replace(/ \[NCS RELEASE\]/ig, '');
  song.filename = song.filename.replace(/ \[NEST.+\]/ig, '');
  song.filename = song.filename.replace(/ \(NEST .+\)/ig, '');
  song.filename = song.filename.replace(/ \{NSD BLACK LABEL\}/ig, '');
  song.filename = song.filename.replace(/ \[I AM SO HIGH.+\]/ig, '');
  song.filename = song.filename.replace(/ \[OTODAYO .+\]/ig, '');
  song.filename = song.filename.replace(/ \[PRIME AUDIO\]/ig, '');
  song.filename = song.filename.replace(/ \(RIDDIM NETWORK .+\)/ig, '');
  song.filename = song.filename.replace(/ \[ROTTUN .+\]/ig, '');
  song.filename = song.filename.replace(/ \(RNE\)/ig, '');
  song.filename = song.filename.replace(/ \[HT.+\]/ig, '');
  song.filename = song.filename.replace(/ \[THISSONGISSICK.+\]/ig, '');
  song.filename = song.filename.replace(/ \(TERMINAL\)/ig, '');

  // Genres
  song.filename = song.filename.replace(/ \[BASS\]/ig, '');
  song.filename = song.filename.replace(/ \[BASS HOUSE\]/ig, '');
  song.filename = song.filename.replace(/ \[CHILL TRAP\]/ig, '');
  song.filename = song.filename.replace(/ \[DNB\]/ig, '');
  song.filename = song.filename.replace(/ \[DRUM&BASS\]/ig, '');
  song.filename = song.filename.replace(/ \[DRUM & BASS\]/ig, '');
  song.filename = song.filename.replace(/ \[DRUM AND BASS\]/ig, '');
  song.filename = song.filename.replace(/ \[DRUMSTEP\]/ig, '');
  song.filename = song.filename.replace(/ \[DUBSTEP\]/ig, '');
  song.filename = song.filename.replace(/ \[EDM\]/ig, '');
  song.filename = song.filename.replace(/ \[ELECTRO\]/ig, '');
  song.filename = song.filename.replace(/ \[ELECTRONIC\]/ig, '');
  song.filename = song.filename.replace(/ \[ELECTRONICA\]/ig, '');
  song.filename = song.filename.replace(/ \[FREAKSTEP\]/ig, '');
  song.filename = song.filename.replace(/ \[FUTURE\]/ig, '');
  song.filename = song.filename.replace(/ \[FUTURE BASS\]/ig, '');
  song.filename = song.filename.replace(/ \[GLITCH HOP\]/ig, '');
  song.filename = song.filename.replace(/ \[HARD DANCE\]/ig, '');
  song.filename = song.filename.replace(/ \[HARDSTYLE TRAP\]/ig, '');
  song.filename = song.filename.replace(/ \[HIP HOP\]/ig, '');
  song.filename = song.filename.replace(/ \[HOUSE\]/ig, '');
  song.filename = song.filename.replace(/ \[HYBRID\]/ig, '');
  song.filename = song.filename.replace(/ \[JUNGLE TERROR\]/ig, '');
  song.filename = song.filename.replace(/ \[MELODIC DUBSTEP\]/ig, '');
  song.filename = song.filename.replace(/ \[NEURO TRAP\]/ig, '');
  song.filename = song.filename.replace(/ \[TRAP\]/ig, '');

  // Tags
  song.filename = song.filename.replace(/ \[ 360 VISUALIZER \]/ig, '');
  song.filename = song.filename.replace(/ \[360 VR VIDEO\]/ig, '');
  song.filename = song.filename.replace(/ \(1440P\)/ig, '');
  song.filename = song.filename.replace(/ \(AUDIO\)/ig, '');
  song.filename = song.filename.replace(/ \(AVAILABLE .+\)/ig, '');
  song.filename = song.filename.replace(/ \(BUY .+\)/ig, '');
  song.filename = song.filename.replace(/ \[BUY .+\]/ig, '');
  song.filename = song.filename.replace(/ \(CLICK BUY.+\)/ig, '');
  song.filename = song.filename.replace(/ \[CLICK BUY.+\]/ig, '');
  song.filename = song.filename.replace(/ \[DOWNLOAD .+\]/ig, '');
  song.filename = song.filename.replace(/ \(EXCLUSIVE\)/ig, '');
  song.filename = song.filename.replace(/ \[EXCLUSIVE\]/ig, '');
  song.filename = song.filename.replace(/ \[EXCLUSIVE .+\]/ig, '');
  song.filename = song.filename.replace(/ \[.+ EXCLUSIVE\]/ig, '');
  song.filename = song.filename.replace(/ \(.+ EXCLUSIVE\)/ig, '');
  song.filename = song.filename.replace(/ \(EXTENDED MIX\)/ig, '');
  song.filename = song.filename.replace(/ \(FINAL\)/ig, '');
  song.filename = song.filename.replace(/ \[FORTHCOMING .+\]/ig, '');
  song.filename = song.filename.replace(/ \[FREE\]/ig, '');
  song.filename = song.filename.replace(/ \(FREE\)/ig, '');
  song.filename = song.filename.replace(/ \(FREE .+\)/ig, '');
  song.filename = song.filename.replace(/ \[FREE .+\]/ig, '');
  song.filename = song.filename.replace(/ FREE DOWNLOAD/ig, '');
  song.filename = song.filename.replace(/ \[OFFICIAL\]/ig, '');
  song.filename = song.filename.replace(/ \(OFFICIAL\)/ig, '');
  song.filename = song.filename.replace(/ \(OFFICIAL .+\)/ig, '');
  song.filename = song.filename.replace(/ \{OFFICIAL .+\}/ig, '');
  song.filename = song.filename.replace(/ \[OFFICIAL .+\]/ig, '');
  song.filename = song.filename.replace(/ \(LYRIC VIDEO\)/ig, '');
  song.filename = song.filename.replace(/ \(MASTER\)/ig, '');
  song.filename = song.filename.replace(/ \(ORIGINAL MIX\)/ig, '');
  song.filename = song.filename.replace(/ \( ORIGINAL MIX \)/ig, '');
  song.filename = song.filename.replace(/ \[ORIGINAL MIX\]/ig, '');
  song.filename = song.filename.replace(/ \(OUT .+\)/ig, '');
  song.filename = song.filename.replace(/ \[OUT .+\]/ig, '');
  song.filename = song.filename.replace(/OUT NO.+/ig, '');
  song.filename = song.filename.replace(/ \[PREMIERE\]/ig, '');
  song.filename = song.filename.replace(/ \[.+ PREMIERE\]/ig, '');
  song.filename = song.filename.replace(/ \(.+ PREMIERE\)/ig, '');
  song.filename = song.filename.replace(/ \[REMASTER\]/ig, '');
  song.filename = song.filename.replace(/ \READ DESCRIPTION/ig, '');
  song.filename = song.filename.replace(/ \(RADIO EDIT\)/ig, '');
  // song.filename = song.filename.replace(/ \- SINGLE/ig, '');

  if (origFilename !== song.filename) {
    song.changed = true
  };

  return song;
}

export function checkRemix(Song) {
  let extension = Song.extension;

  if (/\(.+ REMIX\)/ig.test(Song.filename)) {
    Song.artist = Song.filename.slice(/\(.[^\(]+ REMIX\)/ig.exec(Song.filename).index + 1, / REMIX\)/ig.exec(Song.filename).index).trim().trimLeft();
    Song.filename = Song.filename.slice(0, /\(.[^\(]+ REMIX\)/ig.exec(Song.filename).index - 1).concat(extension);
    Song.remix = true;
    Song.changed = true;
  } else if (/\[.+ REMIX\]/ig.test(Song.filename)) {
    Song.artist = Song.filename.slice(/\[.[^\[]+ REMIX\]/ig.exec(Song.filename).index + 1, / REMIX\]/ig.exec(Song.filename).index).trim().trimLeft();
    Song.filename = Song.filename.slice(0, /\[.[^\[]+ REMIX\]/ig.exec(Song.filename).index - 1).concat(extension);
    Song.remix = true;
    Song.changed = true;
  } else if (/\(.+ REFIX\)/ig.test(Song.filename)) {
    Song.artist = Song.filename.slice(/\(.[^\(]+ REFIX\)/ig.exec(Song.filename).index + 1, / REFIX\)/ig.exec(Song.filename).index).trim().trimLeft();
    Song.filename = Song.filename.slice(0, /\(.[^\(]+ REFIX\)/ig.exec(Song.filename).index - 1).concat(extension);
    Song.remix = true;
    Song.changed = true;
  } else if (/\(.+ FLIP\)/ig.test(Song.filename)) {
    Song.artist = Song.filename.slice(/\(.[^\(]+ FLIP\)/ig.exec(Song.filename).index + 1, / FLIP\)/ig.exec(Song.filename).index).trim().trimLeft();
    Song.filename = Song.filename.slice(0, /\(.[^\(]+ FLIP\)/ig.exec(Song.filename).index - 1).concat(extension);
    Song.remix = true;
    Song.changed = true;
  } else if (/\[.+ FLIP\]/ig.test(Song.filename)) {
    Song.artist = Song.filename.slice(/\[.[^\[]+ FLIP\]/ig.exec(Song.filename).index + 1, / FLIP\]/ig.exec(Song.filename).index).trim().trimLeft();
    Song.filename = Song.filename.slice(0, /\[.[^\[]+ FLIP\]/ig.exec(Song.filename).index - 1).concat(extension);
    Song.remix = true;
    Song.changed = true;
  } else if (/\(.+ EDIT\)/ig.test(Song.filename)) {
    Song.artist = Song.filename.slice(/\(.[^\(]+ EDIT\)/ig.exec(Song.filename).index + 1, / EDIT\)/ig.exec(Song.filename).index).trim().trimLeft();
    Song.filename = Song.filename.slice(0, /\(.[^\(]+ EDIT\)/ig.exec(Song.filename).index - 1).concat(extension);
    Song.remix = true;
    Song.changed = true;
  } else if (/\[.+ EDIT\]/ig.test(Song.filename)) {
    Song.artist = Song.filename.slice(/\[.[^\[]+ EDIT\]/ig.exec(Song.filename).index + 1, / EDIT\]/ig.exec(Song.filename).index).trim().trimLeft();
    Song.filename = Song.filename.slice(0, /\[.[^\[]+ EDIT\]/ig.exec(Song.filename).index - 1).concat(extension);
    Song.remix = true;
    Song.changed = true;
  } else if (/\(.+ BOOTLEG\)/ig.test(Song.filename)) {
    Song.artist = Song.filename.slice(/\(.[^\(]+ BOOTLEG\)/ig.exec(Song.filename).index + 1, / BOOTLEG\)/ig.exec(Song.filename).index).trim().trimLeft();
    Song.filename = Song.filename.slice(0, /\(.[^\(]+ BOOTLEG\)/ig.exec(Song.filename).index - 1).concat(extension);
    Song.remix = true;
    Song.changed = true;
  } else if (/\(.+ EDITION\)/ig.test(Song.filename)) {
    Song.artist = Song.filename.slice(/\(.[^\(]+ EDITION\)/ig.exec(Song.filename).index + 1, / EDITION\)/ig.exec(Song.filename).index).trim().trimLeft();
    Song.filename = Song.filename.slice(0, /\(.[^\(]+ EDITION\)/ig.exec(Song.filename).index - 1).concat(extension);
    Song.remix = true;
    Song.changed = true;
  }

  if (Song.remix) {
    if (Song.count <= 1) {
      Song.album = grabFirst(Song.filename);
    } else {
      Song.album = grabSecond(Song.filename);
    }
    Song = removeAnd(Song, 'album');
  }

  return Song;
}

export function removeAnd(Song, type) {
  let origArtist = Song[type];

  Song[type] = Song[type].replace(/ & /g, ' x ');
  Song[type] = Song[type].replace(/ %26 /g, ' x ');
  Song[type] = Song[type].replace(/, /g, ' x ');
  Song[type] = Song[type].replace(/ X /ig, ' x ');
  Song[type] = Song[type].replace(/ and /ig, ' x ');
  Song[type] = Song[type].replace(/ \+ /ig, ' x ');

  if (origArtist !== Song[type]) {
    Song.changed = true;
  }

  return Song;
}

export function removeClip(title: string): string {
  if (title) {
    title = title.replace(/ \(CLIP\)/ig, '');
    title = title.replace(/ \( CLIP \)/ig, '');
    title = title.replace(/ \[CLIP\]/ig, '');
    title = title.replace(/ CLIP/ig, '');
  }

  return title;
}

export function checkDuplicate(song: Song, musicArr: Song[]): Song {
  if (song.filename.includes(' (1)')) {
    console.log(`***Duplicate: Check ${song.filename}***
        --------------------------------`);
    // fs.unlink(song.fullFilename);
    song.duplicate = true;
  }

  if (musicArr) {
    musicArr.forEach((file, index) => {
      if (file !== song && file.artist === song.artist && file.title === song.title) {
        console.log(`***Duplicate: ${song.artist} - ${song.title}***

------------------------------
`);
        // fs.unlink(song.fullFilename);
        song.duplicate = true;
      }
    });
  }

  return song;
}

export function checkWith(Song) {
  // W- is usually an artist. Adding it to artist with an x

  if (Song.artist.length > 0) {
    if (Song.filename.toUpperCase().includes('(W-')) {
      Song.artist += ` x ${Song.filename.slice(Song.filename.toUpperCase().indexOf('(W- ') + 4, Song.filename.lastIndexOf(Song.extension) - 1)}`;
      Song.filename = Song.filename.slice(0, Song.filename.toUpperCase().indexOf('(W-')).trim().concat(Song.extension);
      Song.changed = true;
    } else if (Song.filename.toUpperCase().includes('(WITH ')) {
      Song.artist += ` x ${Song.filename.slice(Song.filename.toUpperCase().indexOf('(WITH ') + 6, Song.filename.lastIndexOf(Song.extension) - 1)}`;
      Song.filename = Song.filename.slice(0, Song.filename.toUpperCase().indexOf('(WITH')).trim().concat(Song.extension);
      Song.changed = true;
    } else if (Song.filename.toUpperCase().includes('(W_')) {
      Song.artist += ` x ${Song.filename.slice(Song.filename.toUpperCase().indexOf('(W_ ') + 4, Song.filename.lastIndexOf(Song.extension) - 1)}`;
      Song.filename = Song.filename.slice(0, Song.filename.toUpperCase().indexOf('(W_')).trim().concat(Song.extension);
      Song.changed = true;
    } else if (Song.filename.toUpperCase().includes('W-')) {
      Song.artist += ` x ${Song.filename.slice(Song.filename.toUpperCase().indexOf('W- ') + 3, Song.filename.lastIndexOf(Song.extension))}`;
      Song.filename = Song.filename.slice(0, Song.filename.toUpperCase().indexOf('W-')).trim().concat(Song.extension);
      Song.changed = true;
    } else if (Song.filename.toUpperCase().includes('W_')) {
      Song.artist += ` x ${Song.filename.slice(Song.filename.toUpperCase().indexOf('W_ ') + 3, Song.filename.lastIndexOf(Song.extension))}`;
      Song.filename = Song.filename.slice(0, Song.filename.toUpperCase().indexOf('W_')).trim().concat(Song.extension);
      Song.changed = true;
    } else if (Song.filename.toUpperCase().includes(' W ')) {
      Song.artist += ` x ${Song.filename.slice(Song.filename.toUpperCase().indexOf(' W ') + 3, Song.filename.lastIndexOf(Song.extension))}`;
      Song.filename = Song.filename.slice(0, Song.filename.toUpperCase().indexOf(' W ')).trim().concat(Song.extension);
      Song.changed = true;
    }
  }

  return Song;
}

export function checkFeat(Song) {
  let featuringArtist;

  if (Song.filename.toUpperCase().includes('(FEAT.')) {
    if (Song.artist.toUpperCase().indexOf('(FEAT. ') > -1) {
      featuringArtist = Song.artist.slice(Song.artist.toUpperCase().indexOf('(FEAT. ') + 7, Song.artist.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      Song.artist = Song.artist.slice(0, Song.artist.toUpperCase().indexOf('(FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.title.toUpperCase().indexOf('(FEAT. ') > -1) {
      featuringArtist = Song.title.slice(Song.title.toUpperCase().indexOf('(FEAT. ') + 7, Song.title.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      Song.title = Song.title.slice(0, Song.title.toUpperCase().indexOf('(FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.album.toUpperCase().indexOf('(FEAT. ') > -1) {
      featuringArtist = Song.album.slice(Song.album.toUpperCase().indexOf('(FEAT. ') + 7, Song.album.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      Song.album = Song.album.slice(0, Song.album.toUpperCase().indexOf('(FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
  } else if (Song.filename.toUpperCase().includes('(FT.')) {
    if (Song.artist.toUpperCase().indexOf('(FT. ') > -1) {
      featuringArtist = Song.artist.slice(Song.artist.toUpperCase().indexOf('(FT. ') + 5, Song.artist.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      Song.artist = Song.artist.slice(0, Song.artist.toUpperCase().indexOf('(FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.title.toUpperCase().indexOf('(FT. ') > -1) {
      featuringArtist = Song.title.slice(Song.title.toUpperCase().indexOf('(FT. ') + 5, Song.title.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      Song.title = Song.title.slice(0, Song.title.toUpperCase().indexOf('(FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.album.toUpperCase().indexOf('(FT. ') > -1) {
      featuringArtist = Song.album.slice(Song.album.toUpperCase().indexOf('(FT. ') + 5, Song.album.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      Song.album = Song.album.slice(0, Song.album.toUpperCase().indexOf('(FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
  } else if (Song.filename.toUpperCase().includes('(FT ')) {
    if (Song.artist.toUpperCase().indexOf('(FT ') > -1) {
      featuringArtist = Song.artist.slice(Song.artist.toUpperCase().indexOf('(FT ') + 4, Song.artist.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      Song.artist = Song.artist.slice(0, Song.artist.toUpperCase().indexOf('(FT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.title.toUpperCase().indexOf('(FT ') > -1) {
      featuringArtist = Song.title.slice(Song.title.toUpperCase().indexOf('(FT ') + 4, Song.title.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      Song.title = Song.title.slice(0, Song.title.toUpperCase().indexOf('(FT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.album.toUpperCase().indexOf('(FT ') > -1) {
      featuringArtist = Song.album.slice(Song.album.toUpperCase().indexOf('(FT ') + 4, Song.album.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      Song.album = Song.album.slice(0, Song.album.toUpperCase().indexOf('(FT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
  } else if (Song.filename.toUpperCase().includes('[FT. ')) {
    if (Song.artist.toUpperCase().indexOf('[FT. ') > -1) {
      featuringArtist = Song.artist.slice(Song.artist.toUpperCase().indexOf('[FT. ') + 5, Song.artist.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      Song.artist = Song.artist.slice(0, Song.artist.toUpperCase().indexOf('[FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.title.toUpperCase().indexOf('[FT. ') > -1) {
      featuringArtist = Song.title.slice(Song.title.toUpperCase().indexOf('[FT. ') + 5, Song.title.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      Song.title = Song.title.slice(0, Song.title.toUpperCase().indexOf('[FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.album.toUpperCase().indexOf('[FT. ') > -1) {
      featuringArtist = Song.album.slice(Song.album.toUpperCase().indexOf('[FT. ') + 5, Song.album.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      Song.album = Song.album.slice(0, Song.album.toUpperCase().indexOf('[FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
  } else if (Song.filename.toUpperCase().includes('[FEAT. ')) {
    if (Song.artist.toUpperCase().indexOf('[FEAT. ') > -1) {
      featuringArtist = Song.artist.slice(Song.artist.toUpperCase().indexOf('[FEAT. ') + 7, Song.artist.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      Song.artist = Song.artist.slice(0, Song.artist.toUpperCase().indexOf('[FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.title.toUpperCase().indexOf('[FEAT. ') > -1) {
      featuringArtist = Song.title.slice(Song.title.toUpperCase().indexOf('[FEAT. ') + 7, Song.title.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      Song.title = Song.title.slice(0, Song.title.toUpperCase().indexOf('[FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.album.toUpperCase().indexOf('[FEAT. ') > -1) {
      featuringArtist = Song.album.slice(Song.album.toUpperCase().indexOf('[FEAT. ') + 7, Song.album.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      Song.album = Song.album.slice(0, Song.album.toUpperCase().indexOf('[FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
  } else if (Song.filename.toUpperCase().includes('(PROD. ')) {
    if (Song.artist.toUpperCase().indexOf('(PROD. ') > -1) {
      featuringArtist = Song.artist.slice(Song.artist.toUpperCase().indexOf('(PROD. ') + 7, Song.artist.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      Song.artist = Song.artist.slice(0, Song.artist.toUpperCase().indexOf('(PROD. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.title.toUpperCase().indexOf('(PROD. ') > -1) {
      featuringArtist = Song.title.slice(Song.title.toUpperCase().indexOf('(PROD. ') + 7, Song.title.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      Song.title = Song.title.slice(0, Song.title.toUpperCase().indexOf('(PROD. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.album.toUpperCase().indexOf('(PROD. ') > -1) {
      featuringArtist = Song.album.slice(Song.album.toUpperCase().indexOf('(PROD. ') + 7, Song.album.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      Song.album = Song.album.slice(0, Song.album.toUpperCase().indexOf('(PROD. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
  } else if (Song.filename.toUpperCase().includes('[PROD. ')) {
    if (Song.artist.toUpperCase().indexOf('[PROD. ') > -1) {
      featuringArtist = Song.artist.slice(Song.artist.toUpperCase().indexOf('[PROD. ') + 7, Song.artist.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      Song.artist = Song.artist.slice(0, Song.artist.toUpperCase().indexOf('[PROD. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.title.toUpperCase().indexOf('[PROD. ') > -1) {
      featuringArtist = Song.title.slice(Song.title.toUpperCase().indexOf('[PROD. ') + 7, Song.title.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      Song.title = Song.title.slice(0, Song.title.toUpperCase().indexOf('[PROD. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.album.toUpperCase().indexOf('[PROD. ') > -1) {
      featuringArtist = Song.album.slice(Song.album.toUpperCase().indexOf('[PROD. ') + 7, Song.album.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      Song.album = Song.album.slice(0, Song.album.toUpperCase().indexOf('[PROD. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
  } else if (Song.filename.toUpperCase().includes('FEAT.')) {
    if (Song.artist.toUpperCase().indexOf('FEAT. ') > -1) {
      featuringArtist = Song.artist.slice(Song.artist.toUpperCase().indexOf('FEAT. ') + 6);
      Song.artist = Song.artist.slice(0, Song.artist.toUpperCase().indexOf('FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.title.toUpperCase().indexOf('FEAT. ') > -1) {
      featuringArtist = Song.title.slice(Song.title.toUpperCase().indexOf('FEAT. ') + 6);
      Song.title = Song.title.slice(0, Song.title.toUpperCase().indexOf('FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.album.toUpperCase().indexOf('FEAT. ') > -1) {
      featuringArtist = Song.album.slice(Song.album.toUpperCase().indexOf('FEAT. ') + 6);
      Song.album = Song.album.slice(0, Song.album.toUpperCase().indexOf('FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
  } else if (Song.filename.toUpperCase().includes('FT.') && !Song.filename.toUpperCase().includes(`FT${Song.extension.toUpperCase()}`)) {
    if (Song.artist.toUpperCase().indexOf('FT. ') > -1) {
      featuringArtist = Song.artist.slice(Song.artist.toUpperCase().indexOf('FT. ') + 4);
      Song.artist = Song.artist.slice(0, Song.artist.toUpperCase().indexOf('FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.title.toUpperCase().indexOf('FT. ') > -1) {
      featuringArtist = Song.title.slice(Song.title.toUpperCase().indexOf('FT. ') + 4);
      Song.title = Song.title.slice(0, Song.title.toUpperCase().indexOf('FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.album.toUpperCase().indexOf('FT. ') > -1) {
      featuringArtist = Song.album.slice(Song.album.toUpperCase().indexOf('FT. ') + 4);
      Song.album = Song.album.slice(0, Song.album.toUpperCase().indexOf('FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
  } else if (Song.filename.toUpperCase().includes(' FT ')) {
    if (Song.artist.toUpperCase().indexOf(' FT ') > -1) {
      featuringArtist = Song.artist.slice(Song.artist.toUpperCase().indexOf(' FT ') + 4);
      Song.artist = Song.artist.slice(0, Song.artist.toUpperCase().indexOf(' FT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.title.toUpperCase().indexOf(' FT ') > -1) {
      featuringArtist = Song.title.slice(Song.title.toUpperCase().indexOf(' FT ') + 4);
      Song.title = Song.title.slice(0, Song.title.toUpperCase().indexOf(' FT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.album.toUpperCase().indexOf(' FT ') > -1) {
      featuringArtist = Song.album.slice(Song.album.toUpperCase().indexOf(' FT ') + 4);
      Song.album = Song.album.slice(0, Song.album.toUpperCase().indexOf(' FT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
  } else if (Song.filename.toUpperCase().includes(' FEAT ')) {
    if (Song.artist.toUpperCase().indexOf(' FEAT ') > -1) {
      featuringArtist = Song.artist.slice(Song.artist.toUpperCase().indexOf(' FEAT ') + 6);
      Song.artist = Song.artist.slice(0, Song.artist.toUpperCase().indexOf(' FEAT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.title.toUpperCase().indexOf(' FEAT ') > -1) {
      featuringArtist = Song.title.slice(Song.title.toUpperCase().indexOf(' FEAT ') + 6);
      Song.title = Song.title.slice(0, Song.title.toUpperCase().indexOf(' FEAT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
    if (Song.album.toUpperCase().indexOf(' FEAT ') > -1) {
      featuringArtist = Song.album.slice(Song.album.toUpperCase().indexOf(' FEAT ') + 6);
      Song.album = Song.album.slice(0, Song.album.toUpperCase().indexOf(' FEAT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
      Song.changed = true;
    }
  }

  if (Song.remix && featuringArtist) {
    Song.album += ` x ${featuringArtist}`;
  } else if (featuringArtist) {
    Song.artist += ` x ${featuringArtist}`;
  }

  return Song;
}

export function lastCheck(Song): Song {
  if (Song.filename.includes('Track of the Day- ')) {
    Song.album = Song.artist;
    Song.artist = Song.filename.slice(Song.filename.lastIndexOf('- ') + 2, Song.filename.indexOf('"')).trim().trimLeft();
    Song.title = Song.filename.slice(Song.filename.indexOf('"') + 1, Song.filename.lastIndexOf('"')).trim().trimLeft();
    Song.count = 2;
  }
  if (Song.title.indexOf('[') > -1 && Song.title.toUpperCase().indexOf('VIP') === -1 && Song.title.toUpperCase().indexOf('WIP') === -1 && Song.title.toUpperCase().indexOf('CLIP') === -1) {
    console.log(`Title: ${Song.title}`);
    Song.title = Song.title.slice(0, Song.title.indexOf('[')).trim().trimLeft();
  }
  if (Song.artist.indexOf('[') > -1) {
    console.log(`Artist: ${Song.artist}`);
    Song.artist = Song.artist.slice(0, Song.artist.indexOf('[')).trim().trimLeft();
  }
  if (Song.album.indexOf('[') > -1) {
    console.log(`Album: ${Song.album}`);
    Song.album = Song.album.slice(0, Song.album.indexOf('[')).trim().trimLeft();
  }

  if (Song.title.indexOf('(') > -1 && Song.title.toUpperCase().indexOf('VIP') === -1 && Song.title.toUpperCase().indexOf('WIP') === -1 && Song.title.toUpperCase().indexOf('CLIP') === -1) {
    console.log(`Title: ${Song.title}`);
    Song.title = Song.title.slice(0, Song.title.indexOf('(')).trim().trimLeft();
  }
  if (Song.artist.indexOf('(') > -1) {
    console.log(`Artist: ${Song.artist}`);
  }
  if (Song.album.indexOf('(') > -1) {
    console.log(`Album: ${Song.album}`);
  }

  return Song;
}