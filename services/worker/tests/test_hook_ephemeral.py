"""Titre d'accroche éphémère (demande de Luca, 29/09, docs/34 §1) : dans Bibliothèque → Retoucher, le titre peut rester
toute la vidéo (comme avant) ou s'afficher quelques secondes puis s'effacer en fondu. La durée vit dans
videos.retouch.hook_display et prime sur celle du modèle de montage ; le montage lit l'image du titre en boucle le temps
de son affichage, l'efface en fondu, puis laisse passer la vidéo seule."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from worker.montage import HookLayer, MontageTemplate
from worker.retouch import HookDisplay, Retouch
from worker.steps.assemble import RenderPlan, apply_template, build_command, render
from worker.subtitles import FontRegistry


def _plan(**kw) -> RenderPlan:
    return RenderPlan(
        **{**dict(clips=[Path("c0.mp4"), Path("c1.mp4")], clip_durations=[5.0, 5.0], scene_durations=[5.0, 5.0]), **kw}
    )


def test_the_retouch_keeps_the_display_time_apart_from_the_text():
    r = Retouch.model_validate({"hook_display": {"duration_s": 6}})
    assert r and r.hook_display == HookDisplay(duration_s=6) and r.parts() == ["titre d'accroche éphémère (6 s)"]
    assert Retouch.model_validate({"hook_display": {"duration_s": None}}).parts() == ["titre d'accroche sur toute la vidéo"]
    assert Retouch().hook_display is None and not Retouch()  # absent : la durée du modèle de montage
    assert Retouch.model_validate({"hook_title": "Il cache sa mère", "hook_display": {"duration_s": 5.5}}).parts() == [
        "titre d'accroche",
        "titre d'accroche éphémère (5.5 s)",
    ]


def test_the_retouch_display_time_wins_over_the_template(tmp_path):
    pytest.importorskip("PIL")
    fonts = FontRegistry()
    plan = _plan()
    apply_template(plan, MontageTemplate(), "story", hook="Il cache sa mère à son mariage", workdir=tmp_path, fonts=fonts)
    assert plan.hook_png and plan.hook_s is None and plan.hook_filter == "overlay=(W-w)/2:150"  # toute la vidéo
    apply_template(
        plan,
        MontageTemplate(),
        "story",
        hook="Il cache sa mère",
        workdir=tmp_path,
        fonts=fonts,
        hook_display=HookDisplay(duration_s=6),
    )
    assert plan.hook_s == 6.0 and plan.hook_filter == "overlay=(W-w)/2:150:eof_action=pass"
    three = MontageTemplate(hook=HookLayer(duration_s=3))  # le modèle dit 3 s ; la retouche : toute la vidéo
    apply_template(plan, three, "story", hook="Il cache sa mère", workdir=tmp_path, fonts=fonts)
    assert plan.hook_s == 3.0
    apply_template(
        plan, three, "story", hook="Il cache sa mère", workdir=tmp_path, fonts=fonts, hook_display=HookDisplay(duration_s=None)
    )
    assert plan.hook_s is None
    apply_template(
        plan,
        MontageTemplate(),
        "story",
        hook="Il cache sa mère",
        workdir=tmp_path,
        fonts=fonts,
        hook_display=HookDisplay(duration_s=10),
    )  # aussi long que la vidéo : toute la vidéo
    assert plan.hook_s is None and plan.hook_filter == "overlay=(W-w)/2:150"


def test_an_ephemeral_hook_is_looped_for_its_time_then_fades_out():
    cmd = build_command(
        _plan(hook_png=Path("hook.png"), hook_s=6.0, hook_filter="overlay=(W-w)/2:150:eof_action=pass"),
        Path("o.mp4"),
        [],
        "subtitles=subtitles.ass",
    )
    i = cmd.index("hook.png")
    assert cmd[i - 7 : i + 1] == ["-loop", "1", "-framerate", "30", "-t", "6.000", "-i", "hook.png"]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "[2:v]format=rgba,fade=t=out:st=5.600:d=0.400:alpha=1[hook]" in graph
    assert "[vsub][hook]overlay=(W-w)/2:150:eof_action=pass[vout]" in graph
    still = build_command(_plan(hook_png=Path("hook.png")), Path("o.mp4"), [], None)
    assert "-loop" not in still and "[vcat][2:v]overlay=(W-w)/2:150[vout]" in still[still.index("-filter_complex") + 1]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_real_render_shows_the_hook_then_only_the_video(tmp_path):
    pytest.importorskip("PIL")
    clip = tmp_path / "gris.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=108x192:r=30:d=4", str(clip)], check=True)
    plan = RenderPlan(clips=[clip], clip_durations=[4.0], scene_durations=[4.0])
    apply_template(
        plan,
        MontageTemplate(),
        "story",
        hook="Il cache sa mère à son mariage",
        workdir=tmp_path,
        fonts=FontRegistry(),
        hook_display=HookDisplay(duration_s=1.5),
    )
    out = tmp_path / "final.mp4"
    render(plan, out, fonts=FontRegistry(), encoder="cpu")

    def dark_share(t: float) -> float:
        """Part de pixels sombres (plaque #111111 du titre) dans la bande du titre, à l'instant t."""
        png = tmp_path / f"f{t}.png"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-ss",
                str(t),
                "-i",
                str(out),
                "-frames:v",
                "1",
                "-vf",
                "crop=1080:160:0:150",
                str(png),
            ],
            check=True,
        )
        from PIL import Image

        hist = Image.open(png).convert("L").histogram()
        return sum(hist[:60]) / sum(hist)

    assert dark_share(0.5) > 0.1  # le titre est là
    assert dark_share(3.0) < 0.01  # après 1,5 s et le fondu : la vidéo seule
