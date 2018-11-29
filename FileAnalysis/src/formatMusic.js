(() => {
  'use strict';

  /*** TO-DO's ***

  /**************/

  var fs = require('fs');
  var prompt = require('prompt');
  // var mm = require('musicmetadata');
  var id3 = require('node-id3');
  var tw = require('./common');

  init();
  // cleanArtists();

  function init() {
    var currDir = tw.checkOS('music');

    // Incoming: artist - album - title
    fs.readdir(currDir, (e, files) => {
      var cacheArtist = [];

      files.forEach((filename, index) => {
        let Song = tw.formatLocalSong(filename, currDir);

        // unifyArtists(Song, cacheArtist);

        //     let originalFileName = `${currDir}${file}`;
        //     let extension = tw.grabExtension(file);
        //     let filenames = [];
        //     let fileChanged = false;
        //     let finalFileName, readStream;

        //     if (extension !== '.mp3' && extension !== '.flac') { return }

        //     let artist = tw.grabFirst(file);
        //     let artistObj = tw.removeAnd(artist);

        //     if (artistObj.fileChanged) {
        //         artist = artistObj.artist;
        //         fileChanged = true;
        //     }

        //     let album = tw.grabSecond(file);

        //     let title = tw.grabLast(file, extension);
        //     let titleObj = tw.removeFeat(title);

        //     if (titleObj.fileChanged) {
        //         title = titleObj.title;
        //         fileChanged = true;
        //     }

        //     let tags = {
        //         title: title,
        //         artist: artist,
        //         album: album
        //     }

        //     // console.log('-----------------------');

        //     finalFileName = `${currDir}${artist} - ${album} - ${title}${extension}`;

        //     // if (fileChanged) { console.log(finalFileName) };

        //     if (fileChanged) {
        //         let success = id3.write(tags, originalFileName);
        //         if (!success) console.log(`Failed to tag ${fileName}`);

        //         fs.rename(originalFileName, finalFileName);
        //         console.log(`${tags.artist} - ${tags.album} - ${tags.title}`);
        //     }
      });
    });
  }

  function unifyArtists(Song, cacheArtist) {
    let artistArr = Song.artist.split(' x ');

    if (artistArr.length === 1) {
      let artist = artistArr[0];
      let compareArtist = cacheArtist[0];

      if (!compareArtist) {
        cacheArtist = [artist];
      } else if (compareArtist !== artist) {
        if (compareArtist.toUpperCase() === artist.toUpperCase()) {
          console.log(`1: ${compareArtist}
2: ${artist}`);

          var artistPrompt = [{
            name: '1 or 2?'
          }, {
            name: 'done'
          }];
          var confirmPrompt = {
            name: 'confirm'
          };
          var deleteIndex = [];

          prompt.start();

          function ask() {
            // Ask for name until user inputs "done"
            prompt.get(artistPrompt, (e, result) => {
              var index = parseInt(result.index, 10);

              if (result.done !== 'y') {
                console.log(result);

                if (index === 1) {
                  console.log(compareArtist);
                } else {
                  console.log(artist);
                }
                // deleteIndex.push(index);
                ask();
              } else {
                // deleteIndex.push(index);

                // deleteIndex.forEach((index) => {
                //     console.log(artistCache[index].artist);
                // });

                // prompt.get(confirmPrompt, (e, result) => {
                //     if (result.confirm === 'y') {
                //         deleteIndex.forEach((index) => {
                //             var path = `${currDir}${deleteArr[index].full}`;
                //             console.log(deleteArr[index]);
                //             console.log(path);
                //             fs.unlink(path, (e, result) => {
                //                 if (e) {
                //                     console.log(e);
                //                 }
                //                 console.log(`Successfully deleted ${deleteArr[index].full}`);
                //             });
                //         });
                //     }
                // })
              }
            });
          }

          cacheArtist = [artist];
        }
      }
    }
  }

  function cleanFeat() {
    let Song = tw.newSong(filename, currDir);
    Song = tw.checkFeat(Song);
  }

  // check artist names
  // Description - 
  function cleanArtists() {
    var currDir = tw.checkOS('transfer');
    var cacheMusic = [];
    var artistCache = [];
    var superArtistCache = [];

    fs.readdir(currDir, (e, files) => {
      cacheMusic = tw.cacheMusic(files);

      files.forEach((song) => {
        var songObj = tw.newSong(song, currDir);

        songObj.artist = tw.grabFirst(songObj.filename);

        cacheMusic.push(songObj);
      });

      // Group Artists
      var nextIndex = 0;
      var artistCache = [];

      cacheMusic.forEach((origSong, outerIndex, currArr) => {
        // console.log(`Outer Index: ${outerIndex}`);
        if (outerIndex === nextIndex) {
          // console.log(`Top: ${nextIndex}`);
          var filtered = currArr.filter((compareSong, innerIndex) => {
            if (innerIndex >= nextIndex) {
              if (innerIndex === nextIndex) {
                return true
              };
              var regex = new RegExp(`${compareSong.artist}$`, 'i');

              if (origSong.artist.match(regex) && origSong.artist !== compareSong.artist) {
                return true;
              } else if (origSong.artist !== compareSong.artist) {
                if (outerIndex === nextIndex) {
                  nextIndex = innerIndex
                };
                return false;
              } else {
                return false;
              }
            }
          });
          // console.log(filtered);
          // console.log(`Bottom: ${nextIndex}`);
          artistCache.push(filtered);
        }
        // console.log(artistCache);

        var artistPrompt = [{
          name: 'index'
        }, {
          name: 'done'
        }];
        var confirmPrompt = {
          name: 'confirm'
        };
        var deleteIndex = [];

        artistCache.forEach((artistArr) => {
          // Prompt confirmation
          // [0, 1, 2]
          console.log(artistArr);

          prompt.start();

          function ask() {
            // Ask for name until user inputs "done"
            prompt.get(artistPrompt, (e, result) => {
              var index = parseInt(result.index, 10);

              if (result.done !== 'y') {
                console.log(result);
                console.log(artistCache[index]);
                deleteIndex.push(index);
                ask();
              } else {
                deleteIndex.push(index);

                deleteIndex.forEach((index) => {
                  console.log(artistCache[index].artist);
                });

                // prompt.get(confirmPrompt, (e, result) => {
                //     if (result.confirm === 'y') {
                //         deleteIndex.forEach((index) => {
                //             var path = `${currDir}${deleteArr[index].full}`;
                //             console.log(deleteArr[index]);
                //             console.log(path);
                //             fs.unlink(path, (e, result) => {
                //                 if (e) {
                //                     console.log(e);
                //                 }
                //                 console.log(`Successfully deleted ${deleteArr[index].full}`);
                //             });
                //         });
                //     }
                // })
              }
            });
          }

          ask();
        });

        // currArr.forEach((compareSong, innerIndex) => {
        //     if (outerIndex === 0) {
        //         console.log(artistCache.length);
        //         var regex = new RegExp(`${compareSong.artist}$`, 'i');
        //         if (artistCache.length === 0) {
        //             artistCache.push(compareSong.artist);
        //         }

        //         if (origSong.artist.match(regex) && origSong.artist !== compareSong.artist) {
        //             // console.log(`${origSong.artist} == ${compareSong.artist}`);
        //             if (!artistCache.includes(compareSong.artist)) {
        //                 artistCache.push(compareSong.artist);
        //                 console.log(artistCache);
        //             }
        //         } else if (origSong.artist !== compareSong.artist) {
        //             superArtistCache.push(artistCache);
        //             artistCache = [compareSong.artist];
        //         }
        //     }
        // });
      });

      // console.log(superArtistCache);
    });
  }
})();