// 📁 frontend/src/app/components/ui/card.tsx

import * as React from "react";
// vorher: import { cn } from "@lib/utils";
// korrekt mit dem Slash nach @:
import { cn } from "@/lib/utils";

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800",
      className
    )}
    {...props}
  />
));
Card.displayName = "Card";

export { Card };
