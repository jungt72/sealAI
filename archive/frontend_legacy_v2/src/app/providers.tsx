// src/app/providers.tsx
'use client'

import { SessionProvider } from 'next-auth/react'
import type { ReactNode } from 'react'
import { ParamStoreProvider } from "@/lib/stores/paramStore"

export default function Providers({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <ParamStoreProvider>{children}</ParamStoreProvider>
    </SessionProvider>
  )
}
