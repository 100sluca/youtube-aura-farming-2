from datetime import UTC, datetime

from worker.instagram.config import parse_config
from worker.instagram.post import HASHTAGS_MAX, build_caption, post_body
from worker.tiktok.post import read_create, read_post


def test_caption_keeps_five_hashtags_and_drops_shorts():
    desc = "Une histoire vraie.\n\n#shorts #histoire #wikipedia #karma #fruits #drame #vrai #fin"
    caption = build_caption("Le Karma des Fruits", desc)
    tags = [w for w in caption.split() if w.startswith("#")]
    assert tags == ["#histoire", "#wikipedia", "#karma", "#fruits", "#drame"]
    assert len(tags) == HASHTAGS_MAX
    assert caption.startswith("Le Karma des Fruits\n\nUne histoire vraie.")


def test_caption_leaves_anchors_and_html_entities_alone():
    caption = build_caption("Titre", "Licence CC BY-SA https://fr.wikipedia.org/wiki/Page#Section &#39;")
    assert "#Section" in caption and "&#39;" in caption


def test_post_body_reel_scheduled():
    cfg = parse_config({"share_to_feed": False, "ai_label": True})
    when = datetime(2026, 10, 2, 18, 0, tzinfo=UTC)
    body = post_body(caption="c", media_url="https://x/v.mp4", account_id="ig1", cfg=cfg, when=when)
    assert body["mediaItems"] == [{"type": "video", "url": "https://x/v.mp4"}]
    assert body["platforms"] == [
        {"platform": "instagram", "accountId": "ig1", "platformSpecificData": {"shareToFeed": False, "isAiGenerated": True}}
    ]
    assert body["scheduledFor"] == when.isoformat() and "publishNow" not in body


def test_post_body_now_defaults():
    body = post_body(caption="c", media_url="u", account_id="ig1", cfg=parse_config(None), when=None)
    assert body["publishNow"] is True
    assert body["platforms"][0]["platformSpecificData"] == {"shareToFeed": True}


def test_read_instagram_entry():
    post = {
        "_id": "p1",
        "status": "published",
        "platforms": [
            {"platform": "tiktok", "status": "failed"},
            {"platform": "instagram", "status": "published", "platformPostUrl": "https://www.instagram.com/reel/abc/"},
        ],
    }
    out = read_post(post, "instagram")
    assert out.status == "published" and out.url == "https://www.instagram.com/reel/abc/" and out.post_id == "p1"
    assert read_create(201, {"post": post}, "instagram").status == "published"


def test_config_channels():
    cfg = parse_config({"channels": {"c1": {"account_id": "a", "username": "arzakparker", "enabled": True}}})
    assert cfg.for_channel("c1").username == "arzakparker"
    assert cfg.for_channel("c2") is None
