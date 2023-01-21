import * as fs from 'fs'
import * as tw from './common'
import * as readline from 'readline'
import prompt = require('prompt')

let debug = true
let wsl = false

// pass arg "-- move" to write tags and move file
process.argv.forEach((value) => {
  if (value === 'move') {
    debug = false
  }
  if (value === 'wsl') {
    wsl = true
  }
})

interface IPlaylistCount {
  playlistName: string
  count: number
}

const playlistDir = tw.checkOS('playlists', wsl)

const exceptions = ['5 Stars', 'Archive', 'Bangers', 'Dont Sync', 'Unrated']

async function run() {
  prompt.start()
  prompt.get(['Backup playlists and hit enter'], () => {
    // TODO: This sucks, figure out a way to await this properly
    let oldPlaylistCount: IPlaylistCount[] = []
    fs.readdir(playlistDir, async (e, files) => {
      files.forEach(async (filename, index) => {
        oldPlaylistCount.push(await checkFile(filename))
      })
    })

    prompt.start()
    prompt.get(['Sync phone, backup playlists again and hit enter'], (hey) => {
      let newPlaylistCount: IPlaylistCount[] = []
      fs.readdir(playlistDir, async (e, files) => {
        files.forEach(async (filename, index) => {
          newPlaylistCount.push(await checkFile(filename))
        })
      })

      prompt.start()
      prompt.get(['All done, you ready?'], (hey) => {
        newPlaylistCount.forEach((newP) => {
          oldPlaylistCount.forEach((oldP) => {
            // arbitrary 2 difference to account for if I delete some from a playlist
            if (
              newP.playlistName === oldP.playlistName &&
              newP.count < oldP.count
            ) {
              console.log(`Corrupted ${newP.playlistName}`)
            }
          })
        })
      })
    })
  })
}

run()

function checkFile(filename): Promise<IPlaylistCount> {
  return new Promise((res, rej) => {
    try {
      if (!exceptions.some((exc) => filename.includes(exc))) {
        let count = 0
        const rl = readline.createInterface({
          input: fs.createReadStream(`${playlistDir}${filename}`),
        })

        rl.on('line', () => {
          count++
        })

        rl.on('close', () => {
          const pCount: IPlaylistCount = {
            playlistName: filename,
            count: count,
          }

          res(pCount)
        })
      }
    } catch (err) {
      rej(err)
    }
  })
}

// function readPlaylists(): any {
//   // you'll just have to trust me for now -_-
//   fs.readdir(playlistDir, (e, files) => {
//     const playlistCount: IPlaylistCount[] = []
//     files.forEach((filename, index) => {
//       if (!exceptions.some((exc) => filename.includes(exc))) {
//         let count = 0
//         const rl = readline.createInterface({
//           input: fs.createReadStream(`${playlistDir}${filename}`),
//         })

//         rl.on('line', () => {
//           count++
//         })

//         rl.on('close', () => {
//           const pCount: IPlaylistCount = {
//             playlistName: filename,
//             count: count,
//           }
//           playlistCount.push(pCount)

//           if (index === files.length - 1) {
//             return playlistCount
//           }
//         })
//       }
//     })
//   })
// }
