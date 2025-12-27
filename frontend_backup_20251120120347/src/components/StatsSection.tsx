"use client";

import { useEffect, useRef, useState } from "react";
import type { CompanyStat } from "@/lib/strapi";

type StatsProps = {
    stats: CompanyStat[];
};

function AnimatedNumber({
    value,
    prefix = "",
    suffix = "",
}: {
    value: number;
    prefix?: string;
    suffix?: string;
}) {
    const [count, setCount] = useState(0);
    const [hasAnimated, setHasAnimated] = useState(false);
    const ref = useRef<HTMLSpanElement>(null);

    useEffect(() => {
        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0].isIntersecting && !hasAnimated) {
                    setHasAnimated(true);

                    const duration = 2000; // 2 seconds
                    const steps = 60;
                    const increment = value / steps;
                    let current = 0;

                    const timer = setInterval(() => {
                        current += increment;
                        if (current >= value) {
                            setCount(value);
                            clearInterval(timer);
                        } else {
                            setCount(Math.floor(current));
                        }
                    }, duration / steps);

                    return () => clearInterval(timer);
                }
            },
            { threshold: 0.5 }
        );

        if (ref.current) {
            observer.observe(ref.current);
        }

        return () => observer.disconnect();
    }, [value, hasAnimated]);

    return (
        <span ref={ref} className="tabular-nums">
            {prefix}
            {count.toLocaleString()}
            {suffix}
        </span>
    );
}

export default function StatsSection({ stats }: StatsProps) {
    return (
        <section className="bg-slate-900 py-20">
            <div className="mx-auto max-w-7xl px-6 lg:px-8">
                <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
                    {stats.map((stat) => (
                        <div
                            key={stat.id}
                            className="flex flex-col items-center text-center"
                        >
                            {/* Animated Number */}
                            <div className="text-5xl font-bold text-white md:text-6xl">
                                <AnimatedNumber
                                    value={stat.value}
                                    prefix={stat.prefix}
                                    suffix={stat.suffix}
                                />
                            </div>

                            {/* Label */}
                            <p className="mt-3 text-sm font-medium uppercase tracking-wide text-gray-400">
                                {stat.label}
                            </p>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}
