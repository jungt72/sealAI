import Image from "next/image";
import { Section } from "@/lib/types";
import { cn } from "@/lib/utils";
import { sectionY, shell } from "@/lib/layout";

interface ImageTextBlockProps {
    data: Section;
}

export function ImageTextBlock({ data }: ImageTextBlockProps) {
    const isImageLeft = data.image_position === 'left';

    return (
        <section
            className={cn(
                sectionY,
                data.background_color === 'light-blue' ? "bg-blue-50" : "bg-white"
            )}
        >
            <div className={shell}>
                <div className="grid md:grid-cols-2 gap-12 xl:gap-16 items-center">
                    {/* Image Column */}
                    <div className={cn("relative aspect-[4/3] rounded-2xl overflow-hidden shadow-lg", isImageLeft ? "md:order-1" : "md:order-2")}>
                        {data.image?.url ? (
                            <Image
                                src={data.image.url}
                                alt={data.image.alternativeText || data.title}
                                fill
                                className="object-cover"
                            />
                        ) : (
                            <div className="w-full h-full bg-gray-200 flex items-center justify-center">Image Placeholder</div>
                        )}
                    </div>

                    {/* Text Column */}
                    <div className={cn("space-y-6", isImageLeft ? "md:order-2" : "md:order-1")}>
                        <h2 className="h2-b2b text-primary leading-tight text-balance">
                            {data.title}
                        </h2>
                        <p className="body-lg-b2b text-gray-600">
                            {data.subtitle}
                        </p>
                    </div>
                </div>
            </div>
        </section>
    );
}
