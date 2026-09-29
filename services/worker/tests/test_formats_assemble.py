"""Montage des formats visuels (docs/15) : transitions, accélération, interpolation, titre d'accroche, bruitages."""

import shutil
import subprocess
from pathlib import Path

import pytest

from worker.models import ScriptV1
from worker.montage import MontageTemplate, hook_text
from worker.recipes import normalize_script
from worker.sfx import SfxCue
from worker.steps.assemble import TRAILS, RenderPlan, apply_recipe, apply_template, build_command
from worker.subtitles import BUILTIN_PROFILES, FontRegistry, build_ass


def _graph(cmd: list[str]) -> str:
    return cmd[cmd.index("-filter_complex") + 1]


def _plan(**kw) -> RenderPlan:
    base = dict(clips=[Path(f"c{i}.mp4") for i in range(3)], clip_durations=[5.06, 5.06, 5.06], scene_durations=[4.0, 4.0, 5.0])
    return RenderPlan(**{**base, **kw})


def test_whip_transitions_overlap_scenes_and_shorten_the_video():
    plan = _plan(transitions=[("whip", 0.35), ("cut", 0.0), ("cut", 0.0)])
    assert plan.overlaps == [0.35, 0.0] and plan.starts == [0.0, 3.65, 7.65] and plan.total_s == 12.65
    graph = _graph(build_command(plan, Path("o.mp4"), ["-c:v", "libx264"], None))
    assert "[v0][v1]xfade=transition=hblur:duration=0.350:offset=3.650[j1]" in graph
    assert "[j1][v2]concat=n=2:v=1:a=0,settb=1/30[j2]" in graph and "[j2]null[vcat]" in graph
    assert "concat=n=3" not in graph


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg absent")
def test_real_render_with_a_cut_before_a_whip(tmp_path):
    """Régression du 25/09 : une coupe (concat) avant un coup de fouet (xfade) cassait le montage de la visite
    (bases de temps différentes). Rendu FFmpeg réel, clips synthétiques minuscules."""
    clips = []
    for i in range(3):
        c = tmp_path / f"c{i}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=64x112:r=16:d=1.5",
                "-vf",
                f"hue=h={i * 90}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(c),
            ],
            check=True,
        )
        clips.append(c)
    plan = RenderPlan(
        clips=clips,
        clip_durations=[1.5] * 3,
        scene_durations=[1.0, 1.0, 1.0],
        transitions=[("cut", 0.0), ("whip", 0.3), ("cut", 0.0)],
        interpolate=True,
    )
    out = tmp_path / "final.mp4"
    subprocess.run(build_command(plan, out, ["-c:v", "libx264", "-preset", "ultrafast"], None), check=True, capture_output=True)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert float(probe.stdout) == pytest.approx(plan.total_s, abs=0.1)


def test_first_last_clips_are_sped_up_not_cut_and_tours_are_interpolated():
    graph = _graph(build_command(_plan(fit=["speed", "speed", "trim"]), Path("o.mp4"), [], None))
    assert "setpts=0.7905*PTS" in graph  # 5,06 s → 4 s : le clip atteint son image finale
    assert "[2:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p,fps=30" in graph
    smooth = _graph(build_command(_plan(interpolate=True), Path("o.mp4"), [], None))
    assert "[0:v]minterpolate=fps=30:mi_mode=mci" in smooth  # interpolé à la résolution native, puis agrandi
    assert smooth.index("minterpolate") < smooth.index("scale=1080:1920")


def test_timelapse_stages_are_accelerated_with_trails():
    plan = _plan(scene_durations=[1.5, 1.2, 4.0], fit=["speed", "speed", "trim"], max_speedup=4.5, trails=True)
    graph = _graph(build_command(plan, Path("o.mp4"), [], None))
    assert f"setpts=0.2964*PTS,{TRAILS}" in graph  # 5,06 s → 1,5 s : ×3,4, les ouvriers laissent une traînée
    assert "setpts=0.2372*PTS" in graph  # 1,2 s : ×4,2, toujours sous le plafond de la recette
    assert graph.count("tmix") == 2  # la révélation (coupée, pas accélérée) reste nette
    capped = _graph(
        build_command(
            _plan(scene_durations=[0.5, 4.0, 4.0], fit=["speed", "trim", "trim"], max_speedup=4.5), Path("o.mp4"), [], None
        )
    )
    assert "setpts=0.2222*PTS" in capped and "tmix" not in capped  # ×4,5 au plus ; traînées seulement si demandées


def test_gemini_first_last_clips_are_sped_up_whole():
    """Clip Gemini en ligne (10 s) sur une étape de 1,5 s : ×6,7, au-delà du plafond, pour finir sur l'image suivante."""
    plan = _plan(
        clip_durations=[10.0, 10.0, 10.0], scene_durations=[1.5, 1.5, 4.0], fit=["fill", "speed", "trim"], max_speedup=4.5
    )
    graph = _graph(build_command(plan, Path("o.mp4"), [], None))
    assert "setpts=0.1500*PTS" in graph  # fill : 10 s → 1,5 s
    assert "setpts=0.2222*PTS" in graph  # speed : plafonné à ×4,5


def test_hook_title_overlay_and_sfx_mix_without_voice():
    cues = [SfxCue(Path("excavator.wav"), 0.0, 4.0, 0.55, True), SfxCue(Path("whoosh.wav"), 3.4, 1.5, 0.7, False, 0.05)]
    plan = _plan(
        hook_png=Path("hook.png"),
        sfx=cues,
        music=Path("m.mp3"),
        music_gain_db=-10.46,
        profile=BUILTIN_PROFILES["impact"],
        titles=[(0.0, 4.0, "Jour 1")],
    )
    cmd = build_command(plan, Path("o.mp4"), [], "subtitles=subtitles.ass")
    graph = _graph(cmd)
    assert cmd[cmd.index("hook.png") - 1] == "-i"
    loops = [i for i, a in enumerate(cmd) if a == "-stream_loop"]
    assert [cmd[i + 3] for i in loops] == ["m.mp3", "excavator.wav"]  # musique et fond bouclés, pas le whoosh
    assert "[vcat]subtitles=subtitles.ass[vsub]" in graph and "[vsub][4:v]overlay=(W-w)/2:150[vout]" in graph
    assert "volume=-10.46dB" in graph and "eval=frame" not in graph  # musique à son niveau, sans voix : pas de baisse
    assert "adelay=delays=3400:all=1[s1]" in graph and "[s0][s1]amix=inputs=2:duration=longest" in graph
    assert "[main][sfx]amix=inputs=2:duration=first" in graph and "loudnorm=I=-14" in graph
    sfx_only = _graph(build_command(_plan(sfx=cues[:1]), Path("o.mp4"), [], None))
    assert "[s0]apad=whole_dur=13.000" in sfx_only and "[sfx]afade=t=out" in sfx_only


def test_apply_recipe_builds_the_visual_plan(tmp_path):
    pytest.importorskip("PIL")
    for tag in ("excavator", "whoosh"):
        (tmp_path / "sfx" / tag).mkdir(parents=True)
        (tmp_path / "sfx" / tag / f"{tag}.wav").write_bytes(b"x")
    script = normalize_script(
        ScriptV1.model_validate(
            {
                "scenes": [
                    {
                        "index": i,
                        "duration_s": 4,
                        "visual_prompt": "room",
                        "motion_prompt": "glide",
                        "sfx": "excavator, birds",
                        "on_screen_text": {"fr": "Salon · 60 m²"} if i == 1 else {},
                    }
                    for i in range(4)
                ],
                "metadata": {"fr": {"title": "t", "description": "d"}},
                "hook_title": {"fr": "Tu paierais combien pour cette villa ?"},
            }
        ),
        "tour",
    )
    n = len(script.scenes)  # 4 pièces + 3 passages
    plan = RenderPlan(
        clips=[Path(f"c{i}.mp4") for i in range(n)],
        clip_durations=[5.06] * n,
        scene_durations=[s.duration_s for s in script.scenes],
        profile=BUILTIN_PROFILES["impact"],
    )
    report = apply_recipe(plan, script, "fr", "tour", sfx_dir=tmp_path / "sfx", key="v1")
    assert n == 7 and plan.transitions == [("cut", 0.0)] * 7 and plan.interpolate  # le passage relie les pièces
    assert plan.fit == ["trim", "speed"] * 3 + ["trim"] and plan.max_speedup == 4.5 and not plan.trails and not plan.ticks
    assert plan.total_s == 19.6  # 4 pièces de 4 s + 3 passages de 1,2 s
    assert plan.titles == [(5.2, 9.2, "Salon · 60 m²")]  # s'arrête quand le passage suivant commence
    # Modèle de montage d'origine : texte sous l'image, au-dessus des boutons Shorts ; titre d'accroche en haut
    assert (
        apply_template(plan, MontageTemplate(), "tour", hook=hook_text(script, "fr"), workdir=tmp_path, fonts=FontRegistry())
        == {}
    )
    assert plan.title_style and plan.title_style.y == 1330
    assert plan.hook_png and plan.hook_png.exists() and plan.hook_filter == "overlay=(W-w)/2:150"
    assert [c.start for c in plan.sfx if c.path.name == "whoosh.wav"] == [4.05, 9.25, 14.45]  # un whoosh par passage
    assert [(c.start, c.duration) for c in plan.sfx if c.loop] == [(0.0, 4.0), (5.2, 4.0), (10.4, 4.0), (15.6, 4.0)]
    assert report == {"sfx_manquants": ["birds"]}
    graph = _graph(build_command(plan, Path("o.mp4"), [], None))
    assert "setpts=0.2372*PTS" in graph  # passage : 5,06 s → 1,2 s


def test_apply_recipe_timelapse_counts_the_days(tmp_path):
    pytest.importorskip("PIL")
    script = normalize_script(
        ScriptV1.model_validate(
            {
                "scenes": [
                    {
                        "index": i,
                        "duration_s": 1.5,
                        "visual_prompt": "stage",
                        "motion_prompt": "build",
                        "on_screen_text": {"fr": f"Jour {1 + 20 * i}"},
                    }
                    for i in range(4)
                ],
                "metadata": {"fr": {"title": "t", "description": "d"}},
                "hook_title": {"fr": "Personne ne voulait de ce terrain"},
            }
        ),
        "timelapse",
    )
    plan = RenderPlan(
        clips=[Path(f"c{i}.mp4") for i in range(4)],
        clip_durations=[5.06] * 4,
        scene_durations=[s.duration_s for s in script.scenes],
        profile=BUILTIN_PROFILES["impact"],
    )
    apply_recipe(plan, script, "fr", "timelapse", sfx_dir=tmp_path / "sfx", key="v1")
    assert plan.fit == ["speed"] * 3 + ["trim"] and plan.trails and plan.max_speedup == 4.5
    assert plan.titles == [] and plan.ticks[0][2] == "Jour 1" and plan.ticks[-1][2] == "Jour 61"
    ass = build_ass([], plan.profile, plan.titles, ticks=plan.ticks)
    assert ass.count("Dialogue:") == len(plan.ticks) and "\\fad(150,0)}JOUR 1" in ass and "\\fad(0,150)}JOUR 61" in ass
