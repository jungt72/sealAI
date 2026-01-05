"use client";

export default function LogoutButton() {
  return (
    <div className="fixed top-4 right-4 z-50">
      <button
        onClick={() => window.location.assign("/api/auth/sso-logout")}
        aria-label="Abmelden"
        className="backdrop-blur-sm bg-white/70 hover:bg-white/90 active:bg-white
                   border border-black/10 shadow-sm rounded-full px-3.5 h-8
                   inline-flex items-center gap-2 text-[13px] font-medium text-gray-800 transition"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 3v7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
          <path d="M6.3 7.5a7.5 7.5 0 1 0 11.4 0" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
        </svg>
        <span>Abmelden</span>
      </button>
    </div>
  );
}
