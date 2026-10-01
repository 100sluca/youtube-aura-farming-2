"""Publication TikTok par Zernio (docs/36) : légende, heure de publication, corps de la requête, lecture des réponses,
client HTTP (sur un faux serveur) et suivi d'une publication par le step, sans réseau ni base."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from worker.models import Job
from worker.postpone import Postpone
from worker.steps import REGISTRY
from worker.steps import tiktok_publish as step_mod
from worker.tiktok import post as tp
from worker.tiktok.config import TikTokConfig, parse_config
from worker.tiktok.zernio import ZernioClient, ZernioError

NOW = datetime(2026, 9, 29, 1, 0, tzinfo=UTC)


def test_caption_is_title_then_description_without_shorts_tag():
    desc = (
        "Regardez cette grange.\nQuel détail préféré ?\n\n#renovation #loft #Shorts\n\nLieu imaginaire : images générées par IA."
    )
    cap = tp.build_caption("Grange ruinée en loft", desc)
    assert cap.startswith("Grange ruinée en loft\n\nRegardez cette grange.")
    assert "#Shorts" not in cap and "#renovation #loft" in cap
    assert cap.endswith("générées par IA.")  # mentions et licences gardées
    assert tp.build_caption("Titre", None) == "Titre"
    assert tp.build_caption("Titre", "Titre\n\nsuite") == "Titre\n\nsuite"  # pas de titre en double


def test_caption_is_cut_to_tiktok_limit():
    cap = tp.build_caption("T", "x" * 5000)
    assert len(cap) == tp.CAPTION_MAX and cap.endswith("…")


def test_publish_time_follows_youtube_slot_unless_past_or_forced():
    slot = NOW + timedelta(hours=8)
    assert tp.publish_time(slot, NOW) == slot
    assert tp.publish_time(slot, NOW, force_now=True) is None
    assert tp.publish_time(NOW + timedelta(minutes=1), NOW) is None  # trop proche : tout de suite
    assert tp.publish_time(NOW - timedelta(hours=3), NOW) is None
    assert tp.publish_time(None, NOW) is None


def test_idempotency_key_is_stable_per_round():
    vid = uuid4()
    assert tp.idempotency_key(vid, 1) == tp.idempotency_key(vid, 1)
    assert tp.idempotency_key(vid, 1) != tp.idempotency_key(vid, 2)


def test_post_body_public_scheduled_without_ai_label_by_default():
    slot = NOW + timedelta(hours=8)
    body = tp.post_body(
        caption="c", media_url="https://media.zernio.com/temp/v.mp4", account_id="acc", cfg=TikTokConfig(), when=slot
    )
    s = body["tiktokSettings"]
    assert body["scheduledFor"] == slot.isoformat() and "publishNow" not in body
    assert s["privacy_level"] == "PUBLIC_TO_EVERYONE" and s["media_type"] == "video"
    assert s["content_preview_confirmed"] is True and s["express_consent_given"] is True
    assert "video_made_with_ai" not in s  # choix de Luca le 29/09 : pas d'étiquette IA
    assert "draft" not in s
    assert body["platforms"] == [{"platform": "tiktok", "accountId": "acc"}]


def test_post_body_now_draft_and_ai_label_when_asked():
    cfg = TikTokConfig(ai_label=True, allow_duet=False)
    body = tp.post_body(caption="c", media_url="u", account_id="a", cfg=cfg, when=None, draft=True)
    assert body["publishNow"] is True and "scheduledFor" not in body
    assert body["tiktokSettings"]["video_made_with_ai"] is True
    assert body["tiktokSettings"]["draft"] is True and body["tiktokSettings"]["allow_duet"] is False


def test_parse_config_reads_channels_and_defaults():
    cfg = parse_config(
        {
            "channels": {
                "c1": {"account_id": "a1", "username": "arzak", "enabled": True, "enabled_at": "2026-09-29T01:40:00+02:00"}
            },
            "ai_label": "oui",
        }
    )
    assert cfg.for_channel("c1").username == "arzak" and cfg.for_channel("c1").enabled_at.hour == 1
    assert cfg.for_channel("c2") is None
    assert cfg.ai_label is False and cfg.allow_comment is True  # valeur non booléenne : défaut


def test_read_create_handles_success_failure_and_duplicate():
    ok = tp.read_create(
        201, {"post": {"_id": "p1", "status": "scheduled", "platforms": [{"platform": "tiktok", "status": "pending"}]}}
    )
    assert (ok.status, ok.post_id) == ("scheduled", "p1")
    failed = tp.read_create(
        207,
        {
            "post": {
                "_id": "p2",
                "status": "failed",
                "platforms": [{"platform": "tiktok", "status": "failed", "errorMessage": "TikTok flagged this post (spam_risk)"}],
            }
        },
    )
    assert failed.status == "failed" and "spam_risk" in failed.error
    dup = tp.read_create(409, {"error": "Duplicate", "existingPostId": "p0"})
    assert (dup.status, dup.post_id) == ("pending", "p0")
    published = tp.read_post(
        {
            "_id": "p3",
            "status": "published",
            "platforms": [{"platform": "tiktok", "status": "published", "platformPostUrl": "https://www.tiktok.com/@a/video/1"}],
        }
    )
    assert published.url.endswith("/video/1")


def _fake_zernio(log: list):
    def handler(request: httpx.Request) -> httpx.Response:
        log.append((request.method, request.url.host, request.url.path, dict(request.headers)))
        if request.url.path.endswith("/media/presign"):
            assert json.loads(request.content)["contentType"] == "video/mp4"
            return httpx.Response(
                200,
                json={
                    "uploadUrl": "https://bucket.r2.example/temp/v.mp4?sig=1",
                    "publicUrl": "https://media.zernio.com/temp/v.mp4",
                },
            )
        if request.url.host == "bucket.r2.example":
            assert request.headers["content-length"] == str(len(request.read()))
            return httpx.Response(200)
        if request.url.path.endswith("/posts") and request.method == "POST":
            return httpx.Response(
                201,
                json={"post": {"_id": "p1", "status": "scheduled", "platforms": [{"platform": "tiktok", "status": "pending"}]}},
            )
        if request.url.path.endswith("/accounts"):
            return httpx.Response(429, headers={"Retry-After": "30"}, json={"error": "Too many", "code": "rate_limited"})
        return httpx.Response(404, json={"error": "Not found"})

    return httpx.MockTransport(handler)


def test_client_uploads_to_storage_without_api_key_then_creates_post(tmp_path):
    video = tmp_path / "final.mp4"
    video.write_bytes(b"\0" * (3 * 1024 * 1024 + 7))
    calls: list = []
    seen: list[float] = []
    with ZernioClient("sk_test", transport=_fake_zernio(calls)) as zc:
        url = zc.upload_video(video, on_progress=seen.append)
        code, body = zc.create_post({"content": "c"}, "key-1")
    assert url == "https://media.zernio.com/temp/v.mp4" and code == 201
    storage = [c for c in calls if c[1] == "bucket.r2.example"][0]
    assert "authorization" not in storage[3]  # la clé ne part jamais vers le stockage
    api = [c for c in calls if c[2].endswith("/posts")][0]
    assert api[3]["authorization"] == "Bearer sk_test" and api[3]["idempotency-key"] == "key-1"
    assert seen[-1] == 1.0


def test_client_raises_with_retry_after_on_rate_limit():
    with ZernioClient("sk_test", transport=_fake_zernio([])) as zc, pytest.raises(ZernioError) as err:
        zc.accounts()
    assert err.value.status == 429 and err.value.retry_after == 30


class _FakeDb:
    def __init__(self, video: dict):
        self.video = video
        self.saved: list[dict] = []

    def fetch_one(self, sql, params=None):
        if "from videos" in sql:
            return self.video
        return None

    def execute(self, sql, params=None):
        if sql.startswith("update videos set tiktok"):
            self.saved.append(params[0].obj)
            self.video["tiktok"] = params[0].obj
        return 1

    def heartbeat(self, *a, **k):
        return True

    def log(self, *a, **k):
        pass


class _FakeClient:
    def __init__(self, post: dict):
        self.post = post

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def get_post(self, post_id):
        return self.post


def _run(monkeypatch, video: dict, post: dict):
    monkeypatch.setattr(step_mod, "zernio_key", lambda s, d: "sk_test")
    monkeypatch.setattr(step_mod, "ZernioClient", lambda key: _FakeClient(post))
    db = _FakeDb(video)
    job = Job(id=uuid4(), type="tiktok_publish", status="running", priority=30, video_id=uuid4(), created_at=NOW)
    ctx = step_mod.Context(job=job, db=db, settings=SimpleNamespace())
    return REGISTRY["tiktok_publish"].run(ctx), db


def _video(state: dict) -> dict:
    return {
        "id": uuid4(),
        "channel_id": uuid4(),
        "title": "t",
        "description": "d",
        "scheduled_at": None,
        "tiktok": state,
        "local_path": None,
        "timezone": "Europe/Paris",
    }


def test_step_waits_until_the_scheduled_time(monkeypatch):
    slot = datetime.now(UTC) + timedelta(hours=5)
    video = _video({"status": "scheduled", "post_id": "p1", "scheduled_for": slot.isoformat(), "round": 1})
    with pytest.raises(Postpone) as later:
        _run(monkeypatch, video, {"_id": "p1", "status": "scheduled", "platforms": [{"platform": "tiktok", "status": "pending"}]})
    assert 5 * 3600 < later.value.delay_s < 5 * 3600 + 400 and "programmée" in later.value.label


def test_step_records_the_tiktok_link_once_published(monkeypatch):
    video = _video({"status": "scheduled", "post_id": "p1", "scheduled_for": NOW.isoformat(), "round": 1})
    result, db = _run(
        monkeypatch,
        video,
        {
            "_id": "p1",
            "status": "published",
            "platforms": [
                {"platform": "tiktok", "status": "published", "platformPostUrl": "https://www.tiktok.com/@arzak/video/9"}
            ],
        },
    )
    assert result["url"].endswith("/video/9") and db.saved[-1]["status"] == "published"


def test_step_waits_for_the_link_then_gives_up_after_an_hour(monkeypatch):
    pub = {"_id": "p1", "status": "published", "platforms": [{"platform": "tiktok", "status": "published"}]}
    with pytest.raises(Postpone):
        _run(monkeypatch, _video({"status": "published", "post_id": "p1", "round": 1}), pub)
    result, _ = _run(
        monkeypatch, _video({"status": "published", "post_id": "p1", "round": 1, "url_checks": step_mod.URL_CHECKS}), pub
    )
    assert result["status"] == "published" and result["url"] is None


def test_step_fails_loudly_when_tiktok_refuses(monkeypatch):
    video = _video({"status": "publishing", "post_id": "p1", "round": 1})
    with pytest.raises(RuntimeError, match="spam_risk"):
        _run(
            monkeypatch,
            video,
            {
                "_id": "p1",
                "status": "failed",
                "platforms": [{"platform": "tiktok", "status": "failed", "errorMessage": "TikTok flagged this post (spam_risk)"}],
            },
        )
    assert video["tiktok"]["status"] == "failed"


# ---- Vidéo retouchée après son envoi (docs/44) -----------------------------------------------------------------------


def test_new_upload_after_a_retouch_gets_a_new_idempotency_key():
    vid = uuid4()
    assert tp.idempotency_key(vid, 1) == tp.idempotency_key(vid, 1, 0)  # clés déjà données : inchangées
    assert tp.idempotency_key(vid, 1, 1) not in (tp.idempotency_key(vid, 1), tp.idempotency_key(vid, 1, 2))


def test_client_deletes_a_scheduled_post():
    seen: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path.endswith("/posts/gone"):
            return httpx.Response(404, json={"error": "Not found"})
        if request.url.path.endswith("/posts/live"):
            return httpx.Response(400, json={"error": "Published posts cannot be deleted"})
        return httpx.Response(200, json={"message": "deleted"})

    with ZernioClient("sk_test", transport=httpx.MockTransport(handler)) as zc:
        assert zc.delete_post("p1") is True
        assert zc.delete_post("gone") is False
        with pytest.raises(ZernioError) as err:
            zc.delete_post("live")
    assert seen[0] == ("DELETE", "/api/v1/posts/p1") and err.value.status == 400


class _DeletingClient(_FakeClient):
    def __init__(self, error: ZernioError | None = None):
        super().__init__({})
        self.error = error
        self.deleted: list[str] = []

    def delete_post(self, post_id):
        if self.error:
            raise self.error
        self.deleted.append(post_id)
        return True


def _run_delete(monkeypatch, client: _DeletingClient):
    monkeypatch.setattr(step_mod, "zernio_key", lambda s, d: "sk_test")
    monkeypatch.setattr(step_mod, "ZernioClient", lambda key: client)
    db = _FakeDb(_video({}))
    job = Job(
        id=uuid4(),
        type="tiktok_publish",
        status="running",
        priority=25,
        video_id=uuid4(),
        created_at=NOW,
        payload={"delete_post": "p_old", "source": "retouche"},
    )
    ctx = step_mod.Context(job=job, db=db, settings=SimpleNamespace())
    return REGISTRY["tiktok_publish"].run(ctx), db


def test_step_deletes_the_old_post_of_a_retouched_video_without_touching_its_state(monkeypatch):
    client = _DeletingClient()
    result, db = _run_delete(monkeypatch, client)
    assert client.deleted == ["p_old"] and result["deleted"] is True
    assert db.saved == []  # videos.tiktok appartient déjà à la nouvelle version


def test_step_leaves_an_already_published_old_post(monkeypatch):
    client = _DeletingClient(ZernioError("Zernio : 400 Published posts cannot be deleted", status=400))
    result, _ = _run_delete(monkeypatch, client)
    assert result["deleted"] is False and "Published" in result["reason"]
