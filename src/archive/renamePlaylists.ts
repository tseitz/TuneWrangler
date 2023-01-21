import * as fs from 'fs'
import * as tw from './common'
import { PlaylistSong, LocalSong } from './models/Song'
import * as readline from 'readline'

let linux = true

const playlistDir = tw.checkOS('playlists', linux)
const formattedDir = tw.checkOS('formatted', linux)
const musicDir = tw.checkOS('linuxMusic', linux)
const cacheDir = tw.checkOS('music', linux)
const brokenDir = tw.checkOS('broken', linux)
let musicArr: LocalSong[] = []

// pass arg "-- move" to write tags and move file
process.argv.forEach((value) => {
  if (value === 'rename') {
    rename()
  }
  if (value === 'formatBroken') {
    formatBroken()
  }
  if (value === 'moveBroken') {
    moveBroken()
  }
})

function rename() {
  fs.readdir(playlistDir, (e, files) => {
    files.forEach((filename) => {
      fs.readFile(`${playlistDir}${filename}`, 'utf8', function (err, data) {
        if (err) {
          return console.log(err)
        }
        data = tw.removeX(data)

        fs.writeFile(`${formattedDir}_${filename}`, data, 'utf8', function (
          err
        ) {
          if (err) throw err
          console.log(`Renamed: ${filename}`)
        })
      })
    })
  })
}

function formatBroken() {
  const rl = readline.createInterface({
    input: fs.createReadStream(`${brokenDir}deepDarknDangerous.csv`),
  })

  let songList: string[] = []
  rl.on('line', (line) => {
    if (line.endsWith('0')) {
      const [title, artist] = line.split(';')
      const song = `${artist.replace(/\"/g, '')} - ${title.replace(/\"/g, '')}`
      songList.push(tw.addX(song))
      // console.log(`${artist} - ${title}`)
    }
  })

  rl.on('close', () => {
    const sortedData = songList
      .sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))
      .join('\n')
    console.log(sortedData)
    fs.writeFile(
      `${brokenDir}_deepDarknDangerous.txt`,
      sortedData,
      'utf8',
      function (err) {
        if (err) return console.log(err)
      }
    )
  })
}

function moveBroken() {
  const rl = readline.createInterface({
    input: fs.createReadStream(`${brokenDir}_deepInTheNight.txt`),
  })

  let playlistSongs: PlaylistSong[] = []
  rl.on('line', (line) => {
    const playlistSong = new PlaylistSong(line, '')
    playlistSongs.push(playlistSong)
  })

  rl.on('close', () => {
    fs.readdir(cacheDir, (e, files) => {
      musicArr = tw.cacheMusic(files, cacheDir)

      let count = 0
      const origLength = playlistSongs.length
      // start from the end so we can remove elements
      for (let index = playlistSongs.length - 1; index >= 0; index--) {
        const song = playlistSongs[index]
        for (const mySong of musicArr) {
          if (song.artist == mySong.artist && song.title == mySong.title) {
            console.log(`Found: ${song.artist} - ${song.title}`)

            fs.copyFile(
              mySong.fullFilename,
              `${musicDir}${mySong.filename}`,
              (err) => {
                if (err) throw err
                console.log(`Copied: ${song.artist} - ${song.title}`)
              }
            )

            count++
            playlistSongs.splice(index, 1)
          }
        }
      }
      console.log('Start Length: ', origLength)
      console.log('Number Found: ', count)
      console.log('Leftover: ', playlistSongs.length)
      console.log(playlistSongs)
    })
  })
}
