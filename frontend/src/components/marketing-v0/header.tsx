import Link from "next/link";
import Image from "next/image";
import { Button } from "@/components/ui/Button";

export function Header() {
  return (
    <header className="fixed top-0 left-0 right-0 bg-white border-b border-gray-200 z-50">
      <div className="max-w-[1600px] mx-auto px-6">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2">
              <Image
                src="/images/logo-sealai-schwebend-removebg-preview.png"
                alt="sealAI Logo"
                width={48}
                height={48}
                className="w-12 h-12 object-contain"
                priority
              />
              <span className="text-sm font-semibold">sealAI</span>
            </Link>

            <div className="h-6 w-px bg-gray-300" aria-hidden="true" />
            <span className="text-sm font-semibold">Marketing</span>
          </div>

          <nav className="hidden lg:flex items-center gap-6" aria-label="Hauptnavigation">
            <Link
              href="#"
              className="text-sm hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
            >
              Was ist Power Platform
            </Link>
            <Link
              href="#"
              className="text-sm hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
            >
              Produkte
            </Link>
            <Link
              href="#"
              className="text-sm hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
            >
              Preise
            </Link>
            <Link
              href="#"
              className="text-sm hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
            >
              Ressourcen
            </Link>
          </nav>

          <div className="flex items-center gap-4">
            <Button className="bg-[#0078D4] hover:bg-[#106EBE]">Kostenlos einsteigen</Button>
          </div>
        </div>
      </div>
    </header>
  );
}
