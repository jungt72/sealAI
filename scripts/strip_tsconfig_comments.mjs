#!/usr/bin/env node
import fs from "fs";

const inPath = process.argv[2];
if (!inPath) {
  console.error("usage: strip_tsconfig_comments.mjs <tsconfig.json>");
  process.exit(1);
}

const src = fs.readFileSync(inPath, "utf8");
let out = "";
let inString = false;
let stringChar = "";

for (let i = 0; i < src.length; i += 1) {
  const ch = src[i];
  const next = src[i + 1];

  if (!inString && ch === "/" && next === "/") {
    while (i < src.length && src[i] !== "\n") {
      i += 1;
    }
    out += "\n";
    continue;
  }

  if (!inString && ch === "/" && next === "*") {
    i += 2;
    while (i < src.length && !(src[i] === "*" && src[i + 1] === "/")) {
      i += 1;
    }
    i += 1;
    continue;
  }

  out += ch;

  if (inString) {
    if (ch === "\\" && i + 1 < src.length) {
      out += src[i + 1];
      i += 1;
      continue;
    }
    if (ch === stringChar) {
      inString = false;
      stringChar = "";
    }
  } else if (ch === '"' || ch === "'") {
    inString = true;
    stringChar = ch;
  }
}

try {
  const json = JSON.stringify(JSON.parse(out), null, 2);
  process.stdout.write(`${json}\n`);
} catch (err) {
  console.error("Failed to parse stripped JSON:", err.message);
  process.exit(1);
}
