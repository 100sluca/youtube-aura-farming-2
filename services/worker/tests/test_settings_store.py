import base64
import os
from types import SimpleNamespace

from worker.settings_store import PRESET_MODELS, from_env, load_generation_config, load_llm_config, secret_hints
from worker.youtube.auth import decrypt, encrypt

SETTINGS = SimpleNamespace(
    credentials_key=base64.b64encode(os.urandom(32)).decode(),
    llm_provider="anthropic",
    llm_fallback_list=["mistral", "gemini", "ollama"],
    gemini_model="gemini-2.5-flash",
    anthropic_model="claude-sonnet-5",
    mistral_model="mistral-small-latest",
    ollama_model="qwen3-coder:latest",
    gemini_api_key=None,
    anthropic_api_key="sk-env",
    mistral_api_key=None,
)


class FakeDb:
    def __init__(self, llm_row, secrets):
        self.llm_row, self.secrets = llm_row, secrets

    def fetch_one(self, sql, params=None):
        return {"value": self.llm_row} if "app_settings" in sql and self.llm_row else None

    def fetch_all(self, sql, params=None):
        return self.secrets if "app_secrets" in sql else []


def test_encrypt_roundtrip_matches_dashboard_format():
    payload = encrypt(SETTINGS, "AIza-secret-key")
    raw = base64.b64decode(payload)
    assert len(raw) > 12 + 16 and decrypt(SETTINGS, payload) == "AIza-secret-key"
    assert encrypt(SETTINGS, "x") != encrypt(SETTINGS, "x")  # nonce aléatoire


def test_env_config_without_db():
    cfg = load_llm_config(SETTINGS, None)
    assert cfg.source == "env" and cfg.provider == "anthropic" and cfg.key_for("anthropic") == "sk-env"
    assert cfg.model_for("gemini") == "gemini-2.5-flash" and from_env(SETTINGS).fallbacks == ["mistral", "gemini", "ollama"]


def test_db_settings_and_secrets_override_env():
    db = FakeDb(
        {"provider": "gemini", "fallbacks": ["ollama", "bidon"], "models": {"gemini": "gemini-3.8-flash", "ollama": ""}},
        [{"name": "gemini_api_key", "value_encrypted": encrypt(SETTINGS, "AIza-db"), "hint": "a-db"}],
    )
    cfg = load_llm_config(SETTINGS, db, use_cache=False)
    assert cfg.source == "db" and cfg.provider == "gemini" and cfg.fallbacks == ["ollama"]
    assert cfg.key_for("gemini") == "AIza-db" and cfg.key_for("anthropic") == "sk-env"  # .env reste le repli
    assert cfg.model_for("gemini") == "gemini-3.8-flash" and cfg.model_for("ollama") == "qwen3-coder:latest"
    assert secret_hints(db) == {"gemini": "a-db"}
    assert PRESET_MODELS["gemini"][0] == "gemini-3.8-flash"


def test_generation_config_db_overrides_env():
    s = SimpleNamespace(comfy_image_workflow="qwen_image_21", video_provider="comfy_wan22_i2v_4step", storyboard_candidates=2,
                        kokoro_voice_fr="ff_siwis", kokoro_voice_en="af_heart")
    env = load_generation_config(s, None)
    assert env.source == "env" and env.image_workflow == "qwen_image_21" and env.video_provider == "comfy_wan22_i2v_4step"
    db = FakeDb({"image_workflow": "zimage_turbo", "video_workflow": "comfy_wan22_i2v_20step", "storyboard_candidates": 3,
                 "voices": {"en": "am_adam", "fr": ""}}, [])
    cfg = load_generation_config(s, db, use_cache=False)
    assert cfg.source == "db" and cfg.image_workflow == "zimage_turbo" and cfg.video_workflow == "wan22_i2v_20step"
    assert cfg.video_provider == "comfy_wan22_i2v_20step" and cfg.storyboard_candidates == 3
    assert cfg.voices == {"fr": "ff_siwis", "en": "am_adam"}  # une voix vide garde celle du .env
