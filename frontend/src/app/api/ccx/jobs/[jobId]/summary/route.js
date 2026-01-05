import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";

function fileUrlIfExists(dir, jobId, ext) {
  const p = path.join(dir, `${jobId}.${ext}`);
  return fs.existsSync(p) ? `/files/${jobId}.${ext}` : undefined;
}

function tailLines(p, n = 50) {
  try {
    const txt = fs.readFileSync(p, "utf8");
    const lines = txt.split(/\r?\n/).filter(Boolean);
    return lines.slice(-n);
  } catch {
    return [];
  }
}

export async function GET(_req, { params }) {
  const jobId = params?.jobId ?? "unknown";
  const filesDir = process.env.JOB_FILES_DIR
    ? path.resolve(process.env.JOB_FILES_DIR)
    : path.join(process.cwd(), "public", "files");

  const datP = path.join(filesDir, `${jobId}.dat`);
  const frdP = path.join(filesDir, `${jobId}.frd`);
  const msgP = path.join(filesDir, `${jobId}.msg`);

  const logTail =
    tailLines(msgP, 50).length ? tailLines(msgP, 50)
    : tailLines(datP, 50).length ? tailLines(datP, 50)
    : tailLines(frdP, 50).length ? tailLines(frdP, 50)
    : ["kein Log verfügbar"];

  const body = {
    jobId,
    jobName: jobId,
    version: "2.22",
    status: "finished",
    runtimeSec: 0.01,
    converged: true,
    iterations: 1,
    lastUpdated: new Date().toISOString(),
    files: {
      dat: fileUrlIfExists(filesDir, jobId, "dat"),
      frd: fileUrlIfExists(filesDir, jobId, "frd"),
      vtu: fileUrlIfExists(filesDir, jobId, "vtu"),
    },
    logTail,
  };

  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
}
