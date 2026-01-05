// frontend/src/components/Header.tsx
'use client'

import { signIn } from 'next-auth/react'

export default function Header() {
  return (
    <header className="absolute top-0 left-0 right-0 z-50 bg-transparent">
      <div className="mx-auto max-w-7xl px-6 py-4 flex items-center justify-between">
        <a href="/" className="flex items-center gap-3">
          <img src="/logo_sai.svg" alt="SealAI" className="h-6 w-auto" />
          <span className="sr-only">SealAI</span>
        </a>
        <nav aria-label="Primary" className="hidden md:block">
          <ul className="flex items-center gap-8 text-sm text-zinc-300">
            <li>
              <a href="#products" className="hover:text-white">
                Products
              </a>
            </li>
            <li>
              <a href="#api" className="hover:text-white">
                API
              </a>
            </li>
            <li>
              <a href="#company" className="hover:text-white">
                Company
              </a>
            </li>
            <li>
              <a href="#careers" className="hover:text-white">
                Careers
              </a>
            </li>
            <li>
              <a href="#news" className="hover:text-white">
                News
              </a>
            </li>
            <li>
              <a href="/admin" className="hover:text-white">
                Strapi CMS
              </a>
            </li>
          </ul>
        </nav>
        <div className="flex items-center gap-3">
          <a
            href="/api/auth/signin?callbackUrl=/dashboard"
            onClick={(e) => {
              e.preventDefault()
              const base =
                process.env.NEXT_PUBLIC_SITE_URL || window.location.origin
              signIn('keycloak', { callbackUrl: `${base}/dashboard` })
            }}
            className="inline-flex items-center rounded-xl border border-white/20 px-4 py-2 text-sm font-medium text-white hover:bg-white/10"
          >
            Try SealAI
          </a>
        </div>
      </div>
    </header>
  )
}
