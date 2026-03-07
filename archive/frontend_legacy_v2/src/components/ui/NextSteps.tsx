import Image from "next/image";
import { NextStep } from "@/lib/types";
import { Button } from "./Button";
import { Card, CardContent } from "./Card";
import { sectionY, shell } from "@/lib/layout";

interface NextStepsProps {
    steps: NextStep[];
}

export function NextSteps({ steps }: NextStepsProps) {
    return (
        <section className={`${sectionY} bg-gradient-to-b from-white to-blue-50`}>
            <div className={shell}>
                <div className="grid md:grid-cols-2 gap-10">
                    {steps.map((step, index) => (
                        <Card key={index} className="overflow-hidden border-none shadow-lg rounded-2xl flex flex-col h-full">
                            <div className="relative h-48 w-full">
                                {step.image?.url ? (
                                    <Image
                                        src={step.image.url}
                                        alt={step.image.alternativeText || step.title}
                                        fill
                                        className="object-cover"
                                    />
                                ) : (
                        <div className="w-full h-full bg-gray-200 flex items-center justify-center">Image Placeholder</div>
                                )}
                            </div>
                            <CardContent className="flex-1 p-8 flex flex-col items-start space-y-4">
                                <h3 className="h3-b2b text-primary">{step.title}</h3>
                                <p className="body-lg-b2b text-gray-600 flex-1">{step.description}</p>
                                <Button asChild variant="sealPrimary">
                                    <a href={step.cta_link}>{step.cta_text}</a>
                                </Button>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </div>
        </section>
    );
}
