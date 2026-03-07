"use client";

import Image from "next/image";

import { cn } from "@/lib/utils";

type ChatBrandRailProps = {
  className?: string;
};

export function ChatBrandRail({ className }: ChatBrandRailProps) {
  return (
    <div
      className={cn(
        "flex w-full flex-col items-center gap-2 px-0 text-slate-500",
        className
      )}
    >
      <div className="relative h-9 w-9">
        <Image
          src="/sealai_logo_header.png"
          alt="SealAI Logo"
          fill
          sizes="40px"
          className="object-contain"
          priority
        />
      </div>
      <span
        className={cn(
          "text-[10px] font-medium uppercase tracking-[0.35em] text-slate-500",
          "[writing-mode:vertical-rl] [text-orientation:mixed] rotate-180"
        )}
      >
        Sealing Intelligence
      </span>
    </div>
  );
}
