// src/app/page.tsx
'use client';

import { useRouter } from 'next/navigation';

export default function HomePage() {
  const router = useRouter();

  return (
    <div className="flex flex-col items-center justify-center h-[80vh] text-center space-y-6">
      <h1 className="text-4xl font-bold">Willkommen bei SealAI</h1>
      <p className="text-lg text-neutral-600 max-w-xl">
        Deine KI-gestützte Assistenz für die Auswahl von Dichtungen, Werkstoffen und Profilen.
      </p>
      <button
        onClick={() => router.push('/dashboard')}
        className="px-6 py-3 bg-black text-white rounded-2xl shadow hover:bg-neutral-800 transition"
      >
        Jetzt starten
      </button>
    </div>
  );
}
