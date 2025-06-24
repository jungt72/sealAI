// frontend/src/app/api/ai/chat/stream/route.ts
/**
 * Edge-Runtime-Route, die Streaming-Requests an das
 * FastAPI-Backend weiterleitet (→ /api/v1/ai/chat/stream).
 *
 * Vorteile
 * --------
 * • Relativer Aufruf aus dem Frontend (keine CORS-Probleme)
 * • Versteckt die Backend-URL / -Ports
 * • Übernimmt Auth-Header Durchleitung
 *
 * NEXT_PUBLIC_BACKEND_URL  -> z. B. "http://localhost:8000"
 */

import { NextRequest } from 'next/server'

export const runtime = 'edge'

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, '') || 'http://localhost:8000'

export async function POST(req: NextRequest) {
  const body = await req.text()

  // Auth-Header (z. B. “Bearer <JWT>”) einfach weiterreichen
  const headers = new Headers({
    'Content-Type': 'application/json',
  })
  const auth = req.headers.get('authorization')
  if (auth) headers.set('authorization', auth)

  const backendResp = await fetch(`${BACKEND_URL}/api/v1/ai/chat/stream`, {
    method: 'POST',
    headers,
    body,
  })

  // Alle relevanten Header eins-zu-eins übernehmen
  const respHeaders = new Headers()
  backendResp.headers.forEach((v, k) => respHeaders.set(k, v))

  // Stream ungepuffert an den Client durchreichen
  return new Response(backendResp.body, {
    status: backendResp.status,
    headers: respHeaders,
  })
}
