export const runtime = 'edge'
export const dynamic = 'force-dynamic'

import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest, context: any) {
  const conversationId = context?.params?.conversationId

  if (!conversationId) {
    return NextResponse.json(
      { error: 'Missing conversationId in route context' },
      { status: 400 }
    )
  }

  const authHeader = request.headers.get('authorization')
  const token = authHeader?.split(' ')[1]

  if (!token) {
    return NextResponse.json(
      { error: 'Unauthorized – token missing' },
      { status: 401 }
    )
  }

  const body = await request.json()

  // Nutze absolute Backend-URL aus ENV
  const backendUrl =
    (process.env.BACKEND_URL || 'http://localhost:8000') +
    `/api/v1/langgraph/chat/${conversationId}/chat_stream`

  const backendRes = await fetch(backendUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
  })

  return new NextResponse(backendRes.body, {
    status: backendRes.status,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  })
}
