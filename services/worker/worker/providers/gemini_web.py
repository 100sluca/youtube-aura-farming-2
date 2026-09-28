"""Clips fabriqués par l'appli Gemini (abonnement Google AI de Luca), en pilotant Chrome : pas d'API, pas de clé.

Voir docs/17-gemini-en-ligne.md. Le worker ne se connecte jamais à Google lui-même : Luca ouvre une fois le Chrome
dédié (Réglages → Gemini en ligne → « Ouvrir Gemini dans Chrome », ou `yt2 gemini open`) et s'y connecte à son
compte Google AI Pro. Ce Chrome est un Chrome ordinaire, avec son propre profil (DATA_DIR/gemini-chrome) et un port
DevTools local (127.0.0.1:9333) : Playwright s'y branche (connect_over_cdp), sans drapeau d'automatisation
(navigator.webdriver reste faux), et la fenêtre survit au worker.

Déroulé d'un clip (appli Gemini de septembre 2026 : « Créer une vidéo », modèle Gemini Omni, 4 à 10 s, son) :
1. nouvel onglet sur gemini.google.com/u/<compte>/app, mode vidéo (barre latérale « Créer une vidéo », sinon menu
   « + » ou « Outils » → vidéo) ;
2. « Ajouter une image » : l'image retenue de la scène (verticale → vidéo 9:16, aide Google), puis les réglages
   vidéo s'ils sont visibles (format Portrait, durée, modèle) ;
3. prompt en anglais (mouvement, style, contraintes), « Envoyer » ;
4. l'onglet reste ouvert, le job se remet en file (worker/postpone.py) et revient voir toutes les
   GEMINI_POLL_MINUTES : une vidéo prend d'une minute à plusieurs heures, la voie GPU reste libre pendant ce temps ;
5. vidéo prête (<video src="https://contribution.usercontent.google.com/download?…filename=video.mp4…">) :
   téléchargement avec les cookies du profil, repli sur « Partager » → « Télécharger la vidéo ».

Quota Google AI Pro (limites « au calcul » depuis mai 2026) : de l'ordre de 3 vidéos par tranche de 5 h. Le
message de limite remet le job en file jusqu'à l'heure lue dans le message (sinon GEMINI_QUOTA_RETRY_MINUTES) sans
consommer de tentative, et bloque les autres clips jusque-là (app_settings.gemini_status.quota_until).

L'interface n'est pas documentée pour les robots et change : chaque étape essaie plusieurs repères (libellés
français et anglais, rôles ARIA) et, en cas d'échec, enregistre une capture et la liste des boutons visibles dans
DATA_DIR/gemini-debug. `yt2 gemini check` fait le même parcours sans rien envoyer.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from ..config import Settings
from ..postpone import Postpone
from ..settings_store import load_gemini_config, load_gemini_status, save_gemini_status
from .video import STYLE_PRESETS, ClipInfo

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:  # extra « web » absent : browser_context() le signale avec la commande à lancer

    class PlaywrightError(Exception):  # type: ignore[no-redef]
        pass

    class PlaywrightTimeout(PlaywrightError):  # type: ignore[no-redef]
        pass


if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Locator, Page

GEMINI = "https://gemini.google.com"
DURATIONS = (4, 6, 8, 10)  # durées proposées par l'appli (secondes)
_LOCK = threading.Lock()  # un seul pilotage à la fois dans le processus du worker


class GeminiError(RuntimeError):
    pass


class GeminiNotSignedIn(GeminiError):
    pass


class GeminiUiError(GeminiError):
    """Un repère de l'interface introuvable : capture et liste des boutons dans DATA_DIR/gemini-debug."""

    def __init__(self, message: str, stage: str) -> None:
        super().__init__(message)
        self.stage = stage


# ---------------------------------------------------------------------------
# Repères de l'interface (français et anglais)
# ---------------------------------------------------------------------------


def _rx(*alternatives: str) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{a})" for a in alternatives), re.I)


SIGN_IN = _rx(r"^\s*(se connecter|connexion|sign in|log in)\s*$")
OPEN_SIDEBAR = _rx(r"menu principal", r"main menu", r"barre lat[ée]rale", r"sidebar", r"d[ée]velopper le menu", r"expand menu")
CREATE_VIDEO = _rx(r"^\s*cr[ée]er (une|des) vid[ée]os?\s*$", r"^\s*create (a )?videos?\s*$")
VIDEOS_ENTRY = _rx(r"^\s*vid[ée]os?\s*$")
# Menus du champ de saisie qui peuvent contenir l'entrée vidéo (relevé le 25/09/2026, déconnecté : bouton « + » nommé
# « Importation et outils » ; les versions précédentes avaient « Outils » et « Ouvrir le menu d'importation »)
COMPOSER_MENUS = _rx(r"^\s*\+\s*$", r"importation et outils", r"uploads? (and|&) tools", r"menu d.importation", r"upload file menu",
                     r"^\s*(ajouter|add)( des fichiers| files| du contenu| content)?\s*$", r"^\s*(outils|tools)\s*$")
VIDEO_TOOL = _rx(r"^(?!.*(ajouter|add|importer|upload|mes |my )).*\bvid[ée]os?\b")
# Page vidéo connectée (relevé le 25/09/2026, …/u/0/videos) : puce « Vidéos », « Importation de fichiers »,
# « Format, Portrait (9:16) », champ « Décrivez votre vidéo », « Envoyer un message » ; pas de réglage de durée visible
ADD_IMAGE = _rx(r"^\s*(ajouter|importer) (une |des )?(images?|photos?)\s*$", r"^\s*(add|upload) (an |a )?(images?|photos?)\s*$",
                r"^\s*importation de fichiers\s*$", r"^\s*upload files\s*$")
UPLOAD_MENU = _rx(r"importation et outils", r"uploads? (and|&) tools", r"menu d.importation", r"upload file menu",
                  r"^\s*(ajouter|add|importer|upload)( des fichiers| files| du contenu| content| un fichier| a file)?\s*$", r"^\s*\+\s*$")
# Sélecteur de modèle du champ de saisie (« Ouvrir le sélecteur de mode, actuellement 3.5 Flash-Lite »)
MODE_PICKER = _rx(r"s[ée]lecteur de mod", r"(mode|model) (selector|picker|switcher)")
# Bandeau cookies de Google (profil neuf) : on refuse le facultatif, le choix le plus protecteur
CONSENT_REJECT = _rx(r"^\s*tout refuser\s*$", r"^\s*reject all\s*$")
# Fenêtres qui s'intercalent (« Gemini est plus pertinent avec la localisation », nouveautés…, relevé le 26/09) : on
# prend toujours la réponse qui ne donne rien, jamais « Utiliser la position exacte », « Autoriser » ni « Accepter »
DISMISS = _rx(r"^\s*(fermer|close|non merci|no thanks|plus tard|later|pas maintenant|not now|ignorer|dismiss|j.ai compris|got it)\s*$")
DIALOGS = "[role='dialog'], [role='alertdialog'], mat-dialog-container"
VIDEO_CHIP = _rx(r"(close|fermer|d[ée]s[ée]lectionner|deselect|retirer|remove)[^\n]{0,30}vid[ée]os?")  # « close Vidéos »
FORMAT_BUTTON = _rx(r"^\s*format\s*,")  # « Format, Portrait (9:16) »
UPLOAD_ITEM = _rx(r"importer des fichiers", r"importer depuis", r"upload files?", r"upload from", r"depuis (l.|votre )ordinateur",
                  r"from (your |this )?(computer|device)", r"^\s*(photos?|images?|fichiers?|files?)\s*$")
SEND = _rx(r"^\s*(envoyer( un| le)?( message)?|send( message)?|submit|g[ée]n[ée]rer|generate|cr[ée]er|create)\s*$")
PORTRAIT = _rx(r"portrait", r"9\s*:\s*16", r"vertical")
ASPECT_CONTROL = _rx(r"paysage", r"landscape", r"16\s*:\s*9", r"portrait", r"9\s*:\s*16", r"format", r"aspect", r"rapport")
DURATION_TEXT = re.compile(r"^\s*(4|6|8|10)\s*(s|sec|secondes?|seconds?)\s*$", re.I)
MODEL_SWITCH = _rx(r"flash", r"\bpro\b", r"\blite\b", r"\blight\b", r"omni", r"\bveo\b", r"rapide", r"raisonnement", r"thinking")
DOWNLOAD = _rx(r"t[ée]l[ée]charger( la vid[ée]o)?", r"download( video)?")
SHARE = _rx(r"^\s*(partager|share)")

# Réponse de Gemini sans vidéo
QUOTA_RX = _rx(
    r"(utilis[ée]|used|consomm[ée])\s+(tout|all|l.int[ée]gralit[ée] de)\s+(votre|your|du)\s+quota", r"quota\s+(?:est\s+)?([ée]puis[ée]|exhausted|used up)",
    r"(atteint|reached|d[ée]pass[ée]|exceeded|hit)[^.!?\n]{0,80}(limite|limit|quota|plafond)",
    r"(limite|limit|quota|plafond)[^.!?\n]{0,60}(atteint|reached|d[ée]pass[ée]|exceeded)",
    r"(plus de|no more) (g[ée]n[ée]rations?|vid[ée]os?|videos?|generations?)",
    r"(r[ée]essayez|r[ée]essayer|try again)[^.!?\n]{0,30}(plus tard|later|dans \d|in \d|apr[èe]s|after|[àa] \d|at \d)",
)
REFUSED_RX = _rx(
    r"je ne (peux|suis) pas", r"pas en mesure", r"i can.?t (help|create|make|generate|do)", r"i.?m (not able|unable)", r"i cannot",
    r"(ne respecte|enfreint|contraire|violates?|against)[^.]{0,50}(r[èe]gles|consignes|politiques|conditions|policy|policies|guidelines)",
)
ERROR_RX = _rx(r"un probl[èe]me (est survenu|s.est produit)", r"une erreur (est survenue|s.est produite)", r"something went wrong",
               r"an error occurred", r"(impossible|unable) (de g[ée]n[ée]rer|to generate)")


def classify_response(text: str) -> str | None:
    """« quota », « refused », « error » ou None (rien de décisif : la vidéo est peut-être encore en cours)."""
    t = " ".join((text or "").split())
    if not t:
        return None
    if QUOTA_RX.search(t):
        return "quota"
    if REFUSED_RX.search(t):
        return "refused"
    if ERROR_RX.search(t):
        return "error"
    return None


_IN = re.compile(r"(?<!\w)(?:dans|in)\s+(\d{1,3})\s*(h\b|heures?|hours?|hrs?|min\b|minutes?|mins?)", re.I)
_AT = re.compile(r"(?<!\w)(?:[àa]|at|apr[èe]s|after|vers|around|from|d[èe]s)\s+(\d{1,2})\s*(?:h|:)\s*(\d{2})?\s*(am|pm|a\.m\.|p\.m\.)?",
                 re.I)


def parse_retry_at(text: str, now: datetime) -> datetime | None:
    """Heure de reprise lue dans le message de limite (« réessayez dans 4 heures », « after 11:40 PM »…)."""
    t = " ".join((text or "").split())
    m = _IN.search(t)
    if m:
        n = int(m.group(1))
        return now + (timedelta(hours=n) if m.group(2).lower().startswith("h") else timedelta(minutes=n))
    m = _AT.search(t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        ampm = (m.group(3) or "").lower().replace(".", "")
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        if hour < 24 and minute < 60:
            at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return at if at > now else at + timedelta(days=1)
    return None


# ---------------------------------------------------------------------------
# Prompt, durée, état d'une demande (fichier à côté du clip)
# ---------------------------------------------------------------------------


def pick_duration(scene_s: float, setting: str = "auto") -> int:
    """Durée demandée à Gemini : réglage fixe, ou la plus courte des durées proposées qui couvre la scène (le
    montage coupe le clip à la durée de la scène)."""
    if setting.isdigit() and int(setting) in DURATIONS:
        return int(setting)
    return next((d for d in DURATIONS if d + 0.05 >= scene_s), DURATIONS[-1])


def build_prompt(motion: str, style_preset: str | None, scene_s: float, target_s: int, *, with_image: bool, chat: bool = False,
                 end_frame: bool = False) -> str:
    """Prompt en anglais, en phrases (Gemini Omni comprend la langue naturelle mieux qu'une liste de mots-clés).
    end_frame : clip « première + dernière image » (chantier en accéléré, passage d'une visite) : deux images jointes,
    le clip entier est gardé et accéléré au montage."""
    motion = " ".join((motion or "").split()).rstrip(" .")
    parts = ["Create a video (not an image)."] if chat else []
    if end_frame:
        parts.append("Vertical 9:16 video that starts exactly on the first attached image and ends exactly on the second attached image: "
                     "same fixed camera position and framing from start to end, only what differs between the two images changes, "
                     "gradually.")
    else:
        parts.append(
            "Animate the attached image into a vertical 9:16 video: it is the first frame, keep its framing, subject, colors and style."
            if with_image else "Vertical 9:16 video."
        )
    if motion:
        parts.append(f"Action and camera: {motion}.")
    style = STYLE_PRESETS.get(style_preset or "")
    if style:
        parts.append(f"Look: {style}.")
    if not end_frame and target_s - scene_s >= 1:
        parts.append(f"The key motion happens in the first {max(1, round(scene_s))} seconds.")
    parts.append("No on-screen text, captions, logos or watermark. No music, no voice-over, no dialogue: natural ambient sound only. "
                 "Do not add people who are not in the images.")
    return " ".join(parts)


def state_path(out_path: Path) -> Path:
    """Demande en cours pour ce clip (conversation, onglet, heure) : permet au job suivant de reprendre."""
    return out_path.with_name(f"{out_path.stem}.gemini.json")


def read_state(out_path: Path) -> dict[str, Any]:
    try:
        return json.loads(state_path(out_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(out_path: Path, state: dict[str, Any]) -> None:
    p = state_path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_state(out_path: Path, keep: dict[str, Any] | None = None) -> None:
    if keep:
        write_state(out_path, keep)
    else:
        with suppress(OSError):
            state_path(out_path).unlink()


# ---------------------------------------------------------------------------
# Chrome dédié : lancement et connexion (mêmes options que le bouton du dashboard, apps/dashboard/src/lib/gemini.ts)
# ---------------------------------------------------------------------------


def chrome_executable(explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = [Path(explicit)] if explicit else []
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            candidates.append(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    return next((c for c in candidates if c.exists()), None)


def chrome_command(chrome: Path, profile: Path, port: int, url: str, *, minimized: bool) -> list[str]:
    return [
        str(chrome), f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
        # un onglet en arrière-plan doit continuer d'afficher la vidéo quand elle arrive
        "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
        *(["--start-minimized"] if minimized else []), url,
    ]


@dataclass
class Runtime:
    chrome: Path | None
    profile: Path
    port: int
    debug_dir: Path
    authuser: int
    model: str
    duration: str
    poll_s: float
    quota_retry_s: float
    max_wait_s: float

    @classmethod
    def load(cls, settings: Settings, db: Any | None) -> Runtime:
        cfg = load_gemini_config(settings, db)
        return cls(
            chrome=chrome_executable(settings.gemini_chrome_path),
            profile=settings.effective_gemini_profile_dir,
            port=settings.gemini_cdp_port,
            debug_dir=settings.data_dir / "gemini-debug",
            authuser=cfg.authuser,
            model=cfg.model,
            duration=cfg.duration,
            poll_s=max(30.0, settings.gemini_poll_minutes * 60),
            quota_retry_s=max(300.0, settings.gemini_quota_retry_minutes * 60),
            max_wait_s=max(600.0, settings.gemini_max_wait_hours * 3600),
        )

    @property
    def home(self) -> str:
        return f"{GEMINI}/u/{self.authuser}/app"


def devtools_up(port: int) -> bool:
    try:
        return httpx.get(f"http://127.0.0.1:{port}/json/version", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def ensure_browser(rt: Runtime, *, url: str = "about:blank", minimized: bool = True) -> bool:
    """Lance le Chrome dédié s'il ne tourne pas (True = lancé à l'instant)."""
    if devtools_up(rt.port):
        return False
    if rt.chrome is None:
        raise GeminiError("Chrome introuvable : installer Google Chrome ou renseigner GEMINI_CHROME_PATH")
    rt.profile.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":  # détaché : Chrome survit au worker
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(chrome_command(rt.chrome, rt.profile, rt.port, url, minimized=minimized), **kwargs)  # noqa: S603
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if devtools_up(rt.port):
            return True
        time.sleep(0.5)
    raise GeminiError(
        f"le Chrome dédié ne répond pas sur le port {rt.port} : si une fenêtre Chrome utilise déjà le profil {rt.profile} "
        "(ouverte autrement que par le dashboard), la fermer puis relancer"
    )


def open_tab(rt: Runtime, url: str) -> None:
    """Ouvre `url` dans le Chrome dédié (le lance au besoin, fenêtre normale : c'est Luca qui regarde)."""
    if ensure_browser(rt, url=url, minimized=False):
        return
    httpx.put(f"http://127.0.0.1:{rt.port}/json/new?{url}", timeout=10)


def _chrome_pids(profile: Path) -> list[int]:
    """Processus principal du Chrome dédié (Windows : ligne de commande avec ce profil et sans --type=)."""
    if os.name != "nt":
        return []
    query = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -like "
             f"'*--user-data-dir={profile}*' -and $_.CommandLine -notlike '*--type=*' }} | ForEach-Object {{ $_.ProcessId }}")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", query],  # noqa: S607
                             capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [int(x) for x in out.split() if x.isdigit()]


def reset_browser(rt: Runtime) -> bool:
    """Chrome dédié bloqué (constaté le 26/09 : un onglet Gemini figé, qui ne répond plus, empêche Playwright de se
    brancher) : on ferme ses onglets, qui le fait quitter, sinon on l'arrête. Rien n'est perdu : les demandes en cours
    se rouvrent par l'adresse de leur conversation (état à côté du clip). True si le port est libéré."""
    try:
        targets = httpx.get(f"http://127.0.0.1:{rt.port}/json/list", timeout=5).json()
    except (httpx.HTTPError, ValueError):
        targets = []
    for target in targets:
        if target.get("type") == "page":
            with suppress(httpx.HTTPError):
                httpx.get(f"http://127.0.0.1:{rt.port}/json/close/{target['id']}", timeout=5)
    for attempt in range(2):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and devtools_up(rt.port):
            time.sleep(0.5)
        if not devtools_up(rt.port) or attempt:
            break
        for pid in _chrome_pids(rt.profile):  # toujours là : on arrête ce Chrome-là (jamais le Chrome personnel de Luca)
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)  # noqa: S607
    return not devtools_up(rt.port)


@contextmanager
def browser_context(rt: Runtime, *, minimized: bool = True) -> Iterator[BrowserContext]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise GeminiError("Playwright manquant pour piloter Gemini : `uv sync --extra web` dans services/worker (docs/17)") from exc
    ensure_browser(rt, minimized=minimized)
    with sync_playwright() as pw:
        endpoint = f"http://127.0.0.1:{rt.port}"
        try:
            browser = pw.chromium.connect_over_cdp(endpoint, timeout=25_000)
        except PlaywrightError:
            # un onglet figé bloque le branchement : Chrome dédié remis à neuf, puis un seul nouvel essai
            reset_browser(rt)
            ensure_browser(rt, minimized=minimized)
            try:
                browser = pw.chromium.connect_over_cdp(endpoint, timeout=40_000)
            except PlaywrightError as exc:
                raise GeminiError(f"impossible de piloter le Chrome dédié, même relancé : {str(exc).splitlines()[0][:200]}") from exc
        try:
            yield browser.contexts[0] if browser.contexts else browser.new_context()
        finally:
            with suppress(Exception):
                browser.close()  # connexion CDP : ne fait que se débrancher, Chrome et ses onglets restent


# ---------------------------------------------------------------------------
# Interface de Gemini
# ---------------------------------------------------------------------------

_UI_MAP_JS = """() => {
  const out = [];
  const sel = 'button, a, [role=button], [role=menuitem], [role=menuitemradio], [role=option], [role=tab], [role=radio], ' +
              '[role=combobox], input, textarea, [contenteditable=true], video, img[src^="blob:"]';
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none') continue;
    out.push([el.tagName.toLowerCase(), el.getAttribute('role') || '', el.getAttribute('aria-label') || '',
              (el.innerText || el.value || '').trim().replace(/\\s+/g, ' ').slice(0, 80), el.getAttribute('data-test-id') || '',
              (el.getAttribute('placeholder') || el.getAttribute('data-placeholder') || ''), (el.currentSrc || el.src || '').slice(0, 100),
              Math.round(r.x) + ',' + Math.round(r.y)]);
  }
  return out.slice(0, 500);
}"""

_ATTACHMENTS_JS = """() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 8 && r.height > 8; };
  const imgs = [...document.querySelectorAll('img')].filter(i => vis(i) && /^(blob:|data:image)/.test(i.currentSrc || i.src || ''));
  const chips = [...document.querySelectorAll('[aria-label]')].filter(e => vis(e) &&
    /(supprimer|retirer|enlever|remove|delete).{0,25}(fichier|image|photo|file|pi[èe]ce|attachment)/i.test(e.getAttribute('aria-label')));
  const previews = [...document.querySelectorAll('uploader-file-preview, [data-test-id*="file-preview"], [class*="file-preview"]')].filter(vis);
  return imgs.length + chips.length + previews.length;
}"""

_RESULT_JS = """() => {
  const srcOf = v => v.currentSrc || v.src || ((v.querySelector('source') || {}).src) || '';
  const videos = [...document.querySelectorAll('video')].map(srcOf)
    .filter(s => /usercontent\\.google\\.com\\/download|[?&]filename=video/i.test(s));
  const resp = [...document.querySelectorAll('model-response, .model-response, message-content, [data-test-id="model-response"]')];
  const text = resp.length ? (resp[resp.length - 1].innerText || '') : '';
  const alerts = [...document.querySelectorAll('[role="alert"], mat-snack-bar-container, simple-snack-bar')].map(e => e.innerText || '').join(' \\n ');
  return {videos, text, alerts, url: location.href};
}"""

# Bandeau de quota au-dessus du champ de saisie (relevé le 26/09 : « Vous avez utilisé presque tout votre quota. Les
# vidéos peuvent l'é… » + « Vérifier l'utilisation ») : le plus court texte visible qui parle de quota ou de limite
_QUOTA_BANNER_JS = """() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 40 && r.height > 8; };
  const texts = [...document.querySelectorAll('div, span, p')].filter(e => vis(e) && e.children.length <= 4)
    .map(e => (e.innerText || '').trim().replace(/\\s+/g, ' '))
    .filter(t => t.length > 15 && t.length < 400 && /quota|limite (de|d'utilisation|atteinte)|usage limit|limit reached/i.test(t));
  texts.sort((a, b) => a.length - b.length);
  return texts[0] || '';
}"""

_PLACEHOLDER_JS = """() => {
  const e = document.querySelector("rich-textarea [contenteditable='true'], div.ql-editor, [contenteditable='true'], textarea");
  if (!e) return '';
  const host = e.closest('rich-textarea');
  return [e.getAttribute('aria-label'), e.getAttribute('data-placeholder'), e.getAttribute('placeholder'),
          host && host.getAttribute('data-placeholder'), e.dataset && e.dataset.placeholder].filter(Boolean).join(' | ');
}"""

_DROP_JS = """([b64, name, mime]) => {
  const bin = atob(b64); const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  const dt = new DataTransfer(); dt.items.add(new File([buf], name, {type: mime}));
  const target = document.querySelector('rich-textarea') || document.querySelector("[contenteditable='true']") || document.body;
  for (const type of ['dragenter', 'dragover', 'drop']) target.dispatchEvent(new DragEvent(type, {bubbles: true, cancelable: true, dataTransfer: dt}));
}"""


def _clickables(page: Page, rx: re.Pattern[str]) -> list[Locator]:
    roles = ("button", "link", "menuitem", "menuitemradio", "menuitemcheckbox", "option", "tab", "radio")
    return [page.get_by_role(r, name=rx) for r in roles] + [page.get_by_text(rx)]  # type: ignore[arg-type]


def _first_visible(page: Page, locators: list[Locator], timeout_s: float = 0.0) -> Locator | None:
    deadline = time.monotonic() + timeout_s
    while True:
        for loc in locators:
            try:
                for i in range(min(loc.count(), 12)):
                    el = loc.nth(i)
                    if el.is_visible():
                        return el
            except PlaywrightError:
                continue
        if time.monotonic() >= deadline:
            return None
        page.wait_for_timeout(300)


def _wait(page: Page, check: Callable[[], bool], timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while True:
        with suppress(PlaywrightError):
            if check():
                return True
        if time.monotonic() >= deadline:
            return False
        page.wait_for_timeout(400)


def _name(loc: Locator) -> str:
    with suppress(PlaywrightError):
        return " ".join(((loc.get_attribute("aria-label") or "") + " " + loc.inner_text(timeout=2000)).split())
    return ""


def _editor(page: Page, timeout_s: float = 0.0) -> Locator | None:
    return _first_visible(page, [
        page.locator("rich-textarea [contenteditable='true']"), page.locator("div.ql-editor[contenteditable='true']"),
        page.locator("[contenteditable='true'][role='textbox']"), page.locator("[contenteditable='true']"), page.locator("textarea"),
    ], timeout_s)


def _send_button(page: Page) -> Locator | None:
    return _first_visible(page, [page.get_by_role("button", name=SEND)])


def _try_click(loc: Locator | None, timeout_ms: int = 8000) -> bool:
    """Clic qui n'attend pas 30 s un élément recouvert (bandeau, fenêtre) : False, et on passe au repère suivant."""
    if loc is None:
        return False
    try:
        loc.click(timeout=timeout_ms)
        return True
    except PlaywrightError:
        return False


def quota_banner(page: Page) -> str:
    """Texte du bandeau de quota de Gemini s'il est affiché (« Vous avez utilisé presque tout votre quota… »), sinon ""."""
    try:
        return str(page.evaluate(_QUOTA_BANNER_JS) or "")
    except PlaywrightError:
        return ""


def signed_in(page: Page) -> bool | None:
    """False : page de connexion ou bouton « Se connecter » ; True : bouton du compte Google visible ; None : inconnu."""
    if "accounts.google.com" in page.url:
        return False
    if _first_visible(page, [page.get_by_role("button", name=SIGN_IN), page.get_by_role("link", name=SIGN_IN)]):
        return False
    account = page.locator("a[aria-label*='Google Account' i], a[aria-label*='Compte Google' i], [aria-label*='Google Account' i], "
                           "[aria-label*='Compte Google' i], a[href*='SignOutOptions']")
    return True if _first_visible(page, [account]) else None


def dismiss_consent(page: Page) -> bool:
    """Bandeau « Avant d'accéder à Google » (profil sans choix enregistré) : « Tout refuser »."""
    button = _first_visible(page, [page.get_by_role("button", name=CONSENT_REJECT)], 1)
    if not _try_click(button):
        return False
    page.wait_for_timeout(1500)
    return True


def dismiss_popups(page: Page) -> list[str]:
    """Ferme les fenêtres qui s'intercalent au-dessus de Gemini (réponse qui n'autorise ni n'accepte rien)."""
    closed: list[str] = []
    for _ in range(3):
        dialog = _first_visible(page, [page.locator(DIALOGS)])
        if not dialog:
            break
        button = _first_visible(page, [dialog.get_by_role("button", name=DISMISS)])
        name = _name(button) if button else ""
        if not _try_click(button, 5000):
            break
        closed.append(name or "fermer")
        page.wait_for_timeout(800)
    return closed


def open_home(page: Page, rt: Runtime) -> None:
    page.goto(rt.home, wait_until="domcontentloaded", timeout=60_000)
    _first_visible(page, [page.locator("rich-textarea"), page.locator("[contenteditable='true']"),
                          page.get_by_role("button", name=SIGN_IN), page.get_by_role("link", name=SIGN_IN)], 30)
    dismiss_consent(page)
    page.wait_for_timeout(1500)  # les fenêtres de bienvenue ou de localisation arrivent un peu après la page
    dismiss_popups(page)
    if signed_in(page) is False:
        raise GeminiNotSignedIn(
            "pas connecté à Google dans le Chrome dédié : Réglages → Gemini en ligne → « Ouvrir Gemini dans Chrome », "
            "se connecter au compte Google AI, puis relancer"
        )


def video_mode(page: Page) -> bool:
    """Le champ de saisie est-il en mode vidéo ? Repères relevés le 25/09 : puce « Vidéos » (bouton « close Vidéos »),
    placeholder « Décrivez votre vidéo », bouton « Format, Portrait (9:16) », « Importation de fichiers ». Boutons
    seulement : un texte de modèle de style (« Ajouter une photo »…) ne compte pas."""
    if _first_visible(page, [page.get_by_role("button", name=VIDEO_CHIP)]):
        return True
    with suppress(PlaywrightError):
        if re.search(r"vid[ée]o", page.evaluate(_PLACEHOLDER_JS) or "", re.I):
            return True
    return bool(_first_visible(page, [page.get_by_role("button", name=FORMAT_BUTTON), page.get_by_role("button", name=ADD_IMAGE),
                                      page.get_by_role("button", name=_rx(r"^\s*(ajouter|add) (une |a )?vid[ée]o\s*$"))]))


def enter_video_mode(page: Page) -> str:
    """Passe en création de vidéo ; renvoie la méthode, ou "" (la conversation normale reste possible)."""
    dismiss_popups(page)
    if video_mode(page):
        return "déjà en mode vidéo"
    # 1. barre latérale « Créer une vidéo » (aide Google de septembre 2026)
    item = _first_visible(page, _clickables(page, CREATE_VIDEO), 2)
    if not item:
        toggle = _first_visible(page, [page.get_by_role("button", name=OPEN_SIDEBAR)], 2)
        if _try_click(toggle):
            page.wait_for_timeout(800)
        item = _first_visible(page, _clickables(page, CREATE_VIDEO), 3) or _first_visible(page, _clickables(page, VIDEOS_ENTRY), 1)
    if _try_click(item):
        page.wait_for_timeout(1500)
        dismiss_popups(page)  # la page Vidéos peut ouvrir une fenêtre (localisation…) qui masque le champ de saisie
        if _wait(page, lambda: video_mode(page), 12):
            return "barre latérale"
    # 2. menu « Importation et outils » (« + ») du champ de saisie → « Vidéos » / « Créer une vidéo »
    dismiss_popups(page)
    opener = _first_visible(page, [page.get_by_role("button", name=COMPOSER_MENUS)], 1)
    if _try_click(opener):
        page.wait_for_timeout(700)
        entry = _first_visible(page, _clickables(page, CREATE_VIDEO) + [page.get_by_role(r, name=VIDEO_TOOL) for r in
                                                                         ("menuitem", "menuitemcheckbox", "menuitemradio", "option", "button")], 3)
        if _try_click(entry) and _wait(page, lambda: video_mode(page), 10):
            return "menu du champ de saisie"
        with suppress(PlaywrightError):
            page.keyboard.press("Escape")
    return ""


def _choose_file(page: Page, trigger: Locator, path: Path) -> bool:
    try:
        with page.expect_file_chooser(timeout=6000) as chooser:
            trigger.click()
        chooser.value.set_files(str(path))
        return True
    except PlaywrightTimeout:
        return False


def attach_image(page: Page, path: Path) -> str:
    dismiss_popups(page)
    before = int(page.evaluate(_ATTACHMENTS_JS) or 0)
    how = ""
    button = _first_visible(page, _clickables(page, ADD_IMAGE), 2)
    if button and _choose_file(page, button, path):
        how = "« Ajouter une image »"
    if not how:
        opener = _first_visible(page, [page.get_by_role("button", name=UPLOAD_MENU)], 1)
        if opener:
            if _choose_file(page, opener, path):
                how = "bouton d'import"
            else:
                entry = _first_visible(page, _clickables(page, UPLOAD_ITEM), 3)
                if entry and _choose_file(page, entry, path):
                    how = "menu d'import"
                else:
                    page.keyboard.press("Escape")
    if not how:
        inputs = page.locator("input[type='file']")
        if inputs.count():
            inputs.last.set_input_files(str(path))
            how = "champ fichier"
    if not how:
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        page.evaluate(_DROP_JS, [base64.b64encode(path.read_bytes()).decode(), path.name, mime])
        how = "glisser-déposer"
    if not _wait(page, lambda: int(page.evaluate(_ATTACHMENTS_JS) or 0) > before, 45):
        raise GeminiUiError(f"l'image de la scène n'apparaît pas dans le message (méthode essayée : {how})", stage="image")
    _wait(page, lambda: bool((b := _send_button(page)) and b.is_enabled()), 60)  # fin de l'envoi de l'image
    return how


def apply_options(page: Page, *, duration: int, model: str) -> list[str]:
    """Réglages vidéo visibles : format Portrait, durée, modèle. Au mieux : un réglage absent n'arrête rien."""
    notes: list[str] = []
    try:
        control = _first_visible(page, [page.get_by_role(r, name=ASPECT_CONTROL) for r in ("button", "combobox")], 1)
        if control and not PORTRAIT.search(_name(control)):
            control.click()
            page.wait_for_timeout(500)
            option = _first_visible(page, _clickables(page, PORTRAIT), 2)
            if option:
                option.click()
                notes.append("format Portrait choisi")
            else:
                page.keyboard.press("Escape")
        elif control:
            notes.append("format déjà Portrait")
        else:
            radio = _first_visible(page, [page.get_by_role("radio", name=PORTRAIT), page.get_by_role("tab", name=PORTRAIT)])
            if radio:
                radio.click()
                notes.append("format Portrait choisi")
    except PlaywrightError as exc:
        notes.append(f"format : {str(exc)[:80]}")
    try:
        current = _first_visible(page, [page.get_by_role(r, name=DURATION_TEXT) for r in ("button", "combobox")] + [page.get_by_text(DURATION_TEXT)], 1)
        if current:
            shown = DURATION_TEXT.match(_name(current) or "")
            if shown and int(shown.group(1)) == duration:
                notes.append(f"durée {duration} s")
            else:
                current.click()
                page.wait_for_timeout(500)
                want = re.compile(rf"^\s*{duration}\s*(s|sec|secondes?|seconds?)\s*$", re.I)
                option = _first_visible(page, _clickables(page, want), 2)
                if option:
                    option.click()
                    notes.append(f"durée {duration} s")
                else:
                    page.keyboard.press("Escape")
    except PlaywrightError as exc:
        notes.append(f"durée : {str(exc)[:80]}")
    if model:
        try:
            switch = _first_visible(page, [page.get_by_role("button", name=MODE_PICKER), page.get_by_role("button", name=MODEL_SWITCH)], 1)
            if switch and model.lower() not in _name(switch).lower():
                switch.click()
                page.wait_for_timeout(500)
                option = _first_visible(page, _clickables(page, re.compile(re.escape(model), re.I)), 2)
                if option:
                    option.click()
                    notes.append(f"modèle {model}")
                else:
                    page.keyboard.press("Escape")
                    notes.append(f"modèle « {model} » absent du menu")
        except PlaywrightError as exc:
            notes.append(f"modèle : {str(exc)[:80]}")
    return notes


def write_prompt(page: Page, text: str) -> None:
    editor = _editor(page, 15)
    if not editor:
        raise GeminiUiError("champ de saisie introuvable", stage="prompt")
    editor.click()
    probe = " ".join(text.split())[:40]

    def written() -> bool:
        return probe in " ".join(editor.inner_text(timeout=3000).split())

    with suppress(PlaywrightError):
        editor.fill(text)
    if not written():
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        page.keyboard.insert_text(text)
    if not written():
        raise GeminiUiError("le prompt ne s'écrit pas dans le champ de saisie", stage="prompt")


def send(page: Page) -> None:
    dismiss_popups(page)
    ready = _wait(page, lambda: bool((b := _send_button(page)) and b.is_enabled()), 20)
    button = _send_button(page) if ready else None
    if button:
        button.click()
    else:
        editor = _editor(page)
        if not editor:
            raise GeminiUiError("bouton « Envoyer » introuvable", stage="send")
        editor.press("Enter")


def wait_chat_url(page: Page, start_url: str, timeout_s: float = 30) -> str:
    """Adresse de la conversation créée par l'envoi (…/app/<id>) ; l'adresse de départ si elle ne change pas."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        url = page.url
        if url != start_url and re.search(r"/(app|video|videos|c)/[A-Za-z0-9_-]{6,}", url):
            return url
        page.wait_for_timeout(500)
    return page.url


@dataclass
class Result:
    videos: list[str]
    text: str
    alerts: str
    url: str

    @property
    def kind(self) -> str | None:
        return "ready" if self.videos else classify_response(f"{self.text}\n{self.alerts}")


def read_result(page: Page) -> Result:
    r = page.evaluate(_RESULT_JS) or {}
    return Result(videos=list(r.get("videos") or []), text=str(r.get("text") or ""), alerts=str(r.get("alerts") or ""), url=str(r.get("url") or ""))


def download(ctx: BrowserContext, page: Page, src: str, out: Path) -> str:
    """Télécharge la vidéo avec les cookies du profil ; repli sur le bouton de téléchargement de Gemini."""
    out.parent.mkdir(parents=True, exist_ok=True)
    body = b""
    with suppress(PlaywrightError):
        response = ctx.request.get(src, timeout=180_000)
        body = response.body() if response.ok else b""
    if len(body) > 50_000 and body[4:8] == b"ftyp":
        out.write_bytes(body)
        return "lien direct"
    with suppress(PlaywrightError):
        page.locator("video").last.hover()
    button = _first_visible(page, _clickables(page, DOWNLOAD), 2)
    if not button:
        share = _first_visible(page, _clickables(page, SHARE), 2)
        if share:
            share.click()
            page.wait_for_timeout(600)
            button = _first_visible(page, _clickables(page, DOWNLOAD), 3)
    if not button:
        raise GeminiUiError("vidéo prête mais aucun moyen de la télécharger", stage="download")
    with page.expect_download(timeout=180_000) as dl:
        button.click()
    dl.value.save_as(str(out))
    return "bouton « Télécharger »"


def probe(path: Path) -> tuple[float, int, int]:
    """Durée, largeur, hauteur du clip (ffprobe)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
        data = json.loads(out or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0, 0, 0
    stream = (data.get("streams") or [{}])[0]
    return float((data.get("format") or {}).get("duration") or 0), int(stream.get("width") or 0), int(stream.get("height") or 0)


def dump(page: Page, rt: Runtime, stage: str) -> str:
    """Capture d'écran + liste des éléments visibles (boutons, champs, vidéos) pour corriger un repère."""
    rt.debug_dir.mkdir(parents=True, exist_ok=True)
    stem = rt.debug_dir / f"{time.strftime('%Y%m%d-%H%M%S')}_{stage}"
    with suppress(Exception):
        page.screenshot(path=str(stem.with_suffix(".png")))
    with suppress(Exception):
        rows = page.evaluate(_UI_MAP_JS) or []
        lines = [f"url : {page.url}", f"titre : {page.title()}", f"bandeau de quota : {quota_banner(page) or '(aucun)'}",
                 "tag | rôle | aria-label | texte | data-test-id | placeholder | src | x,y", ""]
        lines += [" | ".join(str(c) for c in row) for row in rows]
        stem.with_suffix(".txt").write_text("\n".join(lines), encoding="utf-8")
    return str(stem)


def find_tab(ctx: BrowserContext, state: dict[str, Any]) -> Page | None:
    """L'onglet de la demande, resté ouvert depuis l'envoi (repère window.name, sinon adresse de la conversation)."""
    pages = [p for p in ctx.pages if "gemini.google.com" in p.url]
    for p in pages:
        if state.get("chat_url") and p.url == state["chat_url"]:
            return p
    for p in pages:
        with suppress(PlaywrightError):
            if state.get("marker") and p.evaluate("() => window.name") == state["marker"]:
                return p
    return None


# ---------------------------------------------------------------------------
# Fournisseur vidéo « gemini_web »
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now().astimezone()


class GeminiWebVideo:
    """Même contrat que ComfyVideo (providers/video.py), mais asynchrone : generate() envoie la demande puis lève
    Postpone ; les appels suivants (même out_path) reviennent chercher la vidéo."""

    name = "gemini_web"
    image_to_video = True
    first_last = True  # reçoit aussi l'image d'arrivée (au mieux : Gemini ne garantit pas de finir exactement dessus)
    fixed_length = True  # 4, 6, 8 ou 10 s : le montage coupe le clip à la durée de la scène (ou l'accélère, s'il vise une image)

    def __init__(self, settings: Settings, db: Any | None = None) -> None:
        self.settings = settings
        self.db = db
        self.rt = Runtime.load(settings, db)

    # -- quota -------------------------------------------------------------------------------------------------
    def quota_until(self) -> datetime | None:
        raw = load_gemini_status(self.db).get("quota_until") if self.db is not None else None
        with suppress(TypeError, ValueError):
            until = datetime.fromisoformat(str(raw))
            return until if until > _now() else None
        return None

    def _quota(self, text: str, out_path: Path) -> Postpone:
        now = _now()
        until = parse_retry_at(text, now) or now + timedelta(seconds=self.rt.quota_retry_s)
        hits = int(read_state(out_path).get("quota_hits") or 0) + 1
        if hits > 72:  # ≈ 3 jours d'essais : ce n'est plus un quota passager
            clear_state(out_path)
            raise GeminiError(f"Gemini refuse toujours (limite) après {hits - 1} essais : « {' '.join(text.split())[:200]} »")
        clear_state(out_path, keep={"quota_hits": hits})
        save_gemini_status(self.db, ok=False, quota_until=until.isoformat(timespec="minutes"),
                           message=f"Limite Gemini atteinte : « {' '.join(text.split())[:180]} »")
        return Postpone(f"Gemini : limite atteinte, nouvel essai vers {until:%H:%M}", (until - now).total_seconds() + 60,
                        label=f"Gemini · quota atteint, reprise vers {until:%H:%M}", error="Quota Gemini atteint")

    # -- contrat VideoProvider ---------------------------------------------------------------------------------
    def generate(self, *, prompt: str, style_preset: str | None, duration_s: float, out_path: Path, on_progress: Callable[[int], None],
                 dry_run: bool = False, image_path: Path | None = None, end_image_path: Path | None = None) -> ClipInfo:
        target = pick_duration(duration_s, self.rt.duration)
        if dry_run:
            out_path.write_bytes(b"")
            return ClipInfo(float(target), 720, 1280)
        state = read_state(out_path)
        if not state.get("chat_url"):
            until = self.quota_until()
            if until:  # limite connue : on n'ouvre même pas Gemini
                raise Postpone(f"Gemini : limite atteinte jusque vers {until:%H:%M}", (until - _now()).total_seconds() + 60,
                               label=f"Gemini · quota atteint, reprise vers {until:%H:%M}", error="Quota Gemini atteint")
        with _LOCK, browser_context(self.rt) as ctx:
            if state.get("chat_url"):
                try:
                    return self._follow(ctx, state, out_path, on_progress)
                except PlaywrightError as exc:  # page lente, onglet fermé pendant la lecture : on repassera
                    errors = int(state.get("errors") or 0) + 1
                    if errors >= 5:
                        raise GeminiError(f"lecture de la demande Gemini impossible ({errors} fois) : {str(exc)[:300]} ; "
                                          f"conversation : {state['chat_url']}") from exc
                    state["errors"] = errors
                    write_state(out_path, state)
                    raise Postpone(f"Gemini : lecture impossible ({str(exc)[:200]}), nouvel essai", self.rt.poll_s,
                                   label="Gemini · nouvel essai de lecture") from exc
            raise self._submit(ctx, prompt=prompt, style_preset=style_preset, scene_s=duration_s, target=target,
                               out_path=out_path, image_path=image_path, end_image_path=end_image_path, on_progress=on_progress)

    def _submit(self, ctx: BrowserContext, *, prompt: str, style_preset: str | None, scene_s: float, target: int, out_path: Path,
                image_path: Path | None, end_image_path: Path | None, on_progress: Callable[[int], None]) -> Postpone:
        page = ctx.new_page()
        page.on("filechooser", lambda _chooser: None)  # jamais de fenêtre système « Ouvrir » sur l'écran de Luca
        end_frame = image_path is not None and end_image_path is not None
        try:
            open_home(page, self.rt)
            banner = quota_banner(page)
            if banner and classify_response(banner) == "quota":  # limite annoncée avant même de demander
                with suppress(PlaywrightError):
                    page.close()
                return self._quota(banner, out_path)
            mode = enter_video_mode(page)
            if not mode:
                # Pas de mode vidéo : constaté le 26/09 après 8 vidéos d'affilée, Gemini passe tout seul sur « Flash-Lite »
                # (quota du modèle épuisé) et la page Vidéos n'offre plus que la conversation. On attend la fin de la
                # limite (heure lue dans le bandeau, sinon GEMINI_QUOTA_RETRY_MINUTES) au lieu d'échouer.
                picker = _first_visible(page, [page.get_by_role("button", name=MODE_PICKER)])
                model = ""
                with suppress(PlaywrightError):
                    model = (picker.get_attribute("aria-label") or "") if picker else ""
                reason = " ".join(filter(None, [quota_banner(page) or banner, f"mode vidéo indisponible ({model})" if model
                                                else "mode vidéo indisponible"]))
                if not int(read_state(out_path).get("quota_hits") or 0):  # une capture au premier constat, pas à chaque heure
                    dump(page, self.rt, "sans_mode_video")
                with suppress(PlaywrightError):
                    page.close()
                return self._quota(reason, out_path)
            # image de départ, puis (première + dernière image) celle d'arrivée : l'ordre compte pour le prompt
            how = ", ".join(attach_image(page, p) for p in (image_path, end_image_path if end_frame else None) if p) or "sans image"
            notes = apply_options(page, duration=target, model=self.rt.model) if mode else []
            text = build_prompt(prompt, style_preset, scene_s, target, with_image=image_path is not None, chat=not mode, end_frame=end_frame)
            start_url = page.url
            write_prompt(page, text)
            send(page)
            # la demande part : on note tout de suite de quoi la retrouver (un arrêt juste après ne la perd pas)
            marker = f"yt2-{uuid.uuid4().hex[:10]}"
            with suppress(PlaywrightError):
                page.evaluate("m => { window.name = m }", marker)
            state = {"chat_url": start_url, "marker": marker, "submitted_at": _now().isoformat(timespec="seconds"),
                     "mode": mode or "conversation", "image": how, "options": notes, "duration_s": target, "prompt": text,
                     "quota_hits": int(read_state(out_path).get("quota_hits") or 0)}
            write_state(out_path, state)
            chat_url = state["chat_url"] = wait_chat_url(page, start_url)
            write_state(out_path, state)
            on_progress(10)
            # un refus ou la limite s'affichent en quelques secondes
            deadline = time.monotonic() + 25
            result = read_result(page)
            while result.kind is None and time.monotonic() < deadline:
                page.wait_for_timeout(2500)
                result = read_result(page)
        except GeminiUiError as exc:
            debug = dump(page, self.rt, exc.stage)
            save_gemini_status(self.db, ok=False, message=f"{exc} (capture : {debug})")
            with suppress(PlaywrightError):
                page.close()
            raise GeminiUiError(f"{exc} — capture et liste des boutons : {debug}.png / .txt", exc.stage) from exc
        except GeminiError as exc:
            save_gemini_status(self.db, ok=False, message=str(exc))
            with suppress(PlaywrightError):
                page.close()
            raise
        except PlaywrightError as exc:  # page qui ne charge pas, élément qui disparaît pendant un clic…
            debug = dump(page, self.rt, "playwright")
            save_gemini_status(self.db, ok=False, message=f"Pilotage de Gemini interrompu : {str(exc)[:200]} (capture : {debug})")
            with suppress(PlaywrightError):
                page.close()
            raise GeminiError(f"pilotage de Gemini interrompu : {str(exc)[:300]} — capture : {debug}.png / .txt") from exc
        if result.kind == "quota":
            with suppress(PlaywrightError):
                page.close()
            return self._quota(f"{result.text}\n{result.alerts}", out_path)
        if result.kind in ("refused", "error"):
            clear_state(out_path)
            with suppress(PlaywrightError):
                page.close()
            message = " ".join(f"{result.text} {result.alerts}".split())[:300]
            save_gemini_status(self.db, ok=False, message=f"Gemini a répondu sans vidéo : « {message} »")
            raise GeminiError(f"Gemini a répondu sans vidéo : « {message} »")
        save_gemini_status(self.db, ok=True, quota_until=None, last_submit_at=state["submitted_at"],
                           message=f"Vidéo demandée ({state['mode']}, image : {how}{', ' + ', '.join(notes) if notes else ''})")
        at = _now()
        return Postpone(f"Gemini : vidéo demandée ({chat_url})", self.rt.poll_s, label=f"Gemini · vidéo demandée à {at:%H:%M}")

    def _follow(self, ctx: BrowserContext, state: dict[str, Any], out_path: Path, on_progress: Callable[[int], None]) -> ClipInfo:
        page = find_tab(ctx, state)
        polls = int(state.get("polls") or 0) + 1
        if page is None:
            if not re.search(r"/(app|video|videos|c)/[A-Za-z0-9_-]{6,}", state["chat_url"]):
                clear_state(out_path, keep={"quota_hits": state.get("quota_hits", 0)})  # onglet perdu, conversation introuvable
                raise Postpone("Gemini : onglet de la demande perdu (Chrome relancé ?), nouvelle demande", 30,
                               label="Gemini · nouvelle demande")
            page = ctx.new_page()
            page.on("filechooser", lambda _chooser: None)
            page.goto(state["chat_url"], wait_until="domcontentloaded", timeout=60_000)
            _wait(page, lambda: bool(read_result(page).videos) or bool(read_result(page).text), 20)
            dismiss_popups(page)
            with suppress(PlaywrightError):
                page.evaluate("m => { window.name = m }", state.get("marker") or "")
        elif polls % 4 == 0 and not read_result(page).videos:  # affichage figé : on recharge de temps en temps
            with suppress(PlaywrightError):
                page.reload(wait_until="domcontentloaded", timeout=60_000)
                _wait(page, lambda: bool(read_result(page).videos) or bool(read_result(page).text), 20)
        if signed_in(page) is False:
            raise GeminiNotSignedIn("session Google perdue dans le Chrome dédié : s'y reconnecter (Réglages → Gemini en ligne), puis relancer")
        result = read_result(page)
        if result.kind == "ready":
            try:
                how = download(ctx, page, result.videos[-1], out_path)
            except GeminiUiError as exc:
                debug = dump(page, self.rt, exc.stage)
                raise GeminiUiError(f"{exc} — capture : {debug}.png / .txt", exc.stage) from exc
            duration, width, height = probe(out_path)
            if duration <= 0 or not width:
                raise GeminiError(f"vidéo téléchargée illisible : {out_path}")
            clear_state(out_path)
            with suppress(PlaywrightError):
                page.close()
            save_gemini_status(self.db, ok=True, quota_until=None, last_clip_at=_now().isoformat(timespec="seconds"),
                               message=f"Clip récupéré ({how}, {width}×{height}, {duration:.1f} s)")
            on_progress(100)
            return ClipInfo(duration, width, height, None)
        if result.kind == "quota":
            with suppress(PlaywrightError):
                page.close()
            raise self._quota(f"{result.text}\n{result.alerts}", out_path)
        if result.kind in ("refused", "error"):
            clear_state(out_path)
            with suppress(PlaywrightError):
                page.close()
            message = " ".join(f"{result.text} {result.alerts}".split())[:300]
            save_gemini_status(self.db, ok=False, message=f"Gemini a répondu sans vidéo : « {message} »")
            raise GeminiError(f"Gemini a répondu sans vidéo : « {message} » ({state['chat_url']})")
        submitted = datetime.fromisoformat(state["submitted_at"])
        waited = (_now() - submitted).total_seconds()
        if waited > self.rt.max_wait_s:
            clear_state(out_path)
            with suppress(PlaywrightError):
                page.close()
            raise GeminiError(f"pas de vidéo après {waited / 3600:.1f} h ; la conversation reste dans Gemini : {state['chat_url']}")
        state["polls"] = polls
        write_state(out_path, state)
        on_progress(min(90, 10 + int(80 * waited / 600)))
        minutes = max(1, round(waited / 60))
        raise Postpone(f"Gemini : vidéo en cours depuis {minutes} min ({state['chat_url']})", self.rt.poll_s,
                       label=f"Gemini · en cours depuis {minutes} min")


# ---------------------------------------------------------------------------
# Outils pour `yt2 gemini` (worker/cli_gemini.py)
# ---------------------------------------------------------------------------


def check(settings: Settings, db: Any | None, images: list[Path] | None = None) -> dict[str, Any]:
    """Parcours complet jusqu'au bouton « Envoyer », sans rien envoyer : connexion, mode vidéo, image(s) (deux pour
    vérifier « première + dernière image »), réglages. Laisse une capture et la liste des boutons dans
    DATA_DIR/gemini-debug."""
    rt = Runtime.load(settings, db)
    report: dict[str, Any] = {"chrome": str(rt.chrome) if rt.chrome else None, "profil": str(rt.profile), "port": rt.port, "adresse": rt.home}
    with browser_context(rt, minimized=False) as ctx:
        page = ctx.new_page()
        page.on("filechooser", lambda _chooser: None)
        try:
            page.goto(rt.home, wait_until="domcontentloaded", timeout=60_000)
            _first_visible(page, [page.locator("rich-textarea"), page.locator("[contenteditable='true']"),
                                  page.get_by_role("button", name=SIGN_IN), page.get_by_role("link", name=SIGN_IN)], 30)
            report["bandeau cookies refusé"] = dismiss_consent(page)
            page.wait_for_timeout(1500)
            report["fenêtres fermées"] = dismiss_popups(page)
            report["connecté"] = signed_in(page)
            if report["connecté"] is not False:
                report["mode vidéo"] = enter_video_mode(page) or "introuvable (repli : conversation normale)"
                for n, image in enumerate(images or [], start=1):
                    try:
                        report[f"image {n}"] = attach_image(page, image)
                    except GeminiUiError as exc:
                        report[f"image {n}"] = f"échec : {exc}"
                report["pièces jointes vues"] = int(page.evaluate(_ATTACHMENTS_JS) or 0)
                report["réglages"] = apply_options(page, duration=pick_duration(4, rt.duration), model=rt.model)
                report["champ de saisie"] = bool(_editor(page, 5))
                report["bouton Envoyer"] = bool(_send_button(page))
        finally:
            report["capture"] = dump(page, rt, "check")
            with suppress(PlaywrightError):
                page.close()
    return report
