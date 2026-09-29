"""Chaînes de modèles et clés multiples (Réglages → IA, docs/24 §3) : 1er choix, 2e choix… ; quota ou clé refusée →
clé suivante ; surcharge → modèle suivant. Aucun appel réseau : clients remplacés par des doublures."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pydantic import BaseModel

import worker.providers.llm as llm_mod
from worker.config import Settings
from worker.settings_store import ChainEntry, LlmConfig, key_slots, parse_chain, save_llm_settings, save_secret


class Out(BaseModel):
    ok: bool


def _http(status: int, text: str = "") -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://example.test")
    return httpx.HTTPStatusError(f"{status}", request=req, response=httpx.Response(status, text=text, request=req))


class Scripted:
    """Client qui renvoie, appel après appel, ce qu'on lui a préparé (exception ou réponse)."""

    def __init__(self, name: str, model: str, *outcomes: Any) -> None:
        self.name, self.model, self.outcomes, self.calls = name, model, list(outcomes), 0

    def complete_json(self, system: str, user: str, schema: type, images: Any = ()) -> Any:
        self.calls += 1
        out = self.outcomes.pop(0) if self.outcomes else Out(ok=True)
        if isinstance(out, Exception):
            raise out
        return out


@pytest.fixture(autouse=True)
def _fresh_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_mod, "_COOLING", {})
    monkeypatch.setattr(llm_mod, "SECOND_ROUND_WAIT_S", 0.0)


def test_failures_are_classified():
    assert llm_mod.failure_kind(_http(429, "GenerateRequestsPerDayPerProjectPerModel-FreeTier")) == ("quota", 3600.0)
    assert llm_mod.failure_kind(_http(429, "per minute"))[0:2] == ("quota", 60.0)
    assert llm_mod.failure_kind(_http(403))[0] == "key"
    assert llm_mod.failure_kind(_http(400, '{"error": {"status": "INVALID_ARGUMENT", "reason": "API_KEY_INVALID"}}'))[0] == "key"
    assert llm_mod.failure_kind(_http(404))[0] == "model"
    assert llm_mod.failure_kind(_http(503, "high demand"))[0] == "overload"
    assert llm_mod.failure_kind(httpx.ConnectTimeout("t"))[0] == "overload"
    assert llm_mod.failure_kind(ValueError("réponse sans JSON"))[0] == "other"


def test_quota_or_refused_key_moves_to_the_next_key_then_remembers():
    k1 = Scripted("gemini", "m", _http(429, "PerDay"))
    k2 = Scripted("gemini", "m")
    keyed = llm_mod.KeyedLLM("gemini", "m", [("fp1", k1), ("fp2", k2)])
    assert keyed.complete_json("s", "u", Out).ok and (k1.calls, k2.calls) == (1, 1)
    keyed.complete_json("s", "u", Out)  # la clé 1 a épuisé son quota du jour : la clé 2 passe d'abord
    assert (k1.calls, k2.calls) == (1, 2)
    busy = llm_mod.KeyedLLM("gemini", "m", [("a", Scripted("gemini", "m", _http(503))), ("b", Scripted("gemini", "m"))])
    with pytest.raises(httpx.HTTPStatusError):  # surcharge du modèle : une autre clé n'y change rien, la chaîne décide
        busy.complete_json("s", "u", Out)


def test_the_chain_goes_down_the_choices_and_retries_once_after_an_overload():
    first = Scripted("gemini", "gemini-3.8-flash", _http(503, "high demand"))
    second = Scripted("gemini", "gemini-3.5-flash-lite")
    chain = llm_mod.FallbackLLM([first, second])
    assert chain.complete_json("s", "u", Out).ok and (first.calls, second.calls) == (1, 1)
    assert chain.model == "gemini-3.8-flash" and chain.used == ["gemini:gemini-3.5-flash-lite"]  # qui a vraiment répondu
    # 3.8 est surchargé depuis peu : le 2e choix passe devant jusqu'à la fin de la pause
    chain.complete_json("s", "u", Out)
    assert (first.calls, second.calls) == (1, 2)
    # tout est surchargé au premier tour : second tour après la pause
    a = Scripted("gemini", "x", _http(503))
    b = Scripted("mistral", "y", _http(502))
    assert llm_mod.FallbackLLM([a, b]).complete_json("s", "u", Out).ok and (a.calls, b.calls) == (2, 1)
    dead = llm_mod.FallbackLLM([Scripted("gemini", "z", _http(403), _http(403))])
    with pytest.raises(RuntimeError, match="tous les modèles"):  # clé refusée : pas de second tour
        dead.complete_json("s", "u", Out)


def test_chains_come_from_settings_or_from_the_old_fields():
    assert parse_chain(
        [
            {"provider": "gemini", "model": " a "},
            {"provider": "x", "model": "b"},
            {"provider": "gemini", "model": "a"},
            {"provider": "mistral", "model": ""},
        ]
    ) == [ChainEntry("gemini", "a")]
    old = LlmConfig(
        provider="gemini", fallbacks=["mistral"], models={"gemini": "lite", "mistral": "small"}, writer_models={"gemini": "flash"}
    )
    assert old.chain("writer") == [ChainEntry("gemini", "flash"), ChainEntry("gemini", "lite"), ChainEntry("mistral", "small")]
    assert old.chain("default") == [ChainEntry("gemini", "lite"), ChainEntry("mistral", "small")]
    new = LlmConfig(provider="gemini", fallbacks=[], models={}, chains={"default": [ChainEntry("mistral", "small")]})
    assert new.chain("writer") == [ChainEntry("mistral", "small")]  # pas de chaîne d'écriture : celle des autres agents
    keys = LlmConfig(provider="gemini", fallbacks=[], models={}, api_keys={"gemini": "env"}, keys={"gemini": ["k1", "k2"]})
    assert keys.keys_for("gemini") == ["k1", "k2", "env"] and keys.key_for("gemini") == "k1"


def test_get_llm_builds_every_choice_with_all_its_keys(monkeypatch: pytest.MonkeyPatch):
    cfg = LlmConfig(
        provider="gemini",
        fallbacks=[],
        models={},
        keys={"gemini": ["k1", "k2"]},
        chains={
            "writer": [ChainEntry("gemini", "g-flash"), ChainEntry("gemini", "g-lite"), ChainEntry("anthropic", "c")],
            "default": [ChainEntry("gemini", "g-lite")],
        },
    )
    monkeypatch.setattr(llm_mod, "load_llm_config", lambda s, d: cfg)
    settings = Settings(database_url="postgresql://x", supabase_url="http://x", supabase_service_role_key="x")
    writer = llm_mod.get_llm(settings, None, writer=True)
    assert [p.model for p in writer.chain] == ["g-flash", "g-lite"]  # type: ignore[attr-defined]  (pas de clé Claude)
    assert all(isinstance(p, llm_mod.KeyedLLM) and len(p.clients) == 2 for p in writer.chain)  # type: ignore[attr-defined]
    vision = llm_mod.get_vision_llm(settings, None)
    assert vision is not None and [p.model for p in vision.chain] == ["g-lite"]  # type: ignore[attr-defined]


class SecretsDb:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.value: dict[str, Any] = {}

    def fetch_all(self, sql: str, params: Any = None) -> list[dict]:
        return [{"name": n, **r} for n, r in self.rows.items()]

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        return {"value": self.value} if self.value else None

    def execute(self, sql: str, params: Any = None) -> int:
        if sql.startswith("delete"):
            self.rows.pop(params[0], None)
        elif "app_secrets" in sql:
            self.rows[params[0]] = {"value_encrypted": params[1], "hint": params[2]}
        else:
            self.value = params[0].obj
        return 1


def test_keys_fill_the_next_free_slot_and_chains_are_saved(monkeypatch: pytest.MonkeyPatch):
    import worker.settings_store as store

    monkeypatch.setattr(store, "encrypt", lambda s, v: f"chiffré:{v}")
    db = SecretsDb()
    assert [save_secret(None, db, "gemini", v) for v in ("aaaa1111", "bbbb2222", "cccc3333")] == [1, 2, 3]  # type: ignore[arg-type]
    assert set(db.rows) == {"gemini_api_key", "gemini_api_key_2", "gemini_api_key_3"}
    store.delete_secret(db, "gemini", 2)
    assert save_secret(None, db, "gemini", "dddd4444") == 2  # type: ignore[arg-type]  # le trou est repris
    assert key_slots(db)["gemini"] == [(1, "1111"), (2, "4444"), (3, "3333")]
    v = save_llm_settings(
        db, chains={"writer": [{"provider": "gemini", "model": "g-flash"}, {"provider": "gemini", "model": "g-lite"}]}
    )
    assert v["chains"]["writer"][1] == {"provider": "gemini", "model": "g-lite"}
    assert "writer" not in save_llm_settings(db, chains={"writer": []})["chains"]
