import { Skeleton } from "@/components/ui/skeleton";

/**
 * Écran de chargement de toutes les pages : affiché dès le clic sur un lien, le temps que le serveur prépare la page
 * (docs/56-dashboard-rapide.md). Le titre de la page change déjà dans l'en-tête ; ici, la silhouette du contenu.
 */
export default function Loading() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true" aria-label="Chargement de la page">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-full max-w-2xl" />
        <Skeleton className="h-4 w-2/3 max-w-xl" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Skeleton className="h-72 rounded-xl lg:col-span-2" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    </div>
  );
}
