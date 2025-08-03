'use client';

import { useState, ReactNode } from 'react';
import {
  ChevronDown,
  ClipboardList,
  MessageCircle,
  Settings,
} from 'lucide-react';

/* -------------------------------------------------
   Typdefinition für eine Accordion-Sektion
--------------------------------------------------*/
interface Section {
  id: 'form' | 'history' | 'settings';
  title: string;
  icon: ReactNode;
  content: ReactNode;
}

/* -------------------------------------------------
   AccordionTabs – vertikale Tabs, die nach unten
   ausklappen. Vollständig animiert mit Tailwind.
--------------------------------------------------*/
export default function AccordionTabs() {
  /* ---------- FIX: null zulassen, damit man alles einklappen kann ---------- */
  const [openId, setOpenId] =
    useState<'form' | 'history' | 'settings' | null>('form');

  /* ---------- Sektionen definieren ---------- */
  const SECTIONS: Section[] = [
    {
      id: 'form',
      title: 'Formular',
      icon: <ClipboardList className="h-4 w-4" />,
      content: (
        <form className="grid grid-cols-1 md:grid-cols-3 gap-4 py-4">
          <input className="border rounded px-3 py-2" placeholder="Feld A" />
          <input className="border rounded px-3 py-2" placeholder="Feld B" />
          <input className="border rounded px-3 py-2" placeholder="Feld C" />
          <textarea
            className="border rounded px-3 py-2 col-span-full"
            rows={4}
            placeholder="Beschreibung"
          />
          <button className="col-span-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition">
            Speichern
          </button>
        </form>
      ),
    },
    {
      id: 'history',
      title: 'Chat-History',
      icon: <MessageCircle className="h-4 w-4" />,
      content: (
        <div className="py-4 space-y-2 text-sm text-gray-600">
          {/* Hier später echten Verlauf laden */}
          <p>(Noch kein Verlauf geladen …)</p>
        </div>
      ),
    },
    {
      id: 'settings',
      title: 'Einstellungen',
      icon: <Settings className="h-4 w-4" />,
      content: (
        <div className="py-4 space-y-3 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" className="accent-blue-600" />
            Dark-Mode&nbsp;aktivieren
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="accent-blue-600" />
            Benachrichtigungen
          </label>
        </div>
      ),
    },
  ];

  /* ---------- Render ---------- */
  return (
    <div className="w-full space-y-2 pr-1 overflow-y-auto">
      {SECTIONS.map(sec => {
        const open = openId === sec.id;
        return (
          <div key={sec.id} className="border rounded-lg bg-white">
            {/* Header / Toggle */}
            <button
              onClick={() => setOpenId(open ? null : sec.id)}
              className={`flex w-full items-center justify-between px-3 py-2 text-sm font-medium
                ${open ? 'bg-blue-600 text-white' : 'bg-gray-50 hover:bg-gray-100 text-gray-700'}`}
            >
              <span className="flex items-center gap-2">
                {sec.icon}
                {sec.title}
              </span>
              <ChevronDown
                className={`h-4 w-4 transform transition-transform ${open ? 'rotate-180' : ''}`}
              />
            </button>

            {/* Panel */}
            <div
              className={`overflow-hidden transition-[max-height] duration-300 ease-in-out
                ${open ? 'max-h-screen' : 'max-h-0'}`}
            >
              {open && <div className="px-3">{sec.content}</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
