"""Job long_write (voie io) : l'écriture et la publication des vidéos longues (docs/63).

payload.action :
- ideas {channel_id, count, note?} : des sujets avec leur emballage (titre, miniature, promesse), vérifiés sur Wikipédia ;
- write {long_id} : dossier, plan, chapitres, relecture et corrections, puis titres, description et miniatures ;
  la vidéo passe en « script » : Luca relit et valide dans la page Vidéos longues ;
- chapter {long_id, chapter, note} : un chapitre réécrit selon la remarque de Luca ;
- shots {long_id} : les plans du réalisateur (après validation du script), puis images, clips et miniatures en file ;
- packaging {long_id} : titres, description et concepts de miniature refaits ;
- publish {long_id, publish_at, again?} : envoi sur YouTube (privée, programmée), miniature choisie, chapitres dans la
  description ; again : nouvel envoi après la suppression de l'ancien dans Studio (gardé dans previous_uploads) ;
- thumbnail {long_id} : la miniature choisie reposée sur la vidéo déjà envoyée (après un refus de YouTube).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from ..longform import flow
from ..longform.models import LongIdea, Outline, ReviewProblem
from ..longform.music import mood_list
from ..longform.prompts import IMAGE_RULES_LONG
from ..longform.write import (
    Writer,
    build_dossier,
    frame_subject,
    keyed,
    lint_long,
    packaging,
    plan_shots,
    propose_ideas,
    script_words,
    study_thumbnails,
)
from ..prompts import prompt_text
from .base import Context, Step

AI_NOTICE = (
    "Images et clips générés par intelligence artificielle ; récit écrit d'après les sources ci-dessous et lu par un narrateur."
)


class LongWriteStep(Step):
    type = "long_write"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        p = ctx.job.payload
        action = p.get("action")
        if action == "ideas":
            channel = p.get("channel_id") or (ctx.job.channel_id and str(ctx.job.channel_id))
            if not channel:
                row = ctx.db.fetch_one("select id from channels where is_active order by created_at limit 1")
                channel = row["id"] if row else None
            assert channel, "aucune chaîne"
            cfg = flow.long_settings(ctx.db)
            kept = propose_ideas(
                ctx, channel, int(p.get("count", 8)), list(cfg.get("formats") or ["mystere", "epoque"]), p.get("note", "")
            )
            return {"ideas": kept}
        if action == "thumb_style":  # le style des miniatures de la niche (pas de vidéo longue en particulier)
            return study_thumbnails(ctx)
        lv = flow.get_long(ctx.db, p["long_id"])
        if action == "write":
            return self._write(ctx, lv)
        if action == "chapter":
            return self._chapter(ctx, lv, int(p["chapter"]), p.get("note", ""))
        if action == "shots":
            return self._shots(ctx, lv)
        if action == "packaging":
            pack = packaging(ctx, lv, lv["script"], mood_list())
            flow.update_long(ctx.db, lv["id"], packaging=pack.model_dump())
            return {"titles": len(pack.titles)}
        if action == "publish":
            if p.get("again"):
                self._release(ctx, lv)
            return self._publish(ctx, lv, p.get("publish_at"))
        if action == "thumbnail":
            return self._thumbnail(ctx, lv)
        raise ValueError(f"action inconnue : {action}")

    # ------------------------------------------------------------------------------------------------------------------

    def _write(self, ctx: Context, lv: dict[str, Any]) -> dict[str, Any]:
        _pid, folder = flow.ensure_production(ctx.db, ctx.settings, lv)
        flow.update_long(ctx.db, lv["id"], stage="writing", error=None)
        flow.set_production_status(ctx.db, lv, "scripting")
        if not lv.get("idea"):  # « Mon sujet » : le sujet de Luca devient d'abord une idée emballée
            ctx.progress(3, "Titre, miniature et sources du sujet")
            framed = frame_subject(ctx, lv)
            flow.update_long(ctx.db, lv["id"], idea=framed.model_dump())
            lv["idea"] = framed.model_dump()
            ctx.db.execute(
                "update concepts set title = %s where id = (select concept_id from productions where id = %s)",
                (framed.title[:200], lv["production_id"]),
            )
        idea = LongIdea.model_validate(lv["idea"]) if lv.get("idea") else None
        dossier_file = folder / "dossier.txt"
        if dossier_file.exists() and (lv.get("dossier") or {}).get("sources"):
            dossier = dossier_file.read_text(encoding="utf-8")
        else:
            ctx.progress(5, "Dossier : pages Wikipédia")
            assert idea, "idée manquante"
            dossier, sources = build_dossier(ctx, idea, folder)
            flow.update_long(ctx.db, lv["id"], dossier={"sources": sources, "chars": len(dossier)})
            lv["dossier"] = {"sources": sources}
        if len(dossier) < 3000:
            ctx.log("long.dossier_mince", level="warn", signes=len(dossier))

        def save(part: dict[str, Any]) -> None:
            current = dict(lv.get("script") or {})
            current.update(part)
            lv["script"] = current
            flow.update_long(ctx.db, lv["id"], script=current)

        script = Writer(ctx, lv, save).run(dossier, lambda pct, label: ctx.progress(pct, label))
        save(script)
        ctx.progress(90, "Titres, description et miniatures")
        pack = packaging(ctx, lv, script, mood_list())
        flow.update_long(
            ctx.db, lv["id"], packaging=pack.model_dump(), review=script["work"].get("review"), stage="script", error=None
        )
        flow.set_production_status(ctx.db, lv, "storyboard_review")
        title = pack.titles[pack.chosen].title if pack.titles else lv["subject"]
        flow.mail(
            ctx.db,
            ctx.settings,
            f"📝 Script prêt à relire : {title}",
            f"Le script de « {title} » est écrit ({script['words']} mots, ≈ {script['minutes_at_150']} min).\n"
            f"Relis-le, corrige ce que tu veux et valide-le dans la page Vidéos longues : la fabrication part et le Studio voix "
            f"s'ouvre.\n\n{ctx.settings.dashboard_url.rstrip('/')}/long/{lv['id']}",
        )
        return {"words": script["words"], "chapters": len(script["chapters"]), "lint": len(script["lint"])}

    def _chapter(self, ctx: Context, lv: dict[str, Any], chapter: int, note: str) -> dict[str, Any]:
        script = dict(lv["script"] or {})
        work = dict(script.get("work") or {})
        assert work.get("outline"), "plan absent : réécrire tout le script"
        folder = Path(lv["dir"])
        dossier = (folder / "dossier.txt").read_text(encoding="utf-8") if (folder / "dossier.txt").exists() else ""
        writer = Writer(ctx, lv, lambda _part: None)
        outline = Outline.model_validate(work["outline"])
        current = [{k: v for k, v in c.items() if k not in ("question",)} for c in script["chapters"]]
        for c in current:
            c["paragraphs"] = [{"text": p["text"], "show": p.get("show", "")} for p in c["paragraphs"]]
        ctx.progress(20, f"Chapitre {chapter + 1} réécrit")
        fix = ReviewProblem(
            chapter=chapter, problem=f"remarque de Luca : {note}" if note else "à réécrire", fix=note or "réécrire"
        )
        new = writer._write(outline, dossier, current, [chapter], [fix])  # noqa: SLF001
        chapters = {c["index"]: c for c in current}
        for c in new:
            chapters[c["index"]] = c
        ordered = [chapters[i] for i in sorted(chapters)]
        final = keyed(ordered)
        script["chapters"] = [
            {**c, "question": outline.chapters[c["index"]].question if c["index"] < len(outline.chapters) else ""} for c in final
        ]
        script["words"] = script_words(ordered)
        script["minutes_at_150"] = round(script["words"] / 150, 1)
        script["lint"] = [p.model_dump() for p in lint_long(ordered, outline, float(lv["target_minutes"]))]
        work["chapters"] = {str(c["index"]): c for c in ordered}
        script["work"] = work
        flow.update_long(ctx.db, lv["id"], script=script)
        return {"chapter": chapter, "words": script["words"]}

    def _shots(self, ctx: Context, lv: dict[str, Any]) -> dict[str, Any]:
        flow.ensure_production(ctx.db, ctx.settings, lv)
        script = lv["script"]
        rules = prompt_text(ctx.db, "rules_long_images", IMAGE_RULES_LONG)
        shots, bible = plan_shots(ctx, lv, script, rules, lambda pct, label: ctx.progress(pct, label))
        chapter_of = {p["key"]: c["index"] for c in script["chapters"] for p in c["paragraphs"]}
        ctx.db.execute("delete from long_shots where long_id = %s", (lv["id"],))
        for i, s in enumerate(shots):
            ctx.db.execute(
                """insert into long_shots (long_id, idx, chapter, para, at_word, kind, visual_prompt, motion, map)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    lv["id"],
                    i,
                    chapter_of.get(s.para, 0),
                    s.para,
                    s.at_word,
                    s.kind,
                    s.visual_prompt,
                    s.motion,
                    Jsonb(s.map.model_dump()) if s.map else None,
                ),
            )
        script = {**script, "design_bible": bible}
        flow.update_long(ctx.db, lv["id"], script=script, stage="making")
        flow.set_production_status(ctx.db, lv, "generating")
        lv = flow.get_long(ctx.db, lv["id"])
        jobs = flow.enqueue_visuals(ctx.db, lv)
        kinds = {k: sum(1 for s in shots if s.kind == k) for k in ("image", "clip", "map")}
        ctx.log("long.plans", **kinds)
        return {"shots": len(shots), **kinds, "jobs": len(jobs)}

    def _publish(self, ctx: Context, lv: dict[str, Any], publish_at: str | None) -> dict[str, Any]:
        from ..youtube.client import YouTubeClient

        assert lv.get("video_id"), "vidéo pas encore montée"
        v = ctx.db.fetch_one(
            "select v.*, a.local_path from videos v left join assets a on a.id = v.final_asset_id where v.id = %s",
            (lv["video_id"],),
        )
        assert v and v["local_path"], "fichier final introuvable"
        if v["youtube_video_id"]:
            return {"youtube_video_id": v["youtube_video_id"], "skipped": True}
        when = (
            datetime.fromisoformat(publish_at) if publish_at else (v["scheduled_at"] or flow.next_slot(ctx.db, lv["channel_id"]))
        )
        pack = lv.get("packaging") or {}
        titles = pack.get("titles") or [{"title": lv["subject"]}]
        title = (pack.get("final_title") or titles[min(int(pack.get("chosen") or 0), len(titles) - 1)]["title"])[:100]
        description = full_description(lv, pack, v)
        tags = [str(t)[:60] for t in (pack.get("tags") or [])][:30]
        ctx.db.execute(
            "update videos set title = %s, description = %s, tags = %s, scheduled_at = %s, slot_pinned = true, status = 'uploading' where id = %s",
            (title, description, tags, when, v["id"]),
        )
        if ctx.settings.dry_run:
            yt_id = "dry_long"
        else:
            yt = YouTubeClient.for_channel(ctx.settings, ctx.db, lv["channel_id"])
            yt_id = yt.upload(
                path=v["local_path"],
                title=title,
                description=description,
                tags=tags,
                publish_at=when,
                lang=v["lang"],
                on_progress=lambda f: ctx.progress(int(f * 95), f"Envoi sur YouTube {int(f * 100)} %"),
                synthetic=True,
                category="27",
            )
            ctx.db.record_quota(lv["channel_id"], "videos.insert", 1)
            self._put_thumbnail(ctx, lv, yt, yt_id)
        ctx.db.execute(
            "update videos set youtube_video_id = %s, youtube_publish_at = scheduled_at, status = 'scheduled' where id = %s",
            (yt_id, v["id"]),
        )
        flow.update_long(ctx.db, lv["id"], stage="done")
        flow.set_production_status(ctx.db, lv, "ready")
        return {"youtube_video_id": yt_id, "publish_at": when.isoformat()}

    def _release(self, ctx: Context, lv: dict[str, Any]) -> None:
        """Avant un nouvel envoi : l'ancien est gardé dans videos.previous_uploads (docs/44) et la vidéo le lâche. Refus
        s'il est encore sur YouTube (pas de doublon) : Luca le supprime d'abord dans Studio."""
        from ..youtube.client import YouTubeClient

        v = ctx.db.fetch_one(
            "select id, youtube_video_id, youtube_publish_at, scheduled_at from videos where id = %s", (lv.get("video_id"),)
        )
        if not v or not v["youtube_video_id"]:
            return
        if not ctx.settings.dry_run:
            yt = YouTubeClient.for_channel(ctx.settings, ctx.db, lv["channel_id"])
            still = yt.videos_list([v["youtube_video_id"]])
            ctx.db.record_quota(lv["channel_id"], "videos.list", 1)
            if still:
                why = (
                    f"l'ancien envoi ({v['youtube_video_id']}) est encore sur YouTube : le supprimer dans YouTube Studio, "
                    "puis « Envoyer à nouveau »"
                )
                flow.update_long(ctx.db, lv["id"], error=f"Nouvel envoi refusé : {why}")
                raise RuntimeError(why)
        ctx.db.execute(
            """update videos set previous_uploads = coalesce(previous_uploads, '[]'::jsonb) || jsonb_build_array(
                     jsonb_strip_nulls(jsonb_build_object('youtube_video_id', youtube_video_id,
                       'youtube_publish_at', youtube_publish_at, 'scheduled_at', scheduled_at, 'replaced_at', now()))),
                   youtube_video_id = null, youtube_publish_at = null, published_at = null
               where id = %s""",
            (v["id"],),
        )
        flow.update_long(ctx.db, lv["id"], error=None)
        ctx.log("long.renvoi", ancien=v["youtube_video_id"])

    def _thumbnail(self, ctx: Context, lv: dict[str, Any]) -> dict[str, Any]:
        """Repose la miniature choisie sur la vidéo déjà envoyée (refus de YouTube levé, ou autre miniature choisie)."""
        from ..youtube.client import YouTubeClient

        v = ctx.db.fetch_one("select youtube_video_id from videos where id = %s", (lv.get("video_id"),))
        assert v and v["youtube_video_id"], "vidéo pas encore envoyée sur YouTube"
        if ctx.settings.dry_run:
            return {"youtube_video_id": v["youtube_video_id"], "skipped": True}
        yt = YouTubeClient.for_channel(ctx.settings, ctx.db, lv["channel_id"])
        # un refus n'est pas relancé (50 unités par essai) : il reste écrit sur la fiche
        ok, why = self._put_thumbnail(ctx, lv, yt, v["youtube_video_id"])
        return {"youtube_video_id": v["youtube_video_id"], "ok": ok, "thumbnail": why}

    @staticmethod
    def _put_thumbnail(ctx: Context, lv: dict[str, Any], yt: Any, yt_id: str) -> tuple[bool, str]:
        """La miniature choisie sur la vidéo YouTube ; un refus reste écrit sur la fiche (l'envoi, lui, est fait)."""
        thumb = chosen_thumbnail(lv)
        if not thumb:
            return False, "aucune miniature choisie"
        ok, why = yt.set_thumbnail(yt_id, thumb)
        ctx.db.record_quota(lv["channel_id"], "thumbnails.set", 50)
        if ok:
            flow.update_long(ctx.db, lv["id"], error=None)
        else:
            ctx.log("long.miniature_refusee", level="warn", raison=why)
            flow.update_long(ctx.db, lv["id"], error=f"Miniature refusée par YouTube : {why}")
        return ok, why


def chosen_thumbnail(lv: dict[str, Any]) -> Path | None:
    th = lv.get("thumbnail") or {}
    cands = th.get("candidates") or []
    if not cands:
        return None
    c = cands[min(int(th.get("chosen") or 0), len(cands) - 1)]
    p = Path(c.get("file") or "")
    return p if p.exists() else None


def full_description(lv: dict[str, Any], pack: dict[str, Any], v: dict[str, Any]) -> str:
    """La description de l'agent, puis les chapitres horodatés (00:00 d'abord), les sources Wikipédia (CC BY-SA), la
    mention de l'IA et les hashtags."""
    parts = [str(pack.get("final_description") or pack.get("description") or "").strip()]
    marks = (lv.get("timeline") or {}).get("chapters") or []
    if len(marks) >= 3:
        from ..longform.render import fmt_ts

        parts.append("Chapitres\n" + "\n".join(f"{fmt_ts(float(m['at']))} {m['title']}" for m in marks))
    sources = (lv.get("dossier") or {}).get("sources") or []
    if sources:
        parts.append(
            "Sources (Wikipédia, licence CC BY-SA 4.0)\n" + "\n".join(f"- {s['title']} : {s['url']}" for s in sources[:8])
        )
    parts.append(AI_NOTICE)
    tags = " ".join(pack.get("hashtags") or [])
    if tags:
        parts.append(tags)
    return "\n\n".join(p for p in parts if p)[:4900]
