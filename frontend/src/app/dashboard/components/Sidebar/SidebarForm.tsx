"use client";

export default function SidebarForm() {
  return (
    <form className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700">Temperatur</label>
        <input
          type="number"
          placeholder="z. B. 120"
          className="mt-1 w-full border rounded px-3 py-2 text-sm"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700">Druck</label>
        <input
          type="number"
          placeholder="z. B. 8"
          className="mt-1 w-full border rounded px-3 py-2 text-sm"
        />
      </div>
      <button
        type="submit"
        className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded w-full"
      >
        Berechnen
      </button>
    </form>
  );
}
