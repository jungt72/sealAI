'use client';
export default function Thinking() {
  return (
    <div
      className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
      aria-live="polite"
      role="status"
      title="Antwort wird generiert …"
    >
      <span className="sr-only">Antwort wird generiert …</span>
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: '0ms' }} />
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: '120ms' }} />
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: '240ms' }} />
    </div>
  );
}
