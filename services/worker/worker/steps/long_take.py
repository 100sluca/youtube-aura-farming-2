"""Job long_take (voie preview, pris dans la seconde) : une prise du Studio voix vérifiée par Whisper (docs/63 §4).

Le dashboard range l'enregistrement du navigateur (long_takes.path) et crée ce job ; Whisper (processeur) dit ce qu'il
entend, mot par mot et horodaté ; le résultat (ressemblance avec le texte, passages sautés, mots) va dans
long_takes.check_result, et la prise passe à « ok » ou « problem ». Une prise à problème reste gardée : c'est Luca qui
décide de la refaire.

Action voice_mod (Studio du modificateur, docs/67) : un réglage du modificateur essayé sur l'extrait d'une prise, en
quelques secondes ; le résultat donne les deux fichiers à comparer (original nettoyé, essai), au même niveau.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from ..longform.voice import check_take
from .base import Context, Step


class LongTakeStep(Step):
    type = "long_take"
    lane = "preview"

    def run(self, ctx: Context) -> dict[str, Any]:
        if ctx.job.payload.get("action") == "voice_mod":
            from ..longform import voice_mod

            ctx.progress(20, "Modificateur : essai sur l'extrait")
            return voice_mod.preview(ctx.settings, Path(ctx.job.payload["source"]), ctx.job.payload.get("params") or {})
        take = ctx.db.fetch_one("select * from long_takes where id = %s", (ctx.job.payload["take_id"],))
        assert take, "prise introuvable"
        lv = ctx.db.fetch_one("select script from long_videos where id = %s", (take["long_id"],))
        text = next(
            (
                p["text"]
                for c in ((lv or {}).get("script") or {}).get("chapters", [])
                for p in c["paragraphs"]
                if p["key"] == take["para"]
            ),
            "",
        )
        ctx.progress(10, "Whisper écoute la prise")
        try:
            result = check_take(ctx.settings, Path(take["path"]), text)
        except Exception as exc:  # noqa: BLE001 — la prise reste, sans vérification
            ctx.db.execute(
                "update long_takes set status = 'ok', check_result = %s where id = %s",
                (Jsonb({"unchecked": True, "error": str(exc)[:300]}), take["id"]),
            )
            raise
        status = result.pop("status")
        ctx.db.execute(
            "update long_takes set status = %s, check_result = %s, duration_s = %s where id = %s",
            (status, Jsonb(result), result.get("duration_s"), take["id"]),
        )
        return {"status": status, "ratio": result.get("ratio"), "missing": len(result.get("missing") or [])}
