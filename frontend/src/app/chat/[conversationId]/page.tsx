import ChatScreen from "@/app/dashboard/ChatScreen";

interface ConversationPageProps {
  params: {
    conversationId: string;
  };
}

export default function ConversationPage({ params }: ConversationPageProps) {
  const { conversationId } = params;
  return (
    <div className="flex h-full w-full overflow-hidden bg-white">
      <ChatScreen conversationId={conversationId} />
    </div>
  );
}
