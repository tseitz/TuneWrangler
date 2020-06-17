import * as fs from 'fs'
import * as tw from './common'
import { LocalSong, DownloadedSong } from './models/Song'

let debug = true
let wsl = true
let musicCache: LocalSong[] = []

// pass arg "-- move" to write tags and move file
process.argv.forEach((value) => {
  if (value === 'move') {
    debug = false
  }
  if (value === 'nowsl') {
    wsl = false
  }
})

// Incoming: track # title
// Outgoing: title
const currDir = tw.checkOS('transfer', wsl)
const moveDir = tw.checkOS('music', wsl)

// pass arg "-- move" to write tags and move file
process.argv.forEach((value) => {
  if (value === 'move') {
    debug = false
  }
})

fs.readdir(moveDir, (eL, localFiles) => {
  musicCache = tw.cacheMusic(localFiles, moveDir)

  fs.readdir(currDir, (eD, downloadedFiles) => {
    downloadedFiles.forEach((filename) => {
      const song = new DownloadedSong(filename, currDir)

      if (!song.extension || song.extension === '.m3u') {
        return
      }

      // remove track number
      song.filename = song.filename.slice(3).trim()

      song.duplicate = tw.checkDuplicate(song, musicCache)
      if (song.duplicate) {
        return
      }

      console.log(song.filename)
      console.log('-----------------------------------')

      if (!debug) {
        renameAndMove(song)
      }
    })
  })
})

function renameAndMove(song: DownloadedSong) {
  fs.rename(song.fullFilename, `${moveDir}${song.filename}`, (e) => {
    if (e) {
      console.log(e)
    }
  })
}
