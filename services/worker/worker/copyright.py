"""Vidéos bloquées sur YouTube pour droits d'auteur (docs/58 §6, constat de Luca du 02/10 : « beaucoup de problèmes sur
YouTube »).

L'API ne donne pas les réclamations Content ID d'une chaîne ordinaire, mais elle dit ce qu'elles produisent, dans la
même lecture que les compteurs (videos.list, déjà faite chaque heure, aucune unité de quota en plus) :
- contentDetails.regionRestriction : pays où la vidéo est bloquée (`blocked`) ou seuls pays où elle se voit
  (`allowed`) — la règle « bloquer dans certains pays » d'un ayant droit ;
- status.uploadStatus = rejected avec rejectionReason = claim / copyright : bloquée partout.
Chaque nouveau blocage est gardé dans videos.copyright (migration 0047) avec la musique de la vidéo, et signalé par une
alerte qui nomme la piste : c'est presque toujours elle (images et voix sont générées). La musique de Luca en cause se
décoche dans Montage → Son ; une vidéo touchée se refait sans elle (Bibliothèque → Retoucher → Musique).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb


def restriction(item: dict[str, Any]) -> dict[str, Any] | None:
    """Ce qui bloque la vidéo d'après sa fiche YouTube ; None si elle se voit partout."""
    rr = (item.get("contentDetails") or {}).get("regionRestriction") or {}
    status = item.get("status") or {}
    blocked = sorted(rr.get("blocked") or [])
    allowed = rr.get("allowed")
    rejected = status.get("uploadStatus") == "rejected"
    reason = status.get("rejectionReason")
    if not blocked and allowed is None and not rejected:
        return None
    out: dict[str, Any] = {}
    if blocked:
        out["blocked"] = blocked
    if allowed is not None:
        out["allowed"] = sorted(allowed)
    if rejected:
        out["rejected"] = reason or "rejected"
    return out


def describe(found: dict[str, Any]) -> str:
    if found.get("rejected"):
        return f"bloquée partout ({found['rejected']})"
    if "allowed" in found:
        return f"visible seulement dans {len(found['allowed'])} pays"
    blocked = found.get("blocked") or []
    fr = " dont la France" if "FR" in blocked else ""
    return f"bloquée dans {len(blocked)} pays{fr}"


def check_videos(db: Any, items: dict[str, dict[str, Any]], by_yt: dict[str, Any]) -> int:
    """Relève les blocages des vidéos de l'appli lues dans cette synchro ; une alerte par blocage nouveau ou changé.
    Renvoie le nombre de vidéos bloquées."""
    count = 0
    for yt_id, item in items.items():
        vid = by_yt.get(yt_id)
        if vid is None:
            continue
        found = restriction(item)
        row = db.fetch_one(
            "select title, music_track, to_jsonb(v) -> 'copyright' as copyright from videos v where id = %s", (vid,)
        )
        if row is None:
            continue
        before = row.get("copyright") or None
        if found is None:
            if before and not before.get("cleared_at"):  # levé (litige gagné, musique retirée dans Studio)
                db.execute(
                    "update videos set copyright = copyright || %s where id = %s",
                    (Jsonb({"cleared_at": datetime.now(UTC).isoformat()}), vid),
                )
            continue
        count += 1
        same = before and {k: before.get(k) for k in found} == found and not before.get("cleared_at")
        if same:
            continue
        record = {**found, "music_track": row.get("music_track"), "seen_at": datetime.now(UTC).isoformat()}
        db.execute("update videos set copyright = %s where id = %s", (Jsonb(record), vid))
        track = row.get("music_track")
        db.alert(
            "error",
            f"Vidéo {describe(found)} : « {row.get('title') or yt_id} »",
            (
                f"Musique de la vidéo : {track}. C'est presque toujours elle : la décocher dans Montage → Son, et refaire "
                "la vidéo sans elle (Bibliothèque → Retoucher → Musique)."
                if track
                else "La vidéo n'a pas de musique de la bibliothèque : voir la réclamation dans YouTube Studio → Contenu."
            )
            + " Détail : docs/58-citations.md §6.",
            video_id=vid,
        )
    return count
