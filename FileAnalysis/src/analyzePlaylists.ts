import * as fs from 'fs';
import * as tw from './common';
import { LocalSong } from './models/Song';
import { ArtistAnalysis } from './models/ArtistAnalysis';
import * as readline from 'readline';

/*
  TODO:
    - Implement analyzeAll
    - Implement analysis all per week to get analysis of weekly intake
*/

const musicDir = tw.checkOS('music');
const playlistDir = tw.checkOS('playlists');

const args = process.argv.slice(2); // grab the array of args
if (args[0] !== 'all') {
  analyze(playlistDir, args[0], !!args[1]);
} else {
  // analyzeAll(playlistDir, args[0], !!args[1]);
}

function analyze(dir: string, playlist: string, write = false) {
  fs.readdir(dir, (e, files) => {
    files.forEach((filename) => {
      if (filename.toLowerCase().includes(playlist)) {
        const bangerSongs: LocalSong[] = [];
        const rl = readline.createInterface({
          input: fs.createReadStream(`${playlistDir}${filename}`)
        });

        rl.on('line', (line) => {
          if (line.includes(musicDir)) {
            line = line.slice(musicDir.length);
            const song = new LocalSong(line, musicDir);

            bangerSongs.push(song);
          }
        });

        rl.on('close', () => {
          const artistArr: string[] = [];
          bangerSongs.forEach((song) => {
            artistArr.push(...tw.splitArtist(song.artist.toLowerCase()));
          });
          const sortedArr = artistArr.sort();
          const artistSet = new Set(sortedArr);
          const bangerArtists = Array.from(artistSet).reduce((a, key) => Object.assign(a, { [key]: 0 }), {});

          bangerSongs.forEach((song) => {
            const artists = tw.splitArtist(song.artist);
            artists.forEach((artist) => {
              bangerArtists[artist.toLowerCase()]++;
            });
          });

          const finalArr: ArtistAnalysis[] = [];
          for (const prop in bangerArtists) {
            finalArr.push({ artist: prop, count: bangerArtists[prop] });
          }

          finalArr.sort((a: ArtistAnalysis, b: ArtistAnalysis) => {
            return b.count - a.count;
          });

          if (write) {
            writeToFile(playlist, finalArr);
          } else {
            console.log(finalArr);
          }
        });
      }
    });
  });
}

function writeToFile(playlist: string, artistArr: ArtistAnalysis[]) {
  let finalString = '';

  artistArr.forEach((analysis, index) => {
    if (index === 0) {
      finalString += 'Artist, Count\n';
    }

    finalString += `${analysis.artist}, ${analysis.count}\n`;

    if (index === artistArr.length - 1) {
      fs.writeFile(`output/${playlist}.csv`, finalString, (e) => {
        if (e) {
          console.log(e);
        }
        console.log('Done writing');
      });
    }
  });
}

// function getStarCount(currDir, processAll) {
//   console.log(`
//     Star Count
//     `.red);

//   fs.readdir(currDir, (e, files) => {
//     emitter.once('analysis-done', (starCount) => {
//       starCountObj = starCount;

//       if (processAll) {
//         let countArr = [];

//         Object.keys(starCount).forEach((key) => {
//           let count = 0;
//           let analysisArr = starCount[key].songArray;
//           let fiveArr = [];
//           let fourHalfArr = [];
//           let fourArr = [];
//           let notRated = [];

//           analysisArr.forEach((Song) => {
//             if (Song.rating == 100) {
//               fiveArr.push(Song);
//             } else if (Song.rating == 90) {
//               fourHalfArr.push(Song);
//             } else if (Song.rating == 80) {
//               fourArr.push(Song);
//             } else if (Song.rating == 0) {
//               notRated.push(Song);
//             }
//           });

//           starCount[key].fiveCount = fiveArr.length;
//           starCount[key].fourHalfCount = fourHalfArr.length;
//           starCount[key].fourCount = fourArr.length;
//           starCount[key].notRatedCount = notRated.length;
//         });

//         outputAll();
//       } else {
//         let countArr = [];

//         Object.keys(starCount).forEach((key) => {
//           let count = 0;
//           let analysisArr = starCount[key].songArray;
//           let fiveArr = [];
//           let fourHalfArr = [];
//           let fourArr = [];
//           let notRatedArr = [];

//           analysisArr.forEach((Song) => {
//             if (Song.rating == 100) {
//               fiveArr.push(Song);
//             } else if (Song.rating == 90) {
//               fourHalfArr.push(Song);
//             } else if (Song.rating == 80) {
//               fourArr.push(Song);
//             } else if (Song.rating == 0) {
//               notRatedArr.push(Song);
//             }
//           });

//           countArr.push({
//             filename: key,
//             fiveCount: fiveArr.length,
//             fourHalfCount: fourHalfArr.length,
//             fourCount: fourArr.length,
//             notRatedCount: notRatedArr.length
//           })
//         });
//         countArr.sort((first, second) => {
//           return parseInt(first.filename, 10) - parseInt(second.filename, 10);
//         });
//         countArr.forEach((playlist) => {
//           console.log(`
//         ${playlist.filename}`.green + `    5: ${playlist.fiveCount}   4.5: ${playlist.fourHalfCount}  4: ${playlist.fourCount}  Not Rated: ${playlist.notRatedCount}`);
//           console.log(`____________________________________________________________`.green);
//         });
//       }
//     });

//     getAnalysis(currDir, files);
//   });
// }

// function artistRatio(files) {
//   let artistCountArr = [];
//   let cacheArtistCountArr = tw.cacheMusic(files);

//   var totalCount = 0;
//   artistCountArr.forEach((artistObj) => {
//     if (artistObj.count > 1) {
//       cacheArtistCountArr.forEach((cacheArtistObj) => {
//         if (cacheArtistObj.artist.toUpperCase() === artistObj.artist.toUpperCase()) {
//           artistObj.ratio = artistObj.count / cacheArtistObj.count * 100;
//           artistObj.ratio = artistObj.ratio.toFixed(2);
//         }
//       });
//       totalCount++;
//     } else {
//       artistObj.ratio = 0;
//     }
//   });

//   artistCountArr.sort((a, b) => {
//     return b.count - a.count;
//   });

//   artistCountArr.forEach((artistObj) => {
//     if (artistObj.count > 1) {
//       // console.log(`${artistObj.artist}: ${artistObj.count} - ${artistObj.ratio}`);
//     }
//   });

//   console.log(totalCount);
//   console.log(artistCountArr.length);
// }
