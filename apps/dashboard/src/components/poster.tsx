import { categoryMeta } from "@/lib/labels";
import { cn } from "@/lib/utils";

/** Vignette 9:16 factice : dégradé par catégorie + emoji (remplacée par la miniature YouTube plus tard). */
export function Poster({
  category,
  className,
  size = "sm",
}: {
  category: string | null | undefined;
  className?: string;
  size?: "sm" | "md" | "lg";
}) {
  const meta = categoryMeta(category);
  return (
    <div
      aria-hidden
      className={cn(
        "relative flex shrink-0 items-center justify-center overflow-hidden rounded-md bg-linear-to-b shadow-inner",
        meta.gradient,
        size === "sm" && "h-16 w-9 text-base",
        size === "md" && "h-24 w-[3.375rem] text-2xl",
        size === "lg" && "h-40 w-[5.625rem] text-4xl",
        className
      )}
    >
      <span className="drop-shadow-sm">{meta.emoji}</span>
      <span className="absolute inset-x-0 bottom-0 h-1/3 bg-linear-to-t from-black/40 to-transparent" />
    </div>
  );
}
