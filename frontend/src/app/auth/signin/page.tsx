'use client';

import { signIn } from 'next-auth/react';

export default function SignIn() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <button
        onClick={() => signIn('keycloak', { callbackUrl: '/dashboard' })}
        className="px-6 py-3 rounded bg-blue-600 text-white hover:bg-blue-700"
      >
        Sign in with Keycloak
      </button>
    </div>
  );
}
