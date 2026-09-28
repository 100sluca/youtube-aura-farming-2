import { redirect } from "next/navigation";

/** Ancienne page Expériences : devenue la section « Ce qui marche le mieux » de la Vue d'ensemble (docs/16). */
export default function ExperimentsPage() {
  redirect("/#ce-qui-marche");
}
