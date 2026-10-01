"""« Paf, j'achète » : vendredi visé, fenêtre de préparation, choix de la vidéo et corps envoyé à Zernio (docs/50)."""

from __future__ import annotations

import os
import random
import time
from datetime import UTC, date, datetime, timedelta

from worker.paf import PARIS, PafConfig, due, parse_config, pick_caption, pick_video, post_body, publish_time, upcoming_slot


def paris(*args: int) -> datetime:
    return datetime(*args, tzinfo=PARIS).astimezone(UTC)


def test_upcoming_slot_is_friday_7am_paris():
    # jeudi 01/10/2026 midi → vendredi 02/10 à 7 h, heure de Paris (5 h UTC en heure d'été)
    slot = upcoming_slot(paris(2026, 10, 1, 12))
    assert slot.date() == date(2026, 10, 2)
    assert slot.weekday() == 4 and (slot.hour, slot.minute) == (7, 0)
    assert slot.astimezone(UTC).hour == 5


def test_upcoming_slot_late_friday_then_next_week():
    assert upcoming_slot(paris(2026, 10, 2, 18)).date() == date(2026, 10, 2)  # vendredi raté : encore jusqu'à 19 h
    assert upcoming_slot(paris(2026, 10, 2, 20)).date() == date(2026, 10, 9)
    assert upcoming_slot(paris(2026, 10, 3, 9)).date() == date(2026, 10, 9)


def test_winter_time():
    slot = upcoming_slot(paris(2026, 12, 1, 12))
    assert slot.date() == date(2026, 12, 4) and slot.astimezone(UTC).hour == 6


def test_due_window_and_activation():
    cfg = PafConfig(enabled=True, account_id="acc", enabled_at=paris(2026, 9, 1, 0))
    assert due(cfg, paris(2026, 9, 29, 12)) is None  # mardi : plus de 48 h avant
    assert due(cfg, paris(2026, 9, 30, 8)).date() == date(2026, 10, 2)  # mercredi 8 h : moins de 48 h
    assert due(PafConfig(enabled=False, account_id="acc"), paris(2026, 10, 1, 12)) is None
    assert due(PafConfig(enabled=True), paris(2026, 10, 1, 12)) is None  # pas de compte choisi
    # activé le vendredi à 9 h : celui-ci est passé avant l'activation, on attend le suivant
    late = PafConfig(enabled=True, account_id="acc", enabled_at=paris(2026, 10, 2, 9))
    assert due(late, paris(2026, 10, 2, 9, 5)) is None


def test_publish_time():
    slot = paris(2026, 10, 2, 7)
    assert publish_time(slot, slot - timedelta(hours=20)) == slot
    assert publish_time(slot, slot + timedelta(hours=1)) is None  # passé : tout de suite


def test_pick_video_takes_latest_mp4(tmp_path):
    assert pick_video(tmp_path / "absent") is None
    assert pick_video(tmp_path) is None
    old, new = tmp_path / "ancienne.mp4", tmp_path / "vendredi.MP4"
    old.write_bytes(b"a")
    new.write_bytes(b"b")
    (tmp_path / "notes.txt").write_text("x")
    past = time.time() - 3600
    os.utime(old, (past, past))
    assert pick_video(tmp_path) == new


def test_post_body():
    cfg = parse_config({"enabled": True, "account_id": "acc", "share_to_feed": False})
    slot = paris(2026, 10, 2, 7)
    body = post_body(cfg=cfg, caption=" Bonjour, c'est vendredi. ", media_url="https://cdn/x.mp4", when=slot)
    assert body["content"] == "Bonjour, c'est vendredi."
    assert body["scheduledFor"] == slot.isoformat()
    assert body["platforms"] == [{"platform": "instagram", "accountId": "acc", "platformSpecificData": {"shareToFeed": False}}]
    assert post_body(cfg=cfg, caption="", media_url="u", when=None)["publishNow"] is True


def test_captions_parsing_and_old_single_caption():
    assert parse_config({"captions": [" A ", "", "B", 3]}).captions == ("A", "B")
    assert parse_config({"caption": "Bonjour"}).captions == ("Bonjour",)
    assert parse_config({}).captions == ()


def test_pick_caption_random_but_not_last_week():
    caps = ("A", "B", "C", "D", "E")
    rng = random.Random(1)
    drawn = {pick_caption(caps, "A", rng) for _ in range(200)}
    assert drawn == {"B", "C", "D", "E"}  # toutes sortent, jamais celle du vendredi d'avant
    assert pick_caption(("A",), "A") == "A"  # une seule : on la garde
    assert pick_caption((), None) == ""
