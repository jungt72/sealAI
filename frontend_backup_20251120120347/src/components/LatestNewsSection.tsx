// frontend/src/components/LatestNewsSection.tsx
'use client'

import { useEffect, useMemo, useState } from 'react'

type NewsEntry = {
  id: number
  attributes: {
    title?: string | null
    summary?: string | null
    publishedAt?: string | null
  }
}

type NewsResponse = {
  data?: NewsEntry[]
}

const formatNewsDate = (value?: string | null) => {
  if (!value) return 'Unveröffentlicht'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('de-DE', {
    month: 'long',
    year: 'numeric',
  }).format(date)
}

function useSiteNews() {
  const [entries, setEntries] = useState<NewsEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      try {
        const res = await fetch('/api/site-news', {
          signal: controller.signal,
          cache: 'no-store',
        })
        if (!res.ok) {
          throw new Error(`Failed to load news (${res.status})`)
        }
        const payload = (await res.json()) as NewsResponse
        if (!controller.signal.aborted) {
          setEntries(Array.isArray(payload.data) ? payload.data : [])
        }
      } catch (err) {
        if (controller.signal.aborted) return
        console.error(err)
        setError('News konnten nicht geladen werden.')
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }
    load()
    return () => controller.abort()
  }, [])

  return { entries, loading, error }
}

export default function LatestNewsSection() {
  const { entries, loading, error } = useSiteNews()

  const content = useMemo(() => {
    if (loading) {
      return (
        <ul className="mt-6 space-y-6">
          {[0, 1].map((idx) => (
            <li
              key={`news-skeleton-${idx}`}
              className="flex flex-col gap-3 rounded-xl border border-white/5 p-4 animate-pulse bg-white/5"
            >
              <div className="h-4 w-24 rounded bg-white/10" />
              <div className="h-4 w-3/4 rounded bg-white/20" />
              <div className="h-3 w-full rounded bg-white/10" />
            </li>
          ))}
        </ul>
      )
    }

    if (entries.length === 0) {
      return (
        <p className="mt-6 text-sm text-zinc-400">
          Sobald der erste Beitrag veröffentlicht ist, erscheint er hier automatisch.
        </p>
      )
    }

    return (
      <ul className="mt-6 space-y-6">
        {entries.map(({ id, attributes }) => (
          <li key={id} className="flex flex-col sm:flex-row sm:items-baseline gap-3">
            <span className="text-sm text-zinc-400 w-32 shrink-0">
              {formatNewsDate(attributes?.publishedAt)}
            </span>
            <div>
              <p className="text-zinc-100 font-medium">
                {attributes?.title ?? 'Unbenannter Eintrag'}
              </p>
              {attributes?.summary && (
                <p className="text-sm text-zinc-400 mt-1 max-w-2xl">
                  {attributes.summary}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
    )
  }, [entries, loading])

  return (
    <section id="news" className="relative bg-transparent">
      <div className="mx-auto max-w-7xl px-6 py-16 sm:py-20">
        <h2 className="text-2xl font-medium text-white">Latest news</h2>
        {error && <p className="mt-4 text-sm text-rose-300">{error}</p>}
        {content}
      </div>
    </section>
  )
}
