/*
Takes an m3u file and removes x's and dashes from the name so you can search better

Incoming: artist x artist - title
Outgoing: artist artist title
*/
import { getFolder } from "../core/utils/common.ts";

const startDir = getFolder("djPlaylists");
const importDir = getFolder("djPlaylistImport");

// run the program
await main();

async function main() {
  for await (const currEntry of Deno.readDir(startDir)) {
    if (currEntry.isFile && currEntry.name.endsWith(".m3u8")) {
      console.log("Processing: ", currEntry.name);
      const outputFile = `${importDir}/${currEntry.name}`;
      await Deno.truncate(outputFile);

      const content = await Deno.readTextFile(
        `${startDir}/${currEntry.name}`,
      );
      for (let line of content.split("\n")) {
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
