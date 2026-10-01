"""Banc d'essai « émotion » des voix (docs/41-voix-emotion.md) : les répliques d'un vrai drame (« Madame Figue », 16
répliques, 4 personnages), chacune avec le ton écrit par le scénariste (« mischievous, slow », « whispering, greedy »,
« weak, crying softly », « shouting, pointing »…), dites par plusieurs moteurs. Chaque personnage garde sa voix et le
modèle est chargé une fois par personnage, comme à l'étape voix d'un drame : le temps mesuré est celui d'une vraie vidéo.

1. `run` (Python du worker, .env exporté, depuis C:\\YouTube2) :
   - moteur sur la carte graphique : un job voice_preview par personnage (répliques + tons), priorité 5 : le worker les
     prend entre deux clips et vide ComfyUI avant, comme le bouton « Écouter » des Réglages ;
   - moteur en ligne ou sur le processeur : lancé par le banc lui-même, avec le même code que l'étape voix.
2. `eval` (environnement C:\\YouTube2\\tts\\eval) : ce que Whisper entend (mots mal compris), hauteur et intensité de
   chaque réplique (le jeu : une réplique chuchotée plus basse qu'une réplique criée), ressemblance du timbre d'une
   réplique à l'autre (empreinte de voix sherpa-onnx, si elle est installée).
3. `report` : index.html (une ligne par réplique : texte, ton, un lecteur par moteur ; la scène entière enchaînée),
   README.md, results.csv. `video` : la vidéo de Madame Figue redite par chaque moteur, sur la musique de la vidéo
   (Bibliothèque → Démos et essais).

    set -a; . <dépôt>/services/worker/.env; set +a
    cd /c/YouTube2 && worker-venv/Scripts/python.exe <dépôt>/services/worker/scripts/bench_emotion.py run \\
        --variants qwen3,qwen3_instruct,gemini
    tts/eval/venv/Scripts/python.exe <dépôt>/services/worker/scripts/bench_emotion.py eval <banc>
    worker-venv/Scripts/python.exe <dépôt>/services/worker/scripts/bench_emotion.py report <banc>
    worker-venv/Scripts/python.exe <dépôt>/services/worker/scripts/bench_emotion.py video <banc>
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_voice as bv  # noqa: E402 — mesures (VRAM, RAM), Whisper, hauteur, mise en forme

SHORTS_PER_WEEK = 21
RECIT_CHARS = 1100  # un récit de 75 s (docs/37) : ≈ 1 100 caractères dits par une seule voix
PRODUCTION = "38e4e7aa"  # « Madame Figue », karma_fruits, 28/09/2026 (docs/35)

# Voix du studio Gemini choisies d'après la description de chaque personnage (voix fixes : pas de clonage dans l'UE)
GEMINI_VOICES = {"madame_figue": "Gacrux", "prune": "Algieba", "kiwi": "Achird", "groseille": "Leda"}

# Noms des vidéos de comparaison (Bibliothèque → Démos et essais), dans l'ordre d'écoute proposé à Luca
VIDEO_NAMES = {
    "qwen3": "1_voix_actuelle",
    "qwen3_emotion": "2_references_emues",
    "qwen3_emotion_pure": "3_reference_emue_telle_quelle",
    "qwen3_instruct": "4_voicedesign_avec_le_ton",
    "gemini": "5_gemini_en_ligne",
}

# Variantes : moteur (catalog.json → tts), voix des personnages (« qwen » : la voix Qwen dessinée du script ; « gemini »),
# tons transmis ou non, description du personnage placée devant le ton (Gemini n'a pas de voix d'enfant ni d'aïeule).
VARIANTS: dict[str, dict[str, Any]] = {
    "qwen3": {"label": "Qwen3-TTS Base 0.6B · aujourd'hui", "engine": "qwen3", "voices": "qwen", "tones": False},
    "qwen3_emotion": {
        "label": "Qwen3-TTS Base 0.6B · référence émue, timbre de la voix",
        "engine": "qwen3_emotion",
        "voices": "qwen",
        "tones": True,
    },
    "qwen3_emotion_pure": {
        "label": "Qwen3-TTS Base 0.6B · référence émue clonée telle quelle",
        "engine": "qwen3_emotion_pure",
        "voices": "qwen",
        "tones": True,
    },
    "qwen3_instruct": {
        "label": "Qwen3-TTS VoiceDesign 1.7B · avec le ton",
        "engine": "qwen3_instruct",
        "voices": "qwen",
        "tones": True,
    },
    "gemini": {
        "label": "Gemini 3.8 Flash TTS · en ligne, avec le ton",
        "engine": "gemini",
        "voices": "gemini",
        "tones": True,
        "persona": True,
    },
}


# ---------------------------------------------------------------------------------------------------------------------
# 1. run
# ---------------------------------------------------------------------------------------------------------------------


def load_set(settings: Any) -> dict[str, Any]:
    """Répliques et personnages de la production de référence, recopiés dans le banc au premier lancement (une retouche
    ultérieure de la vidéo ne change pas un banc commencé)."""
    import psycopg

    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute(
            "select p.id::text, p.script, v.id::text from productions p left join videos v on v.production_id = p.id "
            "where p.id::text like %s limit 1",
            (PRODUCTION + "%",),
        ).fetchone()
    assert row and row[1], f"production {PRODUCTION} introuvable"
    script = row[1]
    cast = {
        m["key"]: {"name": m["name"], "voice": m.get("voice", ""), "tts_voice": m.get("tts_voice", "")} for m in script["cast"]
    }
    lines = [
        {"index": s["index"], "who": ln["who"], "text": ln["text"], "tone": ln.get("tone", "")}
        for s in script["scenes"]
        for ln in s.get("lines", [])[:1]
    ]
    return {"production": row[0], "video": row[2], "title": "Madame Figue", "cast": cast, "lines": lines}


def voice_for(variant: dict[str, Any], who: str, cast: dict[str, Any]) -> str:
    if variant["voices"] == "gemini":
        return GEMINI_VOICES.get(who, "Kore")
    return (cast[who]["tts_voice"] or "qwen3:narrateur").split(":", 1)[1]


def tone_for(variant: dict[str, Any], line: dict[str, Any], cast: dict[str, Any]) -> str:
    if not variant.get("tones"):
        return ""
    tone = line["tone"]
    persona = cast[line["who"]]["voice"] if variant.get("persona") else ""
    return f"{persona}; {tone}" if persona and tone else tone or persona


def cmd_run(args: argparse.Namespace) -> None:
    from worker.config import Settings, utf8_console
    from worker.providers.tts import get_engine

    utf8_console()
    settings = Settings()
    folder = Path(args.dir) if args.dir else Path(args.out) / f"{datetime.now():%Y-%m-%d}-voix-emotion"
    folder.mkdir(parents=True, exist_ok=True)
    bench = bv.load_bench(folder) or {**load_set(settings), "variants": {}}
    bench.setdefault("started", datetime.now().isoformat(timespec="seconds"))
    bench["machine"] = bv.machine()
    bench["speed"] = args.speed or bv.channel_speed(settings, "fr")
    bv.save_bench(folder, bench)
    wanted = [v.strip() for v in args.variants.split(",") if v.strip()]
    unknown = [v for v in wanted if v not in VARIANTS]
    if unknown:
        sys.exit(f"variantes inconnues : {unknown} (connues : {', '.join(VARIANTS)})")
    print(f"Banc : {folder}\n{len(bench['lines'])} répliques · {len(bench['cast'])} personnages · vitesse {bench['speed']}")
    groups: dict[str, list[dict[str, Any]]] = {}
    for line in bench["lines"]:
        groups.setdefault(line["who"], []).append(line)
    on_gpu = []
    for vid in wanted:
        variant = VARIANTS[vid]
        engine = get_engine(settings, variant["engine"])
        row = bench["variants"].setdefault(vid, {})
        if row.get("jobs") and not row.get("first_jobs"):
            # deuxième passage : le premier a peut-être créé la banque de références (qwen3_emotion) ; on garde ses temps
            row["first_jobs"] = row.pop("jobs")
        row.update(label=variant["label"], engine=variant["engine"], gpu=bool(getattr(engine, "gpu", False)))
        (folder / vid).mkdir(exist_ok=True)
        if row["gpu"]:
            on_gpu.append((vid, variant))
            continue
        print(f"\n== {variant['label']} (lancé par le banc)")
        run_direct(settings, engine, bench, folder, vid, variant, groups)
        bv.save_bench(folder, bench)
    if on_gpu:  # tous les essais en file d'un coup : aucun clip ne s'intercale entre deux moteurs
        print(f"\n== carte graphique, file du worker : {', '.join(v for v, _ in on_gpu)}")
        run_via_worker(settings, bench, folder, on_gpu, groups)
    print(f"\nFini. Ensuite : bench_emotion.py eval {folder}, puis report {folder}")


def _payloads(bench: dict[str, Any], vid: str, variant: dict[str, Any], groups: dict[str, list[dict[str, Any]]]) -> list:
    out = []
    for who, lines in groups.items():
        voice = voice_for(variant, who, bench["cast"])
        out.append(
            (
                who,
                lines,
                {
                    "voice": f"{variant['engine']}:{voice}",
                    "lang": "fr",
                    "texts": [ln["text"] for ln in lines],
                    "tones": [tone_for(variant, ln, bench["cast"]) for ln in lines],
                    "speed": bench["speed"],
                    "bench": f"voix-emotion/{vid}",
                },
            )
        )
    return out


def run_via_worker(
    settings: Any, bench: dict[str, Any], folder: Path, variants: list[tuple[str, dict[str, Any]]], groups: dict[str, list]
) -> None:
    """Un job voice_preview par variante et par personnage : le worker les prend l'un après l'autre sur sa voie GPU,
    avant les clips (priorité 5)."""
    from psycopg.types.json import Jsonb

    from worker.db import Db
    from worker.providers.tts import get_engine

    db = Db(settings.database_url, max_size=2)
    jobs = {}
    for vid, variant in variants:
        engine_dir = Path(get_engine(settings, variant["engine"]).engine_dir)
        for who, lines, payload in _payloads(bench, vid, variant, groups):
            r = db.fetch_one(
                "insert into jobs (type, priority, max_attempts, payload) values ('voice_preview', 5, 1, %s) returning id",
                (Jsonb(payload),),
            )
            assert r
            jobs[r["id"]] = {"vid": vid, "who": who, "lines": lines, "voice": payload["voice"], "engine_dir": engine_dir}
    print(f"{len(jobs)} essais en file (panneau Tâches : « Essai de voix ») ; le worker les prend entre deux clips.")
    current, vram, ram, last_note = None, None, None, 0.0
    while jobs:
        rows = {
            r["id"]: r
            for r in db.fetch_all(
                "select id, status::text as status, created_at, started_at, finished_at, result, error from jobs "
                "where id = any(%s)",
                (list(jobs),),
            )
        }
        for jid in list(jobs):
            r = rows[jid]
            if r["status"] not in ("done", "failed", "cancelled"):
                continue
            job = jobs.pop(jid)
            mine = current == jid
            if mine:
                bv._close(vram, ram)
            _record(bench, folder, job["vid"], job, r, vram if mine else None, ram if mine else None)
            if mine:
                current, vram, ram = None, None, None
            bv.save_bench(folder, bench)
        running = next((i for i in jobs if rows[i]["status"] == "running"), None)
        if running and current != running:
            bv._close(vram, ram)
            current = running
            vram = bv.VramWindow().__enter__()
            ram = bv.ProcessRam(exe_dir=jobs[running]["engine_dir"]).__enter__()
            print(f"→ {jobs[running]['voice']} ({len(jobs[running]['lines'])} répliques)", flush=True)
        if current is None and time.monotonic() - last_note > 60:
            last_note = time.monotonic()
            busy = db.fetch_one(
                "select type::text as type, progress_label from jobs where status = 'running' and locked_by like '%%/gpu' limit 1"
            )
            if busy:
                print(f"  en attente : le worker finit « {busy['type']} » ({busy['progress_label'] or '…'})", flush=True)
        time.sleep(0.3)
    db.pool.close()


def _record(bench: dict[str, Any], folder: Path, vid: str, job: dict[str, Any], row: dict[str, Any], vram: Any, ram: Any) -> None:
    res = row["result"] or {}
    wait_s = round((row["started_at"] - row["created_at"]).total_seconds(), 1) if row["started_at"] else None
    measures = {
        "voice": job["voice"],
        "job": str(row["id"]),
        "elapsed_s": res.get("elapsed_s"),
        "load_s": res.get("load_s"),
        "wait_s": wait_s,
        "vram_mb": vram.delta_mb if vram else None,
        "ram_mb": ram.peak_mb if ram else None,
        "error": (row["error"] or "")[-600:] if row["status"] != "done" else "",
    }
    _store(bench, folder, vid, job["who"], job["lines"], measures, res.get("paths") or [], res.get("times") or [])
    print(
        f"   {job['who']} : {measures['elapsed_s']} s (chargement {measures['load_s']} s, attente {wait_s} s, "
        f"VRAM +{measures['vram_mb']} Mo) {measures['error'][-300:]}",
        flush=True,
    )


def _store(
    bench: dict[str, Any],
    folder: Path,
    vid: str,
    who: str,
    lines: list[dict[str, Any]],
    measures: dict[str, Any],
    paths: list[str],
    times: list[float],
) -> None:
    import wave

    row = bench["variants"][vid]
    row.setdefault("jobs", {})[who] = measures
    per_line = row.setdefault("lines", {})
    for i, line in enumerate(lines):
        entry: dict[str, Any] = {"compute_s": times[i] if i < len(times) else None}
        if i < len(paths) and Path(paths[i]).exists():
            out = folder / vid / f"{line['index']:02d}.wav"
            shutil.copyfile(paths[i], out)
            with wave.open(str(out), "rb") as w:
                entry.update(file=f"{vid}/{out.name}", audio_s=round(w.getnframes() / w.getframerate(), 2))
        per_line[str(line["index"])] = entry


def run_direct(
    settings: Any, engine: Any, bench: dict[str, Any], folder: Path, vid: str, variant: dict[str, Any], groups: dict
) -> None:
    """Moteur en ligne ou sur le processeur : même appel que l'étape voix (un sous-processus par personnage)."""
    import soundfile as sf

    from worker.timeline import trim_silence

    tmp = folder / vid / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for who, lines, payload in _payloads(bench, vid, variant, groups):
        voice = payload["voice"].split(":", 1)[1]
        started = time.perf_counter()
        error, paths = "", []
        try:
            speeches = engine.speak_many(
                payload["texts"], voice=voice, lang="fr", speed=float(bench["speed"]), tones=payload["tones"]
            )
        except Exception as exc:  # noqa: BLE001 — l'échec est consigné dans le banc
            speeches, error = [], str(exc)[-600:]
        elapsed = round(time.perf_counter() - started, 1)
        for i, sp in enumerate(speeches):
            path = tmp / f"{lines[i]['index']:02d}.wav"
            sf.write(str(path), trim_silence(sp.samples, sp.rate), sp.rate, subtype="PCM_16")
            paths.append(str(path))
        result = getattr(engine, "last_result", {}) or {}
        measures = {
            "voice": payload["voice"],
            "elapsed_s": elapsed,
            "load_s": result.get("load_s"),
            "wait_s": 0.0,
            "vram_mb": None,
            "ram_mb": None,  # moteur en ligne : rien à mesurer sur la machine
            "error": error,
        }
        _store(bench, folder, vid, who, lines, measures, paths, result.get("times") or [])
        print(f"   {who} : {elapsed} s (chargement {measures['load_s']} s) {error[-300:]}", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------------------------------------------------
# 2. eval
# ---------------------------------------------------------------------------------------------------------------------


def cmd_eval(args: argparse.Namespace) -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    folder = Path(args.dir)
    bench = bv.load_bench(folder)
    lines = {str(ln["index"]): ln for ln in bench["lines"]}
    todo = [
        (vid, key, e)
        for vid, row in bench.get("variants", {}).items()
        for key, e in (row.get("lines") or {}).items()
        if e.get("file") and (args.force or "transcript" not in e)
    ]
    if todo:
        os.environ.setdefault("HF_HOME", r"C:\YouTube2\tts\hf-cache")
        from faster_whisper import WhisperModel

        while (ram := bv.ram_gb()) and (ram[1] < args.min_free_gb or ram[2] < 2 * args.min_free_gb):
            print(f"RAM libre {ram[1]:.1f} Go : trop juste pour Whisper, nouvel essai dans 60 s", flush=True)
            time.sleep(60)
        model = WhisperModel(args.whisper, device="cpu", compute_type="int8", cpu_threads=args.threads)
        for vid, key, e in todo:
            for attempt in range(20):  # un clip H3 peut reprendre la RAM en cours de route : on attend qu'elle revienne
                try:
                    segments, _ = model.transcribe(
                        str(folder / e["file"]), language="fr", beam_size=5, temperature=0.0, condition_on_previous_text=False
                    )
                    e["transcript"] = " ".join(s.text.strip() for s in segments).strip()
                    break
                except RuntimeError as exc:
                    print(f"  mémoire insuffisante ({exc}) : nouvel essai dans 30 s ({attempt + 1}/20)", flush=True)
                    time.sleep(30)
            print(f"{vid:<16} {key:>2} {e.get('transcript', '—')}", flush=True)
            bv.save_bench(folder, bench)
    for row in bench.get("variants", {}).values():
        for key, e in (row.get("lines") or {}).items():
            if not e.get("file"):
                continue
            path = folder / e["file"]
            ref = bv.normalize(lines[key]["text"])
            hyp = bv.normalize(e.get("transcript", ""), " ".join(ref))
            ops = bv.align(ref, hyp)
            e["errors"] = [[op, a, b] for op, a, b in ops if op != "="]
            e["wer"] = round(len(e["errors"]) / max(1, len(ref)), 4)
            e["words"] = len(ref)
            e["f0_median_hz"], e["f0_std_st"] = bv.pitch_stats(path)
            e["loudness_db"] = loudness_db(path)
    similarity(folder, bench)
    bv.save_bench(folder, bench)
    print("évaluation enregistrée")


def loudness_db(path: Path) -> float | None:
    """Intensité de la réplique : niveau RMS (dB) des trames parlées. Une réplique chuchotée doit sortir plus bas qu'une
    réplique criée, avant l'égalisation du montage."""
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
    hop = int(0.02 * sr)
    if len(x) < hop * 5:
        return None
    frames = x[: len(x) // hop * hop].reshape(-1, hop)
    rms = np.sqrt((frames**2).mean(axis=1) + 1e-12)
    voiced = rms[rms > 0.1 * rms.max()]
    return round(float(20 * np.log10(np.sqrt((voiced**2).mean()))), 1)


def similarity(folder: Path, bench: dict[str, Any]) -> None:
    """Timbre : empreinte de voix de chaque réplique (sherpa-onnx, modèle 3D-Speaker) ; ressemblance (cosinus) à la
    moyenne des répliques du même personnage dans la même variante (constance), et à la référence de la voix Qwen du
    personnage (même voix qu'aujourd'hui ?). Sans sherpa-onnx ni modèle : rien."""
    import wave

    model = Path(r"C:\YouTube2\tts\eval\models\speaker.onnx")  # wespeaker ResNet34 (VoxCeleb), releases de sherpa-onnx
    try:
        import numpy as np
        import sherpa_onnx
    except ImportError:
        print("sherpa-onnx absent : pas de mesure du timbre")
        return
    if not model.exists():
        print(f"{model} absent : pas de mesure du timbre")
        return
    config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(model), num_threads=4)
    extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)

    def embed(path: Path) -> Any:
        with wave.open(str(path), "rb") as w:
            sr, ch = w.getframerate(), w.getnchannels()
            x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        if ch > 1:
            x = x.reshape(-1, ch).mean(axis=1)
        stream = extractor.create_stream()
        stream.accept_waveform(sr, x)
        stream.input_finished()
        v = np.asarray(extractor.compute(stream), dtype=np.float64)
        return v / (np.linalg.norm(v) + 1e-9)

    refs: dict[str, Any] = {}
    for who, c in bench["cast"].items():
        ref = Path(r"C:\YouTube2\tts\qwen3\voices") / f"{(c['tts_voice'] or ':').split(':', 1)[1]}.wav"
        if ref.exists():
            refs[who] = embed(ref)
    whos = {str(ln["index"]): ln["who"] for ln in bench["lines"]}
    for row in bench.get("variants", {}).values():
        vecs: dict[str, Any] = {k: embed(folder / e["file"]) for k, e in (row.get("lines") or {}).items() if e.get("file")}
        for who in {whos[k] for k in vecs}:
            keys = [k for k in vecs if whos[k] == who]
            centroid = np.mean([vecs[k] for k in keys], axis=0)
            centroid /= np.linalg.norm(centroid) + 1e-9
            for k in keys:
                e = row["lines"][k]
                e["sim_self"] = round(float(vecs[k] @ centroid), 3) if len(keys) > 1 else None
                e["sim_ref"] = round(float(vecs[k] @ refs[who]), 3) if who in refs else None


JUDGE_PROMPT = """Tu es directeur de doublage pour des dessins animés français. Réplique du personnage {who} ({voice}) :
« {text} »
Intention de jeu écrite par le scénariste : « {tone} ».
Tu entends {n} prises de cette réplique, dans l'ordre : {labels}. Note chaque prise de 1 à 5 :
- emotion : l'intention est-elle clairement jouée (5 = on l'entend sans lire l'intention) ;
- naturel : une voix humaine crédible, sans artefact, sans mot avalé ni répété ;
- francais : prononciation française native, sans accent étranger ;
- personnage : la voix colle au personnage (âge, sexe, caractère).
Sois exigeant et compare les prises entre elles. Réponds uniquement en JSON :
{{"A": {{"emotion": 1-5, "naturel": 1-5, "francais": 1-5, "personnage": 1-5, "remarque": "une phrase"}}, ...}}"""


def cmd_judge(args: argparse.Namespace) -> None:
    """Écoute à l'aveugle par Gemini : pour chaque réplique, toutes les prises (une par variante) dans un ordre tiré au
    hasard, sous des lettres ; notes d'émotion, de naturel, d'accent et de personnage. Un repère, pas un verdict : les
    notes automatiques collent mal à l'oreille de francophones (banc chvalois) — l'écoute de Luca tranche."""
    import base64
    import random

    import httpx

    from worker.config import Settings, utf8_console
    from worker.db import Db
    from worker.settings_store import load_llm_config

    utf8_console()
    settings = Settings()
    db = Db(settings.database_url, max_size=1)
    keys = load_llm_config(settings, db, use_cache=False).keys_for("gemini")
    db.pool.close()
    folder = Path(args.dir)
    bench = bv.load_bench(folder)
    rng = random.Random(29)
    judged = bench.setdefault("judge", {"model": args.model, "lines": {}})
    for n, ln in enumerate(bench["lines"]):
        key = str(ln["index"])
        takes = [
            (vid, (row.get("lines") or {}).get(key, {}).get("file"))
            for vid, row in bench["variants"].items()
            if (row.get("lines") or {}).get(key, {}).get("file")
        ]
        if len(takes) < 2 or (key in judged["lines"] and not args.force):
            continue
        rng.shuffle(takes)
        letters = [chr(65 + i) for i in range(len(takes))]
        cast = bench["cast"][ln["who"]]
        parts: list[dict[str, Any]] = [
            {
                "text": JUDGE_PROMPT.format(
                    who=cast["name"],
                    voice=cast["voice"],
                    text=ln["text"],
                    tone=ln["tone"],
                    n=len(takes),
                    labels=", ".join(letters),
                )
            }
        ]
        for letter, (_, file) in zip(letters, takes, strict=True):
            data = base64.b64encode((folder / file).read_bytes()).decode()
            parts += [{"text": f"Prise {letter} :"}, {"inline_data": {"mime_type": "audio/wav", "data": data}}]
        body = {"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
        answer = None
        # modèles dans l'ordre (« high demand » = 503 : le suivant) ; toutes les clés pour chacun
        for model, api_key in ((m, k) for m in args.model.split(",") for k in keys):
            r = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model.strip()}:generateContent",
                headers={"x-goog-api-key": api_key},
                json=body,
                timeout=180,
            )
            if r.status_code == 200:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                answer = json.loads(text[text.find("{") : text.rfind("}") + 1])
                judged.setdefault("models", {})[key] = model.strip()
                break
            print(f"  {model} : {r.status_code} {r.text[:120]}", flush=True)
            time.sleep(3 if r.status_code == 503 else 10)
        if answer is None:
            print(f"réplique {key} : pas de réponse")
            continue
        judged["lines"][key] = {vid: answer.get(letter) for letter, (vid, _) in zip(letters, takes, strict=True)}
        bv.save_bench(folder, bench)
        scores = ", ".join(
            f"{vid} {(answer.get(letter) or {}).get('emotion')}" for letter, (vid, _) in zip(letters, takes, strict=True)
        )
        print(f"{n + 1}/{len(bench['lines'])} {ln['text'][:40]} : {scores}", flush=True)
        time.sleep(4)


# ---------------------------------------------------------------------------------------------------------------------
# 3. report
# ---------------------------------------------------------------------------------------------------------------------

WHISPER = ("whisper", "murmur", "barely audible", "quiet")
SHOUT = ("shout", "loud", "furious", "yell", "scream")


def derive(bench: dict[str, Any]) -> list[dict[str, Any]]:
    """Une ligne par variante : temps d'une vidéo (drame de 16 répliques, 4 voix), coût d'un récit de 75 s, mots mal
    compris, constance du timbre, jeu (écart d'intensité chuchoté / crié, variation de hauteur)."""
    import statistics as st

    lines = {str(ln["index"]): ln for ln in bench["lines"]}
    chars = sum(len(ln["text"]) for ln in bench["lines"])
    out = []
    for vid, row in bench.get("variants", {}).items():
        jobs = list((row.get("jobs") or {}).values())
        per = row.get("lines") or {}
        done = [e for e in per.values() if e.get("file")]
        d: dict[str, Any] = {"variant": vid, "label": row.get("label", vid), "gpu": row.get("gpu"), "lines_ok": len(done)}
        d["errors"] = [j["error"] for j in jobs if j.get("error")]
        if jobs and all(j.get("elapsed_s") is not None for j in jobs):
            d["short_s"] = round(sum(j["elapsed_s"] for j in jobs), 1)
            loads = [j["load_s"] for j in jobs if j.get("load_s") is not None]
            d["load_s"] = round(st.mean(loads), 1) if loads else None
            computes = [e["compute_s"] for e in per.values() if e.get("compute_s") is not None]
            d["compute_s"] = round(sum(computes), 1) if computes else None
            d["audio_s"] = round(sum(e.get("audio_s") or 0 for e in done), 1)
            if d.get("compute_s"):
                d["x_realtime"] = round(d["audio_s"] / d["compute_s"], 2)
                cps = chars / d["compute_s"]
                d["recit_s"] = round((d["load_s"] or 0) + RECIT_CHARS / cps, 0)
                # un seul chargement par vidéo au lieu d'un par personnage (amélioration possible de l'étape voix)
                d["short_once_s"] = round((d["load_s"] or 0) + d["compute_s"], 1)
            d["week_min"] = round(d["short_s"] * SHORTS_PER_WEEK / 60, 0)
            first = list((row.get("first_jobs") or {}).values())
            if first and all(j.get("elapsed_s") is not None for j in first):
                d["first_s"] = round(sum(j["elapsed_s"] for j in first), 1)
            vram = [j["vram_mb"] for j in jobs if j.get("vram_mb")]
            d["vram_mb"] = max(vram) if vram else None
            ram = [j["ram_mb"] for j in jobs if j.get("ram_mb")]
            d["ram_mb"] = max(ram) if ram else None
        scored = [e for e in done if e.get("wer") is not None]
        if scored:
            d["wer"] = round(sum(e["wer"] * e["words"] for e in scored) / max(1, sum(e["words"] for e in scored)), 4)
            d["bad_lines"] = sum(1 for e in scored if e["wer"] > 0.2)
            stds = [e["f0_std_st"] for e in scored if e.get("f0_std_st") is not None]
            d["f0_std_st"] = round(st.mean(stds), 1) if stds else None
            loud = {k: e["loudness_db"] for k, e in per.items() if e.get("loudness_db") is not None}
            quiet = [v for k, v in loud.items() if any(w in lines[k]["tone"].lower() for w in WHISPER)]
            shout = [v for k, v in loud.items() if any(w in lines[k]["tone"].lower() for w in SHOUT)]
            if quiet and shout:
                d["shout_gap_db"] = round(st.mean(shout) - st.mean(quiet), 1)
            if len(loud) > 3:
                vals = sorted(loud.values())
                d["loud_range_db"] = round(vals[int(0.9 * (len(vals) - 1))] - vals[int(0.1 * (len(vals) - 1))], 1)
            for key in ("sim_self", "sim_ref"):
                sims = [e[key] for e in scored if e.get(key) is not None]
                d[key] = round(st.mean(sims), 3) if sims else None
                d[f"{key}_min"] = round(min(sims), 3) if sims else None
        judged = (bench.get("judge") or {}).get("lines") or {}
        for crit in ("emotion", "naturel", "francais", "personnage"):
            notes = [
                float(v[vid][crit])
                for v in judged.values()
                if isinstance(v.get(vid), dict) and isinstance(v[vid].get(crit), int | float)
            ]
            d[f"j_{crit}"] = round(st.mean(notes), 2) if notes else None
        out.append(d)
    return out


COLUMNS = [  # (clé, titre, format)
    ("label", "Moteur", "{}"),
    ("where", "Calcul", "{}"),
    ("short_s", "Un drame : 16 répliques, 4 voix (s)", "{:.0f}"),
    ("first_s", "Première fois, banque des voix comprise (s)", "{:.0f}"),
    ("short_once_s", "Même drame, modèle chargé une fois (s)", "{:.0f}"),
    ("recit_s", "Un récit de 75 s, 1 voix (s, estimé)", "{:.0f}"),
    ("week_min", "Semaine, 21 drames (min)", "{:.0f}"),
    ("load_s", "Chargement (s)", "{:.0f}"),
    ("x_realtime", "× temps réel (calcul)", "{:.1f}"),
    ("vram_mb", "VRAM (Mo)", "{:.0f}"),
    ("j_emotion", "Émotion jouée (juge, /5)", "{:.1f}"),
    ("j_naturel", "Naturel (juge, /5)", "{:.1f}"),
    ("j_francais", "Français natif (juge, /5)", "{:.1f}"),
    ("j_personnage", "Colle au personnage (juge, /5)", "{:.1f}"),
    ("wer", "Mots mal compris", "{:.1%}"),
    ("bad_lines", "Répliques ratées (> 20 %)", "{:.0f}"),
    ("sim_self", "Timbre constant (moyenne)", "{:.2f}"),
    ("sim_self_min", "Timbre constant (pire réplique)", "{:.2f}"),
    ("sim_ref", "Même voix qu'aujourd'hui", "{:.2f}"),
    ("shout_gap_db", "Crié − chuchoté (dB)", "{:+.1f}"),
    ("loud_range_db", "Écart d'intensité (dB)", "{:.1f}"),
    ("f0_std_st", "Variation de hauteur (demi-tons)", "{:.1f}"),
]


def vram_from_log(folder: Path, bench: dict[str, Any]) -> None:
    """VRAM d'un essai d'après vram_log.csv (nvidia-smi -l 1 lancé à côté du banc) : pic pendant le job moins le plus bas
    niveau atteint pendant ce même job (ComfyUI vidé au départ). Complète les essais où le banc n'a rien relevé."""
    log = folder / "vram_log.csv"
    todo = [
        j
        for row in bench.get("variants", {}).values()
        for jobs in (row.get("jobs") or {}, row.get("first_jobs") or {})
        for j in jobs.values()
        if j.get("job") and not j.get("vram_mb")
    ]
    if not log.exists() or not todo:
        return
    import psycopg

    from worker.config import Settings

    samples = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = [p.strip() for p in line.split(",")]
        try:
            at = datetime.strptime(parts[0], "%Y/%m/%d %H:%M:%S.%f")
            samples.append((at, int(parts[1].split()[0])))
        except (ValueError, IndexError):
            continue
    with psycopg.connect(Settings().database_url) as conn:
        for j in todo:
            row = conn.execute("select started_at, finished_at from jobs where id = %s", (j["job"],)).fetchone()
            if not row or not row[0] or not row[1]:
                continue
            start, end = (t.astimezone().replace(tzinfo=None) for t in row)
            inside = [mb for at, mb in samples if start <= at <= end]
            if len(inside) > 2:
                j["vram_mb"] = max(inside) - min(inside)


def cmd_report(args: argparse.Namespace) -> None:
    import numpy as np
    import soundfile as sf

    folder = Path(args.dir)
    bench = bv.load_bench(folder)
    vram_from_log(folder, bench)
    bv.save_bench(folder, bench)
    rows = derive(bench)
    for d in rows:
        d["where"] = "carte graphique" if d.get("gpu") else "en ligne / processeur"
        # la scène entière : les répliques dans l'ordre, un temps entre deux (≈ le montage d'un drame)
        per = bench["variants"][d["variant"]].get("lines") or {}
        parts, rate = [], None
        for ln in bench["lines"]:
            e = per.get(str(ln["index"])) or {}
            if not e.get("file"):
                continue
            x, sr = sf.read(str(folder / e["file"]), dtype="float32", always_2d=False)
            if rate is None:
                rate = sr
            elif sr != rate:
                x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * rate / sr)), np.arange(len(x)), x).astype(np.float32)
            parts += [x, np.zeros(int(0.45 * rate), dtype=np.float32)]
        if parts and rate:
            sf.write(str(folder / f"scene_{d['variant']}.wav"), np.concatenate(parts[:-1]), rate, subtype="PCM_16")
            d["scene"] = f"scene_{d['variant']}.wav"
    with (folder / "results.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["variant", *[k for k, _, _ in COLUMNS]], extrasaction="ignore", delimiter=";")
        w.writeheader()
        w.writerows({k: str(v).replace(".", ",") if isinstance(v, float) else v for k, v in d.items()} for d in rows)
    m = bench.get("machine", {})
    md = [
        f"# Banc « émotion » des voix · {bench['title']}",
        "",
        f"{m.get('gpu', '?')} · {m.get('cpu', '?')} · RAM {m.get('ram', '?')}. {len(bench['lines'])} répliques, "
        f"{len(bench['cast'])} personnages, vitesse {str(bench.get('speed')).replace('.', ',')}. Un drame = somme des "
        "appels au moteur, un par personnage (chargement compris), comme l'étape voix d'une vraie vidéo.",
        "",
        "| " + " | ".join(t for _, t, _ in COLUMNS) + " |",
        "|" + "---|" * len(COLUMNS),
        *["| " + " | ".join(bv.fmt(d.get(k), s) for k, _, s in COLUMNS) + " |" for d in rows],
    ]
    errors = [f"- **{d['variant']}** : {e[-300:]}" for d in rows for e in d.get("errors") or []]
    if errors:
        md += ["", "## Échecs", "", *errors]
    (folder / "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (folder / "index.html").write_text(render_html(bench, rows, folder), encoding="utf-8")
    print(f"{folder / 'README.md'}\n{folder / 'index.html'}")


def render_html(bench: dict[str, Any], rows: list[dict[str, Any]], folder: Path) -> str:
    esc = html.escape
    m = bench.get("machine", {})
    head = "".join(f"<th>{esc(t)}</th>" for _, t, _ in COLUMNS)
    summary = "".join(
        "<tr>"
        + "".join(f"<td>{esc(bv.fmt(d.get(k), s))}</td>" for k, _, s in COLUMNS)
        + "</tr>"
        + (
            f'<tr class="sub"><td colspan="{len(COLUMNS)}">La scène entière : '
            f'<audio controls preload="none" src="{esc(d["scene"])}"></audio></td></tr>'
            if d.get("scene")
            else ""
        )
        for d in rows
    )
    variants = [d["variant"] for d in rows]
    labels = {d["variant"]: d["label"] for d in rows}
    grid_head = "".join(f"<th>{esc(labels[v])}</th>" for v in variants)
    body = []
    for ln in bench["lines"]:
        cells = []
        for v in variants:
            e = (bench["variants"][v].get("lines") or {}).get(str(ln["index"])) or {}
            if not e.get("file"):
                cells.append("<td>—</td>")
                continue
            notes = []
            j = ((bench.get("judge") or {}).get("lines") or {}).get(str(ln["index"]), {}).get(v)
            if isinstance(j, dict):
                notes.append(f"juge : émotion {j.get('emotion')}/5, naturel {j.get('naturel')}/5 — {j.get('remarque', '')}")
            if e.get("wer"):
                notes.append(f"{e['wer']:.0%} mal compris : « {e.get('transcript', '')} »")
            if e.get("sim_self") is not None:
                notes.append(f"timbre {e['sim_self']:.2f}")
            if e.get("loudness_db") is not None:
                notes.append(f"{e['loudness_db']:+.0f} dB")
            cells.append(
                f'<td><audio controls preload="none" src="{esc(e["file"])}"></audio>'
                f'<div class="n">{esc(" · ".join(notes))}</div></td>'
            )
        who = bench["cast"][ln["who"]]["name"]
        body.append(
            f"<tr><td><b>{ln['index'] + 1}. {esc(who)}</b><br>{esc(ln['text'])}<br><i>{esc(ln['tone'])}</i></td>"
            + "".join(cells)
            + "</tr>"
        )
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Banc émotion des voix</title>
<style>
:root {{ --bg:#fbfaf8; --fg:#1d1c1a; --mute:#6b6862; --line:#e4e1db; --head:#f1eee8; --accent:#9a3412; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161514; --fg:#ecebe8; --mute:#a19d96; --line:#2d2b28; --head:#201f1d; --accent:#fb923c; }} }}
body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--fg); font:14px/1.45 system-ui, sans-serif; }}
h1 {{ font-size:20px; margin:0 0 6px; }} h2 {{ font-size:16px; margin:28px 0 8px; }} p {{ color:var(--mute); max-width:1000px; }}
.wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:8px; }}
table {{ border-collapse:collapse; width:100%; }}
th, td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
th {{ background:var(--head); font-weight:600; }} tr.sub td {{ color:var(--mute); }}
td audio {{ display:block; width:250px; height:32px; }} i {{ color:var(--accent); font-style:normal; }}
.n {{ color:var(--mute); font-size:12px; max-width:250px; }}
</style></head><body>
<h1>Banc « émotion » des voix · {esc(bench["title"])}</h1>
<p>{esc(m.get("gpu", ""))} · {esc(m.get("cpu", ""))} · RAM {esc(m.get("ram", ""))}. Les {len(bench["lines"])} répliques
d'un vrai drame, avec le ton écrit par le scénariste (en orange). Chaque personnage garde sa voix ; le temps d'un drame
additionne un appel au moteur par personnage, chargement du modèle compris. Timbre constant : ressemblance (0 à 1) de
chaque réplique à la moyenne des répliques du même personnage. Crié − chuchoté : les répliques criées doivent sortir plus
fort que les chuchotées (en dB, avant l'égalisation du montage).</p>
<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{summary}</tbody></table></div>
<h2>Réplique par réplique</h2>
<div class="wrap"><table><thead><tr><th>Réplique</th>{grid_head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>
</body></html>
"""


# ---------------------------------------------------------------------------------------------------------------------
# 4. video : la vraie vidéo redite par chaque moteur
# ---------------------------------------------------------------------------------------------------------------------


def cmd_video(args: argparse.Namespace) -> None:
    """Les images de la vidéo finale de Madame Figue, ses sous-titres compris, avec les répliques de chaque variante
    posées où la bouche parle (timeline de la vidéo : speech_start de chaque plan) sur la musique de la vidéo. Le
    montage recalerait chaque réplique sur la bouche ; ici une réplique plus longue que l'originale décale la suivante."""
    import numpy as np
    import soundfile as sf

    from worker.config import Settings, utf8_console

    utf8_console()
    settings = Settings()
    folder = Path(args.dir)
    bench = bv.load_bench(folder)
    import psycopg

    with psycopg.connect(settings.database_url) as conn:
        timeline, music_file = conn.execute(
            "select v.timeline, m.file from videos v left join music_tracks m on m.id = v.music_track where v.id::text = %s",
            (bench["video"],),
        ).fetchone()
    music = settings.effective_music_library_dir / music_file if music_file else None
    import subprocess

    # les images une seule fois, en 720p sans le son (≈ 10 Mo au lieu de 70) : chaque version n'y ajoute que sa voix
    final = folder / "_images_720p.mp4"
    if not final.exists():
        source = settings.data_dir / "videos" / bench["video"] / "final.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(source), "-an", "-vf", "scale=720:-2"]
            + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", str(final)],
            check=True,
        )
    starts = {int(s["index"]): float(s.get("speech_start") or s["start"]) for s in timeline["scenes"]}
    duration = float(timeline["scenes"][-1]["start"] + timeline["scenes"][-1]["duration"])
    rate = 24000
    wanted = [v.strip() for v in args.variants.split(",")] if args.variants else list(bench["variants"])
    # Bibliothèque → Démos et essais : les « comparaison… » d'abord, la plus récente en tête → la n° 1 est faite en dernier
    for vid in sorted(wanted, key=lambda v: VIDEO_NAMES.get(v, f"9_{v}"), reverse=True):
        per = bench["variants"][vid].get("lines") or {}
        track = np.zeros(int((duration + 5) * rate), dtype=np.float32)
        cursor = 0.0
        for ln in bench["lines"]:
            e = per.get(str(ln["index"])) or {}
            if not e.get("file"):
                continue
            x, sr = sf.read(str(folder / e["file"]), dtype="float32", always_2d=False)
            if sr != rate:
                x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * rate / sr)), np.arange(len(x)), x).astype(np.float32)
            at = max(starts.get(ln["index"], cursor), cursor + 0.15)
            i = int(at * rate)
            track = np.concatenate([track, np.zeros(max(0, i + len(x) - len(track)), dtype=np.float32)])
            track[i : i + len(x)] += x
            cursor = at + len(x) / rate
        voice = folder / vid / "_voix.wav"
        sf.write(str(voice), track[: int(max(duration, cursor + 0.5) * rate)], rate, subtype="PCM_16")
        out = folder / f"comparaison_{VIDEO_NAMES.get(vid, f'9_{vid}')}.mp4"
        cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(final), "-i", str(voice)]
        # voix à -18 LUFS, musique 10 dB dessous (réglages de départ du montage, docs/26)
        voice_chain = "[1:a]loudnorm=I=-18:TP=-2:LRA=11,aresample=48000[v]"
        if music and Path(music).exists():
            cmd += ["-stream_loop", "-1", "-i", str(music)]
            mix = f"{voice_chain};[2:a]loudnorm=I=-28:TP=-2,aresample=48000[m];[v][m]amix=inputs=2:duration=first:normalize=0[a]"
        else:
            mix = voice_chain.replace("[v]", "[a]")
        cmd += ["-filter_complex", mix, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-t", f"{max(duration, cursor + 0.5):.2f}", str(out)]
        subprocess.run(cmd, check=True)
        print(out)
    final.unlink(missing_ok=True)  # images sans le son : ne doit pas apparaître dans la Bibliothèque
    labels = ", ".join(bench["variants"][v]["label"] for v in bench["variants"])
    (folder / "demo.json").write_text(
        json.dumps(
            {
                "title": f"Voix avec émotion : {bench['title']} redite par plusieurs moteurs",
                "description": f"Banc du {bench.get('started', '')[:10]} (docs/41) : {labels}. Même image, mêmes répliques, "
                "chaque réplique jouée selon le ton écrit par le scénariste. Écoute réplique par réplique : index.html.",
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="faire dire les répliques (Python du worker)")
    r.add_argument("--variants", default="qwen3,qwen3_instruct,gemini", help=f"parmi : {', '.join(VARIANTS)}")
    r.add_argument("--speed", type=float, help="vitesse de parole (défaut : celle de la chaîne)")
    r.add_argument("--out", default=r"C:\YouTube2\bench", help="dossier parent des bancs")
    r.add_argument("--dir", help="banc existant à compléter")
    r.set_defaults(fn=cmd_run)
    e = sub.add_parser("eval", help="Whisper, hauteur, intensité, timbre (environnement tts/eval)")
    e.add_argument("dir")
    e.add_argument("--whisper", default="large-v3-turbo")
    e.add_argument("--threads", type=int, default=4)
    e.add_argument("--min-free-gb", type=float, default=3.0)
    e.add_argument("--force", action="store_true")
    e.set_defaults(fn=cmd_eval)
    j = sub.add_parser("judge", help="écoute à l'aveugle par Gemini (émotion, naturel, accent, personnage)")
    j.add_argument("dir")
    j.add_argument("--model", default="gemini-3.8-flash,gemini-3.7-flash,gemini-3.5-flash", help="modèles dans l'ordre")
    j.add_argument("--force", action="store_true")
    j.set_defaults(fn=cmd_judge)
    p = sub.add_parser("report", help="README.md, index.html, results.csv, scène entière par variante")
    p.add_argument("dir")
    p.set_defaults(fn=cmd_report)
    v = sub.add_parser("video", help="la vidéo de Madame Figue redite par chaque variante (Démos et essais)")
    v.add_argument("dir")
    v.add_argument("--variants", help="variantes à monter (défaut : toutes)")
    v.set_defaults(fn=cmd_video)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
