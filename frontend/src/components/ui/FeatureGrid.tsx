"use client";

import { Feature } from "@/lib/types";
import { Card, CardHeader, CardTitle, CardContent } from "./Card";
import * as Icons from "lucide-react";
import { motion } from "framer-motion";
import { sectionY, shell } from "@/lib/layout";

interface FeatureGridProps {
    features: Feature[];
}

export function FeatureGrid({ features }: FeatureGridProps) {
    return (
        <section className={`${sectionY} bg-gray-50`}>
            <div className={shell}>
                <h2 className="h2-b2b text-primary mb-12 text-center leading-tight text-balance">
                    Intuitiveres Arbeiten mit Copilot in Power Platform
                </h2>
                <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 lg:gap-8">
                    {features.map((feature, index) => {
                        // Dynamic Icon Loading
                        const IconComponent = (Icons as any)[feature.icon] || Icons.HelpCircle;

                        return (
                            <motion.div
                                key={index}
                                whileHover={{ scale: 1.05 }}
                                transition={{ type: "spring", stiffness: 300 }}
                            >
                                <Card className="h-full border-none shadow-md hover:shadow-xl transition-shadow rounded-2xl overflow-hidden">
                                    <CardHeader className="pb-2">
                                        <div className="w-12 h-12 rounded-full bg-secondary/20 flex items-center justify-center mb-4 text-primary">
                                            <IconComponent size={24} />
                                        </div>
                                        <CardTitle className="text-xl mb-2">{feature.title}</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <p className="text-gray-600 text-base leading-relaxed">
                                            {feature.description}
                                        </p>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        );
                    })}
                </div>
            </div>
        </section>
    );
}
