// 'use client' ─ muss im Browser laufen
'use client'

import Chat from './components/Chat/Chat'

export default function ChatScreen() {
  return (
    <div className="flex h-full w-full">
      <Chat />
    </div>
  )
}
