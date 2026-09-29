"""TikTok partout (docs/39) : lecture des statistiques de Zernio, relevé par le step sync_tiktok, rattrapage des vidéos
déjà sorties sur YouTube (créneau choisi, heure transmise au step de publication), sans réseau ni base."""

from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from worker import scheduler
from worker.models import Job
from worker.postpone import Postpone
from worker.steps import REGISTRY
from worker.steps import sync_tiktok as sync_mod
from worker.steps import tiktok_publish as publish_mod
from worker.tiktok import backlog as bl
from worker.tiktok import stats as ts
from worker.tiktok.config import parse_config

NOW = datetime(2026, 9, 30, 8, 0, tzinfo=UTC)
PARIS = ZoneInfo("Europe/Paris")


def _item(**over):
    """Entrée de GET /analytics telle que Zernio la renvoie pour une publication de l'appli (forme vue le 29/09)."""
    item = {
        "postId": "z1",
        "status": "published",
        "content": "Cabane perchée : 14 jours de timelapse 🌲\n\n#cabane",
        "scheduledFor": "2026-09-29T07:00:00.000Z",
        "publishedAt": "2026-09-29T07:00:04.000Z",
        "analytics": {
            "views": 1200,
            "likes": 90,
            "comments": 4,
            "shares": 7,
            "saves": 0,
            "reach": 0,
            "igReelsAvgWatchTime": 0,
            "igReelsVideoViewTotalTime": 0,
            "completionRate": 0,
            "profileViews": 0,
            "follows": None,
            "impressionSources": {},
            "audienceTypes": {},
            "audienceCountries": {},
            "lastUpdated": "2026-09-29T09:10:00.000Z",
        },
        "platformAnalytics": [
            {
                "platform": "tiktok",
                "status": "published",
                "platformPostId": "7551234567890123456",
                "accountId": "acc",
                "accountUsername": "arzakparker",
                "analytics": None,
                "syncStatus": "synced",
                "platformPostUrl": "https://www.tiktok.com/@arzakparker/video/7551234567890123456",
            }
        ],
        "isExternal": False,
        "syncStatus": "synced",
        "platformPostUrl": None,
        "thumbnailUrl": "https://media.zernio.com/media/1790639169489_v9po7hur_final.mp4",
        "mediaType": "video",
        "mediaItems": [
            {
                "type": "video",
                "url": "https://media.zernio.com/media/x_final.mp4",
                "thumbnail": "https://media.zernio.com/media/x_final.mp4",
            }
        ],
    }
    item.update(over)
    return item


# ---- Lecture des réponses -----------------------------------------------------------------------------------------
def test_app_post_keeps_its_zernio_id_and_basic_counters():
    p = ts.parse_post(_item(), "acc")
    assert (p.key, p.zernio_post_id, p.is_external) == ("z1", "z1", False)
    assert (p.views, p.likes, p.comments, p.shares) == (1200, 90, 4, 7)
    assert p.url.endswith("/video/7551234567890123456") and p.tiktok_id == "7551234567890123456"
    assert p.published_at == datetime(2026, 9, 29, 7, 0, 4, tzinfo=UTC)
    assert p.thumbnail_url is None  # Zernio renvoie l'adresse du MP4 : pas une image
    # chiffres TikTok for Business pas encore remplis (24 à 48 h) : inconnus, pas zéro
    assert p.avg_watch_s is None and p.completion_pct is None and p.saves is None and p.follows is None
    assert p.impression_sources is None


def test_business_metrics_once_tiktok_fills_them():
    a = {
        "views": 5000,
        "likes": 300,
        "comments": 12,
        "shares": 40,
        "saves": 25,
        "reach": 4100,
        "follows": 9,
        "profileViews": 60,
        "igReelsAvgWatchTime": 8400,
        "igReelsVideoViewTotalTime": 42_000_000,
        "completionRate": 0.31,
        "impressionSources": {"forYou": 0.92, "follow": 0.03, "search": 0.05},
        "audienceTypes": {"follower": 0.1, "nonFollower": 0.9},
        "audienceCountries": {"FR": 0.8, "BE": 0.1, "other": 0.1},
    }
    p = ts.parse_post(_item(analytics=a), "acc")
    assert (p.avg_watch_s, p.total_watch_s, p.completion_pct) == (8.4, 42000.0, 31.0)
    assert (p.saves, p.reach, p.follows, p.profile_views) == (25, 4100, 9, 60)
    assert p.impression_sources["forYou"] == 0.92 and p.audience_countries["FR"] == 0.8


def test_scheduled_failed_and_inbox_drafts_are_skipped():
    assert ts.parse_post(_item(status="scheduled", platformAnalytics=[]), "acc") is None
    failed = _item(platformAnalytics=[{"platform": "tiktok", "status": "failed", "accountId": "acc"}], status="failed")
    assert ts.parse_post(failed, "acc") is None
    draft = _item(
        platformAnalytics=[
            {
                "platform": "tiktok",
                "status": "published",
                "accountId": "acc",
                "platformPostId": "v_inbox_url~v2.7690732634049316896",
            }
        ]
    )
    assert ts.parse_post(draft, "acc") is None  # brouillon dans la boîte de réception : rien de public


def test_hand_made_tiktok_post_is_external():
    p = ts.parse_post(_item(postId="ext9", isExternal=True, content="Vidéo faite dans l'appli TikTok"), "acc")
    assert (p.key, p.zernio_post_id, p.is_external) == ("ext9", None, True)


def test_synced_copy_of_an_app_post_merges_with_it():
    app = ts.parse_post(_item(), "acc")
    copy = ts.parse_post(
        _item(postId="ext1", latePostId="z1", isExternal=True, analytics={**_item()["analytics"], "views": 1300}), "acc"
    )
    orphan = ts.parse_post(_item(postId="ext2", isExternal=True), "acc")  # même vidéo TikTok, lien Zernio perdu
    merged = ts.merge_posts([app, copy, orphan])
    assert len(merged) == 1
    assert merged[0].key == "z1" and merged[0].views == 1300 and merged[0].zernio_post_id == "z1"


def test_account_insights_and_account_fallback():
    resp = {
        "metrics": {
            "follower_count": {"total": 12},
            "following_count": {"total": 3},
            "likes_count": {"total": 450},
            "video_count": {"total": 6},
        },
        "unavailableMetrics": [],
    }
    assert ts.parse_insights(resp) == {"followers": 12, "following": 3, "likes": 450, "videos": 6}
    acc = {
        "_id": "acc",
        "username": "arzakparker",
        "followersCount": 0,
        "profileUrl": "https://tiktok.com/@arzakparker",
        "metadata": {"apiFlavor": "business", "profileData": {"extraData": {"likesCount": 0, "videoCount": 0}}},
    }
    info = ts.account_info(acc)
    assert info["business"] is True and info["fallback"]["followers"] == 0 and info["username"] == "arzakparker"


def test_video_published_by_hand_in_tiktok_is_recognised_by_its_title():
    made = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)
    videos = {
        ts.norm_title("Garage sombre en atelier de menuiserie en 25 jours"): {
            "id": "v1",
            "created_at": made,
            "tiktok": {"status": "published", "draft": True},
        }
    }
    hand = ts.parse_post(
        _item(
            postId="ext7",
            isExternal=True,
            content="Garage sombre en atelier de menuiserie en 25 jours !\n\nDu garage poussiéreux…",
        ),
        "acc",
    )
    assert ts.match_by_title(hand, videos)["id"] == "v1"  # brouillon terminé dans l'appli TikTok
    before = ts.parse_post(
        _item(
            postId="ext8",
            isExternal=True,
            publishedAt="2026-09-27T10:00:00Z",
            content="Garage sombre en atelier de menuiserie en 25 jours",
        ),
        "acc",
    )
    assert ts.match_by_title(before, videos) is None  # sortie avant la fabrication : une autre vidéo
    assert (
        ts.match_by_title(ts.parse_post(_item(content="Garage sombre en atelier de menuiserie en 25 jours"), "acc"), videos)
        is None
    )


class _MarkDb:
    def __init__(self, job=False):
        self.job = job
        self.sql: list = []

    def fetch_one(self, sql, params=None):
        return {"x": 1} if self.job and "from jobs" in sql else None

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        return 1


def test_mark_manual_records_hand_publication_without_racing_a_job():
    post = ts.parse_post(_item(postId="ext7", isExternal=True), "acc")
    account = {"id": "acc", "username": "arzakparker"}
    db = _MarkDb()
    sync_mod.mark_manual(db, {"id": "v1", "tiktok": None}, post, account)
    state = db.sql[0][1][0].obj
    assert state["status"] == "published" and state["source"] == "manuel" and state["url"].endswith("7551234567890123456")
    busy = _MarkDb(job=True)
    sync_mod.mark_manual(busy, {"id": "v1", "tiktok": None}, post, account)
    assert busy.sql == []  # une publication est en cours : son step écrit l'état
    draft = _MarkDb()
    sync_mod.mark_manual(draft, {"id": "v1", "tiktok": {"status": "published", "draft": True}}, post, account)
    assert "tiktok || " in draft.sql[0][0] and draft.sql[0][1][0].obj["draft"] is False


# ---- Rattrapage : choix du créneau ----------------------------------------------------------------------------------
def test_slot_times_follow_paris_time_across_days():
    slots = bl.slot_times([time(9), time(13), time(18)], "Europe/Paris", NOW)
    assert len(slots) == 9  # veille, aujourd'hui, demain
    assert datetime(2026, 9, 30, 7, 0, tzinfo=UTC) in slots  # 9 h à Paris (heure d'été)
    winter = bl.slot_times(["09:00:00"], "Europe/Paris", datetime(2026, 12, 1, 6, 0, tzinfo=UTC))
    assert datetime(2026, 12, 1, 8, 0, tzinfo=UTC) in winter  # 9 h à Paris (heure d'hiver)


def test_backlog_slot_only_inside_the_last_half_hour_and_when_free():
    slot = NOW + timedelta(minutes=20)
    assert bl.backlog_slot([slot], NOW, []) == slot
    assert bl.backlog_slot([slot], NOW, [slot]) is None  # vidéo YouTube ou TikTok déjà prévue
    assert bl.backlog_slot([slot], NOW, [slot + timedelta(minutes=4)]) is None
    assert bl.backlog_slot([NOW + timedelta(minutes=45)], NOW, []) is None  # YouTube peut encore le prendre
    assert bl.backlog_slot([NOW + timedelta(minutes=3)], NOW, []) is None  # trop tard pour envoyer le fichier


class _PlanDb:
    def __init__(self, slots, busy, candidate):
        self.slots, self.busy, self.candidate = slots, busy, candidate
        self.enqueued: list = []

    def fetch_one(self, sql, params=None):
        if "from channels" in sql:
            return {"publish_slots": self.slots, "timezone": "Europe/Paris"}
        if "v_tiktok_backlog" in sql:
            return self.candidate
        return None

    def fetch_all(self, sql, params=None):
        return [{"at": b} for b in self.busy]

    def enqueue(self, type_, **kw):
        self.enqueued.append((type_, kw))


def _plan(monkeypatch, busy, backlog=True, candidate="default"):
    local = (datetime.now(UTC) + timedelta(minutes=15)).astimezone(PARIS)
    slot_local = time(local.hour, local.minute)
    video = {"id": uuid4(), "title": "Chalet de luxe"} if candidate == "default" else candidate
    cfg = parse_config(
        {"channels": {"c1": {"account_id": "acc", "username": "arzakparker", "enabled": True, "backlog": backlog}}}
    )
    monkeypatch.setattr(scheduler, "load_tiktok_config", lambda db: cfg)
    monkeypatch.setattr(scheduler, "zernio_key", lambda s, d: "sk_test")
    slot = datetime.combine(local.date(), slot_local, tzinfo=PARIS).astimezone(UTC)
    db = _PlanDb([slot_local], [slot] if busy else [], video)
    scheduler.plan_tiktok_backlog(db, SimpleNamespace())
    return db, slot, video


def test_backlog_fills_an_empty_slot_with_the_oldest_video(monkeypatch):
    db, slot, video = _plan(monkeypatch, busy=False)
    assert len(db.enqueued) == 1
    type_, kw = db.enqueued[0]
    assert type_ == "tiktok_publish" and kw["video_id"] == video["id"] and kw["channel_id"] == "c1"
    assert kw["payload"] == {"at": slot.isoformat(), "source": "rattrapage", "account_id": "acc"}


def test_backlog_leaves_taken_slots_and_disabled_channels_alone(monkeypatch):
    assert _plan(monkeypatch, busy=True)[0].enqueued == []
    assert _plan(monkeypatch, busy=False, backlog=False)[0].enqueued == []
    assert _plan(monkeypatch, busy=False, candidate=None)[0].enqueued == []  # plus rien à rattraper


# ---- Publication d'une vidéo rattrapée : l'heure du créneau vide, pas celle de YouTube ------------------------------
class _PublishDb:
    def __init__(self, video):
        self.video = video

    def fetch_one(self, sql, params=None):
        return self.video if "from videos" in sql else None

    def execute(self, sql, params=None):
        if sql.startswith("update videos set tiktok"):
            self.video["tiktok"] = params[0].obj
        return 1

    def heartbeat(self, *a, **k):
        return True

    def log(self, *a, **k):
        pass


class _PublishClient:
    def __init__(self, sent: list):
        self.sent = sent

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def upload_video(self, path, on_progress=None):
        return "https://media.zernio.com/temp/v.mp4"

    def create_post(self, body, key):
        self.sent.append(body)
        return 201, {"post": {"_id": "p9", "status": "scheduled", "platforms": [{"platform": "tiktok", "status": "pending"}]}}


def test_backlog_publication_is_scheduled_at_the_empty_slot(monkeypatch, tmp_path):
    final = tmp_path / "final.mp4"
    final.write_bytes(b"\0" * 1024)
    slot = (datetime.now(UTC) + timedelta(minutes=20)).replace(microsecond=0)
    video = {
        "id": uuid4(),
        "channel_id": uuid4(),
        "title": "Chalet de luxe",
        "description": "#chalet",
        "scheduled_at": datetime.now(UTC) - timedelta(days=3),
        "tiktok": None,
        "local_path": str(final),
        "timezone": "Europe/Paris",
    }
    sent: list = []
    monkeypatch.setattr(publish_mod, "zernio_key", lambda s, d: "sk_test")
    monkeypatch.setattr(publish_mod, "ZernioClient", lambda key: _PublishClient(sent))
    job = Job(
        id=uuid4(),
        type="tiktok_publish",
        status="running",
        priority=55,
        video_id=video["id"],
        created_at=NOW,
        payload={"at": slot.isoformat(), "source": "rattrapage", "account_id": "acc"},
    )
    ctx = publish_mod.Context(job=job, db=_PublishDb(video), settings=SimpleNamespace())
    with pytest.raises(Postpone):  # programmée : le job revient à l'heure dite
        REGISTRY["tiktok_publish"].run(ctx)
    assert sent[0]["scheduledFor"] == slot.isoformat() and "publishNow" not in sent[0]
    assert sent[0]["platforms"] == [{"platform": "tiktok", "accountId": "acc"}]
    assert video["tiktok"]["source"] == "rattrapage" and video["tiktok"]["scheduled_for"] == slot.isoformat()


# ---- Relevé par le step sync_tiktok -------------------------------------------------------------------------------
class _SyncDb:
    def __init__(self, video_id):
        self.video_id = video_id
        self.sql: list[tuple[str, tuple]] = []

    def fetch_all(self, sql, params=None):
        if "from videos where tiktok is not null" in sql:
            return [{"id": self.video_id, "post_id": "z1", "url": None}]
        return []

    def fetch_one(self, sql, params=None):
        return None

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), params))
        return 1

    def heartbeat(self, *a, **k):
        return True

    def log(self, *a, **k):
        pass


class _StatsClient:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def tiktok_accounts(self):
        return [{"_id": "acc", "username": "arzakparker", "platform": "tiktok", "metadata": {"apiFlavor": "business"}}]

    def account_insights(self, account_id):
        return {"metrics": {"follower_count": {"total": 12}, "likes_count": {"total": 450}, "video_count": {"total": 2}}}

    def sync_external(self, account_id):
        return {"postsFound": 1, "postsSynced": 1, "skipped": False}

    def account_posts(self, account_id):
        return [LIVE_APP, LIVE_NEW]

    def post_analytics(self, account_id):
        hand = _item(
            postId="ext9",
            isExternal=True,
            platformAnalytics=[
                {"platform": "tiktok", "status": "published", "platformPostId": "7550000000000000001", "accountId": "acc"}
            ],
        )
        return [_item(), hand], {"lastSync": "2026-09-29T09:00:00.000Z"}


LIVE_APP = {
    "id": "7551234567890123456",
    "message": "Cabane perchée : 14 jours de timelapse 🌲",
    "likeCount": 95,
    "commentCount": 4,
    "shareCount": 7,
    "createdTime": "2026-09-29T07:00:04.000Z",
    "permalink": "https://www.tiktok.com/@arzakparker/video/7551234567890123456?utm_campaign=tt4d_open_api",
}
LIVE_NEW = {
    "id": "7690741999670021398",
    "message": "Sa mère est dévastée.",
    "likeCount": 1,
    "commentCount": 0,
    "shareCount": 0,
    "createdTime": "2026-09-29T00:07:30.000Z",
    "picture": "https://p16.tiktokcdn-eu.com/cover.jpeg?sig=1",
    "permalink": "https://www.tiktok.com/@arzakparker/video/7690741999670021398?utm_campaign=tt4d_open_api",
}


def test_live_posts_show_new_videos_before_zernio_counts_their_views():
    live = [ts.parse_live_post(LIVE_APP), ts.parse_live_post(LIVE_NEW)]
    assert live[1].url == "https://www.tiktok.com/@arzakparker/video/7690741999670021398"  # sans ?utm_campaign
    assert live[1].sync_status == "live" and live[1].views == 0 and live[1].thumbnail_url.endswith("cover.jpeg?sig=1")
    posts = ts.add_live_posts([ts.parse_post(_item(), "acc")], live)
    assert [p.key for p in posts] == ["z1", "7690741999670021398"]  # la vidéo déjà relevée n'est pas doublée
    assert posts[0].likes == 95 and posts[0].views == 1200  # j'aime lus en direct, vues de Zernio
    assert ts.tiktok_id_of("https://www.tiktok.com/@a/video/42?x=1") == "42" and ts.tiktok_id_of(None) is None


def test_sync_step_records_accounts_posts_and_links_app_videos(monkeypatch):
    vid = uuid4()
    monkeypatch.setattr(sync_mod, "zernio_key", lambda s, d: "sk_test")
    monkeypatch.setattr(sync_mod, "ZernioClient", lambda key: _StatsClient())
    db = _SyncDb(vid)
    job = Job(id=uuid4(), type="sync_tiktok", status="running", priority=10, created_at=NOW, payload={})
    out = REGISTRY["sync_tiktok"].run(sync_mod.Context(job=job, db=db, settings=SimpleNamespace(dry_run=False)))
    assert out["accounts"]["@arzakparker"] == {"followers": 12, "videos": 3, "from_app": 1}
    account = next(p for s, p in db.sql if s.startswith("insert into tiktok_accounts"))
    assert account[0] == "acc" and account[5] is True and account[6] == 12  # compte Business, 12 abonnés
    posts = {p[0]: p for s, p in db.sql if s.startswith("insert into tiktok_posts")}
    assert {k: p[2] for k, p in posts.items()} == {"z1": vid, "ext9": None, "7690741999670021398": None}
    assert posts["z1"][11] == 95  # j'aime lus en direct chez TikTok, plus récents que ceux de Zernio
    # pas de relevé pour la vidéo lue en direct : ses vues ne sont pas encore connues
    assert sum(s.startswith("insert into tiktok_post_snapshots") for s, _ in db.sql) == 2
    link = next(p for s, p in db.sql if s.startswith("update videos set tiktok = jsonb_set"))
    assert link == ("https://www.tiktok.com/@arzakparker/video/7551234567890123456", vid)  # lien TikTok rattrapé


def test_analyst_sees_tiktok_numbers_of_the_same_video():
    from worker.performance import facts_from_row, video_block

    row = {
        "id": uuid4(),
        "title": "Cabane perchée",
        "published_at": NOW - timedelta(days=2),
        "views": 900,
        "likes": 30,
        "comments": 2,
        "tt_views": 1200,
        "tt_likes": 95,
        "tt_comments": 4,
        "tt_shares": 7,
        "tt_completion_pct": 31.0,
        "tt_for_you_pct": 92.0,
    }
    block = video_block(facts_from_row(row, NOW))
    assert (
        "TikTok (même vidéo) : vues 1 200 · j'aime 95" in block
        and "jusqu'au bout 31,0 %" in block
        and "« Pour toi » 92 %" in block
    )
    assert "TikTok" not in video_block(facts_from_row({**row, "tt_views": None}, NOW))  # pas sortie sur TikTok


def test_sync_step_without_key_does_nothing(monkeypatch):
    monkeypatch.setattr(sync_mod, "zernio_key", lambda s, d: None)
    job = Job(id=uuid4(), type="sync_tiktok", status="running", priority=10, created_at=NOW, payload={})
    out = REGISTRY["sync_tiktok"].run(sync_mod.Context(job=job, db=_SyncDb(uuid4()), settings=SimpleNamespace(dry_run=False)))
    assert "skipped" in out
