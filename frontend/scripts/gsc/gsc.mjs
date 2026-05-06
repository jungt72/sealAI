import { requireConfig } from "./env.mjs";

const DEFAULT_SITE_URL = "sc-domain:sealai.net";
const DEFAULT_INSPECTION_URL = "https://sealai.net/";

function usage() {
  console.log(`Usage:
  npm run gsc -- sites
  npm run gsc -- sitemaps
  npm run gsc -- submit-sitemap https://sealai.net/sitemap.xml
  npm run gsc -- inspect https://sealai.net/
  npm run gsc -- performance [days]
`);
}

async function getAccessToken(config) {
  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: config.GSC_CLIENT_ID,
      client_secret: config.GSC_CLIENT_SECRET,
      refresh_token: config.GSC_REFRESH_TOKEN,
      grant_type: "refresh_token",
    }),
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Refresh failed: ${JSON.stringify(payload)}`);
  }

  return payload.access_token;
}

async function gscFetch(path, { accessToken, method = "GET", body } = {}) {
  const response = await fetch(`https://searchconsole.googleapis.com${path}`, {
    method,
    headers: {
      authorization: `Bearer ${accessToken}`,
      ...(body ? { "content-type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(`${method} ${path} failed: ${JSON.stringify(payload)}`);
  }

  return payload;
}

function encodeSite(siteUrl) {
  return encodeURIComponent(siteUrl);
}

function todayMinusDays(days) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

const command = process.argv[2];
if (!command) {
  usage();
  process.exit(1);
}

const { config } = requireConfig(["GSC_CLIENT_ID", "GSC_CLIENT_SECRET", "GSC_REFRESH_TOKEN"]);
const siteUrl = config.GSC_SITE_URL || DEFAULT_SITE_URL;
const accessToken = await getAccessToken(config);

if (command === "sites") {
  console.log(JSON.stringify(await gscFetch("/webmasters/v3/sites", { accessToken }), null, 2));
} else if (command === "sitemaps") {
  const path = `/webmasters/v3/sites/${encodeSite(siteUrl)}/sitemaps`;
  console.log(JSON.stringify(await gscFetch(path, { accessToken }), null, 2));
} else if (command === "submit-sitemap") {
  const feedPath = process.argv[3];
  if (!feedPath) throw new Error("Missing sitemap URL.");
  const path = `/webmasters/v3/sites/${encodeSite(siteUrl)}/sitemaps/${encodeURIComponent(feedPath)}`;
  console.log(JSON.stringify(await gscFetch(path, { accessToken, method: "PUT" }), null, 2));
} else if (command === "inspect") {
  const inspectionUrl = process.argv[3] || config.GSC_DEFAULT_URL || DEFAULT_INSPECTION_URL;
  const body = { inspectionUrl, siteUrl, languageCode: "de-DE" };
  console.log(
    JSON.stringify(
      await gscFetch("/v1/urlInspection/index:inspect", {
        accessToken,
        method: "POST",
        body,
      }),
      null,
      2,
    ),
  );
} else if (command === "performance") {
  const days = Number(process.argv[3] || 28);
  const body = {
    startDate: todayMinusDays(days),
    endDate: todayMinusDays(2),
    dimensions: ["query", "page"],
    rowLimit: 100,
  };
  const path = `/webmasters/v3/sites/${encodeSite(siteUrl)}/searchAnalytics/query`;
  console.log(JSON.stringify(await gscFetch(path, { accessToken, method: "POST", body }), null, 2));
} else {
  usage();
  process.exit(1);
}
