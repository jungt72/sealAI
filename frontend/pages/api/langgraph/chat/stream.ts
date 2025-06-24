// 📁 frontend/pages/api/langgraph/chat/stream.ts
import type { NextApiRequest, NextApiResponse } from 'next'
import type { Readable } from 'stream'

export const config = {
  api: {
    bodyParser: false,    // wir parsen den Body selbst
    externalResolver: true, // damit Next.js nicht mittendrin autoflush macht
  },
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'POST') {
    res.status(405).end('Method Not Allowed')
    return
  }

  const auth = req.headers.authorization
  if (!auth?.startsWith('Bearer ')) {
    res.setHeader('WWW-Authenticate', 'Bearer')
    res.status(401).json({ error: 'Unauthorized' })
    return
  }
  const token = auth.split(' ')[1]

  // Body einlesen
  const buffers: Buffer[] = []
  for await (const chunk of (req as any) as AsyncIterable<Buffer>) {
    buffers.push(chunk)
  }
  const { input_text, chat_id } = JSON.parse(Buffer.concat(buffers).toString('utf-8'))
  if (!input_text || !chat_id) {
    res.status(400).json({ error: 'input_text and chat_id required' })
    return
  }

  // eigentliche Backend-URL
  const BACKEND = process.env.BACKEND_URL || 'https://sealai.net'

  // SSE-Header
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    Connection: 'keep-alive',
    'Cache-Control': 'no-cache',
  })

  // Fetch zum echten Backend und Pipe chunkweise
  const upstream = await fetch(
    `${BACKEND}/api/v1/langgraph/chat/stream`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ input_text, chat_id }),
    }
  )
  if (!upstream.body) {
    res.end()
    return
  }

  const reader = (upstream.body as Readable).getReader()
  const decoder = new TextDecoder()
  let done = false
  while (!done) {
    const { value, done: streamDone } = await reader.read()
    done = streamDone
    if (value) {
      // wir schreiben jeden Chunk sofort raus
      const chunk = decoder.decode(value)
      res.write(chunk)
    }
  }

  res.write('\n')  // sicherheitshalber
  res.end()
}
