'use client';

import { FC } from 'react';

const SidebarRight: FC = () => {
  return (
    <div className="h-full w-full p-4">
      <h2 className="text-lg font-semibold mb-4">Optionen</h2>
      <ul className="space-y-2 text-sm">
        <li><button className="hover:underline">🌙 Dark Mode</button></li>
        <li><button className="hover:underline">⚙️ Einstellungen</button></li>
        <li><button className="hover:underline">📤 Export</button></li>
      </ul>
    </div>
  );
};

export default SidebarRight;
