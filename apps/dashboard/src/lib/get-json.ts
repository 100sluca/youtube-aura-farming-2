/**
 * Lecture d'une route GET du dashboard depuis le navigateur. Pour les lectures répétées (bloc Machine, panneau Tâches) :
 * Next exécute les actions serveur une par une, si bien qu'une lecture en action faisait attendre les clics de la page
 * (docs/56-dashboard-rapide.md).
 */
export async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url} : ${res.status}`);
  return (await res.json()) as T;
}
