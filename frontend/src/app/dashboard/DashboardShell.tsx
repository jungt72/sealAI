'use client'

import { useSession } from 'next-auth/react'
import { ReactNode } from 'react'
import { handleLogout } from '@/lib/logout'

interface DashboardShellProps {
  children: ReactNode
}

export default function DashboardShell({ children }: DashboardShellProps) {
  const { data: session, status } = useSession()

  /** Token, den wir an / api/auth/custom-logout schicken */
  const idToken =
    session?.idToken            // falls explizit vorhanden
      ?? session?.accessToken   // sonst Access-Token
      ?? ''

  const userName = session?.user?.name ?? ''

  const handleLogoutClick = () => handleLogout(idToken)

  if (status === 'loading')
    return <div className="p-6 text-gray-500">Authentifizierung läuft …</div>

  return (
    <div className="flex h-screen">
      {/* === Sidebar / Header etc. könnten hier stehen === */}
      <main className="flex-1 overflow-y-auto bg-gray-50 p-6">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-semibold">Willkommen {userName}</h1>
          <button
            onClick={handleLogoutClick}
            className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
          >
            Abmelden
          </button>
        </div>

        {children}
      </main>
    </div>
  )
}
