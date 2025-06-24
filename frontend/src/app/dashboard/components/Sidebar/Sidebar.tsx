// frontend/src/app/dashboard/components/Sidebar/Sidebar.tsx

"use client";
interface SidebarProps {
  open: boolean;
  setOpen: (open: boolean) => void;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  tabs: { key: string; label: string }[];
}

export default function Sidebar({
  open,
  setOpen,
  activeTab,
  setActiveTab,
  tabs,
}: SidebarProps) {
  return (
    <aside
      className={`
        fixed top-0 left-0 h-full z-50 bg-white shadow-2xl border-r transition-all duration-300
        ${open ? "w-[35vw] min-w-[320px]" : "w-0 min-w-0"}
        flex flex-col overflow-x-hidden
      `}
      style={{ willChange: "width" }}
    >
      {/* Logo nur einmal ganz oben */}
      {open && (
        <>
          <div className="flex items-center space-x-2 pl-6 pt-6">
            <img src="/logo_sai.svg" alt="SealAI Logo" className="h-8 w-auto" />
            <span className="text-2xl font-semibold text-gray-700">SealAI</span>
          </div>

          {/* Tabs */}
          <div className="pt-8">
            <div className="flex border-b border-gray-200">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  className={`flex-1 py-2 text-center font-medium transition
                    ${activeTab === tab.key
                      ? "border-b-2 border-blue-600 text-blue-700 bg-blue-50"
                      : "text-gray-500 hover:bg-gray-100"}`}
                  onClick={() => setActiveTab(tab.key)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            {/* Tab-Inhalt */}
            <div className="p-6">
              {activeTab === "form" && <div>Formular kommt hier hin</div>}
              {activeTab === "material" && <div>Materialauswahl kommt hier hin</div>}
              {activeTab === "result" && <div>Ergebnisanzeige kommt hier hin</div>}
            </div>
          </div>

          {/* Close-Button UNTER dem Logo */}
          <button
            className="ml-8 mt-6 p-3 bg-blue-600 text-white rounded-full shadow-lg hover:bg-blue-700 transition"
            onClick={() => setOpen(false)}
            title="Sidebar schließen"
            style={{ minWidth: 48, minHeight: 48 }}
          >
            <span style={{ fontSize: 24 }}>&#10005;</span>
          </button>
        </>
      )}
    </aside>
  );
}
