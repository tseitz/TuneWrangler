// import * as fs from 'fs';
// import * as path from 'path';
import { LocalSong, Song, DownloadedSong } from './models/Song';

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

export function cacheMusic(files: string[], dir: string): LocalSong[] {
  const cache: LocalSong[] = [];

  // lots of songs, so fast for loop
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

  // song.filename = song.filename.replace('andamp;', '&');
  // song.filename = song.filename.replace('#39;', `'`);

  // Name fixes
  song.filename = song.filename.replace('ʟᴜᴄᴀ ʟᴜsʜ', 'LUCA LUSH');
  song.filename = song.filename.replace('Re-Sauce', 'Remix');
  song.filename = song.filename.replace('Re-Crank', 'Remix');
  song.filename = song.filename.replace('Mixmag - Premiere-', 'Mixmag - ');
  song.filename = song.filename.replace('1985  -  Music', '1985 Music');
  song.filename = song.filename.replace('+PRIME+', 'PRIME');
  song.filename = song.filename.replace('Premiere  ', '');

  // Channels
  song.filename = song.filename.toUpperCase().includes('[FIRE') ? song.filename.substring(0, song.filename.toUpperCase().indexOf('[FIRE') - 1).concat('.mp3') : song.filename;
  song.filename = song.filename.includes('NEVER SAY DIE - BLACK LABEL') ? song.filename.replace('Never Say Die - Black Label', 'Never Say Die Black Label') : song.filename;
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
  song.filename = song.filename.replace(/ READ DESCRIPTION/ig, '');
  song.filename = song.filename.replace(/ \(RADIO EDIT\)/ig, '');

  if (origFilename !== song.filename) {
    song.changed = true;
  }

  return song;
}

export function checkRemix(song: Song): Song {
  const origArtist = song.artist;

  if (/\(.+ REMIX\)/ig.test(song.filename)) {
    const regex = /\(.[^\(]+ REMIX\)/ig;
    song.artist = song.filename.slice(regex.exec(song.filename).index + 1, / REMIX\)/ig.exec(song.filename).index).trim().trimLeft();
    song.filename = song.filename.slice(0, /\(.[^\(]+ REMIX\)/ig.exec(song.filename).index - 1).concat(song.extension);
  } else if (/\[.+ REMIX\]/ig.test(song.filename)) {
    song.artist = song.filename.slice(/\[.[^\[]+ REMIX\]/ig.exec(song.filename).index + 1, / REMIX\]/ig.exec(song.filename).index).trim().trimLeft();
    song.filename = song.filename.slice(0, /\[.[^\[]+ REMIX\]/ig.exec(song.filename).index - 1).concat(song.extension);
  } else if (/\(.+ REFIX\)/ig.test(song.filename)) {
    song.artist = song.filename.slice(/\(.[^\(]+ REFIX\)/ig.exec(song.filename).index + 1, / REFIX\)/ig.exec(song.filename).index).trim().trimLeft();
    song.filename = song.filename.slice(0, /\(.[^\(]+ REFIX\)/ig.exec(song.filename).index - 1).concat(song.extension);
  } else if (/\(.+ FLIP\)/ig.test(song.filename)) {
    song.artist = song.filename.slice(/\(.[^\(]+ FLIP\)/ig.exec(song.filename).index + 1, / FLIP\)/ig.exec(song.filename).index).trim().trimLeft();
    song.filename = song.filename.slice(0, /\(.[^\(]+ FLIP\)/ig.exec(song.filename).index - 1).concat(song.extension);
  } else if (/\[.+ FLIP\]/ig.test(song.filename)) {
    song.artist = song.filename.slice(/\[.[^\[]+ FLIP\]/ig.exec(song.filename).index + 1, / FLIP\]/ig.exec(song.filename).index).trim().trimLeft();
    song.filename = song.filename.slice(0, /\[.[^\[]+ FLIP\]/ig.exec(song.filename).index - 1).concat(song.extension);
  } else if (/\(.+ EDIT\)/ig.test(song.filename)) {
    song.artist = song.filename.slice(/\(.[^\(]+ EDIT\)/ig.exec(song.filename).index + 1, / EDIT\)/ig.exec(song.filename).index).trim().trimLeft();
    song.filename = song.filename.slice(0, /\(.[^\(]+ EDIT\)/ig.exec(song.filename).index - 1).concat(song.extension);
  } else if (/\[.+ EDIT\]/ig.test(song.filename)) {
    song.artist = song.filename.slice(/\[.[^\[]+ EDIT\]/ig.exec(song.filename).index + 1, / EDIT\]/ig.exec(song.filename).index).trim().trimLeft();
    song.filename = song.filename.slice(0, /\[.[^\[]+ EDIT\]/ig.exec(song.filename).index - 1).concat(song.extension);
  } else if (/\(.+ BOOTLEG\)/ig.test(song.filename)) {
    song.artist = song.filename.slice(/\(.[^\(]+ BOOTLEG\)/ig.exec(song.filename).index + 1, / BOOTLEG\)/ig.exec(song.filename).index).trim().trimLeft();
    song.filename = song.filename.slice(0, /\(.[^\(]+ BOOTLEG\)/ig.exec(song.filename).index - 1).concat(song.extension);
  } else if (/\(.+ EDITION\)/ig.test(song.filename)) {
    song.artist = song.filename.slice(/\(.[^\(]+ EDITION\)/ig.exec(song.filename).index + 1, / EDITION\)/ig.exec(song.filename).index).trim().trimLeft();
    song.filename = song.filename.slice(0, /\(.[^\(]+ EDITION\)/ig.exec(song.filename).index - 1).concat(song.extension);
  }

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
  title = title.replace(/ \(CLIP\)/ig, '');
  title = title.replace(/ \( CLIP \)/ig, '');
  title = title.replace(/ \[CLIP\]/ig, '');
  title = title.replace(/ CLIP/ig, '');

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
    for (let i = 0, len = musicArr.length; i < len; i++) {
      const file = musicArr[i];
      if (file !== song && file.artist === song.artist && file.title === song.title) {
        console.log(`***Duplicate: ${song.artist} - ${song.title}***
  
  ------------------------------
  `);
        // fs.unlink(song.fullFilename);
        song.duplicate = true;
      }
    }
  }

  return song;
}

export function checkWith(song: Song): Song {
  // W- is usually an artist. Adding it to artist with an x
  const origArtist = song.artist;

  if (song.artist.length > 0) {
    if (song.filename.toUpperCase().includes('(W-')) {
      song.artist += ` x ${song.filename.slice(song.filename.toUpperCase().indexOf('(W- ') + 4, song.filename.lastIndexOf(song.extension) - 1)}`;
      song.filename = song.filename.slice(0, song.filename.toUpperCase().indexOf('(W-')).trim().concat(song.extension);
    } else if (song.filename.toUpperCase().includes('(WITH ')) {
      song.artist += ` x ${song.filename.slice(song.filename.toUpperCase().indexOf('(WITH ') + 6, song.filename.lastIndexOf(song.extension) - 1)}`;
      song.filename = song.filename.slice(0, song.filename.toUpperCase().indexOf('(WITH')).trim().concat(song.extension);
    } else if (song.filename.toUpperCase().includes('(W_')) {
      song.artist += ` x ${song.filename.slice(song.filename.toUpperCase().indexOf('(W_ ') + 4, song.filename.lastIndexOf(song.extension) - 1)}`;
      song.filename = song.filename.slice(0, song.filename.toUpperCase().indexOf('(W_')).trim().concat(song.extension);
    } else if (song.filename.toUpperCase().includes('W-')) {
      song.artist += ` x ${song.filename.slice(song.filename.toUpperCase().indexOf('W- ') + 3, song.filename.lastIndexOf(song.extension))}`;
      song.filename = song.filename.slice(0, song.filename.toUpperCase().indexOf('W-')).trim().concat(song.extension);
    } else if (song.filename.toUpperCase().includes('W_')) {
      song.artist += ` x ${song.filename.slice(song.filename.toUpperCase().indexOf('W_ ') + 3, song.filename.lastIndexOf(song.extension))}`;
      song.filename = song.filename.slice(0, song.filename.toUpperCase().indexOf('W_')).trim().concat(song.extension);
    } else if (song.filename.toUpperCase().includes(' W ')) {
      song.artist += ` x ${song.filename.slice(song.filename.toUpperCase().indexOf(' W ') + 3, song.filename.lastIndexOf(song.extension))}`;
      song.filename = song.filename.slice(0, song.filename.toUpperCase().indexOf(' W ')).trim().concat(song.extension);
    }
  }

  if (song.artist !== origArtist) {
    song.changed = true;
  }

  return song;
}

export function checkFeat(song: Song): Song {
  let featuringArtist;
  const origArtist = song.artist;
  const origTitle = song.title;
  const origAlbum = song.album;

  if (song.filename.toUpperCase().includes('(FEAT.')) {
    if (song.artist.toUpperCase().indexOf('(FEAT. ') > -1) {
      featuringArtist = song.artist.slice(song.artist.toUpperCase().indexOf('(FEAT. ') + 7, song.artist.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      song.artist = song.artist.slice(0, song.artist.toUpperCase().indexOf('(FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.title.toUpperCase().indexOf('(FEAT. ') > -1) {
      featuringArtist = song.title.slice(song.title.toUpperCase().indexOf('(FEAT. ') + 7, song.title.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      song.title = song.title.slice(0, song.title.toUpperCase().indexOf('(FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.album.toUpperCase().indexOf('(FEAT. ') > -1) {
      featuringArtist = song.album.slice(song.album.toUpperCase().indexOf('(FEAT. ') + 7, song.album.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      song.album = song.album.slice(0, song.album.toUpperCase().indexOf('(FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
  } else if (song.filename.toUpperCase().includes('(FT.')) {
    if (song.artist.toUpperCase().indexOf('(FT. ') > -1) {
      featuringArtist = song.artist.slice(song.artist.toUpperCase().indexOf('(FT. ') + 5, song.artist.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      song.artist = song.artist.slice(0, song.artist.toUpperCase().indexOf('(FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.title.toUpperCase().indexOf('(FT. ') > -1) {
      featuringArtist = song.title.slice(song.title.toUpperCase().indexOf('(FT. ') + 5, song.title.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      song.title = song.title.slice(0, song.title.toUpperCase().indexOf('(FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.album.toUpperCase().indexOf('(FT. ') > -1) {
      featuringArtist = song.album.slice(song.album.toUpperCase().indexOf('(FT. ') + 5, song.album.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      song.album = song.album.slice(0, song.album.toUpperCase().indexOf('(FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
  } else if (song.filename.toUpperCase().includes('(FT ')) {
    if (song.artist.toUpperCase().indexOf('(FT ') > -1) {
      featuringArtist = song.artist.slice(song.artist.toUpperCase().indexOf('(FT ') + 4, song.artist.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      song.artist = song.artist.slice(0, song.artist.toUpperCase().indexOf('(FT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.title.toUpperCase().indexOf('(FT ') > -1) {
      featuringArtist = song.title.slice(song.title.toUpperCase().indexOf('(FT ') + 4, song.title.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      song.title = song.title.slice(0, song.title.toUpperCase().indexOf('(FT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.album.toUpperCase().indexOf('(FT ') > -1) {
      featuringArtist = song.album.slice(song.album.toUpperCase().indexOf('(FT ') + 4, song.album.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      song.album = song.album.slice(0, song.album.toUpperCase().indexOf('(FT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
  } else if (song.filename.toUpperCase().includes('[FT. ')) {
    if (song.artist.toUpperCase().indexOf('[FT. ') > -1) {
      featuringArtist = song.artist.slice(song.artist.toUpperCase().indexOf('[FT. ') + 5, song.artist.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      song.artist = song.artist.slice(0, song.artist.toUpperCase().indexOf('[FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.title.toUpperCase().indexOf('[FT. ') > -1) {
      featuringArtist = song.title.slice(song.title.toUpperCase().indexOf('[FT. ') + 5, song.title.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      song.title = song.title.slice(0, song.title.toUpperCase().indexOf('[FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.album.toUpperCase().indexOf('[FT. ') > -1) {
      featuringArtist = song.album.slice(song.album.toUpperCase().indexOf('[FT. ') + 5, song.album.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      song.album = song.album.slice(0, song.album.toUpperCase().indexOf('[FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
  } else if (song.filename.toUpperCase().includes('[FEAT. ')) {
    if (song.artist.toUpperCase().indexOf('[FEAT. ') > -1) {
      featuringArtist = song.artist.slice(song.artist.toUpperCase().indexOf('[FEAT. ') + 7, song.artist.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      song.artist = song.artist.slice(0, song.artist.toUpperCase().indexOf('[FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.title.toUpperCase().indexOf('[FEAT. ') > -1) {
      featuringArtist = song.title.slice(song.title.toUpperCase().indexOf('[FEAT. ') + 7, song.title.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      song.title = song.title.slice(0, song.title.toUpperCase().indexOf('[FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.album.toUpperCase().indexOf('[FEAT. ') > -1) {
      featuringArtist = song.album.slice(song.album.toUpperCase().indexOf('[FEAT. ') + 7, song.album.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      song.album = song.album.slice(0, song.album.toUpperCase().indexOf('[FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
  } else if (song.filename.toUpperCase().includes('(PROD. ')) {
    if (song.artist.toUpperCase().indexOf('(PROD. ') > -1) {
      featuringArtist = song.artist.slice(song.artist.toUpperCase().indexOf('(PROD. ') + 7, song.artist.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      song.artist = song.artist.slice(0, song.artist.toUpperCase().indexOf('(PROD. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.title.toUpperCase().indexOf('(PROD. ') > -1) {
      featuringArtist = song.title.slice(song.title.toUpperCase().indexOf('(PROD. ') + 7, song.title.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      song.title = song.title.slice(0, song.title.toUpperCase().indexOf('(PROD. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.album.toUpperCase().indexOf('(PROD. ') > -1) {
      featuringArtist = song.album.slice(song.album.toUpperCase().indexOf('(PROD. ') + 7, song.album.toUpperCase().lastIndexOf(')')).trim().trimLeft();
      song.album = song.album.slice(0, song.album.toUpperCase().indexOf('(PROD. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
  } else if (song.filename.toUpperCase().includes('[PROD. ')) {
    if (song.artist.toUpperCase().indexOf('[PROD. ') > -1) {
      featuringArtist = song.artist.slice(song.artist.toUpperCase().indexOf('[PROD. ') + 7, song.artist.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      song.artist = song.artist.slice(0, song.artist.toUpperCase().indexOf('[PROD. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.title.toUpperCase().indexOf('[PROD. ') > -1) {
      featuringArtist = song.title.slice(song.title.toUpperCase().indexOf('[PROD. ') + 7, song.title.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      song.title = song.title.slice(0, song.title.toUpperCase().indexOf('[PROD. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.album.toUpperCase().indexOf('[PROD. ') > -1) {
      featuringArtist = song.album.slice(song.album.toUpperCase().indexOf('[PROD. ') + 7, song.album.toUpperCase().lastIndexOf(']')).trim().trimLeft();
      song.album = song.album.slice(0, song.album.toUpperCase().indexOf('[PROD. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
  } else if (song.filename.toUpperCase().includes('FEAT.')) {
    if (song.artist.toUpperCase().indexOf('FEAT. ') > -1) {
      featuringArtist = song.artist.slice(song.artist.toUpperCase().indexOf('FEAT. ') + 6);
      song.artist = song.artist.slice(0, song.artist.toUpperCase().indexOf('FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.title.toUpperCase().indexOf('FEAT. ') > -1) {
      featuringArtist = song.title.slice(song.title.toUpperCase().indexOf('FEAT. ') + 6);
      song.title = song.title.slice(0, song.title.toUpperCase().indexOf('FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.album.toUpperCase().indexOf('FEAT. ') > -1) {
      featuringArtist = song.album.slice(song.album.toUpperCase().indexOf('FEAT. ') + 6);
      song.album = song.album.slice(0, song.album.toUpperCase().indexOf('FEAT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
  } else if (song.filename.toUpperCase().includes('FT.') && !song.filename.toUpperCase().includes(`FT${song.extension.toUpperCase()}`)) {
    if (song.artist.toUpperCase().indexOf('FT. ') > -1) {
      featuringArtist = song.artist.slice(song.artist.toUpperCase().indexOf('FT. ') + 4);
      song.artist = song.artist.slice(0, song.artist.toUpperCase().indexOf('FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.title.toUpperCase().indexOf('FT. ') > -1) {
      featuringArtist = song.title.slice(song.title.toUpperCase().indexOf('FT. ') + 4);
      song.title = song.title.slice(0, song.title.toUpperCase().indexOf('FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.album.toUpperCase().indexOf('FT. ') > -1) {
      featuringArtist = song.album.slice(song.album.toUpperCase().indexOf('FT. ') + 4);
      song.album = song.album.slice(0, song.album.toUpperCase().indexOf('FT. ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
  } else if (song.filename.toUpperCase().includes(' FT ')) {
    if (song.artist.toUpperCase().indexOf(' FT ') > -1) {
      featuringArtist = song.artist.slice(song.artist.toUpperCase().indexOf(' FT ') + 4);
      song.artist = song.artist.slice(0, song.artist.toUpperCase().indexOf(' FT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.title.toUpperCase().indexOf(' FT ') > -1) {
      featuringArtist = song.title.slice(song.title.toUpperCase().indexOf(' FT ') + 4);
      song.title = song.title.slice(0, song.title.toUpperCase().indexOf(' FT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.album.toUpperCase().indexOf(' FT ') > -1) {
      featuringArtist = song.album.slice(song.album.toUpperCase().indexOf(' FT ') + 4);
      song.album = song.album.slice(0, song.album.toUpperCase().indexOf(' FT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
  } else if (song.filename.toUpperCase().includes(' FEAT ')) {
    if (song.artist.toUpperCase().indexOf(' FEAT ') > -1) {
      featuringArtist = song.artist.slice(song.artist.toUpperCase().indexOf(' FEAT ') + 6);
      song.artist = song.artist.slice(0, song.artist.toUpperCase().indexOf(' FEAT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.title.toUpperCase().indexOf(' FEAT ') > -1) {
      featuringArtist = song.title.slice(song.title.toUpperCase().indexOf(' FEAT ') + 6);
      song.title = song.title.slice(0, song.title.toUpperCase().indexOf(' FEAT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
    if (song.album.toUpperCase().indexOf(' FEAT ') > -1) {
      featuringArtist = song.album.slice(song.album.toUpperCase().indexOf(' FEAT ') + 6);
      song.album = song.album.slice(0, song.album.toUpperCase().indexOf(' FEAT ')).trim().trimLeft();
      console.log(`Feat: ${featuringArtist}`);
    }
  }

  if (song.album !== origAlbum || song.artist !== origArtist || song.title !== origTitle) {
    song.changed = true;
    
    // if it's a remix, the featuring artist belongs to the original artist (which is labeled the album)
    if (featuringArtist && song.remix) {
      song.album += ` x ${featuringArtist}`;
    } else if (featuringArtist) { // otherwise add the feature to the artist
      song.artist += ` x ${featuringArtist}`;
    }
  }

  return song;
}

export function lastCheck(song: Song): Song {
  if (song.filename.includes('Track of the Day- ')) {
    song.album = song.artist;
    song.artist = song.filename.slice(song.filename.lastIndexOf('- ') + 2, song.filename.indexOf('"')).trim().trimLeft();
    song.title = song.filename.slice(song.filename.indexOf('"') + 1, song.filename.lastIndexOf('"')).trim().trimLeft();
    song.dashCount = 2;
  }
  if (song.title.includes('[') && 
    !song.title.toUpperCase().includes('VIP') &&
    !song.title.toUpperCase().includes('WIP') &&
    !song.title.toUpperCase().includes('CLIP') &&
    !song.title.toUpperCase().includes('INSTRUMENTAL')
  ) {
    console.log(`Title: ${song.title}`);
    song.title = song.title.slice(0, song.title.indexOf('[')).trim().trimLeft();
  }
  if (song.artist.includes('[')) {
    console.log(`Artist: ${song.artist}`);
    song.artist = song.artist.slice(0, song.artist.indexOf('[')).trim().trimLeft();
  }
  if (song.album.includes('[')) {
    console.log(`Album: ${song.album}`);
    song.album = song.album.slice(0, song.album.indexOf('[')).trim().trimLeft();
  }

  if (song.title.includes('(') && 
    !song.title.toUpperCase().includes('VIP') && 
    !song.title.toUpperCase().includes('WIP') && 
    !song.title.toUpperCase().includes('CLIP') &&
    !song.title.toUpperCase().includes('REPRISE')
  ) {
    console.log(`Title: ${song.title}`);
    song.title = song.title.slice(0, song.title.indexOf('(')).trim().trimLeft();
  }
  if (song.artist.includes('(')) {
    console.log(`Artist: ${song.artist}`);
  }
  if (song.album.includes('(')) {
    console.log(`Album: ${song.album}`);
  }

  return song;
}