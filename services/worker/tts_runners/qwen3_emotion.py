"""Qwen3-TTS Base avec une voix de référence par émotion : le timbre de la voix dessinée, la manière de dire de la
référence (docs/41-voix-emotion.md).

Le modèle Base reprend l'élan de sa référence (mode ICL) : une réplique clonée depuis une référence en larmes sort en
larmes. Pour chaque voix dessinée, une banque de références (joie, tristesse, colère, peur, chuchoté, froid, moqueur,
tendre, surprise) est créée par VoiceDesign 1.7B la première fois qu'une réplique en a besoin : la description de la
voix + l'émotion, 3 essais, on garde celui dont le timbre ressemble le plus à la voix neutre (encodeur de locuteur du
modèle Base) et dont le débit reste plausible. Fichiers : voices/emotions/<voix>/<émotion>.wav (+ .json : texte dit,
ressemblance) ; les essais restent dans voices/emotions/<voix>/_essais pour en choisir un autre à l'oreille.

Le ton de la réplique (anglais, écrit par le scénariste) désigne l'émotion (_common.emotion_of). Option xvector :
« neutral » (défaut) garde l'empreinte de la voix neutre et prend à la référence émue seulement sa façon de dire ;
« emotion » clone la référence émue telle quelle.
Paramètres de voix : ceux des voix « qwen3:<nom> » (ref, ref_text, design.instruct, design.seed), par voices_from.
"""

from __future__ import annotations

import gc
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

import numpy as np
from _common import emotion_of, join_audio, plausible, progress, run, split_text, write_wav

LANGS = {"fr": "French", "en": "English"}
STATE: dict[str, Any] = {}

# émotion → (consigne ajoutée à la description de la voix, phrase dite par la référence)
EMOTIONS: dict[str, tuple[str, str]] = {
    "joie": (
        "overjoyed and excited, bright, almost laughing with happiness",
        "C'est incroyable ! On a réussi, tu te rends compte ? C'est le plus beau jour de ma vie !",
    ),
    "tristesse": (
        "deeply sad, crying softly, the voice breaking with tears",
        "Je n'y arrive plus… Tout ce que j'avais, je l'ai perdu. Pourquoi moi ?",
    ),
    "colere": (
        "furious, shouting with anger, loud and intense",
        "Ça suffit ! Tu m'as menti depuis le début ! Sors d'ici, tout de suite !",
    ),
    "peur": (
        "terrified, trembling voice, breathing fast, on the verge of panic",
        "Il y a quelqu'un dans la maison… Je t'en supplie, ne raccroche pas.",
    ),
    "chuchote": (
        "whispering very softly, secretive, barely audible",
        "Ne fais pas de bruit… S'ils nous entendent, tout est fini. Viens, suis-moi.",
    ),
    "froid": (
        "cold, icy and contemptuous, slow and threatening",
        "Tu crois vraiment que je vais te croire ? Regarde-moi bien. C'est terminé.",
    ),
    "moqueur": (
        "mocking and sarcastic, smug, a sly smile in the voice",
        "Oh, le pauvre petit… Tu pensais vraiment que ça allait marcher ? C'est adorable.",
    ),
    "tendre": (
        "tender and gentle, warm and moved, speaking with love",
        "Viens là, tout va bien maintenant. Tu as été si courageux… Je suis là.",
    ),
    "surprise": (
        "shocked and stunned, gasping in disbelief",
        "Quoi ? Ce n'est pas possible… Tu es sérieux ? Tout cet argent, ici ?",
    ),
}
TRIES = 3
CPS_RANGE = (6.0, 24.0)  # caractères par seconde plausibles (un essai raté saute ou répète des mots)
RETAKES = 3  # prises au plus pour une réplique au débit impossible


def identity(description: str) -> str:
    first = re.split(r"(?<=\.)\s+", description.strip(), maxsplit=1)[0]
    return first if first.endswith(".") else f"{first}."


def _bank_dir(engine_dir: Path, voice: str) -> Path:
    return engine_dir / "voices" / "emotions" / voice


def _free(torch: Any) -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _design_candidates(req: dict[str, Any], labels: list[str], torch: Any, model_cls: Any, device: str) -> None:
    """Essais VoiceDesign des émotions absentes de la banque (le modèle est déchargé ensuite)."""
    opts, params = req.get("options") or {}, req.get("voice_params") or {}
    design = params.get("design") or {}
    if not design.get("instruct"):
        raise ValueError(f"voix {req['voice']} : description absente du catalogue (params.design.instruct)")
    engine_dir = Path(req["engine_dir"])
    model = model_cls.from_pretrained(
        str(engine_dir / "models" / opts.get("design_model", "Qwen3-TTS-12Hz-1.7B-VoiceDesign")),
        device_map=device,
        dtype=torch.bfloat16 if device.startswith("cuda") else torch.float32,
        attn_implementation="sdpa",
    )
    trials = _bank_dir(engine_dir, req["voice"]) / "_essais"
    trials.mkdir(parents=True, exist_ok=True)
    base_seed = int(design.get("seed", 1234)) + 500
    for n, label in enumerate(labels):
        how, text = EMOTIONS[label]
        instruct = f"{identity(design['instruct'])} Emotion: {how}. Native French pronunciation."
        for k in range(TRIES):
            seed = base_seed + 10 * n + k
            torch.manual_seed(seed)
            started = time.perf_counter()
            wavs, rate = model.generate_voice_design(text=text, instruct=instruct, language=LANGS.get(req["lang"], "French"))
            write_wav(trials / f"{label}_{seed}.wav", np.asarray(wavs[0], dtype=np.float32), rate)
            print(f"banque {req['voice']} · {label} · graine {seed} : {time.perf_counter() - started:.0f} s", flush=True)
    del model
    _free(torch)


def _pick(req: dict[str, Any], labels: list[str], model: Any, neutral_xvec: Any, torch: Any) -> None:
    """Pour chaque émotion, l'essai au timbre le plus proche de la voix neutre (cosinus des empreintes du modèle Base),
    parmi ceux au débit plausible."""
    import soundfile as sf

    bank = _bank_dir(Path(req["engine_dir"]), req["voice"])
    for label in labels:
        _, text = EMOTIONS[label]
        scored = []
        for path in sorted((bank / "_essais").glob(f"{label}_*.wav")):
            audio, sr = sf.read(str(path), dtype="float32")
            cps = len(text) / max(len(audio) / sr, 0.1)
            [item] = model.create_voice_clone_prompt(ref_audio=(audio, sr), ref_text=text)
            sim = float(torch.nn.functional.cosine_similarity(item.ref_spk_embedding.float(), neutral_xvec.float(), dim=-1))
            plausible = CPS_RANGE[0] <= cps <= CPS_RANGE[1]
            scored.append((plausible, sim, path, cps))
        if not scored:
            raise RuntimeError(f"aucun essai pour {req['voice']} · {label}")
        plausible, sim, path, cps = max(scored, key=lambda s: (s[0], s[1]))
        shutil.copyfile(path, bank / f"{label}.wav")
        (bank / f"{label}.json").write_text(
            json.dumps({"ref_text": text, "similarity": round(sim, 3), "cps": round(cps, 1), "trial": path.name}),
            encoding="utf-8",
        )
        print(f"banque {req['voice']} · {label} : {path.name} (timbre {sim:.2f}, {cps:.0f} car./s)", flush=True)


def prepare(req: dict[str, Any]) -> None:
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    opts, params = req.get("options") or {}, req.get("voice_params") or {}
    engine_dir = Path(req["engine_dir"])
    device = opts.get("device") or ("cuda:0" if torch.cuda.is_available() else "cpu")
    if not params.get("ref") or not params.get("ref_text"):
        raise ValueError(f"voix {req['voice']} : référence absente du catalogue (params.ref, params.ref_text)")
    labels = sorted({emotion_of(t) for t in req.get("tones") or []} - {"neutre"})
    bank = _bank_dir(engine_dir, req["voice"])
    missing = [lb for lb in labels if not (bank / f"{lb}.wav").exists()]
    if missing:
        progress(0, len(req["texts"]))
        _design_candidates(req, missing, torch, Qwen3TTSModel, device)
    model = Qwen3TTSModel.from_pretrained(
        str(engine_dir / "models" / opts.get("model", "Qwen3-TTS-12Hz-0.6B-Base")),
        device_map=device,
        dtype=torch.bfloat16 if device.startswith("cuda") else torch.float32,
        attn_implementation="sdpa",
    )
    ref, ref_sr = sf.read(str(engine_dir / params["ref"]), dtype="float32")
    [neutral] = model.create_voice_clone_prompt(ref_audio=(ref, ref_sr), ref_text=params["ref_text"])
    if missing:
        _pick(req, missing, model, neutral.ref_spk_embedding, torch)
    prompts = {"neutre": [neutral]}
    for label in labels:
        audio, sr = sf.read(str(bank / f"{label}.wav"), dtype="float32")
        [item] = model.create_voice_clone_prompt(ref_audio=(audio, sr), ref_text=EMOTIONS[label][1])
        if opts.get("xvector", "neutral") == "neutral":
            item.ref_spk_embedding = neutral.ref_spk_embedding  # timbre de la voix, élan de la référence émue
        prompts[label] = [item]
    STATE.update(
        torch=torch,
        model=model,
        prompts=prompts,
        seed=int(opts.get("seed", params.get("seed", 1234))),
        max_chars=int(opts.get("max_chars", 140)),
        language=LANGS.get(req["lang"], "French"),
    )


def synthesize(req: dict[str, Any], text: str, tone: str) -> tuple[np.ndarray, int]:
    """Une prise par phrase ; une prise au débit impossible (mots ajoutés, phrase de la référence répétée) est refaite
    avec une autre graine, 3 fois au plus."""
    torch, model = STATE["torch"], STATE["model"]
    prompt = STATE["prompts"].get(emotion_of(tone), STATE["prompts"]["neutre"])
    chunks, rate = [], 24000
    for i, sentence in enumerate(split_text(text, STATE["max_chars"])):
        for attempt in range(RETAKES):
            torch.manual_seed(STATE["seed"] + i + 1000 * attempt)
            wavs, rate = model.generate_voice_clone(text=sentence, language=STATE["language"], voice_clone_prompt=prompt)
            audio = np.asarray(wavs[0], dtype=np.float32)
            if plausible(sentence, audio, rate):
                break
            print(f"prise refaite ({attempt + 1}) : débit impossible pour « {sentence[:40]} »", flush=True)
        chunks.append(audio)
    return join_audio(chunks, rate), rate


if __name__ == "__main__":
    run(synthesize, prepare=prepare)
