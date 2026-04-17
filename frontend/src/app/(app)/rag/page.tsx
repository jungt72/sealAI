import RagDocumentGrid from "@/components/rag/RagDocumentGrid";

export default function RagPage() {
  return (
    <main className="min-h-screen bg-[radial-gradient(1100px_620px_at_15%_-10%,rgba(14,165,233,0.22),transparent_55%),radial-gradient(900px_520px_at_90%_0%,rgba(20,184,166,0.20),transparent_60%),linear-gradient(165deg,#020617_0%,#0b1221_48%,#111827_100%)] px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-7xl">
        <RagDocumentGrid />
      </div>
    </main>
  );
}
