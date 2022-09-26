import { YouTube } from "https:/deno.land/x/youtube@v0.3.0/mod.ts";
import { readLines } from "https://deno.land/std/io/bufio.ts";
// import { createRequire } from "https://deno.land/std/node/module.ts";

import { getFolder, splitArtist } from "./common.ts";

import { LocalSong } from "./models/Song.ts";

// const require = createRequire(import.meta.url);
// const musicMetadata = require("music-metadata");

const yt = new YouTube(
  Deno.env.get("YOUTUBE_API_KEY") || "",
  "ya29.a0Aa4xrXOCbr3XJ7Tj2caRpHt-WPnu6pl_hcOQ-AXieMGXfcYJX1jFquXm8-qpOs7cn7sY8rDP97k6_rRbXOueELVYuC4riPivxKYQXagyvq63xM6CCSAPgXjnHHLPAopjkpOSGpFYS_JhMNiIFOWP5AULsDi8aCgYKATASARISFQEjDvL9zlFLpZ0itldRrjAM86hUmQ0163"
);

// const playlists = await yt.playlists_list({ part: "id", mine: true });
// console.log(playlists);

// const djDir = "/Users/tseitz/Dropbox/TransferMusic/Youtube";
const djDir = getFolder("djMusic");

const fileNames: LocalSong[] = [];
const f = await Deno.open(
  "/Users/tseitz/code/projects/TuneWrangler/FileAnalysis/fix-list.txt"
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

  let videoId = "";
  if (results.items.length > 0) {
    const firstItem = results.items[0];
    const videoTitle: string = firstItem.snippet.title.toLowerCase();
    // console.log(firstItem);
    console.log("Title: ", firstItem.snippet.title);
    const artistInTitle = artists.some((artist) =>
      videoTitle.includes(artist.toLowerCase())
    );
    if (!artistInTitle && !videoTitle.includes(song.title.toLowerCase())) {
      console.log("**Bad Match**");
      badMatches.push(l);
      continue;
    }
    videoId = firstItem.id.videoId;
  } else {
    badMatches.push(l);
    console.log("No results");
    continue;
  }
  console.log("Video ID: ", videoId);

  // if (videoId !== "") {
  //   const posted = await yt.playlistItems_insert(
  //     { part: "snippet" },
  //     JSON.stringify({
  //       snippet: {
  //         playlistId: "PLvQhc3ic51Lul-yFeQPK2ULQldvk-AwWa",
  //         position: 0,
  //         resourceId: { kind: "youtube#video", videoId },
  //       },
  //     })
  //   );
  //   console.log(posted);
  // }
}

await Deno.writeTextFile(
  "/Users/tseitz/code/projects/TuneWrangler/FileAnalysis/bad-matches.txt",
  badMatches.join("\n")
);
console.log(badMatches);
