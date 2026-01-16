import Link from 'next/link';
import Image from 'next/image';
import { Linkedin, Twitter, Facebook, Instagram, ArrowUpRight } from 'lucide-react';

export function Footer() {
    return (
        <footer className="bg-[#001435] text-white pt-20 pb-10 relative overflow-hidden">
            {/* Background Pattern Effect (Dotted Wave) */}
            <div className="absolute inset-0 opacity-10 pointer-events-none" style={{ 
                backgroundImage: 'radial-gradient(circle, #ffffff 1px, transparent 1px)', 
                backgroundSize: '30px 30px',
                maskImage: 'radial-gradient(ellipse at center, black, transparent 80%)'
            }}></div>

            <div className="max-w-[1600px] mx-auto px-6 relative z-10">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-12 mb-20">
                    
                    {/* Column 1: Logo & Social */}
                    <div className="xl:ml-[137px] space-y-10">
                        <div className="flex items-center">
                            {/* White Logo only - No text 'sealAI' */}
                            <Link href="/" className="flex items-center pr-6 shrink-0">
                                <Image
                                    src="/images/Logo_sealAI_weiss-nav.png"
                                    alt="sealAI Logo"
                                    width={54}
                                    height={54}
                                    className="w-[54px] h-[54px] object-contain"
                                />
                            </Link>
                            {/* Vertical Divider */}
                            <div className="h-8 w-[1.5px] bg-white opacity-30" aria-hidden="true" />
                            {/* Application Name */}
                            <span className="text-[18px] font-semibold text-white pl-6 tracking-tight shrink-0">
                                Sealing Intelligence
                            </span>
                        </div>

                        <div className="space-y-4">
                            <p className="text-xl font-medium">Let's stay in touch</p>
                            <div className="flex gap-4">
                                <Link href="#" className="p-2 rounded-full border border-white/20 hover:bg-white/10 transition-colors">
                                    <Linkedin className="w-5 h-5" />
                                </Link>
                                <Link href="#" className="p-2 rounded-full border border-white/20 hover:bg-white/10 transition-colors">
                                    <Twitter className="w-5 h-5" />
                                </Link>
                                <Link href="#" className="p-2 rounded-full border border-white/20 hover:bg-white/10 transition-colors">
                                    <Facebook className="w-5 h-5" />
                                </Link>
                                <Link href="#" className="p-2 rounded-full border border-white/20 hover:bg-white/10 transition-colors">
                                    <Instagram className="w-5 h-5" />
                                </Link>
                            </div>
                        </div>

                        {/* Professional CTA Button */}
                        <div className="pt-2">
                            <Link 
                                href="mailto:info@sealai.net"
                                className="inline-block bg-white text-[#001435] hover:bg-gray-100 px-8 py-3 rounded-full font-bold text-[15px] transition-all transform hover:scale-[1.02] shadow-lg"
                            >
                                Contact us
                            </Link>
                        </div>
                    </div>

                    {/* Column 2: Connected Websites */}
                    <div>
                        <h3 className="text-xl font-semibold mb-8">Lösungen & Tools</h3>
                        <ul className="space-y-4">
                            <li>
                                <Link href="#" className="text-gray-300 hover:text-white flex items-center gap-1 transition-colors text-[15px]">
                                    Dichtungsauslegung <ArrowUpRight className="w-3 h-3" />
                                </Link>
                            </li>
                            <li>
                                <Link href="#" className="text-gray-300 hover:text-white flex items-center gap-1 transition-colors text-[15px]">
                                    Materialdatenbank <ArrowUpRight className="w-3 h-3" />
                                </Link>
                            </li>
                            <li>
                                <Link href="#" className="text-gray-300 hover:text-white flex items-center gap-1 transition-colors text-[15px]">
                                    Normen-Check <ArrowUpRight className="w-3 h-3" />
                                </Link>
                            </li>
                            <li>
                                <Link href="#" className="text-gray-300 hover:text-white flex items-center gap-1 transition-colors text-[15px]">
                                    Hersteller-Portal <ArrowUpRight className="w-3 h-3" />
                                </Link>
                            </li>
                        </ul>
                    </div>

                    {/* Column 3: Customer Portals */}
                    <div>
                        <h3 className="text-xl font-semibold mb-8">Support & Portale</h3>
                        <ul className="space-y-4">
                            <li>
                                <Link href="#" className="text-gray-300 hover:text-white flex items-center gap-1 transition-colors text-[15px]">
                                    sealAI World for Engineers <ArrowUpRight className="w-3 h-3" />
                                </Link>
                            </li>
                            <li>
                                <Link href="#" className="text-gray-300 hover:text-white flex items-center gap-1 transition-colors text-[15px]">
                                    Knowledge Base <ArrowUpRight className="w-3 h-3" />
                                </Link>
                            </li>
                        </ul>
                    </div>

                    {/* Column 4: Useful links */}
                    <div>
                        <h3 className="text-xl font-semibold mb-8">Nützliche Links</h3>
                        <ul className="space-y-4">
                            <li>
                                <Link href="#" className="text-gray-300 hover:text-white flex items-center gap-1 transition-colors text-[15px]">
                                    Media Centre <ArrowUpRight className="w-3 h-3" />
                                </Link>
                            </li>
                            <li>
                                <Link href="#" className="text-gray-300 hover:text-white flex items-center gap-1 transition-colors text-[15px]">
                                    Brand Centre <ArrowUpRight className="w-3 h-3" />
                                </Link>
                            </li>
                            <li>
                                <Link href="#" className="text-gray-300 hover:text-white flex items-center gap-1 transition-colors text-[15px]">
                                    Karriere <ArrowUpRight className="w-3 h-3" />
                                </Link>
                            </li>
                        </ul>
                    </div>
                </div>

                {/* Bottom Bar */}
                <div className="pt-8 border-t border-white/10 flex flex-col md:flex-row justify-between items-center gap-6 text-[13px] text-gray-400">
                    <div className="flex flex-wrap justify-center gap-6">
                        <Link href="#" className="hover:text-white transition-colors">Privacy policy</Link>
                        <Link href="#" className="hover:text-white transition-colors">Terms of use</Link>
                        <Link href="#" className="hover:text-white transition-colors">Accessibility</Link>
                        <Link href="#" className="hover:text-white transition-colors">Impressum</Link>
                        <Link href="#" className="hover:text-white transition-colors">Cookies Settings</Link>
                    </div>
                    <div className="font-medium">
                        © sealAI 2026.
                    </div>
                </div>
            </div>
        </footer>
    );
}
