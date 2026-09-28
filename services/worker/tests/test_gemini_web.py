"""Gemini en ligne (docs/17) : ce qui se teste sans navigateur — durée demandée, prompt, lecture des réponses de
Gemini (limite, refus), heure de reprise, état d'une demande, commande Chrome, report d'un job (Postpone)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from worker import main
from worker.models import Job
from worker.postpone import Postpone
from worker.providers import gemini_web as gw
from worker.providers.video import get_video_provider


def test_duration_covers_the_scene_with_the_shortest_option():
    assert gw.pick_duration(1.5) == 4
    assert gw.pick_duration(4.0) == 4
    assert gw.pick_duration(4.3) == 6
    assert gw.pick_duration(7.0) == 8
    assert gw.pick_duration(8.0) == 8
    assert gw.pick_duration(12.0) == 10
    assert gw.pick_duration(3.0, "10") == 10  # réglage fixe
    assert gw.pick_duration(3.0, "12") == 4  # valeur inconnue : automatique


def test_prompt_asks_for_vertical_animation_of_the_image():
    p = gw.build_prompt("slow dolly-in towards the hidden door.", "warm_wood", 3.5, 4, with_image=True)
    assert "vertical 9:16" in p and "first frame" in p
    assert "Action and camera: slow dolly-in towards the hidden door." in p
    assert "golden hour" in p  # style du préréglage
    assert "seconds" not in p  # 4 s demandées pour une scène de 3,5 s : rien à préciser
    assert "No music" in p and "no dialogue" in p
    assert "in the first 3 seconds" in gw.build_prompt("dolly-in", None, 3.0, 4, with_image=True)  # 1 s coupée au montage


def test_prompt_mentions_the_cut_when_the_clip_is_much_longer():
    p = gw.build_prompt("pan across the lake", None, 2.0, 4, with_image=False, chat=True)
    assert p.startswith("Create a video (not an image).")
    assert "first 2 seconds" in p and "Vertical 9:16 video." in p


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Vous avez atteint la limite de création de vidéos pour le moment. Réessayez plus tard.", "quota"),
        ("You've reached your video generation limit. Try again later.", "quota"),
        ("Je ne peux plus générer de vidéos aujourd'hui : plus de vidéos disponibles, réessayez dans 4 heures.", "quota"),
        ("Je ne peux pas créer cette vidéo, car elle enfreint nos règles.", "refused"),
        ("I can't create videos of that. It goes against our policy guidelines.", "refused"),
        ("Un problème est survenu. Veuillez réessayer.", "error"),
        ("Je génère ta vidéo, cela peut prendre quelques minutes.", None),
        # bandeau au-dessus du champ de saisie (26/09) : avertissement seulement, puis limite réelle
        ("Vous avez utilisé presque tout votre quota. Les vidéos peuvent l'épuiser rapidement.", None),
        ("Vous avez utilisé tout votre quota de vidéos. Il sera réinitialisé à 04:10.", "quota"),
        ("Votre quota est épuisé pour aujourd'hui.", "quota"),
        ("Voici ta vidéo !", None),
        ("", None),
    ],
)
def test_gemini_replies_are_classified(text, kind):
    assert gw.classify_response(text) == kind


def test_ui_landmarks_match_the_labels_seen_on_gemini():
    """Libellés relevés sur gemini.google.com le 25/09/2026 (capture de `yt2 gemini check`)."""
    assert gw.COMPOSER_MENUS.search("Importation et outils") and gw.UPLOAD_MENU.search("Importation et outils")
    assert gw.MODE_PICKER.search("Ouvrir le sélecteur de mode, actuellement 3.5 Flash-Lite")
    assert gw.OPEN_SIDEBAR.search("Menu principal")
    assert gw.SIGN_IN.search("Se connecter") and gw.CONSENT_REJECT.search("Tout refuser")
    assert gw.CREATE_VIDEO.search("Créer une vidéo") and gw.CREATE_VIDEO.search("Create video")
    assert gw.ADD_IMAGE.search("Ajouter une image") and gw.ADD_IMAGE.search("Add image")
    assert gw.VIDEO_TOOL.search("Vidéo") and not gw.VIDEO_TOOL.search("Ajouter une vidéo")
    assert gw.SEND.search("Envoyer un message") and not gw.SEND.search("Créer une vidéo")
    assert gw.DOWNLOAD.search("Télécharger la vidéo")
    # page vidéo, connecté (…/u/0/videos, capture du 25/09 à 21 h 07)
    assert gw.ADD_IMAGE.search("Importation de fichiers") and gw.PORTRAIT.search("Format, Portrait (9:16)")
    assert gw.ASPECT_CONTROL.search("Format, Portrait (9:16)") and gw.MODE_PICKER.search("Ouvrir le sélecteur de mode, actuellement Gemini Flash")


def test_retry_time_is_read_from_the_limit_message():
    now = datetime(2026, 9, 25, 18, 30).astimezone()
    assert gw.parse_retry_at("Réessayez dans 4 heures.", now) == now + timedelta(hours=4)
    assert gw.parse_retry_at("Try again in 45 minutes", now) == now + timedelta(minutes=45)
    assert gw.parse_retry_at("Vous pourrez recommencer à 23 h 40.", now) == now.replace(hour=23, minute=40)
    assert gw.parse_retry_at("available again after 11:40 PM", now) == now.replace(hour=23, minute=40)
    assert gw.parse_retry_at("Réessayez à 9:15", now) == (now + timedelta(days=1)).replace(hour=9, minute=15)  # demain matin
    assert gw.parse_retry_at("Réessayez plus tard.", now) is None


def test_request_state_lives_next_to_the_clip(tmp_path: Path):
    out = tmp_path / "clips" / "scene_03.mp4"
    assert gw.read_state(out) == {}
    gw.write_state(out, {"chat_url": "https://gemini.google.com/u/0/app/abc123def", "marker": "yt2-x"})
    assert gw.state_path(out).name == "scene_03.gemini.json"
    assert gw.read_state(out)["marker"] == "yt2-x"
    gw.clear_state(out, keep={"quota_hits": 2})
    assert gw.read_state(out) == {"quota_hits": 2}
    gw.clear_state(out)
    assert not gw.state_path(out).exists()


def test_chrome_is_started_with_its_own_profile_and_local_port(tmp_path: Path):
    cmd = gw.chrome_command(Path("chrome.exe"), tmp_path / "profil", 9333, "https://gemini.google.com/u/1/app", minimized=True)
    assert cmd[0] == "chrome.exe" and cmd[-1] == "https://gemini.google.com/u/1/app"
    assert "--remote-debugging-port=9333" in cmd and f"--user-data-dir={tmp_path / 'profil'}" in cmd and "--start-minimized" in cmd
    assert "--enable-automation" not in cmd  # Chrome ordinaire : navigator.webdriver reste faux


def settings(tmp_path: Path, **kw):
    base = dict(gemini_chrome_path=None, gemini_profile_dir=None, gemini_cdp_port=9333, gemini_authuser=0, gemini_video_model=None,
                gemini_video_duration="auto", gemini_poll_minutes=3.0, gemini_quota_retry_minutes=60, gemini_max_wait_hours=6.0,
                data_dir=tmp_path, effective_gemini_profile_dir=tmp_path / "gemini-chrome")
    return SimpleNamespace(**{**base, **kw})


def test_provider_is_chosen_by_name_and_renders_fixed_length_clips(tmp_path: Path):
    provider = get_video_provider(settings(tmp_path, gemini_authuser=1), "gemini_web")
    assert provider.name == "gemini_web" and provider.image_to_video and provider.fixed_length and provider.first_last
    assert provider.rt.home == "https://gemini.google.com/u/1/app"
    out = tmp_path / "scene_00.mp4"
    info = provider.generate(prompt="p", style_preset=None, duration_s=3, out_path=out, on_progress=lambda _p: None, dry_run=True)
    assert out.exists() and info.duration_s == 4 and (info.width, info.height) == (720, 1280)


def test_first_last_frame_is_attempted_with_both_images(tmp_path: Path):
    """Chantier en accéléré, passage d'une visite : Gemini reçoit l'image de départ et celle d'arrivée (au mieux)."""
    provider = gw.GeminiWebVideo(settings(tmp_path))
    info = provider.generate(prompt="p", style_preset=None, duration_s=1.5, out_path=tmp_path / "c.mp4", on_progress=lambda _p: None,
                             dry_run=True, image_path=tmp_path / "a.png", end_image_path=tmp_path / "b.png")
    assert info.duration_s == 4  # clip entier gardé, accéléré au montage (fit « speed »)
    p = gw.build_prompt("steel beams are lifted into place", "timelapse_site", 1.5, 4, with_image=True, end_frame=True)
    assert "starts exactly on the first attached image and ends exactly on the second attached image" in p
    assert "first 2 seconds" not in p and "Animate the attached image" not in p


def test_known_quota_postpones_without_opening_the_browser(tmp_path: Path, monkeypatch):
    provider = gw.GeminiWebVideo(settings(tmp_path))
    until = datetime.now().astimezone() + timedelta(hours=2)
    monkeypatch.setattr(provider, "quota_until", lambda: until)
    monkeypatch.setattr(gw, "browser_context", lambda *_a, **_k: pytest.fail("Chrome ne doit pas être ouvert"))
    with pytest.raises(Postpone) as later:
        provider.generate(prompt="p", style_preset=None, duration_s=3, out_path=tmp_path / "c.mp4", on_progress=lambda _p: None)
    assert later.value.error == "Quota Gemini atteint" and 7000 < later.value.delay_s < 7300
    assert "quota atteint" in later.value.label


class PostponeDb:
    """Ce que run_job utilise (comme tests/test_tasks.py), plus postpone."""

    def __init__(self, status="running"):
        self.status = status
        self.completed = False
        self.failed: str | None = None
        self.logs: list[str] = []
        self.postponed: tuple | None = None

    def job_status(self, job_id):
        return self.status

    def heartbeat(self, job_id, progress=None, label=None):
        return self.status == "running"

    def complete(self, job_id, result=None):
        self.completed = self.status == "running"
        return self.completed

    def fail(self, job_id, error):
        self.failed = error

    def log(self, job_id, level, message, data=None):
        self.logs.append(message)

    def postpone(self, job_id, delay_s, *, label=None, error=None):
        self.postponed = (delay_s, label, error)
        return self.status == "running"


def run_with_step(monkeypatch, db, step_run):
    monkeypatch.setitem(main.REGISTRY, "generate_clip", SimpleNamespace(run=step_run, lane="gpu"))
    job = Job(id=uuid4(), type="generate_clip", status="running", priority=100, created_at=datetime.now(UTC))
    main.run_job(job, db, SimpleNamespace())


def test_postponed_job_is_requeued_not_failed(monkeypatch):
    db = PostponeDb()

    def step(ctx):
        raise Postpone("Gemini : vidéo demandée", 180, label="Gemini · vidéo demandée à 18:40")

    run_with_step(monkeypatch, db, step)
    assert db.failed is None and not db.completed
    assert db.postponed == (180.0, "Gemini · vidéo demandée à 18:40", None)
    assert "Gemini : vidéo demandée" in db.logs


def test_postpone_after_a_stop_leaves_the_job_cancelled(monkeypatch):
    db = PostponeDb(status="cancelled")

    def step(ctx):
        raise Postpone("Gemini : en cours", 180)

    run_with_step(monkeypatch, db, step)
    assert db.failed is None and db.postponed is not None and "Gemini : en cours" not in db.logs
