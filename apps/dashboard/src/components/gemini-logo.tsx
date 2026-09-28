import * as React from "react";

import { cn } from "@/lib/utils";

/** Étoile à quatre branches aux couleurs de Gemini : repère visuel des gestes qui passent par Gemini en ligne. */
export function GeminiLogo({ className, ...props }: React.SVGProps<SVGSVGElement>) {
  const id = React.useId();
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={cn("size-4 shrink-0", className)} {...props}>
      <defs>
        <linearGradient id={id} x1="3" y1="21" x2="21" y2="3" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#1C7DFF" />
          <stop offset="0.52" stopColor="#8B6CF6" />
          <stop offset="1" stopColor="#F06CA8" />
        </linearGradient>
      </defs>
      <path
        fill={`url(#${id})`}
        d="M12 1.5c.5 5.6 4.9 10 10.5 10.5-5.6.5-10 4.9-10.5 10.5C11.5 16.9 7.1 12.5 1.5 12 7.1 11.5 11.5 7.1 12 1.5Z"
      />
    </svg>
  );
}
