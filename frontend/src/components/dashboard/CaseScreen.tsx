"use client";

import ChatPane from "@/components/dashboard/ChatPane";

interface CaseScreenProps {
  caseId?: string;
}

export default function CaseScreen({ caseId }: CaseScreenProps) {
  return (
    <div className="flex h-full w-full overflow-hidden bg-surface">
      <div className="flex-1 min-w-0 relative">
        <ChatPane caseId={caseId} />
      </div>
    </div>
  );
}
