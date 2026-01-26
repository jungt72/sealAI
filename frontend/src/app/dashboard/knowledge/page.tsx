"use client";

import { useMemo } from "react";
import { useAccessToken } from "@/lib/useAccessToken";
import { hasKnowledgeAccess } from "@/lib/authz";
import KnowledgeDocumentsPanel from "../components/Knowledge/KnowledgeDocumentsPanel";

export default function KnowledgePage() {
  const { token, error } = useAccessToken();
  const canManage = useMemo(() => hasKnowledgeAccess(token), [token]);

  if (error === "expired") {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        Sitzung abgelaufen. Bitte erneut anmelden.
      </div>
    );
  }

  if (!token) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        Lade Berechtigungen …
      </div>
    );
  }

  if (!canManage) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="rounded-2xl border border-slate-200 bg-white px-6 py-5 text-center shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-400">403</div>
          <div className="mt-1 text-lg font-bold text-slate-900">Nicht autorisiert</div>
          <div className="mt-2 text-sm text-slate-500">
            Diese Seite ist nur für Admins und Editoren verfügbar.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4">
      <KnowledgeDocumentsPanel canManage={canManage} />
    </div>
  );
}
