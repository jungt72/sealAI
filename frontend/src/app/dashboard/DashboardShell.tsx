'use client';

import { useSession } from 'next-auth/react';
import { ReactNode, useState } from 'react';
import { Menu as MenuIcon, X as XIcon, Info as InfoIcon } from 'lucide-react';
import { logout } from '@/lib/logout';
import AccordionTabs from './components/Sidebar/AccordionTabs';

const bigShadow   = 'shadow-[0_14px_32px_rgba(0,0,0,0.18)]';
const smallShadow = 'shadow-[0_6px_18px_rgba(0,0,0,0.10)]';

interface DashboardShellProps { children: ReactNode; }

export default function DashboardShell({ children }: DashboardShellProps) {
  const { data: session } = useSession();
  const idToken = (session as any)?.idToken;
  const userName = session?.user?.name ?? '';

  const [leftOpen,  setLeftOpen]  = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  return (
    <div className="relative h-screen w-screen flex flex-col bg-white">
      <div className="fixed top-4 left-4 z-50">
        <img src="/logo_sai.svg" alt="SealAI Logo" className="h-10 w-10 md:h-12 md:w-12 drop-shadow-lg select-none" draggable={false}/>
      </div>

      <div className="fixed top-4 right-4 z-50 flex flex-row items-center gap-3">
        <button
          onClick={() => logout(idToken)}
          className="px-4 py-2 bg-red-600 text-white rounded-xl hover:bg-red-700 transition font-medium shadow"
        >
          Abmelden
        </button>
      </div>
      <button
        onClick={() => setRightOpen(o => !o)}
        className="fixed top-28 right-4 z-50 p-2 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-full shadow transition"
      >
        {rightOpen ? <XIcon className="h-5 w-5" /> : <InfoIcon className="h-6 w-6" />}
      </button>

      <div className="flex flex-1 min-h-0">
        <aside
          className={`relative flex flex-col h-full py-6 bg-white border-r transition-all duration-300
            ${leftOpen ? `w-[40vw] max-w-[560px] min-w-[300px] ${bigShadow}`
                       : `w-[8px] min-w-[8px] ${smallShadow}`}`}
        >
          <button
            onClick={() => setLeftOpen(o => !o)}
            className="absolute top-28 left-4 z-50 p-2 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-full shadow transition"
          >
            {leftOpen ? <XIcon className="h-5 w-5" /> : <MenuIcon className="h-6 w-6" />}
          </button>
          {leftOpen && (
            <div className="mt-10 w-full px-4 overflow-hidden">
              <AccordionTabs />
              <div className="mt-6 flex flex-col items-center">
                <span className="text-gray-900 font-medium text-sm truncate max-w-[160px]">
                  {userName}
                </span>
              </div>
            </div>
          )}
        </aside>

        {/* Chat-Bereich ~Grok-Breite */}
        <main className="flex-1 flex flex-col items-center justify-end min-h-0 bg-white">
          <div
            className="
              w-full max-w-[760px] flex flex-col flex-1
              h-full min-h-0 bg-white rounded-2xl shadow-sm
              px-3 sm:px-5 md:px-6 py-3 sm:py-4 mx-auto transition-all
            "
          >
            {children}
          </div>
        </main>

        <aside
          className={`relative flex flex-col h-full py-6 bg-white border-l transition-all duration-300
            ${rightOpen ? `w-[240px] ${bigShadow}` : `w-[8px] min-w-[8px] ${smallShadow}`}`}
        >
          {rightOpen && (
            <div className="mt-10 w-full px-4 overflow-y-auto">
              <h2 className="text-base font-semibold text-gray-700 mb-3">Info &amp; Tools</h2>
              <ul className="space-y-2 text-gray-600 text-sm">
                <li>Hilfe</li>
                <li>Support</li>
                <li>Versionsinfo</li>
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
