'use client';

import { useSession } from 'next-auth/react';
import { useEffect } from 'react';
import { signIn } from 'next-auth/react';
import ChatScreen from './ChatScreen';

export default function DashboardPage() {
  const { status } = useSession();

  useEffect(() => {
    if (status === 'unauthenticated') {
      // Startet Keycloak-SSO sofort im Client – kein SSR-Redirect!
      signIn('keycloak', { callbackUrl: '/dashboard' });
    }
  }, [status]);

  if (status === 'loading') {
    return (
      <div className="flex items-center justify-center min-h-screen text-lg text-gray-500">
        Lade Authentifizierung ...
      </div>
    );
  }
  if (status === 'authenticated') {
    return <ChatScreen />;
  }
  // Falls unauthenticated, wird sofort umgeleitet
  return (
    <div className="flex items-center justify-center min-h-screen text-lg text-gray-500">
      Weiterleitung zum Login ...
    </div>
  );
}
