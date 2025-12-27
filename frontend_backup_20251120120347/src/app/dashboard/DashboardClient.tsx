"use client";

import ChatContainer from "./components/Chat/ChatContainer";

export default function DashboardClient() {
  return (
    <div className="flex h-[calc(100vh-64px)] flex-col bg-gradient-to-b from-slate-50 to-slate-100">
      <main className="flex flex-1 justify-center px-4 py-6">
        <div className="w-full max-w-5xl">
          <ChatContainer />
        </div>
      </main>
    </div>
  );
}
