'use client';

import { useSession, signIn } from 'next-auth/react';
import { useEffect } from 'react';
import { useSearchParams } from "next/navigation";
import ChatContainer from "./components/Chat/ChatContainer";

export default function DashboardClient() {
  const { status } = useSession();
  const searchParams = useSearchParams();
  const chatId = (searchParams?.get("chat_id") || "").trim() || null;

  useEffect(() => {
    if (status === 'unauthenticated') {
      const base = process.env.NEXT_PUBLIC_SITE_URL || window.location.origin;
      signIn('keycloak', { callbackUrl: `${base}/chat` });
    }
  }, [status]);

  if (status === 'loading') {
    return <div className="flex items-center justify-center min-h-screen text-lg text-gray-500">Lade Authentifizierung …</div>;
  }

  return status === 'authenticated'
    ? <ChatContainer chatId={chatId} />
    : <div className="flex items-center justify-center min-h-screen text-lg text-gray-500">Weiterleitung zum Login …</div>;
}
