#!/usr/bin/env node
const fs = require("node:fs");
const path = require("node:path");

const projectRoot = path.resolve(__dirname, "..");
let vitestEntry;
try {
  vitestEntry = require.resolve("vitest", { paths: [projectRoot] });
} catch (err) {
  console.warn("vitest entrypoint not found, skipping patch");
  process.exit(0);
}
const configPath = path.join(path.dirname(vitestEntry), "dist", "config.cjs");

let source;
try {
  source = fs.readFileSync(configPath, "utf8");
} catch (err) {
  console.warn("vitest dist config not readable, skipping patch");
  process.exit(0);
}
if (source.includes("mergeConfig$1")) {
  process.exit(0);
}

const fallbackBlock = `
var vite;
var mergeConfig$1;
try {
  vite = require("vite");
  mergeConfig$1 = vite.mergeConfig;
} catch (error) {
  if (error && error.code !== "ERR_REQUIRE_ESM") {
    throw error;
  }
  mergeConfig$1 = function mergeConfig$1(config, overrides) {
    const base = config ? { ...config } : {};
    if (!overrides) {
      return base;
    }
    for (const key of Object.keys(overrides)) {
      base[key] = overrides[key];
    }
    return base;
  };
}
`;

const modified = source
  .replace("var vite = require('vite');", fallbackBlock.trimStart())
  .replace("return vite.mergeConfig;", "return mergeConfig$1;");

if (modified === source) {
  console.warn("vitest config patch did not change anything");
  process.exit(0);
}

fs.writeFileSync(configPath, modified);
