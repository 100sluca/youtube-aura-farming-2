/**
 * Retoucher → Récit (docs/53-reecrire-le-recit.md) : ce que l'onglet montre d'une vidéo, ses jobs « rewrite » et les
 * autres versions déjà faites de la même vidéo. Serveur uniquement.
 */
import type { HookProposal, RewriteData, RewriteJob, RewriteMode, RewriteShot, RewriteState, RewriteVersion, StoryProposal } from "@/lib/rewrite-types";
import { supabaseAdmin } from "@/lib/supabase-admin";
import type { JobStatus, VideoStatus } from "@/lib/types";

const UUID = /^[0-9a-f-]{36}$/i;
const one = <T,>(v: T | T[] | null | undefined): T | null => (Array.isArray(v) ? (v[0] ?? null) : (v ?? null));

type Scene = { index: number; narration?: Record<string, string>; on_screen_text?: Record<string, string> };
type Script = { scenes?: Scene[]; story?: { beats?: { part: string; text: string }[] } | null; hook_title?: Record<string, string> };

type JobRow = {
  id: string;
  status: JobStatus;
  progress: number | null;
  progress_label: string | null;
  error: string | null;
  payload: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  created_at: string;
  finished_at: string | null;
  run_after: string | null;
};

const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

function toJob(j: JobRow): RewriteJob {
  const p = j.payload ?? {};
  const r = j.result ?? {};
  const proposal = (r.proposal ?? p.proposal ?? null) as StoryProposal | HookProposal | null;
  return {
    id: j.id,
    action: p.action === "make" ? "make" : "propose",
    mode: (p.mode === "hook" ? "hook" : "story") as RewriteMode,
    status: j.status,
    progress: j.progress ?? 0,
    label: j.progress_label,
    // « ValueError: … » : le worker refuse ce texte pour une raison qu'il dit lui-même
    error: j.error ? j.error.replace(/^(ValueError|ValidationError): /, "") : null,
    note: typeof p.note === "string" ? p.note : "",
    pages: strings(p.pages),
    createdAt: j.created_at,
    finishedAt: j.finished_at,
    runAfter: j.status === "queued" && j.run_after && new Date(j.run_after).getTime() > Date.now() + 30_000 ? j.run_after : null,
    proposal,
    issues: strings(r.issues),
    shots: (Array.isArray(r.shots) ? r.shots : []) as RewriteShot[],
    videoId: typeof r.video_id === "string" ? r.video_id : null,
  };
}

export async function getRewriteState(videoId: string): Promise<RewriteState> {
  const db = supabaseAdmin();
  const [{ data: rows }, { data: variants }] = await Promise.all([
    db
      .from("jobs")
      .select("id, status, progress, progress_label, error, payload, result, created_at, finished_at, run_after")
      .eq("video_id", videoId)
      .eq("type", "rewrite")
      .order("created_at", { ascending: false })
      .limit(20),
    db.from("videos").select("id, title, status, created_at, error").eq("variant_of", videoId).order("created_at", { ascending: false }),
  ]);
  const jobs = ((rows ?? []) as JobRow[]).map(toJob);
  // la dernière proposition terminée, sauf si une vidéo en a été faite depuis
  const proposalAt = jobs.findIndex((j) => j.action === "propose" && j.status === "done" && j.proposal);
  const madeAt = jobs.findIndex((j) => j.action === "make" && j.status === "done");
  const versions: RewriteVersion[] = (variants ?? []).map((v) => ({
    id: v.id as string,
    title: (v.title as string | null) ?? "Sans titre",
    status: v.status as VideoStatus,
    createdAt: v.created_at as string,
    error: (v.error as string | null) ?? null,
  }));
  return {
    current: jobs[0] ?? null,
    proposal: proposalAt >= 0 && (madeAt < 0 || proposalAt < madeAt) ? jobs[proposalAt] : null,
    versions,
  };
}

/** Scène de l'accroche et scène de la promesse, chacune seule dans son plan (comme worker/rewrite.py : opening_of). */
function openingOf(script: Script, lang: string): { hook: Scene; promise: Scene } | string {
  const beats = script.story?.beats ?? [];
  if (beats.length < 2 || beats[0].part !== "hook" || beats[1].part !== "promise") return "Seul un récit écrit par le conteur (accroche puis promesse) a une accroche à réécrire seule.";
  const find = (text: string) => (script.scenes ?? []).slice(0, 4).find((s) => (s.narration?.[lang] ?? "").trim() === text.trim());
  const hook = find(beats[0].text);
  const promise = find(beats[1].text);
  return hook && promise ? { hook, promise } : "L’accroche ou la promesse tient sur plusieurs plans : réécris tout le récit.";
}

/** null : pas d'onglet Récit (vidéo sans voix off qui raconte : importée, drame en dialogues, accéléré, visite). */
export async function getRewriteData(videoId: string): Promise<RewriteData | null> {
  if (!UUID.test(videoId)) return null;
  const db = supabaseAdmin();
  const { data: v } = await db
    .from("videos")
    .select("id, title, lang, format, origin, production_id, final_asset_id, files_deleted_at, tts_provider, tts_voice, variant_of, productions(script, series(recipe))")
    .eq("id", videoId)
    .maybeSingle();
  if (!v || v.origin === "imported" || !v.production_id || v.format !== "A_voiceover") return null;
  const prod = one(v.productions as { script: Script | null; series: unknown } | { script: Script | null; series: unknown }[] | null);
  const recipe = one(prod?.series as { recipe: string | null } | { recipe: string | null }[] | null)?.recipe ?? "story";
  if (recipe !== "story") return null; // les drames parlent sur les lèvres des clips : on ne réécrit pas leurs répliques
  const script = prod?.script ?? {};
  const lang = (v.lang as string | null) ?? "fr";

  const blocked = v.files_deleted_at
    ? "Fichiers effacés du PC : il n’y a plus de clips à réutiliser."
    : !v.final_asset_id
      ? "Pas encore montée : le récit se réécrit une fois la vidéo faite."
      : !(v.tts_provider && v.tts_voice)
        ? "Voix de la vidéo inconnue : la nouvelle version ne saurait pas avec quelle voix parler."
        : !(script.scenes ?? []).length
          ? "Script introuvable."
          : null;
  const opening = openingOf(script, lang);
  const currentHook: HookProposal | null =
    typeof opening === "string"
      ? null
      : {
          angle: "",
          hook: opening.hook.narration?.[lang] ?? "",
          promise: opening.promise.narration?.[lang] ?? "",
          on_screen: opening.hook.on_screen_text?.[lang] ?? "",
          hook_title: { [lang]: script.hook_title?.[lang] ?? "" },
          title: (v.title as string | null) ?? "",
        };

  const [state, original] = await Promise.all([
    getRewriteState(videoId),
    v.variant_of ? db.from("videos").select("id, title").eq("id", v.variant_of).maybeSingle() : Promise.resolve({ data: null }),
  ]);
  return {
    videoId,
    lang,
    title: (v.title as string | null) ?? "",
    blocked,
    hookBlocked: typeof opening === "string" ? opening : null,
    currentHook,
    original: original.data ? { id: original.data.id as string, title: (original.data.title as string | null) ?? "Sans titre" } : null,
    state,
  };
}
