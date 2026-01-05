"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { signOut } from "next-auth/react";

export default function SignedOutPage() {
  const router = useRouter();

  useEffect(() => {
    void (async () => {
      try {
        await signOut({ redirect: false });
      } finally {
        router.replace("/auth/signin");
      }
    })();
  }, [router]);

  return (
    <div className="flex min-h-[60vh] w-full items-center justify-center px-6">
      <div className="max-w-md text-center">
        <div className="text-lg font-semibold text-slate-900">Du wirst abgemeldet…</div>
        <div className="mt-2 text-sm text-slate-600">
          Einen Moment bitte, du wirst zur Anmeldung weitergeleitet.
        </div>
      </div>
    </div>
  );
}

