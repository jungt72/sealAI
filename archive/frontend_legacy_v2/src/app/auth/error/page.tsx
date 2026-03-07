// src/app/auth/error/page.tsx
import React, { Suspense } from 'react'
import ErrorClient from './error-client'

export const dynamic = 'force-dynamic'  // zwingt dynamisches Rendering

export default function ErrorPage() {
  return (
    <Suspense fallback={<div>Lade Fehlerseite…</div>}>
      <ErrorClient />
    </Suspense>
  )
}
