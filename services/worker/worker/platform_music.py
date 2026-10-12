"""Musique des plateformes, ajoutée à la publication (docs/58 §4, demande de Luca du 02/10).

Le constat de Luca : des vidéos bloquées ou réclamées pour droits d'auteur à cause de la musique de fond (beaucoup sur
YouTube, un peu sur TikTok), alors que d'autres comptes utilisent les mêmes musiques sans souci — parce qu'ils les
prennent dans la bibliothèque de la plateforme, sous licence. Ce que chaque plateforme permet par l'API :
- TikTok (Zernio, compte relié par l'appli TikTok for Business) : une musique de la bibliothèque commerciale de TikTok
  (Commercial Music Library, libre d'usage pour les comptes pro) attachée à une VIDÉO à sa création
  (tiktokSettings.musicSoundInfo, liste des tendances par pays) ; le son de notre vidéo est baissé
  (videoOriginalSoundVolume). Pour un carrousel PHOTO, TikTok choisit lui-même une musique recommandée
  (auto_add_music). Ignoré pour un brouillon (boîte de réception) : Luca la choisit alors dans l'appli ;
- Instagram (Zernio) : une musique du catalogue d'Instagram attachée au Reel (platformSpecificData.audioConfiguration,
  recherche par mots), seulement pour un compte connecté par Facebook Login (au 02/10, @arzakparker l'est par
  Instagram Login : 400 instagram_audio_requires_facebook_login, la publication repart alors sans) ;
- YouTube : aucune API (les sons des Shorts ne s'ajoutent que dans l'appli mobile, la bibliothèque audio que dans
  YouTube Studio) : la vidéo garde la musique du montage, à prendre sans droits d'auteur tiers (citations : pistes
  générées par ACE-Step, worker/quotes.py).

Réglages (app_settings « tiktok », clé « platform_music », modifiables à la main ou par `yt2 tiktok music`) :
    {"recipes": ["quote"], "volume": 60, "country": "FR"}
`recipes` : recettes dont les vidéos sans voix prennent une musique de TikTok (défaut : les citations) ; une vidéo
narrée garde la sienne (sa voix est mélangée à la musique dans le même fichier).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT = {"recipes": ["quote"], "volume": 60, "country": "FR"}
# Genres de la bibliothèque commerciale de TikTok (champ genres) qui vont sous une citation, par ambiance du script ;
# puis des mots du titre. Les musiques « HIP_HOP », « LATIN », « ELECTRONIC »… ne sont prises qu'en dernier recours.
CALM_GENRES = ("NEW_AGE", "EASY_LISTENING", "SOUNDTRACK", "CLASSICAL", "AMBIENT", "ALL")
MOOD_WORDS: dict[str, tuple[str, ...]] = {
    "triste": ("piano", "sad", "melanchol", "tears", "lonely", "memory", "memories", "rain", "missing", "empty", "forget"),
    "tendre": ("piano", "love", "tender", "heart", "warm", "wedding", "letter", "soft", "dear"),
    "reveur": ("dream", "float", "night", "moon", "calm", "ambient", "sky", "serene", "faint", "glow", "piano"),
    "espoir": ("hope", "light", "sun", "rise", "new", "free", "fly", "piano", "days like"),
}
INSTAGRAM_QUERIES = {
    "triste": "sad piano",
    "tendre": "emotional piano",
    "reveur": "ambient piano",
    "espoir": "hopeful piano",
}


@dataclass(frozen=True)
class PlatformMusic:
    recipes: tuple[str, ...]
    volume: int
    country: str

    def applies(self, recipe: str | None, voiced: bool) -> bool:
        return bool(recipe) and recipe in self.recipes and not voiced


def load_config(db: Any) -> PlatformMusic:
    row = db.fetch_one("select value from app_settings where key = 'tiktok'")
    raw = ((row or {}).get("value") or {}).get("platform_music") or {}
    cfg = {**DEFAULT, **(raw if isinstance(raw, dict) else {})}
    return PlatformMusic(
        recipes=tuple(str(r) for r in cfg.get("recipes") or []),
        volume=max(0, min(100, int(cfg.get("volume") or DEFAULT["volume"]))),
        country=str(cfg.get("country") or "FR").upper()[:2],
    )


def _score(track: dict[str, Any], mood: str | None) -> float:
    genres = {str(g).upper() for g in track.get("genres") or []}
    name = f"{track.get('name', '')} {track.get('artist', '')}".lower()
    score = 0.0
    for k, g in enumerate(CALM_GENRES):
        if g in genres:
            score = max(score, 3.0 - k * 0.3)
    words = MOOD_WORDS.get(mood or "", ()) + MOOD_WORDS["reveur"]
    score += sum(1.5 for w in set(words) if w in name)
    if "lofi" in name or "lo-fi" in name:
        score += 0.5
    if genres & {"HIP_HOP/RAP", "LATIN", "ELECTRONIC", "ROCK", "CHILDHOOD", "DANCE", "METAL"}:
        score -= 2.0
    score -= float(track.get("rank") or 100) / 200  # à égalité, la plus en tendance
    return score


def pick_tiktok_track(tracks: list[dict[str, Any]], mood: str | None, key: str, top: int = 6) -> dict[str, Any] | None:
    """Une musique de la liste, parmi les `top` qui vont le mieux à l'ambiance (stable pour une même vidéo)."""
    if not tracks:
        return None
    ranked = sorted(tracks, key=lambda t: _score(t, mood), reverse=True)[:top]
    return ranked[int(hashlib.sha1(key.encode()).hexdigest(), 16) % len(ranked)]


def cached_tracks(client: Any, account_id: str, country: str, cache_dir: Path) -> list[dict[str, Any]]:
    """Liste des tendances lue une fois par jour et par pays (DATA_DIR/tiktok/commercial-music-FR-<date>.json)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    f = cache_dir / f"commercial-music-{country}-{date.today().isoformat()}.json"
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            pass
    tracks = client.commercial_music(account_id, country)
    f.write_text(json.dumps(tracks, ensure_ascii=False), encoding="utf-8")
    return tracks


def tiktok_settings(track: dict[str, Any], duration_s: float, volume: int) -> dict[str, Any]:
    """Champs à ajouter à tiktokSettings : la musique jouée depuis son début, sur toute la vidéo, et le son de notre
    vidéo coupé (sans voix, sa musique serait en double)."""
    clip = track.get("clip") or {}
    length = float(clip.get("durationSec") or track.get("durationSec") or 0)
    end_ms = int(min(duration_s, length) * 1000) if length else int(duration_s * 1000)
    return {
        "musicSoundInfo": {
            "musicSoundId": str(track["id"]),
            "musicSoundVolume": volume,
            "musicSoundStart": 0,
            "musicSoundEnd": max(1000, end_ms),
        },
        "videoOriginalSoundVolume": 0,
    }


def summary(track: dict[str, Any]) -> dict[str, Any]:
    """Ce qu'on garde dans videos.tiktok (Calendrier, fiche de la vidéo, statistiques par musique)."""
    return {
        "id": str(track.get("id")),
        "name": track.get("name"),
        "artist": track.get("artist"),
        "genres": track.get("genres"),
    }


def video_facts(db: Any, video_id: Any) -> tuple[str | None, bool, str | None, float]:
    """Recette, voix (format A), ambiance musicale du script et durée de la vidéo."""
    row = db.fetch_one(
        """select coalesce(s.recipe, 'story') as recipe, v.format, p.script ->> 'music_mood' as mood, v.duration_s
           from videos v join productions p on p.id = v.production_id left join series s on s.id = p.series_id
           where v.id = %s""",
        (video_id,),
    )
    if not row:
        return None, True, None, 0.0
    return row.get("recipe"), row.get("format") != "B_visual", row.get("mood"), float(row.get("duration_s") or 0)


def instagram_audio(client: Any, account_id: str, mood: str | None, key: str) -> dict[str, Any] | None:
    """Une musique du catalogue d'Instagram pour l'ambiance (recherche « sad piano »…) ; None si rien ne sort. Laisse
    passer l'erreur 400 instagram_audio_requires_facebook_login (l'appelant publie alors sans)."""
    found = client.instagram_audio(account_id, INSTAGRAM_QUERIES.get(mood or "", "piano"))
    if not found:
        return None
    top = found[:5]
    return top[int(hashlib.sha1(key.encode()).hexdigest(), 16) % len(top)]
