// frontend/src/app/auth/error/page.tsx
import type { Metadata } from 'next'
import React, { Suspense } from 'react'
import ErrorClient from './error-client'

export const dynamic = 'force-dynamic' // zwingt dynamisches Rendering

export const metadata: Metadata = {
  title: 'Anmeldefehler',
  robots: {
    index: false,
    follow: false,
  },
}

export default function ErrorPage() {
  return (
    <Suspense fallback={<div>Lade Fehlerseite…</div>}>
      <ErrorClient />
    </Suspense>
  )
}
