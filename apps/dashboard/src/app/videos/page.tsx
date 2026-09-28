import { redirect } from "next/navigation";

/** Ancienne page Vidéos publiées : remplacée par la Bibliothèque (docs/16). */
export default function VideosPage() {
  redirect("/library?statut=publiees");
}
