import { redirect } from "next/navigation";

/** Ancienne page Idées : remplacée par Création (docs/16). */
export default function IdeasPage() {
  redirect("/create");
}
