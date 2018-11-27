
(() => {
	'use strict';

	const fs = require('fs');
	const writeid3 = require('node-id3');
	const tw = require('./common');

	init();

	// Incoming: album - artist - title
	// Outgoing: artist - album - title
	function init() {
		let currDir = tw.checkOS('transfer'); // No Cross-Drive Support!
		let moveDir = tw.checkOS('music');
		let musicCache = [];

		// Cache to check for Duplicates
		fs.readdir(moveDir, (e, files) => {
			musicCache = tw.cacheMusic(files);

			fs.readdir(currDir, (e, files) => {
				files.forEach((filename) => {
					let Song = tw.newSong(filename, currDir);

					if (Song.count < 1) { return };
					if (!Song.extension || Song.extension === '.m3u') { return };

					Song = tw.removeBadCharacters(Song);

					// ARTIST
					Song = tw.checkRemix(Song);

					if (!Song.remix) {
						if (Song.count === 1) {
							Song.artist = tw.grabFirst(Song.filename);
						} else {
							Song.artist = tw.grabSecond(Song.filename);
						}
					}

					Song = tw.checkWith(Song);

					// ALBUM
					if (!Song.album && Song.count > 1) { Song.album = tw.grabFirst(Song.filename); }

					// TITLE
					Song.title = tw.grabLast(Song.filename, true);

					// FINAL
					Song = tw.checkFeat(Song);
					Song = tw.removeAnd(Song, 'artist');
					Song = tw.removeAnd(Song, 'album');
					Song = tw.lastCheck(Song);

					// ALL TOGETHER
					let finalFilename;

					if (Song.count === 1) {
						if (Song.album) {
							finalFilename = `${Song.artist} - ${Song.album} - ${Song.title}${Song.extension}`;
						} else {
							finalFilename = `${Song.artist} - ${Song.title}${Song.extension}`;
						}

						if (Song.changed) {
							let tags = {
								title: Song.title,
								artist: Song.artist,
								album: Song.album // not working
							}

							let success = writeid3.write(tags, Song.fullFilename);
							if (!success) console.log(`Failed to tag ${Song.filename}`);
						}
					} else {
						finalFilename = `${Song.artist} - ${Song.album} - ${Song.title}${Song.extension}`;

						if (Song.changed) {
							let tags = {
								title: Song.title,
								artist: Song.artist,
								album: Song.album
							}

							let success = writeid3.write(tags, Song.fullFilename);
							if (!success) console.log(`Failed to tag ${Song.filename}`);
						}
					}

					Song = tw.checkDuplicate(Song, musicCache);
					if (Song.duplicate) { return };

					// console.log(`${Song.fullFilename.slice(25)}
					// `);
					console.log(`${finalFilename}
                    `);
					console.log(`-----------------------
                    `);

					musicCache.push(Song);

					// Rename file `${moveDir}${finalFilename}`
					fs.rename(Song.fullFilename, `${moveDir}${finalFilename}`, (e) => {
						if (e) { console.log(e); }
					});
				});
			});
		});
	}
})();