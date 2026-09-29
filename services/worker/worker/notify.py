"""Notifications par e-mail (docs/32-notifications-mail.md) : un mail dès qu'une vidéo est terminée, pour aller la voir.

La table `alerts` sert de boîte d'envoi (migration 0019) : le step qa y dépose une alerte `video_ready` la première fois
qu'une vidéo passe le contrôle final, Réglages → Notifications une alerte `test` (« Envoyer un mail d'essai ») ; le
planificateur les envoie toutes les 20 s. Les autres alertes (échecs, quota, tampon : `kind` vide) restent en base sans
mail : elles inonderaient la boîte (tampon faible chaque matin, un mail par clip en échec).

Réglages → Notifications (app_settings.notifications : adresse qui reçoit, case « Vidéo terminée », compte Gmail qui
envoie ; mot de passe d'application chiffré dans app_secrets.smtp_password) prime sur le .env (ALERT_EMAIL_TO,
NOTIFY_ON_REVIEW, SMTP_*, RESEND_API_KEY, DASHBOARD_URL). Jamais bloquant pour le pipeline.
"""

from __future__ import annotations

import re
import smtplib
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import escape
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import structlog

from .config import Settings
from .youtube.auth import decrypt

log = structlog.get_logger(__name__)

KINDS = ("video_ready", "test")
SECRET_NAME = "smtp_password"
DEFAULT_HOST = "smtp.gmail.com"
OUTBOX_HOURS = 6  # une alerte plus vieille ne part plus (envoi en panne longtemps, mot de passe retiré…)
MAX_IMAGE_BYTES = 1_500_000
MSGID_DOMAIN = "youtube2.local"
GMAIL_APP_PASSWORD = re.compile(r"^[a-z]{4}( [a-z]{4}){3}$", re.IGNORECASE)  # affiché par Google en 4 groupes de 4 lettres
NEXT_STEP = {
    "review": "Elle attend ton feu vert : dans sa fiche, « Autoriser la publication » (ou Refuser).",
    "ready": "Publication automatique : elle partira sur YouTube au prochain créneau libre.",
}
VIDEO_SQL = """select v.id, v.title, v.status::text as status, v.duration_s, c.name as channel_name,
                      se.name as series_name, a.local_path as poster
               from videos v join channels c on c.id = v.channel_id
               left join productions p on p.id = v.production_id
               left join series se on se.id = p.series_id
               left join assets a on a.id = v.poster_asset_id
               where v.id = %s"""


@dataclass
class NotifyConfig:
    email_to: str
    on_video_ready: bool
    sender: str  # compte qui envoie (Gmail) ; vide dans les Réglages = l'adresse qui reçoit
    password: str | None  # mot de passe d'application du compte qui envoie
    host: str
    port: int  # 465 = SSL, sinon STARTTLS (587)
    resend_api_key: str | None
    dashboard_url: str
    source: str = "env"  # env | db

    @property
    def can_send(self) -> bool:
        return bool(self.email_to and ((self.sender and self.password) or self.resend_api_key))


@dataclass
class Mail:
    subject: str
    text: str
    html: str | None = None  # « cid:poster » y désigne l'image jointe
    image: bytes | None = None  # image de la vidéo (poster.jpg du montage)


def _clean_password(value: str | None) -> str | None:
    value = (value or "").strip()
    return value.replace(" ", "") if GMAIL_APP_PASSWORD.match(value) else value or None


def load_notify_config(settings: Settings, db: Any | None) -> NotifyConfig:
    """Réglages effectifs : base (app_settings.notifications + app_secrets.smtp_password) par-dessus le .env."""
    cfg = NotifyConfig(
        email_to=(settings.alert_email_to or "").strip(),
        on_video_ready=bool(settings.notify_on_review),
        sender=(settings.smtp_user or "").strip(),
        password=_clean_password(settings.smtp_pass),
        host=settings.smtp_host or DEFAULT_HOST,
        port=int(settings.smtp_port or 465),
        resend_api_key=settings.resend_api_key or None,
        dashboard_url=(settings.dashboard_url or "http://localhost:3000").rstrip("/"),
    )
    if db is not None:
        row = db.fetch_one("select value from app_settings where key = 'notifications'")
        v = row["value"] if row and row["value"] else None
        if v:
            cfg.source = "db"
            cfg.email_to = str(v.get("email_to") or cfg.email_to).strip()
            if isinstance(v.get("on_video_ready"), bool):
                cfg.on_video_ready = v["on_video_ready"]
            cfg.sender = str(v.get("sender") or cfg.sender).strip()
        secret = db.fetch_one("select value_encrypted from app_secrets where name = %s", (SECRET_NAME,))
        if secret and settings.credentials_key:
            try:
                cfg.password = _clean_password(decrypt(settings, secret["value_encrypted"]))
            except Exception:  # noqa: BLE001 — clé de chiffrement changée : on garde celui du .env
                log.warning("notify.mot_de_passe_illisible")
    cfg.sender = cfg.sender or cfg.email_to
    return cfg


# ---------------------------------------------------------------------------------------------------------------------
# Le mail
# ---------------------------------------------------------------------------------------------------------------------


def compose(db: Any, cfg: NotifyConfig, alert: dict[str, Any]) -> Mail | None:
    """Le mail d'une alerte de la boîte d'envoi ; None si sa vidéo a disparu entre-temps."""
    if alert["kind"] == "test":
        return _test_mail(cfg)
    v = db.fetch_one(VIDEO_SQL, (alert["video_id"],)) if alert.get("video_id") else None
    return _video_mail(cfg, v) if v else None


def _video_mail(cfg: NotifyConfig, v: dict[str, Any]) -> Mail:
    title = (v.get("title") or "").strip() or "Short sans titre"
    link = f"{cfg.dashboard_url}/library?video={v['id']}"
    duration = f"{round(float(v['duration_s']))} s" if v.get("duration_s") else None
    meta = " · ".join(x for x in (duration, v.get("channel_name"), v.get("series_name")) if x)
    done = "Ta vidéo est terminée : montée et contrôlée" + (f" ({meta})" if meta else "") + "."
    step = NEXT_STEP.get(v.get("status") or "", f"Statut : {v.get('status')}.")
    image = _poster(v.get("poster"))
    text = f"{title}\n\n{done}\n{step}\n\nLa regarder : {link}\n(lien du dashboard, sur le PC où tourne YouTube 2.0)\n"
    body = _html("YouTube 2.0 · vidéo terminée", title, [done, step], link, "Voir la vidéo", with_image=image is not None)
    return Mail(f"🎬 Vidéo terminée : {title}", text, body, image)


def _test_mail(cfg: NotifyConfig) -> Mail:
    link = f"{cfg.dashboard_url}/settings#notifications"
    lines = [
        "Si tu lis ce message, les notifications marchent : tu recevras un mail comme celui-ci dès qu'une vidéo est terminée.",
        f"Envoyé par {cfg.sender or cfg.email_to} à {cfg.email_to}.",
    ]
    text = "\n\n".join(lines) + f"\n\nRéglages : {link}\n"
    body = _html("YouTube 2.0 · mail d'essai", "Les notifications marchent", lines, link, "Ouvrir les Réglages", with_image=False)
    return Mail("Mail d'essai : les notifications de YouTube 2.0 marchent", text, body)


def _poster(path: str | None) -> bytes | None:
    """L'image de la vidéo (poster.jpg du montage), si elle est encore sur le disque et assez légère pour un mail."""
    try:
        p = Path(path) if path else None
        if p and p.is_file() and 0 < p.stat().st_size <= MAX_IMAGE_BYTES:
            return p.read_bytes()
    except OSError:
        pass
    return None


def _html(kicker: str, title: str, lines: list[str], link: str, button: str, *, with_image: bool) -> str:
    image = (
        '<img src="cid:poster" width="240" alt="" style="display:block;border-radius:10px;margin:0 0 14px">' if with_image else ""
    )
    paras = "".join(f'<p style="margin:0 0 8px;font-size:14px;line-height:1.45">{escape(x)}</p>' for x in lines)
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;color:#111">'
        f'<p style="margin:0 0 4px;color:#666;font-size:12px">{escape(kicker)}</p>'
        f'<h2 style="margin:0 0 14px;font-size:20px;line-height:1.3">{escape(title)}</h2>{image}{paras}'
        f'<p style="margin:16px 0 8px"><a href="{escape(link)}" style="display:inline-block;background:#111;color:#fff;'
        f'padding:10px 16px;border-radius:8px;text-decoration:none;font-size:14px">{escape(button)}</a></p>'
        '<p style="margin:0;color:#888;font-size:12px">Le lien ouvre le dashboard, sur le PC où tourne YouTube 2.0.</p>'
        "</div>"
    )


def build_message(cfg: NotifyConfig, mail: Mail) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr(("YouTube 2.0", cfg.sender or cfg.email_to))
    msg["To"] = cfg.email_to
    msg["Subject"] = mail.subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=MSGID_DOMAIN)
    msg.set_content(mail.text)
    if mail.html:
        cid = make_msgid(domain=MSGID_DOMAIN)
        msg.add_alternative(mail.html.replace("cid:poster", f"cid:{cid[1:-1]}"), subtype="html")
        if mail.image:
            msg.get_payload()[1].add_related(mail.image, maintype="image", subtype="jpeg", cid=cid)
    return msg


def send_email(cfg: NotifyConfig, mail: Mail) -> tuple[bool, str]:
    """Envoie le mail ; renvoie (réussi, explication lisible). Jamais d'exception."""
    if not cfg.email_to:
        return False, "Aucune adresse de réception (Réglages → Notifications)"
    try:
        if cfg.sender and cfg.password:
            msg = build_message(cfg, mail)
            if cfg.port == 465:
                with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=20) as s:
                    s.login(cfg.sender, cfg.password)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(cfg.host, cfg.port, timeout=20) as s:
                    s.starttls()
                    s.login(cfg.sender, cfg.password)
                    s.send_message(msg)
            return True, f"Mail envoyé à {cfg.email_to} par {cfg.sender}"
        if cfg.resend_api_key:
            r = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {cfg.resend_api_key}"},
                json={
                    "from": "YouTube 2.0 <alerts@resend.dev>",
                    "to": [cfg.email_to],
                    "subject": mail.subject,
                    "text": mail.text,
                },
                timeout=15,
            )
            r.raise_for_status()
            return True, f"Mail envoyé à {cfg.email_to} par Resend"
        return False, "Envoi pas encore réglé : Réglages → Notifications, mot de passe d'application du compte Gmail qui envoie"
    except smtplib.SMTPAuthenticationError as exc:
        return False, (
            f"{cfg.host} refuse la connexion de {cfg.sender} ({exc.smtp_code}) : mot de passe d'application faux ou "
            "retiré, ou validation en deux étapes coupée sur ce compte"
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"Envoi impossible : {type(exc).__name__}: {exc}"[:400]


# ---------------------------------------------------------------------------------------------------------------------
# Boîte d'envoi
# ---------------------------------------------------------------------------------------------------------------------


def queue_video_ready(db: Any, settings: Settings, video_id: UUID, title: str | None) -> bool:
    """Dépose l'alerte « vidéo terminée » (le mail part dans les 20 s), une seule fois par vidéo : refaire son montage
    (onglet Montage) ne renvoie pas de mail ; « Refaire » une production crée une nouvelle vidéo, donc un nouveau mail.
    Jamais d'exception : la vidéo reste prête même si la base refuse (migration 0019 absente)."""
    try:
        if not load_notify_config(settings, db).on_video_ready:
            return False
        return (
            db.execute(
                """insert into alerts (severity, kind, title, video_id, production_id)
               select 'info', 'video_ready', %s, v.id, v.production_id from videos v
               where v.id = %s and not exists (select 1 from alerts a where a.video_id = v.id and a.kind = 'video_ready')""",
                (f"Vidéo terminée : {(title or '').strip() or 'Short'}", video_id),
            )
            > 0
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("notify.video_ready_impossible", error=str(exc)[:200])
        return False


@dataclass
class _Pause:
    """Après un envoi raté : pause croissante (1, 2, 4… 30 min) pour ne pas harceler le serveur (Gmail bloque un compte
    qui enchaîne les mauvais mots de passe). Un mail d'essai passe outre, et sa réussite lève la pause."""

    failures: int = 0
    until: float = 0.0

    def active(self) -> bool:
        return time.monotonic() < self.until

    def failed(self) -> None:
        self.failures += 1
        self.until = time.monotonic() + min(1800.0, 60.0 * 2 ** (self.failures - 1))

    def reset(self) -> None:
        self.failures, self.until = 0, 0.0


_pause = _Pause()


def _close(db: Any, alert_id: Any, error: str | None = None) -> None:
    """Alerte close sans mail (acknowledged_at, migration 0019)."""
    db.execute("update alerts set acknowledged_at = now(), email_error = %s where id = %s", (error, alert_id))


def flush_pending_alerts(db: Any, settings: Settings) -> int:
    """Envoie les mails en attente (planificateur, toutes les 20 s), essais d'abord. Renvoie le nombre de mails partis."""
    try:
        rows = db.fetch_all(
            """select id, kind, title, video_id from alerts
               where emailed_at is null and acknowledged_at is null and kind = any(%s)
                 and created_at > now() - make_interval(hours => %s)
               order by (kind = 'test') desc, created_at limit 10""",
            (list(KINDS), OUTBOX_HOURS),
        )
    except Exception as exc:  # noqa: BLE001 — migration 0019 pas encore appliquée, base injoignable un instant
        log.warning("notify.boite_illisible", error=str(exc)[:200])
        return 0
    if not rows:
        return 0
    cfg = load_notify_config(settings, db)
    sent = 0
    for a in rows:
        test = a["kind"] == "test"
        if a["kind"] == "video_ready" and not cfg.on_video_ready:
            _close(db, a["id"])  # case décochée entre-temps
            continue
        if not test and (not cfg.can_send or _pause.active()):
            continue  # attend que l'envoi soit réglé (6 h au plus) ou la fin de la pause
        try:
            mail = compose(db, cfg, a)
        except Exception as exc:  # noqa: BLE001
            log.warning("notify.mail_impossible", error=str(exc)[:200])
            mail = None
        if mail is None:
            _close(db, a["id"])
            continue
        ok, message = (True, "DRY_RUN : mail non envoyé") if settings.dry_run else send_email(cfg, mail)
        if ok:
            db.execute("update alerts set emailed_at = now(), email_error = null where id = %s", (a["id"],))
            _pause.reset()
            sent += 1
            log.info("notify.envoye", kind=a["kind"], to=cfg.email_to, subject=mail.subject)
            continue
        log.warning("notify.echec", kind=a["kind"], error=message)
        if test:
            _close(db, a["id"], message)  # pas retenté : l'erreur s'affiche dans Réglages, on corrige puis on refait l'essai
        else:
            db.execute("update alerts set email_error = %s where id = %s", (message, a["id"]))
            _pause.failed()
    return sent
