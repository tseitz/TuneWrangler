/*
Takes an m3u file and removes x's and dashes from the name so you can search better

Incoming: artist x artist - title
Outgoing: artist artist title
*/
import { readLines } from "https://deno.land/std@0.167.0/io/buffer.ts";

import { getFolder } from "./common.ts";

const unix = true;

const startDir = getFolder("djPlaylists", unix);
const importDir = getFolder("djPlaylistImport", unix);

// run the program
await main();

async function main() {
  for await (const currEntry of Deno.readDir(startDir)) {
    if (currEntry.isFile && currEntry.name.endsWith(".m3u8")) {
      console.log("Processing: ", currEntry.name);
      const outputFile = `${importDir}/${currEntry.name}`;
      await Deno.truncate(outputFile);

      const fileReader = await Deno.open(`${startDir}/${currEntry.name}`);
      for await (let line of readLines(fileReader)) {
        if (/#EXTINF/.test(line)) {
          // line = line.replace(/ - /g, " ");
          line = line.replace(/ x /g, " & ");
        }
        await Deno.writeTextFile(outputFile, `${line}\n`, {
          append: true,
        });
      }
    }
  }
}
