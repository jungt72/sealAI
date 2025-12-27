import Link from "next/link";

type AerospaceHeroProps = {
    eyebrow: string;
    title: string;
    description: string;
    ctaText: string;
    ctaHref: string;
    backgroundImage: string;
};

export default function AerospaceHero({
    eyebrow,
    title,
    description,
    ctaText,
    ctaHref,
    backgroundImage,
}: AerospaceHeroProps) {
    return (
        <section className="relative h-screen w-full overflow-hidden">
            {/* Background Image with Overlay */}
            <div className="absolute inset-0">
                <div
                    className="absolute inset-0 bg-cover bg-center bg-no-repeat"
                    style={{ backgroundImage: `url(${backgroundImage})` }}
                />
                {/* Dark overlay for text readability */}
                <div className="absolute inset-0 bg-gradient-to-b from-slate-900/70 via-slate-900/50 to-slate-900/70" />
            </div>

            {/* Content */}
            <div className="relative z-10 mx-auto flex h-full max-w-7xl flex-col justify-end px-6 pb-24 lg:px-8">
                <div className="max-w-3xl">
                    {/* Eyebrow */}
                    <p className="mb-4 text-sm font-medium uppercase tracking-wider text-blue-300">
                        {eyebrow}
                    </p>

                    {/* Title */}
                    <h1 className="mb-6 text-5xl font-bold leading-tight text-white md:text-6xl lg:text-7xl">
                        {title}
                    </h1>

                    {/* Description */}
                    <p className="mb-8 text-lg text-gray-200 md:text-xl">
                        {description}
                    </p>

                    {/* CTA Button */}
                    <Link
                        href={ctaHref}
                        className="inline-flex items-center justify-center rounded-md bg-blue-600 px-8 py-4 text-base font-semibold text-white shadow-lg transition-all hover:bg-blue-700 hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                    >
                        {ctaText}
                        <svg
                            className="ml-2 h-5 w-5"
                            fill="none"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                        >
                            <path d="M9 5l7 7-7 7" />
                        </svg>
                    </Link>
                </div>
            </div>

            {/* Scroll Indicator */}
            <div className="absolute bottom-8 left-1/2 z-10 -translate-x-1/2 animate-bounce">
                <svg
                    className="h-6 w-6 text-white"
                    fill="none"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                >
                    <path d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>
            </div>
        </section>
    );
}
