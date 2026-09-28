"""Santé de la machine et relances (worker/system.py, docs/28) : bouton « Redémarrer le worker », relance de ComfyUI."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from worker import system

STARTED = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)


def test_restart_request_counts_only_if_pressed_after_the_worker_started():
    assert system.is_after("2026-09-28T14:05:00.000Z", STARTED)  # format de new Date().toISOString() (dashboard)
    assert system.is_after("2026-09-28T16:05:00+02:00", STARTED)
    assert not system.is_after("2026-09-28T13:59:00Z", STARTED)  # déjà servie par cette relance
    assert not system.is_after(None, STARTED)
    assert not system.is_after("hier", STARTED)


class FakeDb:
    def __init__(self, at: str | None) -> None:
        self.at = at

    def fetch_one(self, sql: str, params: tuple) -> dict | None:
        assert params == (system.RESTART_KEY,)
        return {"at": self.at} if self.at else None


def test_restart_requested_reads_the_dashboard_button():
    assert system.restart_requested(FakeDb("2026-09-28T14:01:00Z"), STARTED)
    assert not system.restart_requested(FakeDb(None), STARTED)


def test_comfy_launcher_only_for_a_local_comfyui(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bat = tmp_path / "comfyui.bat"
    bat.write_text("@echo off\r\n")
    monkeypatch.setenv("COMFY_LAUNCHER", str(bat))
    assert system.comfy_launcher("http://127.0.0.1:8188") == bat
    assert system.comfy_launcher("http://localhost:8188/") == bat
    assert system.comfy_launcher("http://192.168.1.20:8188") is None  # ComfyUI sur une autre machine : pas notre affaire
    monkeypatch.setenv("COMFY_LAUNCHER", str(tmp_path / "absent.bat"))
    assert system.comfy_launcher("http://127.0.0.1:8188") is None


def test_ensure_comfy_launches_nothing_when_comfyui_answers_or_has_no_launcher(monkeypatch: pytest.MonkeyPatch):
    launched: list = []
    monkeypatch.setattr(system.subprocess, "Popen", lambda *a, **k: launched.append(a))
    monkeypatch.setattr(system, "comfy_up", lambda base, timeout_s=3.0: True)
    assert system.ensure_comfy("http://127.0.0.1:8188")
    monkeypatch.setattr(system, "comfy_up", lambda base, timeout_s=3.0: False)
    assert not system.ensure_comfy("http://192.168.1.20:8188")  # pas local : on n'attend pas, on ne lance rien
    assert launched == []
