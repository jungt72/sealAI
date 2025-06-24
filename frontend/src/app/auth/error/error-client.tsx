'use client'

import { useSearchParams, useRouter } from 'next/navigation'

export default function ErrorClient() {
  const params = useSearchParams()
  const router = useRouter()
  const error = params?.get('error') || 'Unbekannter Fehler'

  return (
    <div className="flex h-screen items-center justify-center bg-gray-100 p-4">
      <div className="max-w-md bg-white rounded shadow-lg p-8 text-center">
        <h1 className="text-2xl font-bold mb-4">Anmeldefehler</h1>
        <p className="mb-4 text-red-600">{error}</p>
        <button
          onClick={() => router.replace('/auth/signin')}
          className="mt-4 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
        >
          Zurück zur Anmeldung
        </button>
      </div>
    </div>
  )
}
