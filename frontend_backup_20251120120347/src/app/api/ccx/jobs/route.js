import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";

/**
 * Listet vorhandene CCX-Jobs aus JOB_FILES_DIR oder ./public/files.
 * Ein Job gilt als finished, wenn .frd existiert.
 */
export async function GET() {
  const filesDir = process.env.JOB_FILES_DIR
    ? path.resolve(process.env.JOB_FILES_DIR)
    : path.join(process.cwd(), "public", "files");

  let entries = [];
  try {
    entries = fs.readdirSync(filesDir);
  } catch {
    return new Response(JSON.stringify({ jobs: [] }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  const jobIds = new Set(
    entries
      .map((f) => /^(.+)\.(dat|frd|vtu|msg)$/i.exec(f)?.[1])
      .filter(Boolean)
  );

  const jobs = Array.from(jobIds).map((jobId) => {
    const p = (ext) => path.join(filesDir, `${jobId}.${ext}`);
    const has = (ext) => fs.existsSync(p(ext));
    const mtimes = ["msg", "dat", "frd", "vtu"]
      .filter(has)
      .map((ext) => fs.statSync(p(ext)).mtimeMs);
    const lastUpdated =
      mtimes.length ? new Date(Math.max(...mtimes)).toISOString() : null;

    return {
      jobId,
      status: has("frd") ? "finished" : has("dat") ? "running" : "queued",
      lastUpdated,
      files: {
        dat: has("dat") ? `/files/${jobId}.dat` : undefined,
        frd: has("frd") ? `/files/${jobId}.frd` : undefined,
        vtu: has("vtu") ? `/files/${jobId}.vtu` : undefined,
      },
    };
  });

  return new Response(JSON.stringify({ jobs }), {
    headers: { "Content-Type": "application/json" },
  });
}
