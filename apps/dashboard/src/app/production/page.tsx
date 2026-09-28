import { redirect } from "next/navigation";

/** Ancienne page Production (kanban) : la fabrication se suit dans le panneau « Tâches », les storyboards dans
 * Création, les vidéos finies dans la Bibliothèque (docs/16). */
export default function ProductionPage() {
  redirect("/create");
}
