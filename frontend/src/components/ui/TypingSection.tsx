"use client";

import { useEffect, useMemo, useState } from "react";

interface TypingSectionProps {
    staticText: string;
    keywords?: string[];
}

const DEFAULT_KEYWORDS = ["AI-gestützte Beratung", "Low-Code Automatisierung", "Präzise Empfehlungen"];

export default function TypingSection({ staticText, keywords = [] }: TypingSectionProps) {
    const keywordsToShow = useMemo(() => {
        const cleaned = keywords
            .map((keyword) => keyword?.trim())
            .filter(Boolean);
        return cleaned.length > 0 ? cleaned : DEFAULT_KEYWORDS;
    }, [keywords]);

    const [displayed, setDisplayed] = useState("");
    const [isDeleting, setIsDeleting] = useState(false);
    const [keywordIndex, setKeywordIndex] = useState(0);
    useEffect(() => {
        if (keywordsToShow.length === 0) return undefined;

        const currentKeyword = keywordsToShow[keywordIndex % keywordsToShow.length];

        const handleTyping = () => {
            if (!isDeleting && displayed === currentKeyword) {
                setIsDeleting(true);
            } else if (isDeleting && displayed === "") {
                setIsDeleting(false);
                setKeywordIndex((prev) => prev + 1);
            } else {
                const nextLength = isDeleting ? displayed.length - 1 : displayed.length + 1;
                setDisplayed(currentKeyword.slice(0, Math.max(0, nextLength)));
            }
        };

        const pause = !isDeleting && displayed === currentKeyword ? 1200 : isDeleting && displayed === "" ? 200 : 120;
        const timer = setTimeout(handleTyping, pause);

        return () => clearTimeout(timer);
    }, [displayed, isDeleting, keywordIndex, keywordsToShow]);

    return (
        <section className="w-full bg-gradient-to-b from-slate-900/80 to-slate-950/80 px-4 py-16 text-white">
            <div className="mx-auto flex max-w-4xl flex-col items-center gap-6 text-center">
                {staticText && (
                    <p className="text-lg font-semibold uppercase tracking-[0.3em] text-slate-300">
                        {staticText}
                    </p>
                )}
                <p className="text-3xl font-semibold leading-tight md:text-4xl">
                    <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 to-blue-400">SealAI</span>{" "}
                    bringt{" "}
                    <span className="font-mono text-cyan-300">{displayed || keywordsToShow[0]}</span>
                    <span className="animate-pulse text-cyan-300">|</span>
                </p>
                <p className="text-sm text-slate-300/90">
                    Wir kombinieren KI, Automation und Domänenwissen, damit Sie Ihre Produkte schneller optimieren.
                </p>
            </div>
        </section>
    );
}
