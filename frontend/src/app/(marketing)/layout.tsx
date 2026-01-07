import type { ReactNode } from "react";
import { Header } from "@/components/marketing-v0/header";

export default function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Header />
      <main className="pt-16">{children}</main>
    </>
  );
}
