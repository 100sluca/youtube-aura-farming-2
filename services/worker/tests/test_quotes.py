"""Recette « citation » (docs/58) : script d'une scène, durée tirée du texte, texte dessiné, zoom lent, musique générée,
musique des plateformes (TikTok, Instagram), carrousel photo et relevé des blocages YouTube, sans réseau ni GPU."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from worker import copyright as cr
from worker import platform_music as pm
from worker import quotes
from worker.instagram.config import InstagramConfig
from worker.instagram.post import post_body as ig_body
from worker.models import ScriptV1
from worker.recipes import IDEA_GUIDES, SCRIPT_PROMPTS, lint_recipe_script, normalize_script, prompt_key, script_context, spec
from worker.steps.assemble import RenderPlan, build_command
from worker.tiktok import post as tp
from worker.tiktok.carousel import carousel_body, carousel_caption, carousel_title
from worker.tiktok.config import TikTokConfig

QUOTE = "Parfois, on s'en va pour réfléchir. Et parfois, on s'en va parce qu'on a réfléchi."


def _script(texts: dict[str, str] | None = None, *, scenes: int = 1, visual: str | None = None, **extra: Any) -> ScriptV1:
    sc = {
        "index": 0,
        "duration_s": 10,
        "visual_prompt": visual
        or "Oil painting with visible brush strokes, a lone figure seen from behind on a wheat-field path at dusk, calm sky",
        "motion_prompt": "the wheat sways gently",
        "on_screen_text": texts or {"fr": QUOTE},
    }
    return ScriptV1.model_validate(
        {
            "scenes": [{**sc, "index": i} for i in range(scenes)],
            "metadata": {"fr": {"title": "Parfois on s'en va 🥀", "description": QUOTE, "tags": ["citation"]}},
            "music_mood": "sentimental",
            "hook_title": {"fr": "Un titre"},
            **extra,
        }
    )


def test_recipe_is_registered_with_its_agents():
    assert spec("quote").scenes == (1, 1) and not spec("quote").narration
    assert SCRIPT_PROMPTS["quote"] is quotes.SCRIPT_PROMPT and IDEA_GUIDES["quote"] is quotes.IDEA_GUIDE
    assert prompt_key("quote") == "quote"
    assert script_context("quote") == quotes.MUSIC_BRIEF  # ni titre d'accroche ni bruitages


def test_one_scene_script_is_valid_now():
    assert len(_script().scenes) == 1  # ScriptV1 acceptait 4 scènes au moins


def test_normalize_keeps_one_scene_and_sets_duration_from_text():
    s = normalize_script(_script(scenes=3), "quote")
    assert len(s.scenes) == 1 and s.scenes[0].index == 0
    assert s.hook_title == {} and s.scenes[0].narration == {}
    assert s.music_mood == "tendre"  # sentimental → tendre (ambiances des citations)
    assert s.scenes[0].duration_s == quotes.reading_time(QUOTE)
    assert quotes.DURATION_S[0] <= s.scenes[0].duration_s <= quotes.DURATION_S[1]
    assert lint_recipe_script(s, "quote", ["fr"]) == []


def test_reading_time_bounds():
    assert quotes.reading_time("Une erreur répétée est une décision.") == quotes.DURATION_S[0]
    assert quotes.reading_time(" ".join(["mot"] * 80)) == quotes.DURATION_S[1]
    long = quotes.reading_time(" ".join(["mot"] * 27))
    assert long == round(quotes.LEAD_S + 27 / quotes.WORDS_PER_S, 2)


def test_clean_quote_and_author():
    assert quotes.clean_quote("« Une erreur répétée est une décision . »") == "Une erreur répétée est une décision."
    assert quotes.clean_quote("La colère ronge.\n- Sénèque") == "La colère ronge.\n— Sénèque"
    assert quotes.split_author("La colère ronge.\n— Sénèque") == ("La colère ronge.", "Sénèque")
    assert quotes.split_author("Pas d'auteur.") == ("Pas d'auteur.", "")


def test_lint_catches_long_quotes_hashtags_and_text_in_image():
    s = normalize_script(_script({"fr": " ".join(["mot"] * 60) + " #citation"}), "quote")
    issues = " | ".join(lint_recipe_script(s, "quote", ["fr", "en"]))
    assert "61 mots" in issues and "hashtag" in issues  # le hashtag compte comme un mot
    assert "[en] on_screen_text vide" in issues
    s = normalize_script(_script(visual="A quote written in elegant letters on a wall"), "quote")
    assert any("texte dans l'image" in i or "trop court" in i for i in lint_recipe_script(s, "quote", ["fr"]))


def test_stable_choices_per_production():
    assert quotes.move_for("abc") == quotes.move_for("abc") and quotes.move_for("abc") in quotes.MOVES
    st = quotes.text_style_for("abc", ["manuscrit"])
    assert st.key == "manuscrit"
    assert quotes.series_options({"motion": "clip", "text_styles": ["nope"]}) == {
        "motion": "clip",
        "text_styles": list(quotes.TEXT_STYLES),
    }
    assert quotes.series_options(None)["motion"] == "zoom"


def test_zoom_window_stays_inside_the_image():
    base = (1190, 2114)
    full = quotes.window(0.0, "in", base)
    assert full == (0.0, 0.0, 1190.0, 2114.0)
    end = quotes.window(1.0, "in", base)
    assert end[2] - end[0] == pytest.approx(1190 / quotes.ZOOM_MAX)
    for move in ("up", "down", "out"):
        for t in (0.0, 0.5, 1.0):
            x0, y0, x1, y1 = quotes.window(t, move, base)
            assert x0 >= -1e-6 and y0 >= -1e-6 and x1 <= base[0] + 1e-6 and y1 <= base[1] + 1e-6


def test_text_layer_is_full_frame_and_wraps(tmp_path: Path):
    dirs = [Path(__file__).resolve().parents[1] / "assets" / "fonts"]
    st = quotes.TEXT_STYLES["moderne"]
    lay = quotes.layout(QUOTE + " " + QUOTE, st, dirs)
    assert 2 <= len(lay.lines) <= 9
    x0, y0, x1, y1 = lay.box
    assert x0 >= 0 and x1 <= quotes.W and y0 > 0 and y1 < quotes.H
    png = quotes.build_layer(QUOTE + "\n— Sénèque", st, dirs, tmp_path / "q.png")
    from PIL import Image

    img = Image.open(png)
    assert img.size == (quotes.W, quotes.H) and img.mode == "RGBA"
    assert img.getbbox() is not None  # quelque chose est dessiné


def test_card_and_still_clip(tmp_path: Path):
    from PIL import Image

    bg = tmp_path / "bg.png"
    Image.new("RGB", (928, 1664), (200, 190, 170)).save(bg)  # image claire : voile sombre derrière le texte
    assert quotes.veil_alpha(Image.open(bg).convert("RGB"), (100, 600, 900, 900)) > 0.3
    card = quotes.build_card(QUOTE, quotes.TEXT_STYLES["moderne"], [], bg, tmp_path / "card.jpg")
    assert Image.open(card).size == (quotes.W, quotes.H)


def test_fit_command_slows_then_boomerangs():
    assert quotes.fit_command(Path("a.mp4"), Path("b.mp4"), 6.0, 7.0) is None
    slow = quotes.fit_command(Path("a.mp4"), Path("b.mp4"), 8.0, 5.0)
    assert slow and "setpts=1.6000*PTS" in " ".join(slow) and slow[-1] == "b.mp4"
    boom = quotes.fit_command(Path("a.mp4"), Path("b.mp4"), 13.0, 5.0)
    assert boom and "reverse" in " ".join(boom)


def test_generated_music_only_and_mood_fallback(tmp_path: Path):
    assert quotes.pick_track(tmp_path, "triste", "k") is None
    (tmp_path / "citation_reveuse").mkdir()
    (tmp_path / "citation_reveuse" / "a.mp3").write_bytes(b"x")
    assert quotes.pick_track(tmp_path, "triste", "k").name == "a.mp3"  # autre ambiance des citations
    (tmp_path / "citation_triste").mkdir()
    (tmp_path / "citation_triste" / "b.mp3").write_bytes(b"x")
    assert quotes.pick_track(tmp_path, "triste", "k").name == "b.mp3"
    assert quotes.pick_track(tmp_path, "melancolie", "k").name == "b.mp3"  # alias


def test_build_command_fades_the_quote_layer_in():
    plan = RenderPlan(clips=[Path("c.mp4")], clip_durations=[8.0], scene_durations=[8.0])
    plan.hook_png, plan.hook_filter, plan.hook_s, plan.hook_fade_in = Path("quote.png"), "overlay=0:0", 8.0, True
    cmd = " ".join(build_command(plan, Path("out.mp4"), ["-c:v", "libx264"], None))
    assert "fade=t=in" in cmd and "overlay=0:0" in cmd and "-loop 1" in cmd


# ---- Musique des plateformes ------------------------------------------------------------------------------------


class FakeDb:
    def __init__(self, rows: dict[str, Any]) -> None:
        self.rows = rows
        self.executed: list[tuple[str, Any]] = []
        self.alerts: list[tuple[str, str, str]] = []

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        for key, row in self.rows.items():
            if key in sql:
                return row(params) if callable(row) else row
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))

    def alert(self, level: str, title: str, body: str, **_: Any) -> None:
        self.alerts.append((level, title, body))


TRACKS = [
    {"id": "1", "name": "Tokyo Midnight", "artist": "x", "genres": ["HIP_HOP/RAP"], "rank": 1, "durationSec": 173},
    {"id": "2", "name": "A simple piano melody", "artist": "y", "genres": ["ALL"], "rank": 40, "durationSec": 47},
    {"id": "3", "name": "Dreamland", "artist": "z", "genres": ["EASY_LISTENING"], "rank": 21, "clip": {"durationSec": 60}},
]


def test_config_defaults_to_quotes_without_voice():
    cfg = pm.load_config(FakeDb({}))
    assert cfg.recipes == ("quote",) and cfg.volume == 60 and cfg.country == "FR"
    assert cfg.applies("quote", voiced=False) and not cfg.applies("quote", voiced=True) and not cfg.applies("story", False)
    custom = pm.load_config(FakeDb({"app_settings": {"value": {"platform_music": {"recipes": ["timelapse"], "volume": 150}}}}))
    assert custom.recipes == ("timelapse",) and custom.volume == 100


def test_tiktok_pick_prefers_calm_tracks_and_is_stable():
    picked = pm.pick_tiktok_track(TRACKS, "triste", "video-1", top=2)
    assert picked and picked["id"] in {"2", "3"}
    assert pm.pick_tiktok_track(TRACKS, "triste", "video-1", top=2) == picked
    assert pm.pick_tiktok_track([], "triste", "k") is None


def test_tiktok_settings_and_post_body():
    music = pm.tiktok_settings(TRACKS[2], 8.4, 60)
    assert music["musicSoundInfo"] == {"musicSoundId": "3", "musicSoundVolume": 60, "musicSoundStart": 0, "musicSoundEnd": 8400}
    assert music["videoOriginalSoundVolume"] == 0  # notre musique ne joue pas en double
    body = tp.post_body(caption="c", media_url="u", account_id="a", cfg=TikTokConfig(), when=None, music=music)
    assert body["tiktokSettings"]["musicSoundInfo"]["musicSoundId"] == "3"
    draft = tp.post_body(caption="c", media_url="u", account_id="a", cfg=TikTokConfig(), when=None, draft=True, music=music)
    assert "musicSoundInfo" not in draft["tiktokSettings"]  # ignoré par TikTok pour un brouillon


def test_instagram_audio_configuration():
    body = ig_body(caption="c", media_url="u", account_id="a", cfg=InstagramConfig(), when=None, audio_id="482")
    assert body["platforms"][0]["platformSpecificData"]["audioConfiguration"] == {
        "audioId": "482",
        "audioVolume": 100,
        "videoVolume": 0,
    }
    plain = ig_body(caption="c", media_url="u", account_id="a", cfg=InstagramConfig(), when=None)
    assert "audioConfiguration" not in plain["platforms"][0]["platformSpecificData"]


def test_carousel_body_photo_with_tiktok_music():
    texts = [QUOTE, "Le temps ne guérit rien.\nIl t'apprend à vivre avec."]
    body = carousel_body(
        title=carousel_title(texts),
        caption=carousel_caption(texts, ["citation", "#amour", "citation"]),
        image_urls=["u1", "u2"],
        account_id="a",
        cfg=TikTokConfig(),
        when=None,
    )
    s = body["tiktokSettings"]
    assert s["media_type"] == "photo" and s["auto_add_music"] is True and s["photo_cover_index"] == 0
    assert body["mediaItems"] == [{"type": "image", "url": "u1"}, {"type": "image", "url": "u2"}]
    assert len(body["content"]) <= 90 and "#" not in body["content"]
    assert "#citation #amour" in s["description"] and "1 à 2" in s["description"]
    draft = carousel_body(title="t", caption="c", image_urls=["u"], account_id="a", cfg=TikTokConfig(), when=None, draft=True)
    assert draft["tiktokSettings"]["draft"] is True and "auto_add_music" not in draft["tiktokSettings"]


# ---- Blocages YouTube -------------------------------------------------------------------------------------------


def test_restriction_reads_blocked_allowed_and_rejected():
    assert cr.restriction({"status": {"uploadStatus": "processed"}, "contentDetails": {}}) is None
    blocked = cr.restriction({"contentDetails": {"regionRestriction": {"blocked": ["FR", "BE"]}}, "status": {}})
    assert blocked == {"blocked": ["BE", "FR"]} and "dont la France" in cr.describe(blocked)
    assert cr.restriction({"contentDetails": {"regionRestriction": {"allowed": ["US"]}}})["allowed"] == ["US"]
    rej = cr.restriction({"status": {"uploadStatus": "rejected", "rejectionReason": "claim"}})
    assert rej == {"rejected": "claim"} and "partout" in cr.describe(rej)


def test_check_videos_alerts_once_and_names_the_track():
    state: dict[str, Any] = {"copyright": None}
    db = FakeDb({"from videos v": lambda _p: {"title": "Aouli", "music_track": "music_7", "copyright": state["copyright"]}})
    items = {"yt1": {"contentDetails": {"regionRestriction": {"blocked": ["FR"]}}, "status": {}}, "yt2": {"status": {}}}
    assert cr.check_videos(db, items, {"yt1": "v1", "yt2": "v2"}) == 1
    assert len(db.alerts) == 1 and "music_7" in db.alerts[0][2]
    state["copyright"] = {"blocked": ["FR"], "music_track": "music_7"}
    cr.check_videos(db, items, {"yt1": "v1"})
    assert len(db.alerts) == 1  # même blocage : pas de nouvelle alerte


def test_settings_like_namespace_font_dirs():
    dirs = quotes.font_dirs(SimpleNamespace(data_dir=Path("d"), fonts_dir=Path("f")))
    assert dirs[0] == Path("d") / "fonts" and dirs[1] == Path("f")


def test_music_window_skips_a_quiet_intro():
    points = [(t / 10, -40.0 if t < 150 else -18.0) for t in range(0, 600)]
    start, lufs = quotes.music_window(points, 9.0)
    assert 12.0 <= start <= 15.0 and lufs > -25
    assert quotes.music_window([], 9.0) is None
