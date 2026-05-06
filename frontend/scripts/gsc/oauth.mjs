import { createServer } from "node:http";
import { mkdirSync, appendFileSync, readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, resolve } from "node:path";
import { randomBytes } from "node:crypto";
import { DEFAULT_ENV_FILE, requireConfig } from "./env.mjs";

const PORT = Number(process.env.GSC_OAUTH_PORT || 8765);
const REDIRECT_URI = `http://localhost:${PORT}/oauth2callback`;
const SCOPES = [
  "https://www.googleapis.com/auth/webmasters",
  "https://www.googleapis.com/auth/webmasters.readonly",
];

function hasRefreshToken(file) {
  return existsSync(file) && readFileSync(file, "utf8").includes("GSC_REFRESH_TOKEN=");
}

async function exchangeCode({ code, clientId, clientSecret }) {
  const body = new URLSearchParams({
    code,
    client_id: clientId,
    client_secret: clientSecret,
    redirect_uri: REDIRECT_URI,
    grant_type: "authorization_code",
  });

  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Token exchange failed: ${JSON.stringify(payload)}`);
  }

  if (!payload.refresh_token) {
    throw new Error(
      "Google did not return a refresh token. Re-run with prompt=consent or remove the app grant from your Google account.",
    );
  }

  return payload.refresh_token;
}

const { file, config } = requireConfig(["GSC_CLIENT_ID", "GSC_CLIENT_SECRET"]);
const state = randomBytes(18).toString("hex");
const authUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
authUrl.searchParams.set("client_id", config.GSC_CLIENT_ID);
authUrl.searchParams.set("redirect_uri", REDIRECT_URI);
authUrl.searchParams.set("response_type", "code");
authUrl.searchParams.set("scope", SCOPES.join(" "));
authUrl.searchParams.set("access_type", "offline");
authUrl.searchParams.set("prompt", "consent");
authUrl.searchParams.set("state", state);

const server = createServer(async (request, response) => {
  try {
    const requestUrl = new URL(request.url, REDIRECT_URI);

    if (requestUrl.pathname !== "/oauth2callback") {
      response.writeHead(404);
      response.end("Not found");
      return;
    }

    if (requestUrl.searchParams.get("state") !== state) {
      response.writeHead(400);
      response.end("Invalid OAuth state.");
      return;
    }

    const code = requestUrl.searchParams.get("code");
    if (!code) {
      response.writeHead(400);
      response.end(`OAuth failed: ${requestUrl.searchParams.get("error") || "missing code"}`);
      return;
    }

    const refreshToken = await exchangeCode({
      code,
      clientId: config.GSC_CLIENT_ID,
      clientSecret: config.GSC_CLIENT_SECRET,
    });

    mkdirSync(dirname(file), { recursive: true, mode: 0o700 });
    if (!hasRefreshToken(file)) {
      appendFileSync(file, `\nGSC_REFRESH_TOKEN=${refreshToken}\n`, { mode: 0o600 });
    }

    response.writeHead(200, { "content-type": "text/plain; charset=utf-8" });
    response.end("SealingAI GSC OAuth ist verbunden. Dieses Browserfenster kann geschlossen werden.");
    console.log(`Refresh token saved to ${file}`);
    server.close();
  } catch (error) {
    response.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    response.end(error instanceof Error ? error.message : String(error));
    console.error(error);
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`Open this URL and approve Search Console access:\n${authUrl.toString()}`);
  console.log(`Waiting on ${REDIRECT_URI}`);
  console.log(`Secrets file: ${file || DEFAULT_ENV_FILE}`);
});
