// .js cuz screw ESM

import * as fs from 'fs';
import { parseFile } from 'music-metadata';

// const djDir = '/Users/tseitz/Dropbox/DJ/SlimChance DJ Music/Collection/'
const djDir = '/Users/tseitz/Dropbox/TransferMusic/Youtube'

fs.readdir(djDir, (eL, localFiles) => {
  localFiles.forEach(async (filename) => {
    if (filename.includes('.DS_Store')) return
    try {
      const fileMetadata = await parseFile(`${djDir}/${filename}`)
      // console.log(fileMetadata.format.bitrate)
      // if (fileMetadata.format.bitrate < 200000) {
        console.log(Math.round(fileMetadata.format.bitrate), filename)
      // }
    } catch (e) {
      console.log(e)
    }
  })
})
