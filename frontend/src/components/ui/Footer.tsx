import Link from "next/link";
import { shell } from "@/lib/layout";

export function Footer() {
    return (
        <footer className="bg-gray-100 py-16 text-sm text-gray-600">
            <div className={shell}>
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-8 mb-12">
                    <div className="col-span-2 lg:col-span-2">
                        <div className="flex items-center space-x-2 mb-4">
                            <div className="w-6 h-6 bg-primary rounded-full"></div>
                            <span className="text-primary font-bold text-lg">SealAI</span>
                        </div>
                        <p className="mb-4 max-w-xs">
                            Die führende KI-gestützte Low-Code-Plattform für Unternehmen jeder Größe.
                        </p>
                        <div className="flex space-x-4">
                            {/* Social Icons Placeholders */}
                            <div className="w-5 h-5 bg-gray-300 rounded-full"></div>
                            <div className="w-5 h-5 bg-gray-300 rounded-full"></div>
                            <div className="w-5 h-5 bg-gray-300 rounded-full"></div>
                        </div>
                    </div>

                    <div>
                        <h4 className="font-semibold text-gray-900 mb-4">Neuigkeiten</h4>
                        <ul className="space-y-2">
                            <li><Link href="#" className="hover:underline">Features</Link></li>
                            <li><Link href="#" className="hover:underline">Sicherheit</Link></li>
                            <li><Link href="#" className="hover:underline">Roadmap</Link></li>
                        </ul>
                    </div>

                    <div>
                        <h4 className="font-semibold text-gray-900 mb-4">Microsoft Store</h4>
                        <ul className="space-y-2">
                            <li><Link href="#" className="hover:underline">Konto-Profil</Link></li>
                            <li><Link href="#" className="hover:underline">Download Center</Link></li>
                            <li><Link href="#" className="hover:underline">R??ckgaben</Link></li>
                        </ul>
                    </div>

                    <div>
                        <h4 className="font-semibold text-gray-900 mb-4">Bildungswesen</h4>
                        <ul className="space-y-2">
                            <li><Link href="#" className="hover:underline">Microsoft Bildung</Link></li>
                            <li><Link href="#" className="hover:underline">Ger??te f??r Bildung</Link></li>
                            <li><Link href="#" className="hover:underline">Microsoft Teams</Link></li>
                        </ul>
                    </div>

                    <div>
                        <h4 className="font-semibold text-gray-900 mb-4">Unternehmen</h4>
                        <ul className="space-y-2">
                            <li><Link href="#" className="hover:underline">Microsoft Cloud</Link></li>
                            <li><Link href="#" className="hover:underline">Microsoft Security</Link></li>
                            <li><Link href="#" className="hover:underline">Azure</Link></li>
                        </ul>
                    </div>
                </div>

                <div className="pt-8 border-t border-gray-200 flex flex-col md:flex-row justify-between items-center">
                    <div className="flex space-x-6 mb-4 md:mb-0">
                        <Link href="#" className="hover:underline">Impressum</Link>
                        <Link href="#" className="hover:underline">Datenschutz</Link>
                        <Link href="#" className="hover:underline">Cookies</Link>
                    </div>
                    <div>
                        &copy; {new Date().getFullYear()} SealAI GmbH. Alle Rechte vorbehalten.
                    </div>
                </div>
            </div>
        </footer>
    );
}
