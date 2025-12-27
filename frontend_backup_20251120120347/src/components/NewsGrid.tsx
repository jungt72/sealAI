import Link from "next/link";
import type { NewsArticle } from "@/lib/strapi";

type NewsGridProps = {
    articles: NewsArticle[];
};

function formatDate(dateString: string): string {
    const date = new Date(dateString);
    return date.toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
    });
}

export default function NewsGrid({ articles }: NewsGridProps) {
    return (
        <section id="news" className="bg-gray-50 py-24">
            <div className="mx-auto max-w-7xl px-6 lg:px-8">
                {/* Section Header */}
                <div className="mb-16 text-center">
                    <h2 className="text-4xl font-bold tracking-tight text-slate-900 md:text-5xl">
                        Latest News
                    </h2>
                    <p className="mt-4 text-lg text-slate-600">
                        Stay updated with our latest innovations and achievements
                    </p>
                </div>

                {/* News Grid */}
                <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
                    {articles.map((article) => (
                        <article
                            key={article.id}
                            className="group overflow-hidden rounded-lg bg-white shadow-md transition-all hover:shadow-xl"
                        >
                            {/* Image */}
                            <div className="aspect-[4/3] overflow-hidden">
                                <img
                                    src={article.imageUrl}
                                    alt={article.imageAlt}
                                    className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                                />
                            </div>

                            {/* Content */}
                            <div className="p-6">
                                {/* Date */}
                                <time
                                    dateTime={article.publishedDate}
                                    className="text-sm font-medium text-blue-600"
                                >
                                    {formatDate(article.publishedDate)}
                                </time>

                                {/* Title */}
                                <h3 className="mt-3 text-xl font-semibold text-slate-900 line-clamp-2">
                                    {article.title}
                                </h3>

                                {/* Excerpt */}
                                <p className="mt-3 text-sm text-slate-600 line-clamp-3">
                                    {article.excerpt}
                                </p>

                                {/* Read More Link */}
                                <Link
                                    href={`/news/${article.slug}`}
                                    className="mt-4 inline-flex items-center text-sm font-semibold text-blue-600 transition-colors hover:text-blue-700"
                                >
                                    Read more
                                    <svg
                                        className="ml-1 h-4 w-4"
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
                        </article>
                    ))}
                </div>
            </div>
        </section>
    );
}
