"use client";

interface IntroHeadlineProps {
    text: string;
}

export function IntroHeadline({ text }: IntroHeadlineProps) {
    return (
        <section className="w-full py-16 bg-white">
            <div className="w-full max-w-[1600px] mx-auto px-5">
                <div className="max-w-4xl mx-auto">
                    <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold text-center text-gray-900 leading-tight">
                        {text}
                    </h2>
                </div>
            </div>
        </section>
    );
}
