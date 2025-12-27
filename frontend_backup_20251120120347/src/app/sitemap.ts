// frontend/src/app/sitemap.ts
import type { MetadataRoute } from 'next'

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000'

export default function sitemap(): MetadataRoute.Sitemap {
  const staticRoutes: string[] = [
    '/',
    '/docs',
    '/status',
    '/impressum',
    '/datenschutz',
    '/news',
  ]

  const now = new Date()

  return staticRoutes.map((route) => ({
    url: `${siteUrl}${route}`,
    lastModified: now,
    changeFrequency: route === '/' ? 'daily' : 'weekly',
    priority: route === '/' ? 1.0 : 0.7,
  }))
}
