import Link from "next/link";

export default function Sidebar({ className = "" }: { className?: string }) {
  return (
    <aside className={className + " flex flex-col p-6"}>
      <h2 className="text-2xl font-bold mb-8 dark:text-gray-100">SealAI</h2>
      <nav className="flex-1 space-y-2">
        <Link
          href="/dashboard"
          className="block px-4 py-2 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
        >
          Chat
        </Link>
        <Link
          href="/dashboard/history"
          className="block px-4 py-2 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
        >
          Verlauf
        </Link>
      </nav>
    </aside>
  );
}
