import { NextRequest, NextResponse } from "next/server";
import { getAccessToken } from "@/lib/bff/auth-token";
import { buildBackendUrl } from "@/lib/bff/backend";

export const dynamic = "force-dynamic";
export const revalidate = 0;

/**
 * POST /api/bff/medium-intelligence
 * Proxies to backend GET /api/agent/medium-intelligence?medium=...&include_web_research=...
 * Returns structured medium intelligence JSON for the dashboard tile.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let medium: string;
  let includeWebResearch = false;

  try {
    const body = (await request.json()) as {
      medium?: unknown;
      include_web_research?: unknown;
    };
    const raw = body?.medium;
    if (typeof raw !== "string" || !raw.trim()) {
      return NextResponse.json(
        { error: "medium parameter required" },
        { status: 400 }
      );
    }
    medium = raw.trim();
    includeWebResearch = body?.include_web_research === true;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  let accessToken: string;
  try {
    accessToken = await getAccessToken(request);
  } catch {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const backendUrl = buildBackendUrl(
    `/api/agent/medium-intelligence?medium=${encodeURIComponent(medium)}&include_web_research=${includeWebResearch ? "true" : "false"}`
  );

  try {
    const res = await fetch(backendUrl, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
      signal: AbortSignal.timeout(includeWebResearch ? 90_000 : 60_000),
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: `Backend error: ${res.status}` },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: "Failed to fetch medium intelligence", detail: message },
      { status: 502 }
    );
  }
}
