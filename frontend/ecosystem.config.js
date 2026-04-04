const fs = require("fs");
const path = require("path");

function loadEnvFile(filePath) {
  const content = fs.readFileSync(filePath, "utf8");
  const env = {};

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    const separatorIndex = line.indexOf("=");
    if (separatorIndex === -1) continue;

    const key = line.slice(0, separatorIndex).trim();
    let value = line.slice(separatorIndex + 1).trim();

    value = value.replace(/\$\{([^}]+)\}/g, (_, name) => env[name] ?? process.env[name] ?? "");
    env[key] = value;
  }

  return env;
}

const productionEnvPath = path.resolve(__dirname, "..", ".env.prod");
const productionEnv = loadEnvFile(productionEnvPath);

module.exports = {
  apps: [
    {
      name: "sealai-frontend",
      script: "./.next/standalone/server.js",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 10,
      watch: false,
      env: {
        NODE_ENV: "production",
        PORT: 3000,
        AUTH_TRUST_HOST: productionEnv.AUTH_TRUST_HOST,
        AUTH_URL: productionEnv.AUTH_URL,
        AUTH_SECRET: productionEnv.AUTH_SECRET,
        NEXTAUTH_URL: productionEnv.NEXTAUTH_URL,
        NEXTAUTH_SECRET: productionEnv.NEXTAUTH_SECRET,
        NEXTAUTH_DEBUG: productionEnv.NEXTAUTH_DEBUG,
        AUTH_DEBUG: productionEnv.AUTH_DEBUG,
        KEYCLOAK_CLIENT_ID: productionEnv.KEYCLOAK_CLIENT_ID,
        KEYCLOAK_CLIENT_SECRET: productionEnv.KEYCLOAK_CLIENT_SECRET,
        KEYCLOAK_ISSUER: productionEnv.KEYCLOAK_ISSUER,
        NEXT_PUBLIC_API_BASE: productionEnv.NEXT_PUBLIC_API_BASE,
        // Set at deploy time via: pm2 restart sealai-frontend --update-env
        // This allows Next.js to signal stale clients when the build changes.
        NEXT_DEPLOYMENT_ID: process.env.NEXT_DEPLOYMENT_ID || "local",
      },
    },
  ],
};
