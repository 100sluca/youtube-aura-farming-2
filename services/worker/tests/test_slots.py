"""Les créneaux libres d'abord (docs/55) : premier créneau libre, lecture de YouTube Studio, vidéo prête avancée,
créneau TikTok / Instagram, sans réseau ni base."""

from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

from worker import slots
from worker.tiktok.backlog import slot_times

NOW = datetime(2026, 10, 1, 20, 0, tzinfo=UTC)  # 22 h à Paris
PUBLISH = [time(9), time(13), time(18)]
CRENEAUX = slot_times(PUBLISH, "Europe/Paris", NOW, days=6)


def paris(day: int, hour: int) -> datetime:
    return datetime(2026, 10, day, hour - 2, 0, tzinfo=UTC)  # heure d'été : Paris = UTC + 2


def item(privacy: str, publish_at: datetime | None = None) -> dict:
    st = {"privacyStatus": privacy}
    if publish_at:
        st["publishAt"] = publish_at.isoformat().replace("+00:00", "Z")
    return {"id": "yt1", "status": st, "snippet": {"publishedAt": "2026-10-01T07:00:00Z"}}


# ---- Premier créneau libre -------------------------------------------------------------------------------------------
def test_first_free_slot_fills_a_hole_before_the_last_scheduled_day():
    # trois vidéos par jour jusqu'au 05/10 ; Luca a retiré celle du 03/10 à 13 h
    busy = [s for s in CRENEAUX if paris(2, 9) <= s <= paris(5, 18) and s != paris(3, 13)]
    assert slots.first_free(CRENEAUX, busy, NOW) == paris(3, 13)


def test_first_free_slot_goes_to_the_next_day_when_all_are_taken():
    busy = [s for s in CRENEAUX if paris(2, 9) <= s <= paris(5, 18)]
    assert slots.first_free(CRENEAUX, busy, NOW) == paris(6, 9)


def test_a_post_a_few_minutes_off_still_takes_the_slot():
    busy = [paris(2, 9) + timedelta(minutes=4)]
    assert slots.first_free(CRENEAUX, busy, NOW) == paris(2, 13)


# ---- Ce que Luca change dans YouTube Studio --------------------------------------------------------------------------
def test_unlisted_in_youtube_studio_frees_the_slot():
    change = slots.youtube_change("scheduled", paris(3, 13), item("unlisted"), NOW)
    assert change and change.kind == "withdrawn" and "non répertoriée" in change.reason


def test_private_without_date_frees_the_slot_but_only_before_its_time():
    assert slots.youtube_change("scheduled", paris(3, 13), item("private"), NOW).kind == "withdrawn"
    # créneau passé et toujours privée : YouTube ne l'a pas publiée (projet API non audité), on prévient
    assert slots.youtube_change("scheduled", paris(1, 9), item("private"), NOW).kind == "late"


def test_deleted_from_youtube_frees_the_slot():
    assert slots.youtube_change("scheduled", paris(3, 13), None, NOW).kind == "withdrawn"
    assert slots.youtube_change("unpublished", None, None, NOW) is None


def test_moved_in_youtube_studio_follows_the_new_date():
    assert slots.youtube_change("scheduled", paris(3, 13), item("private", paris(3, 13)), NOW) is None
    change = slots.youtube_change("scheduled", paris(3, 13), item("private", paris(7, 9)), NOW)
    assert change and change.kind == "moved" and change.at == paris(7, 9)


def test_a_withdrawn_video_comes_back_when_luca_gives_it_a_date_again():
    change = slots.youtube_change("unpublished", None, item("private", paris(8, 18)), NOW)
    assert change and change.kind == "back" and change.at == paris(8, 18)
    assert slots.youtube_change("unpublished", None, item("unlisted"), NOW) is None
    assert slots.youtube_change("unpublished", None, item("public"), NOW).kind == "public"


class StudioDb:
    """Vidéos programmées de la chaîne ; withdraw_from_schedule et les alertes enregistrées."""

    def __init__(self, videos: list[dict], *, busy_upload: bool = False):
        self.videos = videos
        self.withdrawn: list[tuple] = []
        self.updates: list[tuple] = []
        self.alerts: list[tuple] = []
        self.busy_upload = busy_upload

    def fetch_all(self, sql, params=None):
        return self.videos

    def fetch_one(self, sql, params=None):
        if "withdraw_from_schedule" in sql:
            self.withdrawn.append(params)
            return {"ok": not self.busy_upload}
        return None

    def execute(self, sql, params=None):
        self.updates.append((sql, params))
        return 1

    def alert(self, severity, title, body=None, **refs):
        self.alerts.append((severity, title, body))


def _scheduled(yt_id: str, at: datetime, status: str = "scheduled") -> dict:
    return {
        "id": uuid4(),
        "title": "Varsovie 1939",
        "status": status,
        "youtube_video_id": yt_id,
        "at": at,
        "timezone": "Europe/Paris",
    }


def test_follow_youtube_withdraws_an_unlisted_video_and_says_which_slot_is_free():
    db = StudioDb([_scheduled("yt1", paris(3, 13)), _scheduled("yt2", paris(3, 18))])
    out = slots.follow_youtube(
        db, uuid4(), {"yt1": item("unlisted"), "yt2": item("private", paris(3, 18))}, alert_private=True, now=NOW
    )
    assert out["withdrawn"] == 1 and len(db.withdrawn) == 1
    assert "non répertoriée" in db.withdrawn[0][1]
    assert db.alerts[0][1] == "Créneau libéré : 03/10 à 13:00"


def test_follow_youtube_retries_later_when_a_tiktok_upload_is_running():
    db = StudioDb([_scheduled("yt1", paris(3, 13))], busy_upload=True)
    out = slots.follow_youtube(db, uuid4(), {"yt1": item("unlisted")}, alert_private=True, now=NOW)
    assert out["withdrawn"] == 0 and db.alerts == []


def test_follow_youtube_never_concludes_to_deletions_when_youtube_returned_nothing():
    db = StudioDb([_scheduled("yt1", paris(3, 13))])
    assert slots.follow_youtube(db, uuid4(), {}, alert_private=True, now=NOW)["withdrawn"] == 0
    assert db.withdrawn == []


def test_follow_youtube_moves_the_video_to_its_new_date():
    db = StudioDb([_scheduled("yt1", paris(3, 13))])
    out = slots.follow_youtube(db, uuid4(), {"yt1": item("private", paris(7, 9))}, alert_private=False, now=NOW)
    assert out["moved"] == 1
    sql, params = db.updates[0]
    assert "status = 'scheduled'" in sql and params[0] == paris(7, 9)


# ---- Vidéo prête avancée dans un créneau libéré ----------------------------------------------------------------------
class ReadyDb:
    def __init__(self, ready: list[dict], free: datetime | None):
        self.ready = ready
        self.free = free
        self.moved: list[tuple] = []
        self.jobs: list[tuple] = []

    def fetch_all(self, sql, params=None):
        return self.ready

    def fetch_one(self, sql, params=None):
        assert "next_free_slot" in sql
        return {"at": self.free}

    def execute(self, sql, params=None):
        (self.moved if sql.lstrip().startswith("update videos") else self.jobs).append(params)
        return 1


def test_a_ready_video_moves_up_into_the_freed_slot_and_uploads_earlier():
    v = {"id": uuid4(), "channel_id": uuid4(), "scheduled_at": paris(5, 9), "title": "Lukangol"}
    db = ReadyDb([v], free=paris(3, 13))
    assert slots.fill_free_slots(db) == 1
    assert db.moved == [(paris(3, 13), v["id"])]
    assert db.jobs == [(paris(3, 13) - slots.UPLOAD_LEAD, v["id"])]


def test_a_ready_video_never_moves_back():
    v = {"id": uuid4(), "channel_id": uuid4(), "scheduled_at": paris(5, 9), "title": "Lukangol"}
    db = ReadyDb([v], free=paris(6, 9))
    assert slots.fill_free_slots(db) == 0 and db.moved == []


# ---- TikTok et Instagram ---------------------------------------------------------------------------------------------
class PostDb:
    def __init__(self, busy: list[datetime]):
        self.busy = busy

    def fetch_one(self, sql, params=None):
        return {"channel_id": uuid4(), "publish_slots": PUBLISH, "timezone": "Europe/Paris"}

    def fetch_all(self, sql, params=None):
        return [{"at": b} for b in self.busy]


def test_tiktok_takes_its_own_first_free_slot():
    # tout est pris jusqu'au 05/10 sauf le 03/10 à 13 h (publication supprimée chez Zernio)
    busy = [s for s in CRENEAUX if paris(2, 9) <= s <= paris(5, 18) and s != paris(3, 13)]
    assert slots.free_post_slot(PostDb(busy), uuid4(), "tiktok", None, NOW) == paris(3, 13)


def test_tiktok_keeps_the_youtube_time_when_the_first_free_slot_is_too_far():
    assert slots.free_post_slot(PostDb([]), uuid4(), "instagram", None, NOW) == paris(2, 9)
    busy = [s for s in slot_times(PUBLISH, "Europe/Paris", NOW, days=10) if s > NOW]
    assert slots.free_post_slot(PostDb(busy), uuid4(), "tiktok", None, NOW) is None
