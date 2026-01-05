// frontend/src/app/robots.ts
import type { MetadataRoute } from 'next'

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: ['/'],
        disallow: [
          '/auth',
          '/dashboard',
          '/admin',
          '/api', // API-Routen sollen i.d.R. nicht indexiert werden
        ],
      },
    ],
    sitemap: `${siteUrl}/sitemap.xml`,
  }
}
