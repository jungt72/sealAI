export const dynamic = "force-dynamic";

export async function GET() {
  const enc = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      const send = (obj) => controller.enqueue(enc.encode(`data: ${JSON.stringify(obj)}\n\n`));
      send({ status: "running" });
      setTimeout(() => { send({ status: "finished", converged: true }); controller.close(); }, 500);
    }
  });
  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive"
    }
  });
}
