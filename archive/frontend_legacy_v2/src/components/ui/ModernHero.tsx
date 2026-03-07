'use client';

import React from 'react';
import { motion } from 'framer-motion';
import Image from 'next/image';
import { shell } from '@/lib/layout';
import { HeroSection } from '@/lib/types';

interface ModernHeroProps {
    data?: HeroSection;
    onPrimaryCta?: () => void;
}

export default function ModernHero({ data, onPrimaryCta }: ModernHeroProps) {
    // Fallback values if no data provided
    const title = data?.title || 'Physikalisch validierte\nGenerative Intelligenz';
    const subtitle = data?.subtitle || 'Wir liefern keine Wahrscheinlichkeiten, sondern auditierbare L??sungen. Optimieren Sie Ihre Prozesse mit KI, die auf physikalischen Gesetzen basiert.';
    const ctaText = data?.cta_text || 'Demo anfragen';
    const ctaLink = data?.cta_link || '#';
    const backgroundImage = data?.background_image?.url;

    return (
        <section className="relative w-full min-h-[85vh] flex items-center justify-center overflow-hidden bg-slate-950">
            {/* Background Image with Overlay */}
            <div className="absolute inset-0 z-0">
                {backgroundImage ? (
                    <Image
                        src={backgroundImage}
                        alt={data?.background_image?.alternativeText || 'Hero Background'}
                        fill
                        className="object-cover"
                        priority
                    />
                ) : (
                    /* Gradient fallback if no image */
                    <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-950 to-indigo-950" />
                )}
                {/* Dark overlay for text readability */}
                <div className="absolute inset-0 bg-black/40" />
            </div>

            {/* Content Container */}
            <div className={`relative z-10 ${shell}`}>
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6 }}
                    className="flex flex-col items-center text-center md:items-start md:text-left gap-8"
                >
                    {/* Headline */}
                    <h1 className="h1-b2b text-white text-balance whitespace-pre-line">
                        {title}
                    </h1>

                    {/* Subheadline */}
                    <p className="body-lg-b2b text-white/90 max-w-3xl">
                        {subtitle}
                    </p>

                    {/* CTA Button - Minimal Airbus Style */}
                    <motion.a
                        href={ctaLink}
                        onClick={(event: React.MouseEvent<HTMLAnchorElement>) => {
                            if (!onPrimaryCta) return;
                            event.preventDefault();
                            onPrimaryCta();
                        }}
                        className="inline-flex items-center gap-2 text-white text-base font-normal hover:opacity-80 transition-opacity"
                        whileHover={{ x: 5 }}
                        transition={{ duration: 0.2 }}
                    >
                        <span>{ctaText}</span>
                        <svg
                            className="w-5 h-5"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M17 8l4 4m0 0l-4 4m4-4H3"
                            />
                        </svg>
                    </motion.a>

                    {/* Secondary CTA if available */}
                    {data?.secondary_cta_text && (
                        <motion.a
                            href={data.secondary_cta_link || '#'}
                            className="inline-flex items-center gap-2 text-white/80 text-base font-normal hover:text-white transition-colors"
                            whileHover={{ x: 5 }}
                            transition={{ duration: 0.2 }}
                        >
                            <span>{data.secondary_cta_text}</span>
                        </motion.a>
                    )}

                    {/* Trust Indicators if available */}
                    {data?.trust_indicators && data.trust_indicators.length > 0 && (
                        <div className="mt-8 pt-8 border-t border-white/10 w-full">
                            <p className="text-sm text-white/60 uppercase tracking-wider mb-4">Trusted by</p>
                            <div className="flex flex-wrap gap-6">
                                {data.trust_indicators.map((indicator, index) => (
                                    <span key={index} className="text-white/80 font-medium">{indicator}</span>
                                ))}
                            </div>
                        </div>
                    )}
                </motion.div>
            </div>

            {/* Optional: Scroll Indicator */}
            <motion.div
                className="absolute bottom-8 left-1/2 transform -translate-x-1/2"
                animate={{ y: [0, 10, 0] }}
                transition={{ duration: 2, repeat: Infinity }}
            >
                <svg
                    className="w-6 h-6 text-white/60"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                >
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 14l-7 7m0 0l-7-7m7 7V3"
                    />
                </svg>
            </motion.div>
        </section>
    );
}


