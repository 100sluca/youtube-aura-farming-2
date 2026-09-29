import sys
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

WORKER_ROOT = Path(__file__).resolve().parent.parent  # services/worker
REPO_ROOT = WORKER_ROOT.parent.parent


def utf8_console() -> None:
    """Sous Windows, une sortie redirigée (fichier, tube, fenêtre du lanceur) retombe en cp1252 : un titre
    avec émoji ou une flèche y ferait planter le print. On force l'UTF-8 dès le point d'entrée."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


class Settings(BaseSettings):
    """Configuration lue depuis l'environnement / .env (voir .env.example à la racine)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    database_url: str  # chaîne « Session pooler » (IPv4) du projet Supabase, ou postgresql://…@127.0.0.1:54322/postgres en local
    supabase_url: str
    supabase_service_role_key: str

    # Worker
    worker_id: str = "desktop"
    worker_job_types: str = (
        "script,storyboard,render,generate_clip,tts,seo,assemble,qa,upload,ideate,improve,strategy,"
        "sync_metrics,sync_retention,sync_comments,import_channel,voice_preview,montage_preview,analyze,tiktok_publish,"
        "sync_tiktok"
    )
    data_dir: Path = Path("./data")
    dry_run: bool = False
    poll_interval_s: float = 5.0
    io_concurrency: int = 3  # jobs réseau / LLM en parallèle ; la voie GPU est toujours à 1

    # LLM : principal + chaîne de secours (voir providers/llm.py)
    llm_provider: Literal["anthropic", "mistral", "gemini", "ollama"] = "anthropic"
    llm_fallbacks: str = "mistral,gemini,ollama"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    mistral_api_key: str | None = None
    mistral_model: str = "mistral-small-latest"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"

    # Vidéo : un workflow ComfyUI par fournisseur (services/worker/workflows/<nom>.json)
    # comfy_wan22_i2v_4step = image → vidéo Wan 2.2 en 4 passes (GGUF, 8 Go), cf. docs/11
    video_provider: str = "comfy_ltx"
    comfy_base_url: str = "http://127.0.0.1:8188"
    comfy_workflow_dir: Path = WORKER_ROOT / "workflows"
    comfy_timeout_s: int = 3600
    # Résolution des clips, ex. "704x1280" (multiples de 32 pour Wan 2.2 5B, de 16 pour le 14B). Vide = valeur
    # native du modèle (480×832). Le 5B est entraîné en 720p : 704×1280 est nettement plus net, ~2,5× plus long.
    video_size: str | None = None

    # Storyboard : une image par scène avant l'animation (route image → vidéo), validée à la main
    storyboard_enabled: bool = True
    storyboard_review: bool = True  # False = l'image retenue part directement en animation
    keyframe_qc: bool = True  # contrôle des images clés des formats visuels par un modèle de vision (worker/keyframe_qc.py)
    keyframe_qc_retries: int = 2  # une image refusée est refaite au plus N fois
    storyboard_autopass: bool = False  # True = le rendu part sans revue humaine quand toutes les images passent le contrôle
    clip_qc: bool = True  # contrôle des clips des formats visuels (personne, appareil de tournage ou objet inventés)
    clip_qc_retries: int = 1  # un clip refusé est refait au plus N fois (≈ 4 min 30 chacun sur la RTX 3070)
    # Drame en voix constantes : la voix de chaque personnage calée sur la bouche de son clip (worker/lipsync.py, docs/38)
    drama_lipsync: bool = True
    storyboard_candidates: int = 2  # images générées par scène
    comfy_image_workflow: str = "flux1_schnell_gguf"

    # Continuité entre clips (docs/12 §4) : "script" = l'agent script décide scène par scène
    # (continues_previous), "chain" = chaque clip part de la dernière image du précédent, "cut" = chaque
    # clip part de sa propre image de storyboard. Après continuity_max_chain clips enchaînés, on repart
    # d'une image de storyboard pour limiter la dérive (flou, couleurs) qui s'accumule d'un clip à l'autre.
    clip_continuity: Literal["script", "chain", "cut"] = "script"
    continuity_max_chain: int = 3

    # Formats visuels (docs/15, worker/recipes.py) : images clés retouchées en chaîne (chantier en accéléré)
    # par Qwen-Image-Edit-2511 ; si son modèle manque dans ComfyUI, repli sur Z-Image en image → image (le cadre
    # bouge un peu, la transformation est moins franche). Les clips « première + dernière image » prennent la variante
    # flf2v du modèle vidéo de la production (wan22_i2v_4step → wan22_flf2v_4step, 20step → 20step).
    # 4 passes (LoRA Lightning) par défaut : ≈ 1 min 30 par image et un cadre identique au pixel près ; en 40 passes,
    # 13 min par image avec la RAM saturée (mesures du 25/09, docs/15 §5) : à réserver à un PC déchargé.
    comfy_edit_workflow: str = "qwen_image_edit_2511_4step"
    comfy_edit_fallback: str = "zimage_img2img"

    # Gemini en ligne (docs/17-gemini-en-ligne.md) : le bouton Gemini de Création fait fabriquer les clips par l'appli
    # Gemini (abonnement Google AI de Luca) au lieu du modèle local ; le worker pilote un Chrome dédié (Playwright,
    # extra « web »). Compte, durée et modèle se règlent dans Réglages → Gemini en ligne (app_settings.gemini).
    gemini_chrome_path: Path | None = None  # défaut : Chrome installé (Program Files, LocalAppData)
    gemini_profile_dir: Path | None = None  # défaut : DATA_DIR/gemini-chrome (profil dédié, connecté à la main une fois)
    gemini_cdp_port: int = 9333  # port DevTools du Chrome dédié, sur 127.0.0.1 seulement
    gemini_authuser: int = 0  # numéro du compte Google dans ce profil (…/u/<n>/app)
    gemini_video_model: str | None = None  # libellé du modèle à choisir dans l'appli ; vide = celui proposé
    gemini_video_duration: str = "auto"  # auto = la plus courte des durées proposées (4, 6, 8, 10 s) qui couvre la scène
    gemini_poll_minutes: float = 3.0  # vidéo demandée : on revient voir toutes les N minutes (la voie GPU reste libre)
    gemini_quota_retry_minutes: int = 60  # limite atteinte sans heure de reprise lisible : nouvel essai après N minutes
    gemini_max_wait_hours: float = 6.0  # vidéo toujours pas là après N heures : la demande est abandonnée (job en échec)

    # Séries de contenu et production automatique (worker/series.py, scheduler.py)
    auto_produce: bool = True  # crée les productions des concepts approuvés, série par série selon les poids
    productions_per_day: int = 3
    max_productions_in_flight: int = 3
    ideas_per_series: int = 6  # sous ce nombre de concepts en attente, l'agent idée de la série est relancé
    wikipedia_user_agent: str | None = None  # défaut : yt2-worker/0.1 (+ALERT_EMAIL_TO), exigé par Wikimedia

    # Montage
    video_encoder: Literal["auto", "nvenc", "cpu"] = "auto"  # auto = NVENC si la carte le permet
    # Polices livrées ; celles ajoutées depuis l'onglet Montage vont dans DATA_DIR/fonts (worker/montage.py)
    fonts_dir: Path = WORKER_ROOT / "assets" / "fonts"
    # Musiques de fond (worker/music.py, docs/26-musique.md) : les pistes de Luca, dossier « music » du dépôt ; décrites,
    # choisies et réglées dans l'onglet Montage (table music_tracks). music_dir : ancienne bibliothèque générée
    # (DATA_DIR/music/<ambiance>/*.mp3), seulement à défaut de la première.
    music_library_dir: Path | None = None  # défaut : <dépôt>/music
    music_dir: Path | None = None  # défaut : DATA_DIR/music/<ambiance>/*.mp3
    sfx_dir: Path | None = None  # défaut : DATA_DIR/sfx/<étiquette>/*.wav|flac|mp3 (worker/sfx.py)
    # Titre d'accroche, sous-titres et textes à l'écran : modèle de l'onglet Montage (table montage_templates,
    # docs/23-montage.md). SUBTITLE_PROFILE ne sert plus qu'aux aperçus de la CLI (yt2 subtitles preview).
    subtitle_profile: str = "impact"

    # TTS (docs/18-voix.md) : la voix de chaque langue se choisit dans Réglages → Modèles de génération (« moteur:voix ») ;
    # KOKORO_VOICE_FR / _EN ne servent que de repli. Les moteurs autres que Kokoro vivent dans <yt2_home>/tts/<moteur>
    # (environnement Python et modèles, scripts/install_tts.ps1).
    tts_provider: str = "kokoro"
    yt2_home: Path = Path("C:/YouTube2")
    kokoro_voice_fr: str = "ff_siwis"
    kokoro_voice_en: str = "af_heart"
    kokoro_speed: float = 1.05  # défaut si channels.voice_speed est absent
    kokoro_model_path: Path = WORKER_ROOT / "models" / "kokoro-v1.0.onnx"
    kokoro_voices_path: Path = WORKER_ROOT / "models" / "voices-v1.0.bin"

    # Agents SEO et stratégie
    seo_enabled: bool = True
    strategy_window_days: int = 28
    strategy_min_videos: int = 6  # en dessous : rapport chiffré sans proposition (pas assez de données)

    # YouTube / Google
    google_client_id: str | None = None
    google_client_secret: str | None = None
    credentials_key: str | None = None  # base64, 32 octets (AES-GCM) — même clé que le dashboard

    # TikTok par Zernio (docs/36-publication-tiktok.md) : la clé se colle dans Réglages → TikTok (chiffrée en base) ;
    # celle-ci ne sert que de repli, pour la CLI ou une base neuve
    zernio_api_key: str | None = None

    # Mail « vidéo terminée » (worker/notify.py, docs/32) : Réglages → Notifications prime sur ces valeurs
    alert_email_to: str = ""  # adresse qui reçoit (ALERT_EMAIL_TO du .env ; jamais dans le dépôt, qui est public)
    notify_on_review: bool = True  # un mail dès qu'une vidéo est terminée (nom d'origine : les vidéos à valider)
    resend_api_key: str | None = None
    smtp_host: str | None = None  # défaut : smtp.gmail.com
    smtp_port: int = 465  # 465 = SSL, 587 = STARTTLS
    smtp_user: str | None = None  # compte qui envoie
    smtp_pass: str | None = None  # son mot de passe d'application
    dashboard_url: str = "http://localhost:3000"  # liens des mails

    @property
    def job_types(self) -> list[str]:
        return [t.strip() for t in self.worker_job_types.split(",") if t.strip()]

    @property
    def llm_fallback_list(self) -> list[str]:
        return [t.strip() for t in self.llm_fallbacks.split(",") if t.strip()]

    @property
    def effective_music_library_dir(self) -> Path:
        return self.music_library_dir or REPO_ROOT / "music"

    @property
    def effective_music_dir(self) -> Path:
        return self.music_dir or self.data_dir / "music"

    @property
    def effective_sfx_dir(self) -> Path:
        return self.sfx_dir or self.data_dir / "sfx"

    @property
    def effective_gemini_profile_dir(self) -> Path:
        return self.gemini_profile_dir or self.data_dir / "gemini-chrome"

    @property
    def effective_wikipedia_user_agent(self) -> str:
        contact = f"; {self.alert_email_to}" if self.alert_email_to else ""
        return self.wikipedia_user_agent or f"yt2-worker/0.1 (https://github.com/100sluca/youtube-aura-farming-2{contact})"
