// frontend/src/app/auth/signin/SignInClient.tsx
'use client'

import { signIn } from 'next-auth/react'
import { DEFAULT_CALLBACK_URL, toRelativeCallbackUrl } from "@/lib/utils";

type SignInClientProps = { callbackUrl?: string; provider?: string };

export default function SignInClient({ callbackUrl, provider }: SignInClientProps) {
  const resolvedCallbackUrl = callbackUrl
    ? toRelativeCallbackUrl(callbackUrl)
    : DEFAULT_CALLBACK_URL;
  const resolvedProvider = provider || 'keycloak'

  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <button
        onClick={() =>
          signIn(resolvedProvider, {
            callbackUrl: resolvedCallbackUrl,
          })
        }
        className="px-6 py-3 rounded bg-blue-600 text-white hover:bg-blue-700"
      >
        Sign in with Keycloak
      </button>
    </div>
  )
}
