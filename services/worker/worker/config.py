from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration lue depuis l'environnement / .env (voir .env.example à la racine)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    database_url: str  # chaîne « Session pooler » (IPv4) du projet Supabase
    supabase_url: str
    supabase_service_role_key: str

    # Worker
    worker_id: str = "desktop"
    worker_job_types: str = "script,generate_clip,tts,assemble,qa,upload,ideate,improve,sync_metrics,sync_retention,sync_comments"
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

    # Vidéo
    video_provider: str = "comfy_ltx"
    comfy_base_url: str = "http://127.0.0.1:8188"
    comfy_workflow_dir: Path = Path("./workflows")

    # TTS
    tts_provider: str = "kokoro"
    kokoro_voice_fr: str = "ff_siwis"
    kokoro_voice_en: str = "af_heart"

    # YouTube / Google
    google_client_id: str | None = None
    google_client_secret: str | None = None
    credentials_key: str | None = None  # base64, 32 octets (AES-GCM) — même clé que le dashboard

    # Alertes (échecs, quota, tampon faible) et demandes de validation humaine
    alert_email_to: str = "adresse@example.com"
    notify_on_review: bool = True  # mail dès qu'une vidéo attend une validation (auto_publish = false)
    resend_api_key: str | None = None
    smtp_host: str | None = None
    smtp_user: str | None = None
    smtp_pass: str | None = None

    @property
    def job_types(self) -> list[str]:
        return [t.strip() for t in self.worker_job_types.split(",") if t.strip()]

    @property
    def llm_fallback_list(self) -> list[str]:
        return [t.strip() for t in self.llm_fallbacks.split(",") if t.strip()]
