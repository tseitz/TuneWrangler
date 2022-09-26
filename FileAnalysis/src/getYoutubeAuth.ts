import {
  authenticator,
  authParams,
} from "https://deno.land/x/youtube@v0.3.0/mod.ts";

const auth = new authenticator();
const creds: authParams = {
  client_id:
    // "412629290078-rkmhif1ve1kntgtru5g46sfhcoeqb84n.apps.googleusercontent.com",
    "629368326955-ag26ghcq8ctmp0hcaahdmqardjn63c7a.apps.googleusercontent.com",
  redirect_uri: "https://localhost:8081",
  scope: "https://www.googleapis.com/auth/youtube",
};

const auth_url: string = auth.authenticate(creds);
console.log(auth_url);
