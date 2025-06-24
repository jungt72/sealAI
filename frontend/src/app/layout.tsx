// src/app/layout.tsx

import Providers from './providers'
import type { ReactNode } from 'react'
import '../styles/globals.css'  // korrigierter Pfad

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="de">
      <body>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  )
}
