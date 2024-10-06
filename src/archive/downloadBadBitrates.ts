/*
Redownloads low bitrate files from YouTube using youtube-dl

Requires:
- checkBitrate to be ran first which outputs fix-list.txt
- youtube-dl to be installed
- getYoutubeAuth to be ran first to get token
*/
import { YouTube } from "https:/deno.land/x/youtube@v0.3.0/mod.ts";
import { readLines } from "https://deno.land/std@0.167.0/io/buffer.ts";

import { getFolder } from "../common.ts";

import { LocalSong } from "../models/Song.ts";

const yt = new YouTube(Deno.env.get("YOUTUBE_API_KEY") || "", "");

const djDir = getFolder("djMusic");

const f = await Deno.open("/Users/tseitz/code/projects/TuneWrangler/FileAnalysis/fix-list.txt");

const badMatches: string[] = [];

for await (const l of readLines(f)) {
  console.log("****************");
  console.log("Processing:", l);
  const song = new LocalSong(l, djDir);
  // console.log(song);

  const artists = song.splitArtist();
  const q = `${artists.join(" ")} ${song.title}`;
  console.log(`Search: ${q}`);
  const results = await yt.search_list({
    part: "snippet",
    q,
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
    // TODO: this should probably be more restrictive
    const artistInTitle = artists.some((artist) => videoTitle.includes(artist.toLowerCase()));
    if (!artistInTitle && !videoTitle.includes(song.title.toLowerCase())) {
      console.log("**Bad Match**");
      badMatches.push(l);
      continue;
    }
    videoId = firstItem.id.videoId;
  } else {
    console.log("No results");
    badMatches.push(l);
    continue;
  }
  console.log("Video ID: ", videoId);

  if (videoId && videoId !== "") {
    try {
      const p = Deno.run({
        cmd: [
          "youtube-dl",
          `https://www.youtube.com/watch?v=${videoId}`,
          "--abort-on-error", // TODO: doesn't trigger catch
        ],
        stderr: "piped",
      });
      // TODO: fix this, not throwing error properly
      const [status, err] = await Promise.all([p.status(), p.stderrOutput()]);
      // await p.status();
      console.log(err);
      p.close();
    } catch (e) {
      console.log("caught error", e);
      badMatches.push(l);
    }
  } else {
    console.log("Bad Video ID");
    badMatches.push(l);
    continue;
  }

  // const p = Deno.run({ cmd: ["youtube-dl", "hWNAo_G2iAs"] });
  // console.log(p);
}

await Deno.writeTextFile(
  "/Users/tseitz/code/projects/TuneWrangler/FileAnalysis/bad-matches.txt",
  badMatches.join("\n")
);
console.log(badMatches);
