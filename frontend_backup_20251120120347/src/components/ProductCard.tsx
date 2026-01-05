// frontend/src/components/ProductCard.tsx
'use client'

import { MouseEvent } from 'react'
import { signIn } from 'next-auth/react'

type ProductCardProps = {
  title: string
  desc: string
  cta: string
  href: string
  secondary?: boolean
  id?: string
}

export default function ProductCard({
  title,
  desc,
  cta,
  href,
  secondary,
  id,
}: ProductCardProps) {
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (href !== '/auth/signin') return

    event.preventDefault()
    const base =
      typeof window === 'undefined'
        ? process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000'
        : window.location.origin

    // Keycloak-Login via NextAuth
    signIn('keycloak', { callbackUrl: `${base}/dashboard` })
  }

  const effectiveHref =
    href === '/auth/signin'
      ? '/api/auth/signin?callbackUrl=/dashboard'
      : href

  return (
    <a
      id={id}
      href={effectiveHref}
      onClick={handleClick}
      className={[
        'group block rounded-2xl border p-6 transition bg-white/[0.03]',
        secondary ? 'border-white/15 hover:bg-white/5' : 'border-white/20 hover:bg-white/[0.06]',
      ].join(' ')}
    >
      <div className="text-base font-medium text-white">{title}</div>
      <p className="mt-2 text-sm text-zinc-400">{desc}</p>
      <div className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-white">
        {cta}
        <svg
          className="size-4 opacity-70 group-hover:translate-x-0.5 transition"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M5 12h14M13 5l7 7-7 7"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </a>
  )
}
