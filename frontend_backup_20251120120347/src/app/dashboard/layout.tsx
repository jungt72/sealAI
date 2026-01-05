// frontend/src/app/dashboard/layout.tsx
import type { ReactNode } from 'react'
import type { Metadata } from 'next'
import DashboardShell from './DashboardShell'

export const dynamic = 'force-dynamic'
export const revalidate = 0

// Dashboard ist rein intern → noindex
export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
}

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>
}
