'use client';

import { useSession, signIn } from 'next-auth/react';
import { useEffect } from 'react';
import { useSearchParams } from "next/navigation";
import { toRelativeCallbackUrl } from "@/lib/utils";
import Dashboard from "./Dashboard";

export default function DashboardClient() {
  const { status } = useSession();
  const searchParams = useSearchParams();
  // ChatId extracted for context if needed, though Dashboard handles its children
  // const chatId = (searchParams?.get("chat_id") || "").trim() || null;

  useEffect(() => {
    if (status === 'unauthenticated') {
      const callbackUrl = toRelativeCallbackUrl(window.location.href);
      signIn('keycloak', { callbackUrl });
    }
  }, [status]);

  if (status === 'loading') {
    return <div className="flex items-center justify-center min-h-screen text-lg text-gray-500">Lade Authentifizierung …</div>;
  }

  // ENFORCED: Platinum Supervisor View via Dashboard component
  return status === 'authenticated'
    ? <Dashboard />
    : <div className="flex items-center justify-center min-h-screen text-lg text-gray-500">Weiterleitung zum Login …</div>;
}
