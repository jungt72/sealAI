// WS-only: SSE-Proxy deaktiviert.
// Gibt 410 zurück, damit nichts mehr über SSE läuft.

export const runtime = "edge";
export const dynamic = "force-dynamic";

function gone() {
  return new Response(
    JSON.stringify({
      error: "SSE removed. Please use WebSocket at /api/v1/ai/ws.",
    }),
    {
      status: 410,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    }
  );
}

export async function GET() {
  return gone();
}

export async function POST() {
  return gone();
}
