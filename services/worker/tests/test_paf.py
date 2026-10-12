"""« Paf, j'achète » : vendredi visé, fenêtre de préparation, choix de la vidéo et corps envoyé à Zernio (docs/50)."""

from __future__ import annotations

import os
import random
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock

from worker.paf import (
    PARIS,
    PafConfig,
    date_label,
    due,
    hour_label,
    late_limit,
    main_clash,
    moved,
    parse_config,
    pick_caption,
    pick_video,
    post_body,
    publish_time,
    render_caption,
    slot_of,
    upcoming_slot,
)


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


def test_main_clash_same_instagram_on_both_zernio_accounts():
    main = [
        {"platform": "tiktok", "username": "arzakparker", "platformUserId": "t1"},
        {"platform": "instagram", "username": "arzakparker", "platformUserId": "28831063366579885"},
    ]
    # Instagram ouvert sur @arzakparker au moment de brancher le second compte Zernio : même compte, autre _id
    assert main_clash({"_id": "b", "username": "arzakparker", "platformUserId": "28831063366579885"}, main) == "arzakparker"
    assert main_clash({"_id": "b", "username": "ArzakParker", "platformUserId": ""}, main) == "arzakparker"
    assert main_clash({"_id": "c", "username": "paf.jachete", "platformUserId": "999"}, main) is None
    assert main_clash({"_id": "c", "username": "paf.jachete", "platformUserId": "999"}, []) is None


def test_hour_setting():
    assert parse_config({}).hour == clock(7, 0)
    assert parse_config({"hour": "09:00"}).hour == clock(9, 0)
    assert parse_config({"hour": "9:30"}).hour == clock(9, 30)
    assert parse_config({"hour": "25:00"}).hour == clock(7, 0)  # illisible : 7 h
    assert hour_label(clock(9, 0)) == "9 h" and hour_label(clock(9, 5)) == "9 h 05"


def test_upcoming_slot_at_chosen_hour():
    slot = upcoming_slot(paris(2026, 10, 12, 12), clock(9, 0))  # lundi 12/10 → vendredi 16/10 à 9 h
    assert slot.date() == date(2026, 10, 16) and (slot.hour, slot.minute) == (9, 0)
    # 9 h : vendredi raté encore publié jusqu'à 21 h
    assert upcoming_slot(paris(2026, 10, 16, 20, 59), clock(9, 0)).date() == date(2026, 10, 16)
    assert upcoming_slot(paris(2026, 10, 16, 21, 1), clock(9, 0)).date() == date(2026, 10, 23)
    # 18 h : jamais après minuit, pas le samedi matin
    late = slot_of(date(2026, 10, 16), clock(18, 0))
    assert late_limit(late) == datetime(2026, 10, 17, 0, 0, tzinfo=PARIS)
    assert upcoming_slot(paris(2026, 10, 17, 0, 30), clock(18, 0)).date() == date(2026, 10, 23)


def test_due_uses_chosen_hour():
    cfg = PafConfig(enabled=True, account_id="acc", hour=clock(9, 0))
    assert due(cfg, paris(2026, 10, 14, 8, 30)) is None  # mercredi 8 h 30 : plus de 48 h avant 9 h
    assert due(cfg, paris(2026, 10, 14, 9, 30)) == slot_of(date(2026, 10, 16), clock(9, 0))


def test_date_label():
    assert date_label(date(2026, 10, 16)) == "vendredi 16 octobre"
    assert date_label(date(2027, 1, 1)) == "vendredi 1er janvier"


def test_render_caption_with_date():
    friday = date(2026, 10, 16)
    cap = "Bonjour, c'est vendredi. 🕺\n#actions #vendredi"
    assert render_caption(cap, friday) == cap
    assert render_caption(cap, friday, "start") == "Vendredi 16 octobre\n" + cap
    assert render_caption(cap, friday, "end") == "Bonjour, c'est vendredi. 🕺\nVendredi 16 octobre\n#actions #vendredi"
    assert render_caption("Sans hashtag", friday, "end") == "Sans hashtag\nVendredi 16 octobre"
    assert render_caption(cap, friday, "only") == "Vendredi 16 octobre"
    assert render_caption("", friday, "start") == "Vendredi 16 octobre"
    # {date} dans la légende : la date à cet endroit, pas en double
    assert render_caption("Bonjour, on est {date} !", friday, "start") == "Bonjour, on est vendredi 16 octobre !"
    assert render_caption("Bonjour, on est {date} !", friday) == "Bonjour, on est vendredi 16 octobre !"


def test_pick_caption_recognises_last_week_with_its_date():
    caps = ("A\n#x", "B\n#x")
    sent = render_caption("A\n#x", date(2026, 10, 9), "start")
    rng = random.Random(3)
    assert {pick_caption(caps, sent, rng, previous_friday=date(2026, 10, 9)) for _ in range(50)} == {"B\n#x"}


def test_moved_when_hour_changes_after_scheduling():
    friday = date(2026, 10, 16)
    old = slot_of(friday, clock(7, 0))
    wed = paris(2026, 10, 14, 10)
    cfg = PafConfig(enabled=True, account_id="acc", hour=clock(9, 0))
    assert moved(cfg, friday, old, wed) == slot_of(friday, clock(9, 0))
    assert moved(PafConfig(enabled=True, account_id="acc"), friday, old, wed) is None  # même heure
    assert moved(cfg, friday, old, old - timedelta(minutes=3)) is None  # sort dans 3 min : on n'y touche plus
    assert moved(cfg, friday, wed - timedelta(minutes=1), wed) is None  # publié tout de suite
    assert moved(PafConfig(enabled=False, account_id="acc", hour=clock(9, 0)), friday, old, wed) is None
