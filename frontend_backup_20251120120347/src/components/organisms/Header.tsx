'use client';

import React from 'react';

interface HeaderProps {
  onToggle: () => void;
  isSidebarOpen: boolean;
}

export default function Header({ onToggle, isSidebarOpen }: HeaderProps) {
  return (
    <div className="flex items-center justify-between h-16 px-4 border-b border-gray-200">
      <button 
        onClick={onToggle}
        className="p-2 rounded hover:bg-gray-100"
        aria-label="Toggle Sidebar"
      >
        {isSidebarOpen ? '←' : '☰'}
      </button>
      <span className="font-semibold text-lg">🦭 SealAI</span>
      <div /> {/* Platzhalter für Rechtsshift */}
    </div>
  );
}
