import AerospaceNav from "@/components/AerospaceNav";
import AerospaceHero from "@/components/AerospaceHero";
import NewsGrid from "@/components/NewsGrid";
import StatsSection from "@/components/StatsSection";
import {
    getNavigationItems,
    getAerospaceHero,
    getLatestNews,
    getCompanyStats,
} from "@/lib/strapi";

export default async function AerospacePage() {
    // Fetch all data from Strapi (currently using mock data)
    const [navItems, heroData, newsArticles, stats] = await Promise.all([
        getNavigationItems(),
        getAerospaceHero(),
        getLatestNews(),
        getCompanyStats(),
    ]);

    return (
        <div className="min-h-screen bg-white">
            {/* Navigation */}
            <AerospaceNav items={navItems} />

            {/* Hero Section */}
            <AerospaceHero
                eyebrow={heroData.eyebrow}
                title={heroData.title}
                description={heroData.description}
                ctaText={heroData.ctaText}
                ctaHref={heroData.ctaHref}
                backgroundImage={heroData.backgroundImage}
            />

            {/* Stats Section */}
            <StatsSection stats={stats} />

            {/* News Grid */}
            <NewsGrid articles={newsArticles} />

            {/* Products Section Placeholder */}
            <section id="products" className="bg-white py-24">
                <div className="mx-auto max-w-7xl px-6 lg:px-8">
                    <div className="text-center">
                        <h2 className="text-4xl font-bold tracking-tight text-slate-900 md:text-5xl">
                            Our Solutions
                        </h2>
                        <p className="mt-6 text-lg leading-8 text-slate-600 max-w-2xl mx-auto">
                            Cutting-edge aerospace technology designed for performance,
                            efficiency, and sustainability. Explore our comprehensive range of
                            products and services.
                        </p>
                    </div>

                    {/* Product Grid Placeholder */}
                    <div className="mt-16 grid gap-8 md:grid-cols-2 lg:grid-cols-3">
                        {[
                            {
                                title: "Commercial Aircraft",
                                description:
                                    "Next-generation platforms for passenger and cargo transport",
                            },
                            {
                                title: "Defense Systems",
                                description:
                                    "Advanced solutions for military and security applications",
                            },
                            {
                                title: "Space Technology",
                                description:
                                    "Innovative systems for satellite and space exploration",
                            },
                        ].map((product, idx) => (
                            <div
                                key={idx}
                                className="rounded-lg border border-slate-200 p-8 transition-all hover:border-blue-600 hover:shadow-lg"
                            >
                                <h3 className="text-xl font-semibold text-slate-900">
                                    {product.title}
                                </h3>
                                <p className="mt-3 text-slate-600">{product.description}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Footer */}
            <footer className="bg-slate-900 py-12">
                <div className="mx-auto max-w-7xl px-6 lg:px-8">
                    <div className="text-center">
                        <p className="text-sm text-gray-400">
                            © 2025 Aerospace Corp. All rights reserved.
                        </p>
                    </div>
                </div>
            </footer>
        </div>
    );
}
