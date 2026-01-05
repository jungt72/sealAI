import { redirect } from "next/navigation";

interface ConversationPageProps {
  params: {
    conversationId: string;
  };
}

export default function ConversationPage({ params }: ConversationPageProps) {
  const { conversationId } = params;
  redirect(`/dashboard?chat_id=${encodeURIComponent(conversationId)}`);
}
