// frontend/src/app/auth/signin/SignInClient.tsx
'use client'

import { signIn } from 'next-auth/react'

export default function SignInClient() {
  const base =
    typeof window === 'undefined'
      ? process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000'
      : window.location.origin

  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <button
        onClick={() =>
          signIn('keycloak', {
            callbackUrl: `${base}/chat`,
          })
        }
        className="px-6 py-3 rounded bg-blue-600 text-white hover:bg-blue-700"
      >
        Sign in with Keycloak
      </button>
    </div>
  )
}
