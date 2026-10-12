"""Voix des clips d'un drame, au montage (docs/70 §6) : une voix fixe par personnage, et des plans muets sans paroles.

Luca (12/10) garde les voix que MiniMax H3 fait avec la vidéo : voix, ambiance et bruits y sont cohérents. Deux défauts
mesurés sur les 10 drames publiés :
- **la voix d'un personnage change d'un plan à l'autre** : ses répliques ne se ressemblent pas plus entre elles (0,48 à
  0,75) qu'elles ne ressemblent aux autres personnages (0,49), d'après l'empreinte de voix du banc docs/49 §12 ;
- **H3 invente des paroles dans les plans sans réplique**, presque toujours en anglais (« Hey you little muscle »,
  « Yeah, starry man ») : 8 plans muets sur 19.

Au montage, pour chaque drame en voix des clips :
1. la voix de chaque clip parlé (et de chaque plan muet qui parle) est séparée de son ambiance (Demucs), une fois pour
   toutes (rangées à côté du clip : `scene_03.voix.wav`, `scene_03.ambiance.wav`) ;
2. l'empreinte de chaque réplique classe celles de chaque personnage, des plus typiques (les plus proches de toutes les
   autres) aux plus éloignées ; sa **référence** est la suite de ses répliques bien dites, en français, mises bout à
   bout (15 s au plus) ;
3. toutes ses répliques prennent le timbre de cette référence (Chatterbox VC) : le jeu de H3, son rythme et le calage
   sur les lèvres ne changent pas, l'ambiance du clip est remise dessous. Banc du 12/10 sur « La fille du gardien » :
   une seule réplique en référence ne changeait presque rien ; la référence longue, appliquée à toutes, rapproche les
   répliques d'un personnage (0,66 → 0,68) et l'éloigne des autres (0,52 → 0,47) ;
4. un plan muet où H3 a parlé garde son ambiance seule.
Le résultat remplace le son de ces clips dans la piste de voix (drama.build_dialogue_track, `whole`). Rien ne bloque
le montage : un environnement absent ou une étape en échec laisse le son des clips tel quel, et le dit.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .drama import invented_words, line_said, line_text, transcribe, voice_file, whisper_python
from .models import ScriptV1

REF_MAX_S = 15.0  # référence d'un personnage : ses meilleures répliques mises bout à bout, jusqu'à cette durée
CONVERT_TIMEOUT_S = 3600


@dataclass
class Line:
    pos: int  # position de la scène dans le script
    who: str
    ok: bool  # réplique dite, dans la langue de la vidéo : elle peut servir de référence
    spans: list[list[float]] = field(default_factory=list)  # passages parlés du clip (Whisper, assets.meta.dialogue)


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b, strict=False)))


def reference_sets(lines: Sequence[Line], emb: dict[int, list[float]]) -> dict[str, list[int]]:
    """Référence de chaque personnage qui a au moins deux répliques : les positions de ses répliques bien dites (toutes
    s'il n'en a pas), des plus typiques (les plus proches, en moyenne, de ses autres répliques) aux moins typiques."""
    out: dict[str, list[int]] = {}
    for who in dict.fromkeys(ln.who for ln in lines):
        mine = [ln for ln in lines if ln.who == who]
        if len(mine) < 2:
            continue
        pool = [ln for ln in mine if ln.ok] or mine

        def typical(ln: Line, mine: list[Line] = mine) -> float:
            others = [o for o in mine if o.pos != ln.pos and o.pos in emb]
            if ln.pos not in emb or not others:
                return -1.0
            return sum(dot(emb[ln.pos], emb[o.pos]) for o in others) / len(others)

        out[who] = [ln.pos for ln in sorted(pool, key=typical, reverse=True)]
    return out


def consistency(lines: Sequence[Line], emb: dict[int, list[float]]) -> dict[str, float]:
    """Ressemblance moyenne des répliques de chaque personnage entre elles (empreintes de voix), pour le rapport."""
    out: dict[str, float] = {}
    for who in dict.fromkeys(ln.who for ln in lines):
        mine = [ln.pos for ln in lines if ln.who == who and ln.pos in emb]
        pairs = [(a, b) for i, a in enumerate(mine) for b in mine[i + 1 :]]
        if pairs:
            out[who] = round(sum(dot(emb[a], emb[b]) for a, b in pairs) / len(pairs), 2)
    return out


def reference_key(clips: Sequence[Path]) -> str:
    """Identité d'une référence : ses clips et leur version (un clip refait change la référence)."""
    raw = "|".join(f"{c.name}:{int(c.stat().st_mtime) if c.is_file() else 0}" for c in clips)
    return hashlib.sha1(raw.encode()).hexdigest()[:8]


def ambience_file(clip: Path) -> Path:
    """Ambiance seule d'un clip, sans la voix (scene_03.mp4 → scene_03.ambiance.wav)."""
    return clip.with_suffix(".ambiance.wav")


def converted_file(clip: Path, key: str) -> Path:
    """Son d'un clip, voix au timbre de la référence de son personnage (scene_05.mp4 → scene_05.timbre_1a2b3c4d.wav)."""
    return clip.with_name(f"{clip.stem}.timbre_{key}.wav")


def fresh(out: Path, *sources: Path) -> bool:
    return out.is_file() and all(out.stat().st_mtime >= s.stat().st_mtime for s in sources if s.is_file())


def _run(
    python: Path, runner: str, request: dict[str, Any], tmp_root: Path, timeout_s: int, env: dict[str, str]
) -> dict[str, Any]:
    script = Path(__file__).resolve().parents[1] / "tts_runners" / runner
    with tempfile.TemporaryDirectory(prefix="voix_clips_", dir=tmp_root) as tmp:
        req = Path(tmp) / "request.json"
        out = Path(tmp) / "result.json"
        request = {**request, "work": str(Path(tmp) / "work"), "out": str(out)}
        req.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [str(python), str(script), str(req)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", **env},
            timeout=timeout_s,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(f"{runner} en échec (code {proc.returncode}) : {(proc.stderr or '')[-1500:]}")
        return json.loads(out.read_text(encoding="utf-8"))


def fix_voices(
    settings: Any,
    script: ScriptV1,
    clips: Sequence[dict[str, Any]],
    lang: str,
    *,
    log: Callable[..., None] | None = None,
) -> tuple[dict[int, Path], dict[str, Any]]:
    """Son de remplacement des clips d'un drame en voix des clips → ({position : fichier, son du clip entier}, rapport).
    `clips[i]` : {"local_path", "dialogue" : assets.meta.dialogue ou None}."""
    say = log or (lambda *a, **k: None)
    home = Path(settings.yt2_home)
    vc_python = home / "tts" / "vc" / "venv" / "Scripts" / "python.exe"
    eval_python = whisper_python(settings)
    model = home / "tts" / "eval" / "models" / "speaker.onnx"
    if not vc_python.exists() or not eval_python.exists() or not model.exists():
        return {}, {"indisponible": "environnements tts/vc et tts/eval (install_tts.ps1 -Engine vc, -Engine eval)"}
    tmp_root = Path(settings.data_dir) / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    hf = {"HF_HOME": str(home / "tts" / "hf-cache")}
    paths = [Path(str(c.get("local_path") or "")) for c in clips]
    report: dict[str, Any] = {}

    # Plans muets : des paroles inventées par le modèle vidéo ? (clips d'avant le 12/10 : écoutés maintenant)
    silent = [k for k, sc in enumerate(script.scenes) if not sc.lines and paths[k].is_file()]
    unheard = [k for k in silent if not isinstance((clips[k].get("dialogue") or {}).get("invented"), list)]
    heard_now: dict[int, list[str]] = {}
    if unheard:
        try:
            got = transcribe(settings, [paths[k] for k in unheard], None) or []
            heard_now = {k: invented_words(r.get("words") or []) for k, r in zip(unheard, got, strict=False)}
        except Exception as exc:  # noqa: BLE001
            say("voix_clips.ecoute_indisponible", level="warn", erreur=str(exc)[:300])
    talking = [k for k in silent if (heard_now.get(k) if k in heard_now else (clips[k].get("dialogue") or {}).get("invented"))]

    lines = [
        Line(
            k,
            sc.lines[0].who,
            line_said(clips[k].get("dialogue"), lang),
            list((clips[k].get("dialogue") or {}).get("speech") or []),
        )
        for k, sc in enumerate(script.scenes)
        if sc.lines and line_text(sc) and paths[k].is_file()
    ]
    # 1. voix et ambiance séparées, une fois pour toutes
    need = [
        k
        for k in [ln.pos for ln in lines] + talking
        if not (fresh(voice_file(paths[k]), paths[k]) and fresh(ambience_file(paths[k]), paths[k]))
    ]
    if need:
        try:
            res = _run(
                vc_python,
                "drama_voices.py",
                {
                    "split": [
                        {"clip": str(paths[k]), "voice": str(voice_file(paths[k])), "rest": str(ambience_file(paths[k]))}
                        for k in need
                    ],
                    "device": settings.drama_voice_device,
                },
                tmp_root,
                CONVERT_TIMEOUT_S,
                hf,
            )
            report["separation"] = {"clips": len(need), "secondes": res.get("seconds"), "processeur": res.get("device")}
        except Exception as exc:  # noqa: BLE001
            say("voix_clips.separation_impossible", level="warn", erreur=str(exc)[:300])
            return {}, {**report, "echec": "séparation des voix"}
    out: dict[int, Path] = {k: ambience_file(paths[k]) for k in talking if ambience_file(paths[k]).is_file()}
    if out:
        report["muets_sans_paroles"] = sorted(script.scenes[k].index for k in out)

    # 2. empreintes et références
    if len(lines) < 2:
        return out, report
    try:
        res = _run(
            eval_python,
            "speaker_embed.py",
            {"items": [{"file": str(voice_file(paths[ln.pos])), "spans": ln.spans} for ln in lines], "model": str(model)},
            tmp_root,
            900,
            hf,
        )
        emb = {ln.pos: v for ln, v in zip(lines, res["embeddings"], strict=False) if v}
    except Exception as exc:  # noqa: BLE001
        say("voix_clips.empreintes_impossibles", level="warn", erreur=str(exc)[:300])
        return out, {**report, "echec": "empreintes de voix"}
    sets = reference_sets(lines, emb)
    by_pos = {ln.pos: ln for ln in lines}
    report["references"] = {who: [script.scenes[k].index for k in ks] for who, ks in sets.items()}
    report["ressemblance_avant"] = consistency(lines, emb)

    # 3. le timbre de sa référence sur toutes les répliques du personnage
    jobs = []
    for who, ks in sets.items():
        ref_clips = [paths[k] for k in ks]
        key = reference_key(ref_clips)
        parts = [{"file": str(voice_file(paths[k])), "spans": by_pos[k].spans} for k in ks]
        for ln in (x for x in lines if x.who == who):
            target = converted_file(paths[ln.pos], key)
            out[ln.pos] = target
            if not fresh(target, paths[ln.pos], *ref_clips):
                jobs.append(
                    {
                        "voice": str(voice_file(paths[ln.pos])),
                        "rest": str(ambience_file(paths[ln.pos])),
                        "reference_parts": parts,
                        "reference_key": key,
                        "out": str(target),
                    }
                )
    report["converties"] = sorted(script.scenes[k].index for k in out if k in by_pos)
    if jobs:
        try:
            res = _run(
                vc_python,
                "drama_voices.py",
                {"convert": jobs, "device": settings.drama_voice_device, "reference_max_s": REF_MAX_S},
                tmp_root,
                CONVERT_TIMEOUT_S,
                hf,
            )
            report["conversion"] = {"repliques": len(jobs), "secondes": res.get("seconds"), "processeur": res.get("device")}
        except Exception as exc:  # noqa: BLE001
            say("voix_clips.conversion_impossible", level="warn", erreur=str(exc)[:300])
            for k in by_pos:
                out.pop(k, None)
            report["echec"] = "conversion des voix"
    return {k: p for k, p in out.items() if p.is_file()}, report
