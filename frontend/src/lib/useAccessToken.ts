// 📁 frontend/src/lib/useAccessToken.ts
import { useSession } from 'next-auth/react'
import { useEffect, useState } from 'react'

export default function useAccessToken() {
  const { data } = useSession()
  const [token, setToken] = useState<string | null>(null)

  /* 1) aus NextAuth   */
  useEffect(() => {
    if (data?.accessToken) setToken(data.accessToken as string)
  }, [data])

  /* 2) einmaliges Fallback: sessionStorage */
  useEffect(() => {
    if (!token) {
      const t = sessionStorage.getItem('sealai_jwt')
      if (t) setToken(t)
    } else {
      sessionStorage.setItem('sealai_jwt', token)
    }
  }, [token])

  return token
}
