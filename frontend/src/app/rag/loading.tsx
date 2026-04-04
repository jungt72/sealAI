/**
 * Loading-Skeleton für die RAG/Knowledge-Base-Seite.
 * Spiegelt das Dokumenten-Grid-Layout — feste Dimensionen verhindern CLS.
 */
export default function RagLoading() {
  return (
    <div className="min-h-full bg-seal-bg p-6">
      {/* Header Skeleton */}
      <div className="mb-6">
        <div className="mb-2 h-7 w-48 animate-pulse rounded-xl bg-slate-200" />
        <div className="h-4 w-72 animate-pulse rounded-lg bg-slate-100" />
      </div>

      {/* Upload-Zone Skeleton */}
      <div className="mb-6 h-28 w-full animate-pulse rounded-2xl border-2 border-dashed border-slate-200 bg-white/60" />

      {/* Dokument-Grid Skeleton */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, index) => (
          <div
            key={index}
            className="flex h-40 flex-col justify-between rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-sm"
          >
            <div className="space-y-2">
              <div className="h-4 w-3/4 animate-pulse rounded-lg bg-slate-100" />
              <div className="h-3 w-1/2 animate-pulse rounded-lg bg-slate-100" />
            </div>
            <div className="flex items-center justify-between">
              <div className="h-5 w-16 animate-pulse rounded-full bg-slate-100" />
              <div className="h-7 w-7 animate-pulse rounded-lg bg-slate-100" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
