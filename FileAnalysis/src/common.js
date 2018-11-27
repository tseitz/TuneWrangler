'use strict';

// When artist - title, album is still in metadata

const fs = require('fs');
const path = require('path')

function checkOS(type) {
    let currDir;

    if (type === 'transfer') {
        if (process.env.OS === 'Windows_NT') {
            currDir = 'F:\\Dropbox\\TransferMusic\\';
        } else {
            currDir = '/Users/tseitz10/Dropbox/TransferMusic/';
        }
    } else if (type === 'music') {
        if (process.env.OS === 'Windows_NT') {
            currDir = 'F:\\Dropbox\\Music\\';
        } else {
            currDir = '/Users/tseitz10/Dropbox/Music/';
        }
    } else if (type === 'downloads') {
        if (process.env.OS === 'Windows_NT') {
            currDir = 'C:\\Users\\Scooter\\Downloads\\';
        } else {
            currDir = '/Users/tseitz10/Downloads/';
        }
    } else if (type === 'playlists') {
        if (process.env.OS === 'Windows_NT') {
            currDir = 'F:\\Dropbox\\MediaMonkeyPlaylists\\';
        } else {
            currDir = '/Users/tseitz10/Dropbox/MediaMonkeyPlaylists/';
        }
    }

    return currDir;
}

function newSong(filename, directory) {
    let Song = {
        artist: '',
        album: '',
        title: '',
        extension: grabExtension(filename),
        count: countDash(filename),
        filename: filename,
        fullFilename: `${directory}${filename}`,
        remix: false,
        changed: false,
        duplicate: false
    };

    return Song;
}

function formatLocalSong(filename, dir) {
    let Song = newSong(filename, dir);

    Song.artist = grabFirst(Song.filename);
    Song.album = grabSecond(Song.filename);
    Song.title = grabThird(Song.filename);
    Song.rating = grabLast(Song.filename);

    if (!parseInt(Song.rating, 10)) {
        Song.rating = 0;
    }

    return Song;
}

function formatDownloadedSong(filename, dir) {
    let Song = newSong(filename, dir);

    Song.artist = grabSecond(Song.filename);
    Song.album = grabFirst(Song.filename);
    Song.title = grabLast(Song.filename);

    return Song;
}

function cacheMusic(files, dir) {
    let cache = [];

    files.forEach((filename, index) => {
        let Song = formatLocalSong(filename, dir);
        cache.push(Song);
    });

    return cache;
}

function countDash(filename) {
    // filename length - filename length without dash = number of dashes / 3 characters per dash
    return filename.split(' - ').length - 1;
}


function grabFirst(filename) {
    return filename = filename.split(' - ')[0].trim().trimLeft();
}

function grabSecond(filename) {
    let second = '';

    if (filename.split(' - ')[1]) {
        second = filename.split(' - ')[1].trim().trimLeft();
    }

    // YouTube naming Artist - Topic
    if (second.trim().trimLeft() === 'Topic' && !filename.includes('Various Artists')) {
        second = grabFirst(filename);
    }

    return second;
}

function grabThird(filename) {
    return filename = filename.split(' - ')[2];
}

function grabLast(filename) {
    if (!filename.includes('-')) { return filename.slice(0, filename.lastIndexOf('.')).trim().trimLeft() };

    return filename.slice(filename.lastIndexOf(' - ') + 3, filename.lastIndexOf('.')).trim().trimLeft();
}

function grabExtension(filename) {
    return path.extname(filename) || undefined;
}

function splitArtist(artist) {
    // check when Bonnie x Clyde etc.
    let artistArr = artist.split ? artist.split(' x ') : [];

    return artistArr;
}

function removeBadCharacters(Song) {
    let origFilename = Song.filename;

    Song.filename = Song.filename.replace('\u3010', '['); // 【
    Song.filename = Song.filename.replace('\u3011', '] '); // 】
    Song.filename = Song.filename.replace('\u2768', '['); // ❨
    Song.filename = Song.filename.replace('\u2769', ']'); // ❩
    Song.filename = Song.filename.replace('\u2770', '['); // ❰
    Song.filename = Song.filename.replace('\u2771', ']'); // ❱
    Song.filename = Song.filename.replace('\u2716', 'x'); // ✖
    Song.filename = Song.filename.replace('\u2718', 'x');
    Song.filename = Song.filename.replace(/\u00DC/, 'U'); // Ü
    Song.filename = Song.filename.replace(/\u00FC/g, 'u'); // ü
    Song.filename = Song.filename.replace(/\u016B/g, 'u'); // ū
    Song.filename = Song.filename.replace(/\u014d/g, 'o'); // ō
    Song.filename = Song.filename.replace(/\u00f3/g, 'o'); // ó
    Song.filename = Song.filename.replace(/\u00D8/g, 'o'); // Ø
    Song.filename = Song.filename.replace(/\u00f8/g, 'o'); // ø
    Song.filename = Song.filename.replace(/\u0126/g, 'H'); // Ħ
    Song.filename = Song.filename.replace(/\u0127/g, 'H'); // ħ

    Song.filename = Song.filename.replace(/[\u201C-\u201D]/g, '"');
    Song.filename = Song.filename.replace('andamp;', '&');
    Song.filename = Song.filename.replace('#39;', `'`);
    Song.filename = Song.filename.replace('ʟᴜᴄᴀ ʟᴜsʜ', 'LUCA LUSH');
    Song.filename = Song.filename.replace('Re-Sauce', 'Remix');
    Song.filename = Song.filename.replace('Re-Crank', 'Remix');
    Song.filename = Song.filename.replace('Mixmag - Premiere-', 'Mixmag - ');
    Song.filename = Song.filename.replace('djmag - Premiere', 'djmag ');
    Song.filename = Song.filename.replace('1985  -  Music', '1985 Music');
    Song.filename = Song.filename.replace('+PRIME+', 'PRIME');
    Song.filename = Song.filename.replace(/[\u1400-\u167F\u1680-\u169F\u16A0-\u16FF\u1700-\u171F\u1720-\u173F\u1740-\u175F\u1760-\u177F\u1780-\u17FF\u1800-\u18AF\u1900-\u194F\u1950-\u197F\u1980-\u19DF\u19E0-\u19FF\u1A00-\u1A1F\u1B00-\u1B7F\u1D00-\u1D7F\u1D80-\u1DBF\u1DC0-\u1DFF\u1E00-\u1EFF\u1F00-\u1FFF\u2000-\u206F\u2070-\u209F\u20A0-\u20CF\u20D0-\u20FF\u2100-\u214F\u2150-\u218F\u2190-\u21FF\u2200-\u22FF\u2300-\u23FF\u2400-\u243F\u2440-\u245F\u2460-\u24FF\u2500-\u257F\u2580-\u259F\u25A0-\u25FF\u2600-\u26FF\u2700-\u27BF\u27C0-\u27EF\u27F0-\u27FF\u2800-\u28FF\u2900-\u297F\u2980-\u29FF\u2A00-\u2AFF\u2B00-\u2BFF\u2C00-\u2C5F\u2C60-\u2C7F\u2C80-\u2CFF\u2D00-\u2D2F\u2D30-\u2D7F\u2D80-\u2DDF\u2E00-\u2E7F\u2E80-\u2EFF\u2F00-\u2FDF\u2FF0-\u2FFF\u3000-\u303F\u3040-\u309F\u30A0-\u30FF\u3100-\u312F\u3130-\u318F\u3190-\u319F\u31A0-\u31BF\u31C0-\u31EF\u31F0-\u31FF\u3200-\u32FF\u3300-\u33FF\u3400-\u4DBF\u4DC0-\u4DFF\u4E00-\u9FFF\uA000-\uA48F\uA490-\uA4CF\uA700-\uA71F\uA720-\uA7FF\uA800-\uA82F\uA840-\uA87F\uAC00-\uD7AF\uD800-\uDB7F\uDB80-\uDBFF\uDC00-\uDFFF\uE000-\uF8FF\uF900-\uFAFF\uFB00-\uFB4F\uFB50-\uFDFF\uFE00-\uFE0F\uFE10-\uFE1F\uFE20-\uFE2F\uFE30-\uFE4F\uFE50-\uFE6F\uFE70-\uFEFF\uFF00-\uFFEF\uFFF0-\uFFFF]/g, '');

    // Channels
    Song.filename.toUpperCase().includes('[FIRE') ? Song.filename = Song.filename.substring(0, Song.filename.toUpperCase().indexOf('[FIRE') - 1).concat('.mp3') : Song.filename;
    Song.filename.toUpperCase().includes('NEVER SAY DIE - BLACK LABEL') ? Song.filename = Song.filename.replace('Never Say Die - Black Label', 'Never Say Die Black Label') : Song.filename;

    Song.filename = Song.filename.replace(/ \(SUBLMNL .+\)/ig, '');

    Song.filename = Song.filename.replace(/ \(CIRCUS .+\)/ig, '');
    Song.filename = Song.filename.replace(/ \[COOKERZ]/ig, '');
    Song.filename = Song.filename.replace(/ \[.+ CROWSNEST\]/ig, '');
    Song.filename = Song.filename.replace(/ \[DS FREEBIE\]/ig, '');
    Song.filename = Song.filename.replace(/ \[ELECTROSTEP .+]/ig, '');
    Song.filename = Song.filename.replace(/ \(EATBRAIN.+\)/ig, '');
    Song.filename = Song.filename.replace(/ \[FOOLS GOLD]/ig, '');
    Song.filename = Song.filename.replace(/ \[GOOD ENUFF RELEASE\]/ig, '');
    Song.filename = Song.filename.replace(/ \(KILL THE COPYRIGHT RELEASE\)/ig, '');
    Song.filename = Song.filename.replace(/ \[JD4D .+\]/ig, '');
    Song.filename = Song.filename.replace(/ \(METHLAB .+\)/ig, '');
    Song.filename = Song.filename.replace(/ \[MONSTERCAT .+\]/ig, '');
    Song.filename = Song.filename.replace(/ \[NCS RELEASE\]/ig, '');
    Song.filename = Song.filename.replace(/ \[NEST.+\]/ig, '');
    Song.filename = Song.filename.replace(/ \(NEST .+\)/ig, '');
    Song.filename = Song.filename.replace(/ \{NSD BLACK LABEL\}/ig, '');
    Song.filename = Song.filename.replace(/ \[I AM SO HIGH.+\]/ig, '');
    Song.filename = Song.filename.replace(/ \[OTODAYO .+\]/ig, '');
    Song.filename = Song.filename.replace(/ \[PRIME AUDIO\]/ig, '');
    Song.filename = Song.filename.replace(/ \(RIDDIM NETWORK .+\)/ig, '');
    Song.filename = Song.filename.replace(/ \[ROTTUN .+\]/ig, '');
    Song.filename = Song.filename.replace(/ \(RNE\)/ig, '');
    Song.filename = Song.filename.replace(/ \[HT.+\]/ig, '');
    Song.filename = Song.filename.replace(/ \[THISSONGISSICK.+\]/ig, '');
    Song.filename = Song.filename.replace(/ \(TERMINAL\)/ig, '');

    // Genres
    Song.filename = Song.filename.replace(/ \[BASS\]/ig, '');
    Song.filename = Song.filename.replace(/ \[BASS HOUSE\]/ig, '');
    Song.filename = Song.filename.replace(/ \[CHILL TRAP\]/ig, '');
    Song.filename = Song.filename.replace(/ \[DNB\]/ig, '');
    Song.filename = Song.filename.replace(/ \[DRUM&BASS\]/ig, '');
    Song.filename = Song.filename.replace(/ \[DRUM & BASS\]/ig, '');
    Song.filename = Song.filename.replace(/ \[DRUM AND BASS\]/ig, '');
    Song.filename = Song.filename.replace(/ \[DRUMSTEP\]/ig, '');
    Song.filename = Song.filename.replace(/ \[DUBSTEP\]/ig, '');
    Song.filename = Song.filename.replace(/ \[EDM\]/ig, '');
    Song.filename = Song.filename.replace(/ \[ELECTRO\]/ig, '');
    Song.filename = Song.filename.replace(/ \[ELECTRONIC\]/ig, '');
    Song.filename = Song.filename.replace(/ \[ELECTRONICA\]/ig, '');
    Song.filename = Song.filename.replace(/ \[FREAKSTEP\]/ig, '');
    Song.filename = Song.filename.replace(/ \[FUTURE\]/ig, '');
    Song.filename = Song.filename.replace(/ \[FUTURE BASS\]/ig, '');
    Song.filename = Song.filename.replace(/ \[GLITCH HOP\]/ig, '');
    Song.filename = Song.filename.replace(/ \[HARD DANCE\]/ig, '');
    Song.filename = Song.filename.replace(/ \[HARDSTYLE TRAP\]/ig, '');
    Song.filename = Song.filename.replace(/ \[HIP HOP\]/ig, '');
    Song.filename = Song.filename.replace(/ \[HOUSE\]/ig, '');
    Song.filename = Song.filename.replace(/ \[HYBRID\]/ig, '');
    Song.filename = Song.filename.replace(/ \[JUNGLE TERROR\]/ig, '');
    Song.filename = Song.filename.replace(/ \[MELODIC DUBSTEP\]/ig, '');
    Song.filename = Song.filename.replace(/ \[NEURO TRAP\]/ig, '');
    Song.filename = Song.filename.replace(/ \[TRAP\]/ig, '');

    // Tags
    Song.filename = Song.filename.replace(/ \[ 360 VISUALIZER \]/ig, '');
    Song.filename = Song.filename.replace(/ \[360 VR VIDEO\]/ig, '');
    Song.filename = Song.filename.replace(/ \(1440P\)/ig, '');
    Song.filename = Song.filename.replace(/ \(AUDIO\)/ig, '');
    Song.filename = Song.filename.replace(/ \(AVAILABLE .+\)/ig, '');
    Song.filename = Song.filename.replace(/ \(BUY .+\)/ig, '');
    Song.filename = Song.filename.replace(/ \[BUY .+\]/ig, '');
    Song.filename = Song.filename.replace(/ \(CLICK BUY.+\)/ig, '');
    Song.filename = Song.filename.replace(/ \[CLICK BUY.+\]/ig, '');
    Song.filename = Song.filename.replace(/ \[DOWNLOAD .+\]/ig, '');
    Song.filename = Song.filename.replace(/ \(EXCLUSIVE\)/ig, '');
    Song.filename = Song.filename.replace(/ \[EXCLUSIVE\]/ig, '');
    Song.filename = Song.filename.replace(/ \[EXCLUSIVE .+\]/ig, '');
    Song.filename = Song.filename.replace(/ \[.+ EXCLUSIVE\]/ig, '');
    Song.filename = Song.filename.replace(/ \(.+ EXCLUSIVE\)/ig, '');
    Song.filename = Song.filename.replace(/ \(EXTENDED MIX\)/ig, '');
    Song.filename = Song.filename.replace(/ \(FINAL\)/ig, '');
    Song.filename = Song.filename.replace(/ \[FORTHCOMING .+\]/ig, '');
    Song.filename = Song.filename.replace(/ \[FREE\]/ig, '');
    Song.filename = Song.filename.replace(/ \(FREE\)/ig, '');
    Song.filename = Song.filename.replace(/ \(FREE .+\)/ig, '');
    Song.filename = Song.filename.replace(/ \[FREE .+\]/ig, '');
    Song.filename = Song.filename.replace(/ FREE DOWNLOAD/ig, '');
    Song.filename = Song.filename.replace(/ \[OFFICIAL\]/ig, '');
    Song.filename = Song.filename.replace(/ \(OFFICIAL\)/ig, '');
    Song.filename = Song.filename.replace(/ \(OFFICIAL .+\)/ig, '');
    Song.filename = Song.filename.replace(/ \{OFFICIAL .+\}/ig, '');
    Song.filename = Song.filename.replace(/ \[OFFICIAL .+\]/ig, '');
    Song.filename = Song.filename.replace(/ \(LYRIC VIDEO\)/ig, '');
    Song.filename = Song.filename.replace(/ \(MASTER\)/ig, '');
    Song.filename = Song.filename.replace(/ \(ORIGINAL MIX\)/ig, '');
    Song.filename = Song.filename.replace(/ \( ORIGINAL MIX \)/ig, '');
    Song.filename = Song.filename.replace(/ \[ORIGINAL MIX\]/ig, '');
    Song.filename = Song.filename.replace(/ \(OUT .+\)/ig, '');
    Song.filename = Song.filename.replace(/ \[OUT .+\]/ig, '');
    Song.filename = Song.filename.replace(/OUT NO.+/ig, '');
    Song.filename = Song.filename.replace(/ \[PREMIERE\]/ig, '');
    Song.filename = Song.filename.replace(/ \[.+ PREMIERE\]/ig, '');
    Song.filename = Song.filename.replace(/ \(.+ PREMIERE\)/ig, '');
    Song.filename = Song.filename.replace(/ \[REMASTER\]/ig, '');
    Song.filename = Song.filename.replace(/ \READ DESCRIPTION/ig, '');
    Song.filename = Song.filename.replace(/ \(RADIO EDIT\)/ig, '');
    // Song.filename = Song.filename.replace(/ \- SINGLE/ig, '');

    if (origFilename !== Song.filename) { Song.changed = true };

    return Song;
}

function checkRemix(Song) {
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

function removeAnd(Song, type) {
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

function removeClip(title) {
    if (title) {
        title = title.replace(/ \(CLIP\)/ig, '');
        title = title.replace(/ \( CLIP \)/ig, '');
        title = title.replace(/ \[CLIP\]/ig, '');
        title = title.replace(/ CLIP/ig, '');
    }

    return title;
}

function checkDuplicate(Song, musicArr) {
    if (Song.filename.includes(' (1)')) {
        console.log(`***Duplicate: Check ${Song.filename}***
        --------------------------------`);
        // fs.unlink(Song.fullFilename);
        Song.duplicate = true;
    }

    if (musicArr) {
        musicArr.forEach((file, index) => {
            if (file !== Song && file.artist === Song.artist && file.title === Song.title) {
                console.log(`***Duplicate: ${Song.artist} - ${Song.title}***

------------------------------
`);
                // fs.unlink(Song.fullFilename);
                Song.duplicate = true;
            }
        });
    }

    return Song;
}

function checkWith(Song) {
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

function checkFeat(Song) {
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

function lastCheck(Song) {
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

module.exports = {
    checkOS: checkOS,
    newSong: newSong,
    formatLocalSong: formatLocalSong,
    formatDownloadedSong: formatDownloadedSong,
    cacheMusic: cacheMusic,
    countDash: countDash,
    grabFirst: grabFirst,
    grabSecond: grabSecond,
    grabThird: grabThird,
    grabLast: grabLast,
    grabExtension: grabExtension,
    splitArtist: splitArtist,
    removeBadCharacters: removeBadCharacters,
    checkRemix: checkRemix,
    removeAnd: removeAnd,
    removeClip: removeClip,
    checkDuplicate: checkDuplicate,
    checkWith: checkWith,
    checkFeat: checkFeat,
    lastCheck: lastCheck
}