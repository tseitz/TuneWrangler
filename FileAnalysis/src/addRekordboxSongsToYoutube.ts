import { YouTube } from "https:/deno.land/x/youtube@v0.3.0/mod.ts";
import { readLines } from "https://deno.land/std/io/bufio.ts";
// import { createRequire } from "https://deno.land/std/node/module.ts";

import { getFolder, splitArtist } from "./common.ts";

import { LocalSong } from "./models/Song.ts";

// const require = createRequire(import.meta.url);
// const musicMetadata = require("music-metadata");

const yt = new YouTube(Deno.env.get("YOUTUBE_API_KEY") || "", "");

// const playlists = await yt.playlists_list({ part: "id", mine: true });
// console.log(playlists);

// const djDir = "/Users/tseitz/Dropbox/TransferMusic/Youtube";
const djDir = getFolder("djMusic");

const fileNames: LocalSong[] = [];
const f = await Deno.open(
  "/Users/tseitz/code/projects/TuneWrangler/FileAnalysis/log.txt"
);

const badMatches: string[] = [];

for await (const l of readLines(f)) {
  console.log("****************");
  console.log("Processing:", l);
  const song = new LocalSong(l, djDir);
  // console.log(song);

  const artists = splitArtist(song.artist);
  console.log(`Search: ${artists.join(" ")} ${song.title}`);
  const results = await yt.search_list({
    part: "snippet",
    q: `${song.artist} ${song.title}`,
    maxResults: 1,
  });
  if (results.error) {
    console.log(results.error.message);
    badMatches.push(l);
    continue;
  }
  if (results.items.length > 0) {
    const firstItem = results.items[0];
    const videoTitle: string = firstItem.snippet.title;
    // console.log(firstItem);
    console.log("Title: ", firstItem.snippet.title);
    const artistInTitle = artists.some((artist) => videoTitle.includes(artist));
    if (!artistInTitle || !videoTitle.includes(song.title)) {
      console.log("**Bad Match**");
      badMatches.push(l);
    }
  } else {
    badMatches.push(l);
    console.log("No results");
  }
  // console.log("Video ID: ", firstItem.id.videoId);

  // const posted = await yt.playlistItems_insert(
  //   { part: "snippet" },
  //   JSON.stringify({
  //     snippet: {
  //       playlistId: "PLvQhc3ic51Lul-yFeQPK2ULQldvk-AwWa",
  //       position: 0,
  //       resourceId: { kind: "youtube#video", videoId: "ePTQ3So22P8" },
  //     },
  //   })
  // );
}

await Deno.writeTextFile(
  "/Users/tseitz/code/projects/TuneWrangler/FileAnalysis/bad-matches.txt",
  badMatches.join("\n")
);
console.log("File written to bad-matches.txt");
// for await (const entry of Deno.readDir(djDir)) {
//   if (entry.isFile && !entry.name.includes(".DS_Store")) {
//     // const fileMetadata = await parseFile(`${djDir}/${entry.name}`);
//     const file = await Deno.readFile(`${djDir}/${entry.name}`);
//     // const r = readableStreamFromReader(file);
//     const fileMetadata = await parseBuffer(new Buffer(file));
//     console.log(Math.round(fileMetadata.format.bitrate), entry.name);
//     // const song = new LocalSong(entry.name, djDir);
//     // fileNames.push(song);
//   }
// }

// Deno.readDir(djDir, (eL, localFiles) => {
//   localFiles.forEach(async (filename) => {
//     if (filename.includes(".DS_Store")) return;
//     try {
//       const fileMetadata = await parseFile(`${djDir}/${filename}`);
//       // console.log(fileMetadata.format.bitrate)
//       // if (fileMetadata.format.bitrate < 200000) {
//       console.log(Math.round(fileMetadata.format.bitrate), filename);
//       // }
//     } catch (e) {
//       console.log(e);
//     }
//   });
// });

// const posted = await yt.playlistItems_insert(
//   { part: "snippet" },
//   JSON.stringify({
//     snippet: {
//       playlistId: "PLvQhc3ic51Lul-yFeQPK2ULQldvk-AwWa",
//       position: 0,
//       resourceId: { kind: "youtube#video", videoId: "ePTQ3So22P8" },
//     },
//   })
// );

// console.log(posted);

// {"snippet":{"playlistId":"PLvQhc3ic51Lul-yFeQPK2ULQldvk-AwWa","position":0,"resourceId":{"kind":"youtube#video","videoId":"ePTQ3So22P8"}}}
