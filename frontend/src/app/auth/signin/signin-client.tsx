'use client'

import { signIn } from 'next-auth/react'
import Image from 'next/image'

export default function SignInButton() {
  return (
    <button
      onClick={() =>
        signIn('keycloak', { callbackUrl: '/chat' }) // ← wichtig!
      }
      className="px-6 py-3 rounded bg-blue-600 text-white hover:bg-blue-700"
    >
      <span className="mr-2 inline-block">
        <Image src="/keycloak.svg" alt="Keycloak" width={20} height={20} />
      </span>
      Sign in with Keycloak
    </button>
  )
}
