import {
  authenticator,
  authParams,
  YouTube,
} from 'https:/deno.land/x/youtube@v0.3.0/mod.ts'

// const auth = new authenticator()
// const creds: authParams = {
//   client_id:
//     '412629290078-rkmhif1ve1kntgtru5g46sfhcoeqb84n.apps.googleusercontent.com',
//   redirect_uri: 'https://localhost:8080',
//   scope: 'https://www.googleapis.com/auth/youtube',
// }

// const auth_url: string = auth.authenticate(creds)
// console.log(auth_url)

const yt = new YouTube(
  'AIzaSyBCkBmfhg93lUjJ_9_PhkQtEkaNMbBuLTc',
  'ya29.a0Aa4xrXOoopVfGAnyJWTiLUrTOk1TRwKYpHkmO_nX2Y77Ee8aR9MSTugXNITq8c1XjAzbx_U2xVfVtt1R8b4KrdEBptopTDthMFpLXiLAwAakFcdKmiCRDni1O9blmUelq0NrNMLLrnEQXEPwoD22xsu_aLs3aCgYKATASARESFQEjDvL9NSTKq5J1C32AdUDyMvdD5g0163'
)

const playlists = await yt.playlists_list({ part: 'id', mine: true })
console.log(playlists)
