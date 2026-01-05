// frontend/src/app/auth/signin/page.tsx
import type { Metadata } from 'next'
import SignInClient from './SignInClient'

export const metadata: Metadata = {
  title: 'Anmelden',
  robots: {
    index: false,
    follow: false,
  },
}

export default function SignInPage() {
  return <SignInClient />
}
