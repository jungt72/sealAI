export const dynamic = "force-dynamic";
export const revalidate = 0;

// Server Component – KEIN "use client", KEINE Hooks.
// "params" ist optional, damit kein Runtime-Fehler entsteht.
export default function CcxPage(props: { params?: { chatId?: string } }) {
  const chatId = props?.params?.chatId ?? null;

  return (
    <main className="max-w-3xl mx-auto p-6">
      <h1 className="text-2xl font-semibold tracking-tight">CCX</h1>
      <p className="text-zinc-600 dark:text-zinc-300 mt-2">
        {chatId ? <>Chat-ID: <code>{chatId}</code></> : "Keine Chat-ID übergeben."}
      </p>
    </main>
  );
}
