import Image from "next/image";
import { CommunityConference } from "@/lib/types";
import { Button } from "./Button";
import { sectionY, shell } from "@/lib/layout";

interface CommunityBlockProps {
    data: CommunityConference;
}

export function CommunityBlock({ data }: CommunityBlockProps) {
    return (
        <section className={`${sectionY} bg-white`}>
            <div className={shell}>
                <div className="bg-gray-50 rounded-3xl overflow-hidden shadow-sm border border-gray-100">
                    <div className="grid md:grid-cols-2">
                        <div className="p-10 md:p-12 flex flex-col justify-center space-y-6">
                            <span className="text-secondary font-semibold uppercase tracking-wider text-sm">
                                Community
                            </span>
                            <h2 className="h2-b2b text-primary leading-tight text-balance">
                                {data.title}
                            </h2>
                            <p className="body-lg-b2b text-gray-600">
                                {data.description}
                            </p>
                            <div>
                                <Button asChild variant="outline" className="border-primary text-primary hover:bg-primary hover:text-white">
                                    <a href={data.cta_link}>{data.cta_text}</a>
                                </Button>
                            </div>
                        </div>
                        <div className="relative min-h-[320px]">
                            {data.image?.url ? (
                                <Image
                                    src={data.image.url}
                                    alt={data.image.alternativeText || "Community"}
                                    fill
                                    className="object-cover"
                                />
                            ) : (
                                <div className="w-full h-full bg-gray-200 flex items-center justify-center">Image Placeholder</div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
