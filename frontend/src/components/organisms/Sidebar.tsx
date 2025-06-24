'use client';
// frontend/src/components/organisms/Sidebar.tsx

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Home, MessageSquare } from 'lucide-react';

export default function Sidebar() {
  const path = usePathname();

  const items = [
    { label: 'Home', href: '/', icon: Home },
    { label: 'Chat', href: '/dashboard', icon: MessageSquare },
  ];

  return (
    <nav className="flex flex-col p-4 space-y-2">
      {items.map(({ label, href, icon: Icon }) => {
        const active = path === href;
        return (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-2 px-3 py-2 rounded-md ${
              active
                ? 'bg-brand-600 text-white'
                : 'hover:bg-gray-100 dark:hover:bg-gray-700'
            }`}
          >
            <Icon className="w-5 h-5" />
            <span className="font-medium">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
