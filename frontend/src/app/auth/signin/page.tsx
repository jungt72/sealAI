'use client'

import { signIn } from 'next-auth/react'
import { useEffect } from 'react'

export default function SignIn() {
  useEffect(() => {
    signIn() // ruft den Keycloak-Fluss auf
  }, [])

  return <p>Weiterleitung zum Login …</p>
}
