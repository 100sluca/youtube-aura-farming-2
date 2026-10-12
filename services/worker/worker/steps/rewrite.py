"""Réécrire le récit d'une vidéo faite, depuis Bibliothèque → Retoucher → Récit (docs/53, worker/rewrite.py).

Deux temps, un job chacun, sur la vidéo d'origine :
- « propose » : le conteur réécrit tout le récit sur les plans tels qu'ils sont (mode « story », relu comme au script),
  ou seulement l'accroche et la promesse (mode « hook »), d'après les remarques de Luca. Rien n'est créé : le texte
  proposé va dans le résultat du job, Luca le relit et peut le corriger.
- « make » : le texte relu devient une nouvelle vidéo (copie de la production, clips liés, voix → montage → contrôle,
  SEO refait pour un récit entier). Elle arrive à valider ; la vidéo d'origine ne change pas.
"""

from __future__ import annotations

from typing import Any

from ..rewrite import HookRewrite, StoryRewrite, load_source, make_hook, make_story, rewrite_hook, rewrite_story
from .base import Context, Step

MODES = ("story", "hook")


def shots_view(ctx: Context) -> list[dict[str, Any]]:
    """Les plans tels que le Dashboard les montre à côté du texte proposé : ce qu'on voit, l'ancien texte, la place."""
    src = load_source(ctx.db, ctx.job.video_id)
    return [
        {"index": s.index, "seconds": round(s.seconds, 1), "shows": s.shows, "said": s.said, "words_max": s.words_max}
        for s in src.shots
    ]


class RewriteStep(Step):
    type = "rewrite"
    lane = "io"

    def run(self, ctx: Context) -> dict[str, Any]:
        p = ctx.job.payload
        mode = p.get("mode")
        if mode not in MODES or not ctx.job.video_id:
            raise ValueError(f"réécriture : mode {mode!r} ou vidéo manquante")
        data_dir = ctx.settings.data_dir
        if p.get("action") == "make":
            ctx.progress(30, "Nouvelle vidéo : copie des plans")
            if mode == "story":
                out, issues = make_story(ctx.db, data_dir, ctx.job.video_id, StoryRewrite.model_validate(p["proposal"]))
            else:
                out = make_hook(ctx.db, data_dir, ctx.job.video_id, HookRewrite.model_validate(p["proposal"]))
                issues = out.issues
            ctx.log("reecriture.video", video=str(out.video_id), production=str(out.production_id), lies=out.linked)
            return {
                "action": "make",
                "mode": mode,
                "video_id": str(out.video_id),
                "production_id": str(out.production_id),
                "linked": out.linked,
                "issues": issues,
            }

        note = str(p.get("note") or "")
        pages = [str(t).strip() for t in p.get("pages") or [] if str(t).strip()]
        if mode == "story":
            _, rw, issues = rewrite_story(
                ctx.db, ctx.settings, data_dir, ctx.job.video_id, note, pages=pages, dry=True, progress=ctx.progress
            )
            proposal: dict[str, Any] = rw.model_dump(mode="json")
        else:
            hr, issues = rewrite_hook(ctx.db, ctx.settings, data_dir, ctx.job.video_id, note, pages=pages, progress=ctx.progress)
            proposal = hr.model_dump(mode="json")
        return {"action": "propose", "mode": mode, "proposal": proposal, "issues": issues, "shots": shots_view(ctx)}
