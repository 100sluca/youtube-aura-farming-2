"""Mail « vidéo terminée » (worker/notify.py, docs/32) : réglages en base par-dessus le .env, contenu du mail, boîte
d'envoi (alertes video_ready et test), pause après un refus. Base et serveur d'envoi remplacés par des doublures."""

from __future__ import annotations

import base64
import os
import smtplib
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from worker import notify
from worker.youtube.auth import encrypt

KEY = base64.b64encode(os.urandom(32)).decode()
MIRROR = "Le miroir qui ouvre sur un dressing secret"
GMAIL = {"email_to": "moi@gmail.com", "on_video_ready": True, "sender": ""}
APP_PASSWORD = "abcdefghijklmnop"


def env(**over: Any) -> SimpleNamespace:
    base = {
        "alert_email_to": "luca@example.com",
        "notify_on_review": True,
        "smtp_user": "",
        "smtp_pass": "",
        "smtp_host": "",
        "smtp_port": 465,
        "resend_api_key": None,
        "dashboard_url": "http://localhost:3000/",
        "credentials_key": KEY,
        "dry_run": False,
    }
    return SimpleNamespace(**{**base, **over})


class FakeDb:
    """app_settings.notifications, le mot de passe chiffré, la boîte d'envoi et la vidéo ; garde les écritures."""

    def __init__(
        self,
        notifications: dict | None = None,
        password: str | None = None,
        alerts: list[dict] | None = None,
        video: dict | None = None,
    ) -> None:
        self.notifications, self.password, self.video = notifications, password, video
        self.alerts = alerts or []
        self.executed: list[tuple[str, Any]] = []

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        if "from app_settings" in sql:
            return {"value": self.notifications} if self.notifications else None
        if "from app_secrets" in sql:
            return {"value_encrypted": encrypt(env(), self.password)} if self.password else None
        if "from videos v" in sql:
            return self.video
        return None

    def fetch_all(self, sql: str, params: Any = None) -> list[dict]:
        if "from alerts" not in sql:
            return []
        return sorted((a for a in self.alerts if a["kind"] in params[0]), key=lambda a: a["kind"] != "test")  # essais d'abord

    def execute(self, sql: str, params: Any = None) -> int:
        self.executed.append((" ".join(sql.split()), params))
        return 1

    def closed(self) -> list[Any]:
        return [p for s, p in self.executed if "acknowledged_at = now()" in s]

    def sent(self) -> list[Any]:
        return [p[0] for s, p in self.executed if s.startswith("update alerts set emailed_at = now()")]


class Outbox:
    """Remplace send_email : réponses prévues dans l'ordre (réussite ensuite), objets des mails gardés."""

    def __init__(self, *answers: tuple[bool, str]) -> None:
        self.answers, self.subjects = list(answers), []

    def __call__(self, cfg: notify.NotifyConfig, mail: notify.Mail) -> tuple[bool, str]:
        self.subjects.append(mail.subject)
        return self.answers.pop(0) if self.answers else (True, "envoyé")


def alert(kind: str, video_id: Any = None) -> dict:
    return {"id": uuid.uuid4(), "kind": kind, "title": "…", "video_id": video_id}


def video(vid: Any, poster: str | None = None, status: str = "review") -> dict:
    return {
        "id": vid,
        "title": MIRROR,
        "status": status,
        "duration_s": 31.6,
        "channel_name": "Chaîne de test",
        "series_name": "Maisons de rêve",
        "poster": poster,
    }


@pytest.fixture(autouse=True)
def fresh_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notify, "_pause", notify._Pause())


# ---- Réglages -------------------------------------------------------------------------------------------------------


def test_env_is_the_fallback_and_the_db_settings_win():
    cfg = notify.load_notify_config(env(smtp_user="bot@gmail.com", smtp_pass="abcd efgh ijkl mnop"), None)
    assert (cfg.email_to, cfg.sender, cfg.password) == (
        "luca@example.com",
        "bot@gmail.com",
        APP_PASSWORD,
    )  # espaces de Google ôtés
    assert (cfg.host, cfg.port, cfg.dashboard_url, cfg.on_video_ready, cfg.source) == (
        "smtp.gmail.com",
        465,
        "http://localhost:3000",
        True,
        "env",
    )
    assert not notify.load_notify_config(env(), None).can_send  # ni mot de passe ni Resend
    db = FakeDb({"email_to": "moi@gmail.com", "on_video_ready": False, "sender": ""}, password=APP_PASSWORD)
    cfg = notify.load_notify_config(env(), db)
    assert cfg.source == "db" and cfg.email_to == "moi@gmail.com" and not cfg.on_video_ready
    assert cfg.sender == "moi@gmail.com" and cfg.password == APP_PASSWORD and cfg.can_send  # vide = l'adresse qui reçoit


# ---- Le mail --------------------------------------------------------------------------------------------------------


def test_the_video_mail_gives_title_image_next_step_and_link(tmp_path):
    poster = tmp_path / "poster.jpg"
    poster.write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 64)
    vid = uuid.uuid4()
    cfg = notify.load_notify_config(env(), None)
    mail = notify.compose(FakeDb(video=video(vid, str(poster))), cfg, alert("video_ready", vid))
    link = f"http://localhost:3000/library?video={vid}"
    assert mail and mail.subject == f"🎬 Vidéo terminée : {MIRROR}"
    assert link in mail.text and "Autoriser la publication" in mail.text
    assert "(32 s · Chaîne de test · Maisons de rêve)" in mail.text
    msg = notify.build_message(cfg, mail)
    assert msg["To"] == "luca@example.com" and msg["Subject"] == mail.subject and msg["Date"]
    body = msg.get_body(("html",))
    images = [p for p in msg.walk() if p.get_content_maintype() == "image"]
    assert body is not None and len(images) == 1 and images[0].get_payload(decode=True).startswith(b"\xff\xd8")
    html = body.get_content()
    assert link in html and "cid:poster" not in html and f"cid:{images[0]['Content-ID'][1:-1]}" in html


def test_an_auto_published_video_leaves_on_its_own_and_a_missing_image_is_skipped():
    vid = uuid.uuid4()
    cfg = notify.load_notify_config(env(), None)
    mail = notify.compose(FakeDb(video=video(vid, "C:/nulle/part/poster.jpg", status="ready")), cfg, alert("video_ready", vid))
    assert mail and "prochain créneau libre" in mail.text and mail.image is None
    assert not [p for p in notify.build_message(cfg, mail).walk() if p.get_content_maintype() == "image"]
    assert notify.compose(FakeDb(), cfg, alert("video_ready", vid)) is None  # vidéo supprimée entre-temps


# ---- Boîte d'envoi --------------------------------------------------------------------------------------------------


def test_pending_mails_go_out_once_tests_first(monkeypatch):
    out = Outbox()
    monkeypatch.setattr(notify, "send_email", out)
    vid = uuid.uuid4()
    v, t = alert("video_ready", vid), alert("test")
    db = FakeDb(GMAIL, password=APP_PASSWORD, alerts=[v, t], video=video(vid))
    assert notify.flush_pending_alerts(db, env()) == 2
    assert out.subjects == ["Mail d'essai : les notifications de YouTube 2.0 marchent", f"🎬 Vidéo terminée : {MIRROR}"]
    assert db.sent() == [t["id"], v["id"]] and db.closed() == []


def test_a_refused_test_is_closed_with_its_error_and_a_video_mail_waits(monkeypatch):
    out = Outbox((False, "Gmail refuse"), (False, "Gmail refuse"))
    monkeypatch.setattr(notify, "send_email", out)
    vid = uuid.uuid4()
    v, t = alert("video_ready", vid), alert("test")
    db = FakeDb(GMAIL, password=APP_PASSWORD, alerts=[v, t], video=video(vid))
    assert notify.flush_pending_alerts(db, env()) == 0
    assert db.closed() == [("Gmail refuse", t["id"])]  # l'essai n'est pas retenté
    assert ("update alerts set email_error = %s where id = %s", ("Gmail refuse", v["id"])) in db.executed
    # pendant la pause, la vidéo attend…
    db.alerts, db.executed = [v], []
    assert notify.flush_pending_alerts(db, env()) == 0 and db.executed == [] and len(out.subjects) == 2
    # … mais un nouvel essai passe outre, et sa réussite lève la pause : la vidéo part avec lui
    t2 = alert("test")
    db.alerts = [v, t2]
    assert notify.flush_pending_alerts(db, env()) == 2 and db.sent() == [t2["id"], v["id"]]


def test_unchecked_video_mail_is_closed_and_without_password_it_waits_silently(monkeypatch):
    out = Outbox()
    monkeypatch.setattr(notify, "send_email", out)
    vid = uuid.uuid4()
    v = alert("video_ready", vid)
    db = FakeDb({**GMAIL, "on_video_ready": False}, password=APP_PASSWORD, alerts=[v], video=video(vid))
    assert notify.flush_pending_alerts(db, env()) == 0 and out.subjects == [] and db.closed() == [(None, v["id"])]
    waiting = FakeDb(GMAIL, alerts=[v], video=video(vid))  # pas de mot de passe : elle partira une fois l'envoi réglé
    assert notify.flush_pending_alerts(waiting, env()) == 0 and out.subjects == [] and waiting.executed == []


def test_dry_run_marks_the_mail_without_sending(monkeypatch):
    out = Outbox()
    monkeypatch.setattr(notify, "send_email", out)
    t = alert("test")
    db = FakeDb(GMAIL, alerts=[t])
    assert notify.flush_pending_alerts(db, env(dry_run=True)) == 1 and out.subjects == [] and db.sent() == [t["id"]]


def test_the_video_alert_is_queued_once_per_video_and_only_when_checked():
    vid = uuid.uuid4()
    db = FakeDb(GMAIL)
    assert notify.queue_video_ready(db, env(), vid, "  Le miroir ")
    sql, params = db.executed[-1]
    assert "not exists" in sql and "'video_ready'" in sql and params == ("Vidéo terminée : Le miroir", vid)
    off = FakeDb({**GMAIL, "on_video_ready": False})
    assert not notify.queue_video_ready(off, env(), vid, "Le miroir") and off.executed == []

    class Stale(FakeDb):  # migration 0019 pas encore appliquée
        def execute(self, sql: str, params: Any = None) -> int:
            raise RuntimeError('column "kind" of relation "alerts" does not exist')

    assert not notify.queue_video_ready(Stale(GMAIL), env(), vid, "Le miroir")  # la vidéo reste prête


# ---- Envoi SMTP ------------------------------------------------------------------------------------------------------


class FakeSmtp:
    calls: list[tuple[Any, ...]] = []

    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        FakeSmtp.calls.append(("connect", type(self).__name__, host, port))

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def starttls(self) -> None:
        FakeSmtp.calls.append(("starttls",))

    def login(self, user: str, password: str) -> None:
        FakeSmtp.calls.append(("login", user, password))

    def send_message(self, msg: Any) -> None:
        FakeSmtp.calls.append(("send", msg["From"], msg["To"], msg["Subject"]))


class Ssl(FakeSmtp):
    pass


class Plain(FakeSmtp):
    pass


def test_ssl_on_465_and_starttls_on_587(monkeypatch):
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", Ssl)
    monkeypatch.setattr(notify.smtplib, "SMTP", Plain)
    FakeSmtp.calls = []
    cfg = notify.load_notify_config(env(smtp_user="bot@gmail.com", smtp_pass="pw"), None)
    assert notify.send_email(cfg, notify.Mail("Objet", "texte")) == (True, "Mail envoyé à luca@example.com par bot@gmail.com")
    cfg.port = 587
    assert notify.send_email(cfg, notify.Mail("Objet", "texte"))[0]
    sent = ("send", '"YouTube 2.0" <bot@gmail.com>', "luca@example.com", "Objet")  # nom entre guillemets : il a un point
    assert FakeSmtp.calls == [
        ("connect", "Ssl", "smtp.gmail.com", 465),
        ("login", "bot@gmail.com", "pw"),
        sent,
        ("connect", "Plain", "smtp.gmail.com", 587),
        ("starttls",),
        ("login", "bot@gmail.com", "pw"),
        sent,
    ]


def test_a_refused_password_is_explained_and_a_missing_one_too(monkeypatch):
    class Refused(Ssl):
        def login(self, user: str, password: str) -> None:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", Refused)
    ok, message = notify.send_email(
        notify.load_notify_config(env(smtp_user="bot@gmail.com", smtp_pass="pw"), None), notify.Mail("Objet", "texte")
    )
    assert not ok and "(535)" in message and "mot de passe d'application" in message
    ok, message = notify.send_email(notify.load_notify_config(env(), None), notify.Mail("Objet", "texte"))
    assert not ok and message.startswith("Envoi pas encore réglé")
