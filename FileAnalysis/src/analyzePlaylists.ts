import * as fs from 'fs';
import * as tw from './common';
import * as nodeId3 from 'node-id3';
import { LocalSong, DownloadedSong } from './models/Song';
// var readline = require('readline');
// const EventEmitter = require('events');

const musicDir = tw.checkOS('music');
let currentCountObj = {};
let bangerCountObj = {};
let starCountObj = {};
let emitter = new EventEmitter();

function init() {
  const currDir = tw.checkOS('playlists');

  process.argv.forEach((val) => {
    if (val === 'current-count') {
      getCurrentCount(currDir);
    } else if (val === 'bangers') {
      getBangerCount(currDir);
    } else if (val === 'five-star') {
      getFiveStarCount(currDir);
    } else if (val === 'stars') {
      getStarCount(currDir);
    } else if (val === 'all') {
      getCurrentCount(currDir, true);
    }
});
}
init();

function getCurrentCount(currDir, processAll) {
  console.log(`
    Current Count
    `);

  fs.readdir(currDir, (e, files) => {
    emitter.once('count-analysis-done', (currentCount) => {
      currentCountObj = currentCount;

      if (processAll) {
        getBangerCount(currDir, true);
      } else {
        const keyArr = Object.keys(currentCount);
        keyArr.sort((a, b) => {
          return parseInt(a, 10) - parseInt(b, 10);
        });
        keyArr.forEach((key) => {
          console.log(`
                    ${key}: ${currentCount[key].count}`);
          console.log(`____________________________________________________________`);
        });
      }
    });

    getCountAnalysis(currDir, files);
  });
}

function getBangerCount(currDir, processAll) {
  console.log(`
    Banger Count
    `.red);

  fs.readdir(currDir, (e, files) => {
    emitter.once('analysis-done', (allPlaylists) => {
      if (processAll) {
        Object.keys(allPlaylists).forEach((key) => {
          let analysisArr = allPlaylists[key].songArray;
          bangerCountObj[key] = {
            count: 0
          };

          analysisArr.forEach((SongA) => {
            bangerObj.songArray.forEach((SongB) => {
              if (SongA.title == SongB.title && SongA.artist == SongB.artist) {
                bangerCountObj[key].count++;
              }
            });
          });
        });

        getStarCount(currDir, true);
      } else {
        let countArr = [];

        Object.keys(allPlaylists).forEach((key) => {
          let count = 0;
          let analysisArr = allPlaylists[key].songArray;

          analysisArr.forEach((SongA) => {
            bangerObj.songArray.forEach((SongB) => {
              if (SongA.title == SongB.title && SongA.artist == SongB.artist) {
                count++;
              }
            });
          });
          countArr.push({
            filename: key,
            count: count
          });
        });

        countArr.sort((first, second) => {
          return parseInt(first.filename, 10) - parseInt(second.filename, 10);
        });
        countArr.forEach((playlist) => {
          console.log(`
                        ${playlist.filename}`.green + `: ${playlist.count}`);
          console.log(`____________________________________________________________`.green);
        });
      }
    });

    let bangerObj = {
      songArray: []
    };
    files.forEach((filename, index) => {
      if (filename.includes('_Bangerzzzzzzz.m3u')) {
        const rl = readline.createInterface({
          input: fs.createReadStream(`${currDir}${filename}`)
        });

        rl.on('line', (line) => {
          if (line.includes(musicDir) > 0) {
            line = line.slice(musicDir.length);
            var Song = tw.formatLocalSong(line, musicDir);

            bangerObj.songArray.push(Song);
          }
        });
      }
    });

    getAnalysis(currDir, files);
  });
}

function getStarCount(currDir, processAll) {
  console.log(`
    Star Count
    `.red);

  fs.readdir(currDir, (e, files) => {
    emitter.once('analysis-done', (starCount) => {
      starCountObj = starCount;

      if (processAll) {
        let countArr = [];

        Object.keys(starCount).forEach((key) => {
          let count = 0;
          let analysisArr = starCount[key].songArray;
          let fiveArr = [];
          let fourHalfArr = [];
          let fourArr = [];
          let notRated = [];

          analysisArr.forEach((Song) => {
            if (Song.rating == 100) {
              fiveArr.push(Song);
            } else if (Song.rating == 90) {
              fourHalfArr.push(Song);
            } else if (Song.rating == 80) {
              fourArr.push(Song);
            } else if (Song.rating == 0) {
              notRated.push(Song);
            }
          });

          starCount[key].fiveCount = fiveArr.length;
          starCount[key].fourHalfCount = fourHalfArr.length;
          starCount[key].fourCount = fourArr.length;
          starCount[key].notRatedCount = notRated.length;
        });

        outputAll();
      } else {
        let countArr = [];

        Object.keys(starCount).forEach((key) => {
          let count = 0;
          let analysisArr = starCount[key].songArray;
          let fiveArr = [];
          let fourHalfArr = [];
          let fourArr = [];
          let notRatedArr = [];

          analysisArr.forEach((Song) => {
            if (Song.rating == 100) {
              fiveArr.push(Song);
            } else if (Song.rating == 90) {
              fourHalfArr.push(Song);
            } else if (Song.rating == 80) {
              fourArr.push(Song);
            } else if (Song.rating == 0) {
              notRatedArr.push(Song);
            }
          });

          countArr.push({
            filename: key,
            fiveCount: fiveArr.length,
            fourHalfCount: fourHalfArr.length,
            fourCount: fourArr.length,
            notRatedCount: notRatedArr.length
          })
        });
        countArr.sort((first, second) => {
          return parseInt(first.filename, 10) - parseInt(second.filename, 10);
        });
        countArr.forEach((playlist) => {
          console.log(`
        ${playlist.filename}`.green + `    5: ${playlist.fiveCount}   4.5: ${playlist.fourHalfCount}  4: ${playlist.fourCount}  Not Rated: ${playlist.notRatedCount}`);
          console.log(`____________________________________________________________`.green);
        });
      }
    });

    getAnalysis(currDir, files);
  });
}

function outputAll() {
  let finalString = '';

  let keyArr = Object.keys(bangerCountObj);
  keyArr.sort((a, b) => {
    return parseInt(a, 10) - parseInt(b, 10);
  });
  keyArr.forEach((key, index) => {
    let currentCount = currentCountObj[key].count;

    let bangerCount = bangerCountObj[key].count;

    let fiveCount = starCountObj[key].fiveCount;
    let fourHalfCount = starCountObj[key].fourHalfCount;
    let fourCount = starCountObj[key].fourCount;
    let notRatedCount = starCountObj[key].notRatedCount;

    if (index === 0) {
      finalString += 'Key, Current Count, Banger Count, Five Star Count, Four Half Star Count, Four Star Count, Not Rated Count\n';
    }

    finalString += `${key}, ${currentCount}, ${bangerCount}, ${fiveCount}, ${fourHalfCount}, ${fourCount}, ${notRatedCount}
`;

    if (index === keyArr.length - 1) {
      fs.writeFile('analysis.csv', finalString, (e) => {
        if (e) {
          console.log(e);
        }
        console.log('Done writing');
      });
    }
  });
}

function getAnalysis(currDir, files) {
  let allPlaylists = {};
  files = files.filter((filename) => {
    return filename.includes('Analysis');
  });
  files.forEach((filename, index) => {
    const rl = readline.createInterface({
      input: fs.createReadStream(`${currDir}${filename}`)
    });
    let trimmedFilename = filename.substring(filename.indexOf('-') + 2, filename.indexOf('.'));
    allPlaylists[trimmedFilename] = {
      songArray: []
    };
    let curPlaylist = allPlaylists[trimmedFilename];

    rl.on('line', (line) => {
      if (line.includes(musicDir) > 0) {
        line = line.slice(musicDir.length);
        var Song = tw.formatLocalSong(line, musicDir);

        curPlaylist.songArray.push(Song);
      }
    });

    rl.on('close', () => {
      if (index === files.length - 1) {
        emitter.emit('analysis-done', allPlaylists);
      }
    });
  });
}

function getCountAnalysis(currDir, files) {
  let allPlaylists = {};
  files = files.filter((filename) => {
    return filename.includes('Analysis');
  });
  files.forEach((filename, index) => {
    const rl = readline.createInterface({
      input: fs.createReadStream(`${currDir}${filename}`)
    });
    let trimmedFilename = filename.substring(filename.indexOf('-') + 2, filename.indexOf('.'));
    allPlaylists[trimmedFilename] = {
      count: 0
    };
    let curPlaylist = allPlaylists[trimmedFilename];

    rl.on('line', (line) => {
      if (line.includes(musicDir) > 0) {
        curPlaylist.count++;
      }
    });

    rl.on('close', () => {
      if (index === files.length - 1) {
        emitter.emit('count-analysis-done', allPlaylists);
      }
    });
  });
}

function artistRatio(files) {
  let artistCountArr = [];
  let cacheArtistCountArr = tw.cacheMusic(files);

  var totalCount = 0;
  artistCountArr.forEach((artistObj) => {
    if (artistObj.count > 1) {
      cacheArtistCountArr.forEach((cacheArtistObj) => {
        if (cacheArtistObj.artist.toUpperCase() === artistObj.artist.toUpperCase()) {
          artistObj.ratio = artistObj.count / cacheArtistObj.count * 100;
          artistObj.ratio = artistObj.ratio.toFixed(2);
        }
      });
      totalCount++;
    } else {
      artistObj.ratio = 0;
    }
  });

  artistCountArr.sort((a, b) => {
    return b.count - a.count;
  });

  artistCountArr.forEach((artistObj) => {
    if (artistObj.count > 1) {
      // console.log(`${artistObj.artist}: ${artistObj.count} - ${artistObj.ratio}`);
    }
  });

  console.log(totalCount);
  console.log(artistCountArr.length);
}

function countArtists(arr, artist) {
  let found = false;
  let foundIndex = -1;

  arr.forEach((artistObj, index) => {
    if (artistObj.artist.toUpperCase() === artist.toUpperCase()) {
      foundIndex = index;
    }
  });

  // if it exists increment count, if not set up initial object
  if (foundIndex > -1) {
    let artistObj = arr[foundIndex];

    artistObj.count++;
  } else {
    let artistObj = {
      artist: artist,
      count: 1
    };

    arr.push(artistObj);
  }
}