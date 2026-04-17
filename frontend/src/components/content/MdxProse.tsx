"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";
import { ArrowRight, Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface MdxProseProps {
  content: string;
  type: "medien" | "werkstoffe" | "wissen";
  slug: string;
}

export default function MdxProse({ content, type, slug }: MdxProseProps) {
  // Mapping for Context-Link
  const contextParam = type === "medien" ? "medium" : type === "werkstoffe" ? "material" : "context";

  return (
    <article className="max-w-4xl mx-auto py-12 px-6">
      <div className="prose-clean">
        <ReactMarkdown 
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ node, ...props }) => <h1 className="text-4xl font-bold mb-8 text-seal-blue border-b border-border pb-4" {...props} />,
            h2: ({ node, ...props }) => <h2 className="text-2xl font-bold mt-12 mb-6 text-seal-blue" {...props} />,
            h3: ({ node, ...props }) => <h3 className="text-xl font-bold mt-8 mb-4 text-seal-blue" {...props} />,
            p: ({ node, ...props }) => <p className="text-[17px] leading-relaxed mb-6 text-foreground/80" {...props} />,
            ul: ({ node, ...props }) => <ul className="list-disc pl-6 mb-8 space-y-3" {...props} />,
            ol: ({ node, ...props }) => <ol className="list-decimal pl-6 mb-8 space-y-3" {...props} />,
            li: ({ node, ...props }) => <li className="text-[17px] leading-relaxed" {...props} />,
            table: ({ node, ...props }) => (
              <div className="overflow-x-auto my-10 border border-border rounded-xl">
                <table className="w-full text-left text-sm border-collapse" {...props} />
              </div>
            ),
            thead: ({ node, ...props }) => <thead className="bg-slate-50 border-b border-border" {...props} />,
            th: ({ node, ...props }) => <th className="px-4 py-3 font-bold text-seal-blue uppercase tracking-wider text-[11px]" {...props} />,
            td: ({ node, ...props }) => <td className="px-4 py-3 border-b border-border/50 text-[14px]" {...props} />,
            blockquote: ({ node, ...props }) => (
              <blockquote className="border-l-4 border-seal-blue bg-slate-50 px-6 py-4 my-8 italic text-foreground/70" {...props} />
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>

      {/* DASHBOARD CTA */}
      <div className="mt-20 p-8 rounded-2xl bg-seal-blue text-white shadow-xl flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-white/10 rounded-xl">
            <Info size={28} className="text-seal-light-blue" />
          </div>
          <div>
            <h4 className="text-lg font-bold mb-1">Dichtungsanalyse starten</h4>
            <p className="text-sm opacity-80 text-seal-light-blue">Qualifizieren Sie Ihren Fall fachspezifisch für {slug.replace(/-/g, " ")}.</p>
          </div>
        </div>
        <Link
          href={`/dashboard/new?${contextParam}=${slug}`}
          className="group flex items-center gap-3 bg-white text-seal-blue px-6 py-3 rounded-full font-bold transition-all hover:bg-seal-light-blue active:scale-95 whitespace-nowrap"
        >
          <span>Fall jetzt analysieren</span>
          <ArrowRight size={18} className="transition-transform group-hover:translate-x-1" />
        </Link>
      </div>
    </article>
  );
}
