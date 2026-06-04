import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { auth } from "@/auth";
import DashboardShell from "@/components/dashboard/DashboardShell";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AuthenticatedDashboard>{children}</AuthenticatedDashboard>;
}

async function AuthenticatedDashboard({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.accessToken || session.error === "RefreshTokenError") {
    redirect("/login");
  }

  return <DashboardShell>{children}</DashboardShell>;
}
