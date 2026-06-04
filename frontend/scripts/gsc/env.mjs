import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { resolve } from "node:path";

export const DEFAULT_ENV_FILE = resolve(homedir(), ".sealai", "gsc.env");

export function loadEnv(file = process.env.GSC_ENV_FILE || DEFAULT_ENV_FILE) {
  if (!existsSync(file)) {
    return { file, values: {} };
  }

  const values = {};
  const raw = readFileSync(file, "utf8");

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const separator = trimmed.indexOf("=");
    if (separator === -1) continue;

    const key = trimmed.slice(0, separator).trim();
    let value = trimmed.slice(separator + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }

  return { file, values };
}

export function requireConfig(requiredKeys) {
  const { file, values } = loadEnv();
  const config = { ...values, ...process.env };
  const missing = requiredKeys.filter((key) => !config[key]);

  if (missing.length) {
    throw new Error(
      `Missing ${missing.join(", ")}. Add them to ${file} or export them in the shell.`,
    );
  }

  return { file, config };
}
