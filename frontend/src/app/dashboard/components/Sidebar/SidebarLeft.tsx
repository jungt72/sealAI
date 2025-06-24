// src/app/dashboard/components/Sidebar/SidebarLeft.tsx
'use client';

import { FC } from 'react';
import { X } from 'lucide-react';

type Props = {
  onClose: () => void;
};

const SidebarLeft: FC<Props> = ({ onClose }) => {
  return (
    <div className="fixed inset-0 z-40 bg-black/40 md:static md:bg-white md:shadow-none">
      <aside className="w-64 h-full bg-white shadow-md p-4 md:relative md:z-0">
        {/* Schließen-Button nur auf mobilen Geräten */}
        <div className="flex justify-end md:hidden">
          <button onClick={onClose} className="text-gray-500 hover:text-gray-800">
            <X />
          </button>
        </div>

        <h2 className="text-base font-semibold mb-4">Navigation</h2>
        <ul className="space-y-2 text-sm">
          <li><a href="/dashboard" className="hover:underline">🏠 Start</a></li>
          <li><a href="/dashboard/chat" className="hover:underline">💬 Chat</a></li>
          <li><a href="/dashboard/formular" className="hover:underline">📝 Formular</a></li>
          <li><a href="/dashboard/historie" className="hover:underline">📊 Verlauf</a></li>
        </ul>
      </aside>
    </div>
  );
};

export default SidebarLeft;
