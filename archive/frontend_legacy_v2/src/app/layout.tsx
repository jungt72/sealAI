// src/app/layout.tsx
import Providers from './providers'
import type { ReactNode } from 'react'
import '../styles/globals.css'
import SiteBackground from '../components/SiteBackground'

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="de">
      <body className="bg-black text-zinc-200 antialiased">
        {/* Globaler Hintergrund für die komplette Seite */}
        <SiteBackground />

        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  )
}
