"""Suivi des clés API (docs/49 §9, worker/keyusage.py) : lecture des refus de Google, alerte d'une clé qui tombe, relevé
à chaque appel de la rotation des clés (providers/llm.KeyedLLM)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from worker import keyusage
from worker.providers.llm import KeyedLLM

DAY = '{"error": {"message": "Rate limit exceeded for model gemini-3.8-flash-tts (limit: 10 requests per day on Free Tier)."}}'


def test_refusals_are_read():
    status, limit, until = keyusage.classify(429, DAY)
    assert (status, limit) == ("quota_day", 10) and until is not None and until.hour == 0
    assert keyusage.classify(429, "Resource exhausted, retry in 46s")[0] == "quota_minute"
    assert keyusage.classify(400, "API key not valid. Please pass a valid API key.")[0] == "invalid"
    assert keyusage.classify(503, "overloaded")[0] == "error"


def test_next_reset_is_midnight_in_los_angeles():
    now = datetime(2026, 10, 1, 23, 30, tzinfo=keyusage.PACIFIC)
    assert keyusage.next_reset(now) == datetime(2026, 10, 2, 0, 0, tzinfo=keyusage.PACIFIC)


def test_alert_names_the_next_key():
    title, body = keyusage.alert_text("gemini", "gemini-3.8-flash-tts", "voix", 2, 5, "quota_day", 10, keyusage.next_reset())
    assert title == "Clé voix n°2 sur 5 (gemini-3.8-flash-tts) : quota du jour épuisé"
    assert "la clé n°3" in body and "10 par jour" in body
    assert keyusage.alert_text("gemini", "m", "ia", 1, 1, "invalid", None, None)[0].endswith("refusée")


class FakeDb:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.alerts: list[str] = []
        self.before = "ok"

    def fetch_one(self, sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
        self.calls.append(params)
        before, self.before = self.before, params[7]
        return {"before": before}

    def alert(self, severity: str, title: str, body: str | None = None) -> None:
        self.alerts.append(title)


def test_a_key_that_falls_alerts_once():
    db = FakeDb()
    for _ in range(2):
        keyusage.record(
            db, provider="gemini", model="m", fingerprint="f", pool="voix", slot=1, slots=2, ok=False, status_code=429, text=DAY
        )
    assert len(db.alerts) == 1 and db.calls[0][7] == "quota_day" and db.calls[0][9] == 10


class Out(BaseModel):
    ok: bool


class Client:
    def __init__(self, fail: bool) -> None:
        self.fail = fail

    def complete_json(self, system: str, user: str, schema: type[Out]) -> Out:
        if self.fail:
            req = httpx.Request("POST", "https://x")
            raise httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, text=DAY, request=req))
        return Out(ok=True)


def test_rotation_records_each_key(monkeypatch: pytest.MonkeyPatch):
    seen: list[tuple[str, int, bool]] = []
    llm = KeyedLLM("gemini", "m", [("fp1", Client(True)), ("fp2", Client(False))])
    llm.recorder = lambda fp, slot, exc: seen.append((fp, slot, exc is None))
    assert llm.complete_json("s", "u", Out).ok
    assert seen == [("fp1", 1, False), ("fp2", 2, True)]
