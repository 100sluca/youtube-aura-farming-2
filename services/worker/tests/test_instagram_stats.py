"""Réseaux et comptes (docs/62) : lecture des statistiques Instagram de Zernio et relevé par le step sync_instagram, pour
les deux comptes Zernio (@arzakparker et « Paf, j'achète »), sans réseau ni base."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

from worker import scheduler
from worker.instagram import stats as ist
from worker.models import Job
from worker.steps import REGISTRY
from worker.steps import sync_instagram as sync_mod
from worker.tiktok.zernio import ZernioError

NOW = datetime(2026, 10, 4, 11, 0, tzinfo=UTC)
IG_USER = "28831063366579885"


def _reel(**over):
    """Entrée de GET /analytics pour un Reel publié par l'appli (forme vue le 04/10)."""
    item = {
        "postId": "6ac233647a0e51e75194d27a",
        "latePostId": "6abe7fbcff3b2932029349cf",
        "status": "published",
        "content": "Il pouvait se venger. Il a fait mieux 🐕\n\n#karma #histoire",
        "publishedAt": "2026-10-02T16:03:59.000Z",
        "isExternal": True,
        "thumbnailUrl": "https://cdn.example/reel.jpg",
        "platformAnalytics": [
            {
                "platform": "instagram",
                "status": "published",
                "platformPostId": "18334833781276604",
                "accountId": "zmain",
                "platformPostUrl": "https://www.instagram.com/reel/Dd_3njFDkTk/",
                "syncStatus": "synced",
                "analytics": {
                    "views": 156,
                    "reach": 138,
                    "likes": 2,
                    "comments": 0,
                    "shares": 0,
                    "saves": 1,
                    "follows": None,
                    "igReelsAvgWatchTime": 18198,
                    "igReelsVideoViewTotalTime": 2638820,
                    "reelsSkipRate": 39.1,
                    "videoDurationSeconds": 74,
                    "lastUpdated": "2026-10-04 11:09:04",
                },
            }
        ],
    }
    item.update(over)
    return item


LIVE_REEL = {
    "id": "18334833781276604",
    "message": "Il pouvait se venger. Il a fait mieux 🐕",
    "createdTime": "2026-10-02T16:03:59.000Z",
    "picture": "https://cdn.example/live.jpg",
    "permalink": "https://www.instagram.com/reel/Dd_3njFDkTk/",
    "mediaType": "video",
    "likeCount": 3,
    "commentCount": 1,
}
LIVE_PAF = {
    "id": "17990000000000001",
    "message": "Bonjour, c'est vendredi 🕺",
    "createdTime": "2026-10-09T05:00:02.000Z",
    "permalink": "https://www.instagram.com/reel/PafVendredi1/",
    "mediaType": "video",
    "likeCount": 9,
    "commentCount": 2,
}
PHOTO = {"id": "1799", "mediaType": "image", "permalink": "https://www.instagram.com/p/Photo1/"}


def _account(zid, ig=IG_USER, username="arzakparker"):
    return {
        "_id": zid,
        "platform": "instagram",
        "platformUserId": ig,
        "username": username,
        "displayName": "Arzak",
        "profilePicture": "https://cdn.example/avatar.jpg",
        "profileUrl": f"https://instagram.com/{username}",
        "followersCount": 1,
        "metadata": {"profileData": {"extraData": {"mediaCount": 2, "accountType": "MEDIA_CREATOR", "followsCount": 15}}},
    }


# ---- Lecture des réponses -----------------------------------------------------------------------------------------
def test_parse_reel_keeps_instagram_id_and_reel_metrics():
    p = ist.parse_post(_reel(), "zmain")
    assert p.key == "18334833781276604"  # id Instagram : le même pour les deux comptes Zernio
    assert p.zernio_post_id == "6abe7fbcff3b2932029349cf"  # = videos.instagram->>'post_id'
    assert p.is_external is False  # copie synchronisée d'une publication de l'appli
    assert (p.views, p.reach, p.likes, p.saves, p.follows) == (156, 138, 2, 1, None)
    assert p.avg_watch_s == 18.2 and p.total_watch_s == 2638.82 and p.duration_s == 74
    assert p.skip_rate_pct == 39.1 and p.url == "https://www.instagram.com/reel/Dd_3njFDkTk/"
    assert ist.shortcode_of(p.url) == "Dd_3njFDkTk" and ist.shortcode_of("https://instagram.com/p/Abc-1/?x") == "Abc-1"


def test_unknown_watch_numbers_stay_unknown_and_unpublished_is_ignored():
    bare = _reel()
    bare["platformAnalytics"][0]["analytics"] |= {"igReelsAvgWatchTime": 0, "igReelsVideoViewTotalTime": 0, "reelsSkipRate": 0}
    p = ist.parse_post(bare, "zmain")
    assert p.avg_watch_s is None and p.total_watch_s is None and p.skip_rate_pct is None  # 0 = pas encore donné
    scheduled = _reel()
    scheduled["platformAnalytics"][0]["status"] = "scheduled"
    assert ist.parse_post(scheduled, "zmain") is None
    assert ist.parse_post(_reel(platform="tiktok", platformAnalytics=[]), "zmain") is None


def test_live_reels_missing_from_zernio_list_are_found():
    posts = [ist.parse_post(_reel(), "zmain")]
    live = [p for p in (ist.parse_live_post(x) for x in (LIVE_REEL, LIVE_PAF, PHOTO)) if p]
    assert [lp.key for lp in live] == ["18334833781276604", "17990000000000001"]  # la photo n'est pas suivie
    assert [lp.key for lp in ist.missing_live(posts, live)] == ["17990000000000001"]
    ist.refresh_live_counters(posts, live)
    assert (posts[0].likes, posts[0].comments, posts[0].views) == (3, 1, 156)  # j'aime lus en direct, vues de Zernio


def test_account_info_uses_instagram_id_and_insights():
    info = ist.account_info(_account("zpaf"))
    assert info["id"] == IG_USER and info["zernio_id"] == "zpaf"
    assert (info["followers"], info["following"], info["media_count"], info["account_type"]) == (1, 15, 2, "MEDIA_CREATOR")
    resp = {"metrics": {"views": {"total": 316}, "reach": {"total": 260}, "total_interactions": {"total": 12}}}
    assert ist.parse_insights(resp) == {"views_28d": 316, "reach_28d": 260, "interactions_28d": 12, "engaged_28d": None}


# ---- Relevé par le step sync_instagram ----------------------------------------------------------------------------
class _SyncDb:
    def __init__(self, video_id):
        self.video_id = video_id
        self.sql: list[tuple[str, tuple]] = []

    def fetch_all(self, sql, params=None):
        if "from videos where instagram is not null" in sql:
            return [{"id": self.video_id, "post_id": "6abe7fbcff3b2932029349cf", "url": None}]
        if "from paf_posts where post_id is not null" in sql:
            return [{"friday": date(2026, 10, 9), "post_id": "zpafpost", "url": "https://www.instagram.com/reel/PafVendredi1/"}]
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


class _Client:
    """Deux comptes Zernio : le principal voit @arzakparker ; celui de « Paf, j'achète » voit le même compte (état du
    04/10) et @paf.jachete."""

    def __init__(self, key):
        self.key = key
        self.lookups: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def accounts(self):
        if self.key == "main":
            return [_account("zmain"), {"_id": "ztt", "platform": "tiktok", "username": "arzakparker"}]
        return [_account("zpaf1"), _account("zpaf2", ig="999", username="paf.jachete")]

    def instagram_insights(self, account_id):
        return {"metrics": {"views": {"total": 316}, "reach": {"total": 260}}}

    def sync_external(self, account_id):
        return {"postsFound": 2}

    def post_analytics(self, account_id, platform="tiktok"):
        assert platform == "instagram"
        return ([_reel()] if account_id == "zmain" else []), {"lastSync": "2026-10-04T11:09:04.943Z"}

    def account_posts(self, account_id):
        return [LIVE_REEL] if account_id == "zmain" else [LIVE_PAF]

    def post_analytics_one(self, post_id):
        self.lookups.append(post_id)
        if post_id == "17990000000000001":  # le Reel du vendredi, absent de la liste : lu un par un
            reel = _reel(
                latePostId="zpafpost",
                content="Bonjour, c'est vendredi 🕺",
                publishedAt="2026-10-09T05:00:02.000Z",
            )
            reel["platformAnalytics"][0] |= {
                "platformPostId": post_id,
                "accountId": "zpaf2",
                "platformPostUrl": "https://www.instagram.com/reel/PafVendredi1/",
            }
            return 200, reel
        raise ZernioError("inconnu", status=404)


def test_sync_step_reads_both_zernio_accounts_once_per_instagram_account(monkeypatch):
    vid = uuid4()
    clients: dict[str, _Client] = {}
    monkeypatch.setattr(sync_mod, "zernio_key", lambda s, d: "main")
    monkeypatch.setattr(sync_mod, "paf_key", lambda s, d: "paf")
    monkeypatch.setattr(sync_mod, "ZernioClient", lambda key: clients.setdefault(key, _Client(key)))
    db = _SyncDb(vid)
    job = Job(id=uuid4(), type="sync_instagram", status="running", priority=10, created_at=NOW, payload={})
    out = REGISTRY["sync_instagram"].run(sync_mod.Context(job=job, db=db, settings=SimpleNamespace(dry_run=False)))

    assert set(out["accounts"]) == {"@arzakparker", "@paf.jachete"}  # @arzakparker relevé une seule fois
    accounts = [p for s, p in db.sql if s.startswith("insert into instagram_accounts")]
    assert [a[0] for a in accounts] == [IG_USER, "999"]
    assert accounts[0][9] == 316 and accounts[0][13].obj == {"main": "zmain"}
    # le même compte vu par le second compte Zernio : son id Zernio est noté, rien n'est relu
    assert "update instagram_accounts set zernio_ids = zernio_ids || %s where id = %s" in [s for s, _ in db.sql]
    noted = next(p for s, p in db.sql if s.startswith("update instagram_accounts set zernio_ids"))
    assert noted[0].obj == {"paf": "zpaf1"} and noted[1] == IG_USER

    posts = {p[0]: p for s, p in db.sql if s.startswith("insert into instagram_posts")}
    assert posts["18334833781276604"][2] == vid and posts["18334833781276604"][3] is None  # vidéo de l'appli
    assert posts["17990000000000001"][2] is None and posts["17990000000000001"][3] == date(2026, 10, 9)  # vendredi
    assert posts["18334833781276604"][13] == 3  # j'aime lus en direct
    assert clients["paf"].lookups == ["17990000000000001"] and clients["main"].lookups == []
    assert sum(s.startswith("insert into instagram_post_snapshots") for s, _ in db.sql) == 2
    link = next(p for s, p in db.sql if s.startswith("update videos set instagram = jsonb_set"))
    assert link == ("https://www.instagram.com/reel/Dd_3njFDkTk/", vid)  # lien du Reel rattrapé


def test_sync_step_without_any_key_does_nothing(monkeypatch):
    monkeypatch.setattr(sync_mod, "zernio_key", lambda s, d: None)
    monkeypatch.setattr(sync_mod, "paf_key", lambda s, d: None)
    job = Job(id=uuid4(), type="sync_instagram", status="running", priority=10, created_at=NOW, payload={})
    out = REGISTRY["sync_instagram"].run(sync_mod.Context(job=job, db=_SyncDb(uuid4()), settings=SimpleNamespace(dry_run=False)))
    assert "skipped" in out


def test_one_refused_key_does_not_stop_the_other(monkeypatch):
    class _Refused(_Client):
        def accounts(self):
            raise ZernioError("Zernio comptes : 401 clé refusée", status=401)

    monkeypatch.setattr(sync_mod, "zernio_key", lambda s, d: "main")
    monkeypatch.setattr(sync_mod, "paf_key", lambda s, d: "paf")
    monkeypatch.setattr(sync_mod, "ZernioClient", lambda key: _Refused(key) if key == "paf" else _Client(key))
    job = Job(id=uuid4(), type="sync_instagram", status="running", priority=10, created_at=NOW, payload={})
    out = REGISTRY["sync_instagram"].run(sync_mod.Context(job=job, db=_SyncDb(uuid4()), settings=SimpleNamespace(dry_run=False)))
    assert list(out["accounts"]) == ["@arzakparker"] and "401" in out["errors"][0]


def test_hourly_counters_enqueue_once(monkeypatch):
    enqueued = []
    db = SimpleNamespace(fetch_one=lambda sql, params=None: None, enqueue=lambda t, **k: enqueued.append((t, k)))
    monkeypatch.setattr(scheduler, "zernio_key", lambda s, d: None)
    monkeypatch.setattr(scheduler, "paf_key", lambda s, d: "paf")
    scheduler.instagram_counters(db, SimpleNamespace())
    assert enqueued == [("sync_instagram", {"payload": {"source": "horaire"}, "priority": 86})]
