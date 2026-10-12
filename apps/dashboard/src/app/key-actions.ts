"use server";

/** Suivi des clés API (docs/49 §9) : relu par l'encart « Clés API » du gestionnaire des tâches pendant qu'il est ouvert. */
import { getKeyBoard } from "@/lib/api-keys";
import type { KeyBoard } from "@/lib/api-key-types";

export async function fetchKeyBoard(): Promise<KeyBoard> {
  return getKeyBoard();
}
