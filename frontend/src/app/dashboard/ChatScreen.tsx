'use client';
import Chat from './components/Chat/ChatContainer';

type ChatScreenProps = {
  conversationId?: string;
};

export default function ChatScreen({ conversationId }: ChatScreenProps) {
  return <Chat chatId={conversationId ?? null} />;
}
