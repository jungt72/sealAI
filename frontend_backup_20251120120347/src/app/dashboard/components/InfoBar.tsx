'use client';

import { useState } from 'react';
import clsx from 'clsx';
import { XMarkIcon, Bars3Icon } from '@heroicons/react/24/solid';

export default function InfoBar() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Drawer */}
      <aside
        className={clsx(
          'fixed right-0 top-0 h-full w-72 bg-white shadow-lg z-40',
          'transition-transform duration-300',
          open ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-semibold">Info</h3>
          <button onClick={() => setOpen(false)}>
            <XMarkIcon className="w-5 h-5 text-gray-500" />
          </button>
        </div>
        <div className="p-4 text-sm leading-relaxed">
          {/* z. B. RAG-Treffer, System-Status, Token-Verbrauch … */}
          Noch keine Inhalte.
        </div>
      </aside>

      {/* Toggle-FAB */}
      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-6 right-6 z-50 rounded-full p-3 shadow-lg
                   bg-blue-600 text-white hover:bg-blue-700 transition-colors"
      >
        {open ? <XMarkIcon className="w-6 h-6" /> : <Bars3Icon className="w-6 h-6" />}
      </button>
    </>
  );
}
