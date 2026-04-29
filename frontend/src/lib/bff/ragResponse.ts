import { sanitizeRagPayload, sanitizeUserVisibleText } from "@/lib/ragRedaction";

export function ragPassthroughResponse(response: Response, body: string) {
  const contentType = response.headers.get("content-type") || "application/json; charset=utf-8";
  const isJson = contentType.toLowerCase().includes("application/json");

  if (!isJson || !body) {
    return new Response(sanitizeUserVisibleText(body), {
      status: response.status,
      headers: { "Content-Type": contentType },
    });
  }

  try {
    return Response.json(sanitizeRagPayload(JSON.parse(body)), {
      status: response.status,
    });
  } catch {
    return new Response(sanitizeUserVisibleText(body), {
      status: response.status,
      headers: { "Content-Type": contentType },
    });
  }
}
