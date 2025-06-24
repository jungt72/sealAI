// 📄 frontend/components/ui/card.tsx

import React from "react";

export function Card({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        border: "1px solid #ccc",
        borderRadius: "0.5rem",
        padding: "1rem",
        backgroundColor: "#fff",
        boxShadow: "0 2px 6px rgba(0,0,0,0.05)"
      }}
    >
      {children}
    </div>
  );
}
