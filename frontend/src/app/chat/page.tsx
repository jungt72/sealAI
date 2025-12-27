"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ChatRootPage() {
  const router = useRouter();

  useEffect(() => {
    const id = crypto.randomUUID();
    router.replace(`/chat/${id}`);
  }, [router]);

  return (
    <div className="flex h-full items-center justify-center text-sm text-slate-500">
      Starte neue Unterhaltung …
    </div>
  );
}
