"""Modèle de montage (onglet Montage, docs/23-montage.md) : valeurs d'origine, positions, polices, fonds, rendu exact."""

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from worker.hooktitle import HookStyle, render_image
from worker.models import ScriptV1, WordTiming
from worker.montage import DEFAULTS_FILE, MontageTemplate, hook_text, load_template, subtitle_presets
from worker.steps.assemble import RenderPlan, apply_template
from worker.steps.montage_preview import MontagePreviewStep
from worker.subtitles import BUILTIN_PROFILES, FontRegistry, TitleStyle, build_ass, write_subtitles

WIN_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
WORDS = [WordTiming(text="Personne", start=0.0, end=0.5), WordTiming(text="ne", start=0.5, end=0.7)]


def _style(ass: str, name: str) -> list[str]:
    return next(line for line in ass.splitlines() if line.startswith(f"Style: {name},")).split(",")


def _dialogues(ass: str, layer: int) -> list[str]:
    return [line for line in ass.splitlines() if line.startswith(f"Dialogue: {layer},")]


def test_defaults_file_matches_the_code():
    """Le dashboard lit assets/montage/defaults.json : il doit rester identique au modèle d'origine et aux profils du code."""
    defaults = json.loads(DEFAULTS_FILE.read_text(encoding="utf-8"))
    assert defaults["template"] == MontageTemplate().model_dump(mode="json")
    assert defaults["subtitle_presets"] == subtitle_presets()


def test_origin_template_reproduces_the_previous_look():
    t = MontageTemplate()
    impact = BUILTIN_PROFILES["impact"]
    same = (
        "font_family",
        "font_size",
        "bold",
        "text_transform",
        "highlight_mode",
        "highlight_color",
        "outline_width",
        "shadow_opacity",
        "max_words",
        "max_chars",
        "animation",
        "background",
    )
    assert all(getattr(t.profile(), k) == getattr(impact, k) for k in same)
    assert (t.subtitles.x, t.subtitles.y) == (540, round(0.52 * 1920))  # « center » du profil impact
    # Titre d'accroche sur toutes les vidéos ; textes à l'écran sur les chantiers et les visites seulement (Luca, 28/09)
    assert (t.hook.formats, t.titles.formats) == (["story", "timelapse", "tour"], ["timelapse", "tour"])
    ts = t.title_style()
    assert (ts.size, ts.y, ts.style, ts.padding, ts.transform) == (76, 1330, "box", 16, "uppercase")
    # Titre d'accroche : pixel pour pixel celui de MJClipIt (Arial Black 64, plaque #111111, marges 22 × 10)
    pytest.importorskip("PIL")
    text = "Ils ont transformé ce terrain abandonné en villa de rêve"
    assert render_image(text, t.hook_style(FontRegistry())).tobytes() == render_image(text, HookStyle()).tobytes()


def test_subtitles_and_titles_follow_the_template_positions():
    t = MontageTemplate.model_validate(
        {
            "subtitles": {"x": 300, "y": 1500, "background": "box", "background_padding": 20},
            "titles": {"x": 700, "y": 400, "background": "outline", "outline_width": 5, "uppercase": False},
        }
    )
    ass = build_ass([WORDS], t.profile(), [(0.0, 1.0, "Salon")], title_style=t.title_style())
    assert all("\\pos(300,1500)" in d for d in _dialogues(ass, 2))
    main = _style(ass, "Main")
    assert (main[15], main[17]) == ("4", "20")  # boîte unique ; libass prend Shadow comme marge de la boîte
    title = _style(ass, "Title")
    assert (title[15], title[16]) == ("1", "5")  # texte contouré, sans boîte
    assert _dialogues(ass, 3)[0].endswith("{\\an5\\pos(700,400)\\fad(150,150)}Salon")  # casse d'origine gardée


def test_too_wide_scene_text_shrinks_instead_of_leaving_the_frame():
    ts = TitleStyle(size=120)
    ass = build_ass([], BUILTIN_PROFILES["impact"], [(0.0, 1.0, "Suite parentale avec vue sur le pic")], title_style=ts)
    dialogue = _dialogues(ass, 3)[0]
    assert "\\fs" in dialogue and int(dialogue.split("\\fs")[1].split("}")[0]) < 120
    short = build_ass([], BUILTIN_PROFILES["impact"], [(0.0, 1.0, "Jour 12")], title_style=ts)
    assert "\\fs" not in _dialogues(short, 3)[0]


def test_title_font_is_copied_next_to_the_subtitles_and_stale_fonts_removed(tmp_path):
    fonts = FontRegistry.scan(Path(__file__).parent.parent / "assets" / "fonts")
    (tmp_path / "fonts").mkdir()
    (tmp_path / "fonts" / "ancienne.ttf").write_bytes(b"x")  # police d'un montage précédent
    profile = BUILTIN_PROFILES["impact"]
    flt = write_subtitles(tmp_path, "[Script Info]\n", profile, fonts, TitleStyle(font_family="Bebas Neue", bold=False))
    assert flt == "subtitles=subtitles.ass:fontsdir=fonts"
    assert sorted(p.name for p in (tmp_path / "fonts").iterdir()) == ["BebasNeue-Regular.ttf", "Montserrat-SemiBold.ttf"]


@pytest.mark.skipif(not (WIN_FONTS / "segoeuib.ttf").is_file(), reason="polices Windows absentes")
def test_font_pick_prefers_the_exact_family_and_the_right_weight():
    fonts = FontRegistry.scan(
        *(
            WIN_FONTS / n
            for n in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguibl.ttf", "arial.ttf", "arialbd.ttf", "ariblk.ttf")
        )
    )
    assert fonts.pick("Segoe UI", True).path.name == "segoeuib.ttf"
    assert fonts.pick("Segoe UI", False).path.name == "segoeui.ttf"
    assert fonts.pick("Segoe UI Black", True).path.name == "seguibl.ttf"
    assert fonts.pick("Arial Black", True).path.name == "ariblk.ttf" and not fonts.pick("Arial Black", True).synthetic_bold
    assert fonts.pick("Arial", True).path.name == "arialbd.ttf"
    # une police déjà grasse est demandée en gras à libass, pour qu'il ne prenne pas l'« Arial » normal du même nom
    profile = BUILTIN_PROFILES["impact"].model_copy(update={"font_family": "Arial", "bold": True})
    assert _style(build_ass([WORDS], profile, fonts=fonts), "Main")[7] == "-1"


def test_hook_alignment_and_backgrounds():
    pytest.importorskip("PIL")
    text = "Tu paierais combien pour cette villa de rêve ?"
    left = render_image(text, HookStyle(x=300, width_pct=0.5, align="left"))
    cols = [x for x in range(1080) if left.getpixel((x, 20))[3] == 255]
    assert cols and cols[0] < 100 and cols[-1] < 600  # bloc gardé à gauche, première ligne alignée à gauche
    plate = render_image(text, HookStyle(width_pct=0.6, line_spacing=1.4))
    block = render_image(text, HookStyle(width_pct=0.6, line_spacing=1.4, bg_mode="block"))
    column = [plate.getpixel((540, y))[3] for y in range(plate.size[1])]
    gap = next(y for y in range(1, len(column)) if column[y - 1] == 255 and column[y] == 0)  # sous la première plaque
    assert block.getpixel((540, gap + 2))[3] == 255  # une seule plaque : l'interligne est couvert
    ghost = render_image(text, HookStyle(bg_opacity=0.5))
    alphas = ghost.getchannel("A").histogram()
    assert alphas[255] > 0 and sum(alphas[120:137]) > 5000  # plaque à moitié transparente, texte plein
    bare = render_image(text, HookStyle(bg=False))
    assert bare.getpixel((2, 2))[3] == 0


def test_apply_template_shows_layers_per_format(tmp_path):
    script = ScriptV1.model_validate(
        {
            "scenes": [{"index": i, "duration_s": 3, "visual_prompt": "v", "motion_prompt": "m"} for i in range(4)],
            "metadata": {"fr": {"title": "Ce miroir cachait un dressing 😱", "description": "d"}},
        }
    )
    assert hook_text(script, "fr") == "Ce miroir cachait un dressing"  # récit écrit sans titre d'accroche : titre de la vidéo

    def plan() -> RenderPlan:
        return RenderPlan(
            clips=[Path("c.mp4")] * 4,
            clip_durations=[3.0] * 4,
            scene_durations=[3.0] * 4,
            words_by_scene=[WORDS],
            titles=[(0.0, 3.0, "1 an plus tard")],
        )

    pytest.importorskip("PIL")
    story = plan()
    apply_template(story, MontageTemplate(), "story", hook=hook_text(script, "fr"), workdir=tmp_path, fonts=FontRegistry())
    # d'origine, un récit : titre d'accroche et sous-titres, pas de texte à l'écran en plus
    assert story.hook_png and story.hook_png.exists() and story.words_by_scene and story.titles == []
    custom = MontageTemplate.model_validate(
        {"hook": {"formats": ["tour"]}, "subtitles": {"enabled": False}, "titles": {"formats": ["story"]}}
    )
    other = plan()
    apply_template(other, custom, "story", hook=hook_text(script, "fr"), workdir=tmp_path, fonts=FontRegistry())
    assert other.hook_png is None and other.words_by_scene == [] and other.titles == [(0.0, 3.0, "1 an plus tard")]


class _Db:
    def __init__(self, row=None, error=None):
        self.row, self.error = row, error

    def fetch_one(self, sql, params=None):
        if self.error:
            raise self.error
        return self.row


def test_load_template_falls_back_to_the_origin():
    t, name = load_template(_Db({"name": "Ma patte", "template": {"hook": {"y": 400, "formats": ["story"]}}}))
    assert (name, t.hook.y, t.hook.formats, t.subtitles.y) == ("Ma patte", 400, ["story"], 998)
    assert load_template(_Db(None))[1] == "Modèle d'origine"
    assert load_template(_Db({"name": "Cassé", "template": {"hook": {"y": "haut"}}}))[1] == "Modèle d'origine"
    assert load_template(_Db(error=RuntimeError("relation montage_templates does not exist")))[1] == "Modèle d'origine"


def _preview_ctx(tmp_path, payload, dry_run):
    settings = SimpleNamespace(
        data_dir=tmp_path, fonts_dir=Path(__file__).parent.parent / "assets" / "fonts", video_encoder="cpu", dry_run=dry_run
    )
    job = SimpleNamespace(id=uuid4(), payload=payload)
    return SimpleNamespace(job=job, db=_Db(None), settings=settings, progress=lambda *a, **k: None)


def test_montage_preview_dry_run_writes_the_files(tmp_path):
    ctx = _preview_ctx(tmp_path, {"template": {"hook": {"formats": ["story"]}}, "recipe": "story"}, dry_run=True)
    res = MontagePreviewStep().run(ctx)
    assert Path(res["path"]).exists() and Path(res["poster"]).exists() and res["recipe"] == "story"
    assert not (tmp_path / "previews" / "montage" / str(ctx.job.id)).exists()  # dossier de travail effacé


def test_every_step_is_a_known_job_type():
    """Un type de job absent de models.JobType fait échouer claim_jobs après avoir pris le job (resté « running »)."""
    from typing import get_args

    from worker.config import Settings
    from worker.models import JobType
    from worker.steps import REGISTRY

    assert set(REGISTRY) <= set(get_args(JobType))
    assert set(Settings.model_fields["worker_job_types"].default.split(",")) <= set(REGISTRY)


def test_preview_lane_runs_jobs_while_the_main_loop_is_busy(monkeypatch):
    """Le rendu exact a son propre fil : il n'attend pas la fin d'un clip de 10 min sur la voie GPU."""
    import threading

    from worker import main

    ran, jobs = [], [[SimpleNamespace(id="j1", type="montage_preview")]]
    busy, stop = threading.Event(), threading.Event()

    class Db:
        def claim_jobs(self, worker, types, n):
            assert worker.endswith("/preview") and types == ["montage_preview"] and n == 1
            return jobs.pop() if jobs else []

    def fake_run(job, db, settings):
        assert busy.is_set()  # une relance attend la fin de ce job
        ran.append(job.id)
        stop.set()

    monkeypatch.setattr(main, "run_job", fake_run)
    monkeypatch.setattr(stop, "wait", lambda timeout=None: stop.is_set())
    main.preview_lane(Db(), SimpleNamespace(worker_id="w"), ["montage_preview"], busy, stop)
    assert ran == ["j1"] and not busy.is_set()
    assert MontagePreviewStep.lane == "preview"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_montage_preview_real_render(tmp_path):
    pytest.importorskip("PIL")
    payload = {
        "template": {"hook": {"formats": ["story"], "y": 300}, "titles": {"font_family": "Bebas Neue", "bold": False}},
        "recipe": "story",
        "duration_s": 3,
        "texts": {"hook": "Regarde ce qui se cache derrière"},
    }
    res = MontagePreviewStep().run(_preview_ctx(tmp_path, payload, dry_run=False))
    assert Path(res["path"]).stat().st_size > 10_000 and Path(res["poster"]).stat().st_size > 5_000
