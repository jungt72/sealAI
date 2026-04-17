/**
 * Loading-Skeleton für das Dashboard.
 * Spiegelt das echte Layout (Chat-Pane + Workspace-Sidebar) —
 * feste Dimensionen verhindern CLS.
 */
export default function DashboardLoading() {
  return (
    <div className="h-full w-full overflow-hidden bg-seal-dashboard">
      <div className="relative mx-auto grid h-full w-full max-w-[1880px] grid-cols-1 gap-4 p-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,0.95fr)] 2xl:grid-cols-[minmax(0,1.6fr)_minmax(400px,0.9fr)]">
        {/* Chat-Pane Skeleton */}
        <div className="flex h-full flex-col overflow-hidden rounded-[30px] border border-slate-200/80 bg-white/95 shadow-[0_22px_60px_rgba(15,23,42,0.08)]">
          <div className="flex flex-1 flex-col items-center justify-center gap-6 px-8">
            <div className="h-20 w-60 animate-pulse rounded-2xl bg-slate-100" />
            <div className="h-8 w-72 animate-pulse rounded-xl bg-slate-100" />
          </div>
          {/* Composer Skeleton */}
          <div className="mx-auto w-full max-w-3xl px-4 pb-8">
            <div className="h-[56px] w-full animate-pulse rounded-2xl border border-slate-200 bg-slate-50" />
          </div>
        </div>

        {/* Workspace-Sidebar Skeleton (nur xl+) */}
        <div className="hidden h-full flex-col overflow-hidden rounded-[30px] border border-slate-200/80 bg-white/95 shadow-[0_22px_60px_rgba(15,23,42,0.08)] xl:flex">
          <div className="border-b border-slate-200 px-5 py-4">
            <div className="mb-1.5 h-2.5 w-28 animate-pulse rounded-full bg-slate-200" />
            <div className="h-5 w-36 animate-pulse rounded-full bg-slate-100" />
          </div>
          <div className="flex flex-1 flex-col gap-4 overflow-hidden px-4 py-4">
            <div className="h-36 w-full animate-pulse rounded-3xl bg-slate-50" />
            <div className="h-28 w-full animate-pulse rounded-3xl bg-slate-50" />
            <div className="h-44 w-full animate-pulse rounded-3xl bg-slate-50" />
          </div>
        </div>
      </div>
    </div>
  );
}
