"""Récits (docs/24) : scène carte (worker/maps.py), règles d'enjeu et de remplissage, relecture éditoriale du script,
modèle d'écriture. Réseau, base et LLM remplacés par des doublures."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from worker import maps
from worker.config import Settings
from worker.dag import continuity_plan
from worker.models import Job, MapSpec, ScriptReview, ScriptV1
from worker.settings_store import LlmConfig
from worker.steps import script as script_step
from worker.steps.base import Context
from worker.steps.seo import MAP_CREDIT, finalize
from worker.storytelling import lint_script, normalize_story

ROLES = ["hook", "setup", "reveal", "escalation", "escalation", "payoff", "loop"]
LINES = [
    "Charlemagne en rêvait déjà en 793, avec sept mille ouvriers.",
    "Relier le Rhin au Danube, c'est joindre la mer du Nord à la mer Noire.",
    "Mais entre les deux, une ligne de partage des eaux à quatre cent six mètres.",
    "Le canal Ludwig essaie en 1845, trop petit, puis bombardé.",
    "Le nouveau chantier dure soixante-dix ans et divise l'Allemagne.",
    "En 1992, cent soixante et onze kilomètres et seize écluses sont ouverts.",
    "Douze siècles pour réaliser le rêve de Charlemagne.",
]


def _script(lines=LINES, maps_at: dict[int, dict] | None = None, **overrides: Any) -> ScriptV1:
    scenes = []
    for i, text in enumerate(lines):
        scene: dict[str, Any] = {"index": i, "duration_s": 5, "role": ROLES[i % len(ROLES)], "visual_prompt": "v",
                                 "narration": {"fr": text}, "continues_previous": i > 0}
        if maps_at and i in maps_at:
            scene["map"] = maps_at[i]
        scenes.append(scene)
    return ScriptV1.model_validate({"scenes": scenes, "loop_note": "retour", "metadata": {"fr": {"title": "t", "description": "d"}},
                                    **overrides})


# ---------------------------------------------------------------------------
# Script : scène carte, normalisation, correcteur
# ---------------------------------------------------------------------------


def test_map_spec_accepts_what_an_llm_writes():
    spec = MapSpec.model_validate({"place": "Canal Rhin-Main-Danube", "ends": "Bamberg, Kelheim", "context": None})
    assert spec.ends == ["Bamberg", "Kelheim"] and spec.context == [] and spec.lines == []
    s = _script(maps_at={1: {"place": "  "}, 2: {"place": "Canal Rhin-Main-Danube", "ends": ["Bamberg"]}})
    assert not s.scenes[1].is_map and s.scenes[2].is_map


def test_normalize_story_makes_the_map_a_cut_of_sane_length():
    s = normalize_story(_script(maps_at={1: {"place": ""}, 2: {"place": "Canal"}}))
    assert s.scenes[1].map is None  # carte vide : plus de carte
    assert s.scenes[2].continues_previous is False and s.scenes[3].continues_previous is False
    long = _script(maps_at={1: {"place": "Canal"}})
    long.scenes[1].duration_s = 8
    assert normalize_story(long).scenes[1].duration_s == 7.0
    # la continuité ignore les cartes, même en mode « chain »
    assert continuity_plan(_script(maps_at={2: {"place": "Canal"}}), "chain", 9)[1:5] == [True, False, False, True]


def test_lint_flags_thin_narration_and_two_maps():
    assert lint_script(_script(), ["fr"], 35) == []
    thin = _script([f"Phrase courte numéro {i}." for i in range(7)])
    assert any("narration trop maigre" in i for i in lint_script(thin, ["fr"], 35))
    two = _script(maps_at={1: {"place": "A"}, 3: {"place": "B"}})
    assert any("scènes carte" in i for i in lint_script(two, ["fr"], 35))


def test_seo_credits_the_map_sources(monkeypatch: pytest.MonkeyPatch):
    from worker.models import SeoPack
    from worker.steps import seo

    pack = SeoPack.model_validate({"titles": [{"title": "Titre", "angle": "a"}, {"title": "Autre", "angle": "b"}],
                                   "description": "d", "hashtags": []})
    monkeypatch.setattr(seo, "MAP_CREDIT", {"fr": "Carte : EOX, OpenStreetMap", "en": "Map"})
    assert finalize(pack, map_credit=True)[1].endswith("Carte : EOX, OpenStreetMap")
    assert "EOX" not in finalize(pack)[1]
    monkeypatch.setattr(seo, "MAP_CREDIT", {"fr": "", "en": ""})  # mention retirée : pas de lignes vides en trop
    assert finalize(pack, map_credit=True)[1] == "d"
    assert MAP_CREDIT is not None


# ---------------------------------------------------------------------------
# Carte : géométrie, caméra, rendu
# ---------------------------------------------------------------------------


def test_names_geometry_and_chaining():
    assert maps.label_of("Main (rivière)") == "Main" and maps.label_of("Bamberg") == "Bamberg"
    line = [(0.0, 0.0), (1.0, 0.001), (2.0, 0.0), (3.0, 1.0)]
    assert maps.simplify(line, 0.01) == [(0.0, 0.0), (2.0, 0.0), (3.0, 1.0)]
    # trois morceaux dans le désordre, dont un à l'envers : un seul trait, depuis le repère de départ
    pieces = [[(2.0, 0.0), (3.0, 0.0)], [(1.0, 0.0), (0.0, 0.0)], [(1.0, 0.0), (2.0, 0.0)]]
    strokes = maps.chain(pieces, start=(3.1, 0.0))
    assert strokes == [[(3.0, 0.0), (2.0, 0.0), (1.0, 0.0), (0.0, 0.0)]]
    far = maps.chain([[(0.0, 0.0), (1.0, 0.0)], [(5.0, 0.0), (6.0, 0.0)]], start=(0.0, 0.0))
    assert len(far) == 2 and maps.stroke_lengths(far)[1][-1] == pytest.approx(2.0, rel=1e-3)
    data = {"elements": [{"type": "relation", "members": [
        {"type": "way", "geometry": [{"lat": 49.9, "lon": 10.9}, {"lat": 49.8, "lon": 11.0}]},
        {"type": "node", "lat": 1, "lon": 2}]}, {"type": "node", "lat": 49.2, "lon": 11.2}]}
    lines, point = maps.overpass_lines(data)
    assert lines == [[(10.9, 49.9), (11.0, 49.8)]] and point == (11.2, 49.2)
    poly = {"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]]}
    assert maps.geojson_lines(poly) == [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]]


def _canal() -> tuple[maps.Place, list[maps.Place]]:
    place = maps.Place("Canal", 11.3, 49.4, lines=[[(10.9, 49.9), (11.1, 49.5), (11.3, 49.2)], [(11.3, 49.2), (11.87, 48.92)]], source="osm")
    return place, [maps.Place("Bamberg", 10.89, 49.9), maps.Place("Kelheim", 11.87, 48.92)]


def test_plan_descends_from_space_then_traces():
    place, ends = _canal()
    plan = maps.make_plan(place, ends, [])
    assert plan.keys[0][1].scale == maps.GLOBE_SCALE and plan.keys[1][1].scale > 50 * maps.GLOBE_SCALE
    assert plan.strokes[0][0] == (10.9, 49.9)  # le tracé part de Bamberg, premier repère
    assert plan.progress(0.2) == 0 and plan.progress(1.0) == 1
    wide = maps.make_plan(place, ends, [maps.Place("Mer du Nord", 4.0, 56.0), maps.Place("Mer Noire", 34.0, 43.0)])
    assert len(wide.keys) == 5 and wide.context_show[0] < wide.trace[0]
    near = maps.make_plan(place, ends, [maps.Place("Nuremberg", 11.08, 49.45)])  # repère dans le cadre : pas de pause large
    assert len(near.keys) == 3 and near.context == []
    # le plus court chemin en longitude, et un zoom régulier (géométrique) à mi-parcours
    v = maps.blend_view(maps.View(170.0, 0.0, 100.0), maps.View(-170.0, 0.0, 10000.0), 0.5)
    assert v.lon > 170.0 and v.scale == pytest.approx(1000.0)


class BlueTiles(maps.TileCache):
    def __init__(self) -> None:  # pas de disque ni de réseau
        self._mem, self.missing = {}, 0

    def tile(self, z: int, x: int, y: int) -> np.ndarray:
        return np.full((maps.TILE, maps.TILE, 3), (20, 80, 160), dtype=np.uint8)


def test_frames_render_space_globe_and_gold_trace():
    place, ends = _canal()
    plan = maps.make_plan(place, ends, [], [maps.Place("Danube", 11.9, 48.9, lines=[[(10.0, 48.7), (12.5, 49.0)]])])
    r = maps.Renderer(plan, BlueTiles(), None, credit="", size=(108, 192))
    start, end = r.frame(0.0, 6.0), r.frame(1.0, 6.0)
    assert start.shape == (192, 108, 3) and start.dtype == np.uint8
    assert start[2, 2].sum() < 120  # coin : l'espace, sombre
    gold = (end[..., 0] > 200) & (end[..., 1] > 150) & (end[..., 2] < 140)
    assert gold.sum() > 20  # le canal tracé en or
    assert r.tiles_for(r.view_at(1.0))  # des tuiles à précharger


def test_resolver_reads_its_cache_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    res = maps.GeoResolver(tmp_path, lang="fr")
    place, _ = _canal()
    key = __import__("hashlib").sha1(b"fr|Canal Rhin-Main-Danube|True").hexdigest()[:16]
    (tmp_path / f"{key}.json").write_text(json.dumps(place.to_json()), encoding="utf-8")
    monkeypatch.setattr(res, "_resolve", lambda *a: pytest.fail("pas de réseau attendu"))
    got = res.resolve("Canal Rhin-Main-Danube", shape=True)
    assert got and got.lines == place.lines and got.source == "osm"


# ---------------------------------------------------------------------------
# Relecture éditoriale et modèle d'écriture
# ---------------------------------------------------------------------------


class FakeDb:
    def __init__(self) -> None:
        self.logs: list[tuple[str, Any]] = []

    def fetch_one(self, sql: str, params: Any = None) -> dict | None:
        return None  # ni prompt en base, ni série

    def fetch_all(self, sql: str, params: Any = None) -> list[dict]:
        return []

    def heartbeat(self, *a: Any) -> None:
        pass

    def log(self, job_id: Any, level: str, message: str, data: Any) -> None:
        self.logs.append((message, data))


class FakeLlm:
    """Premier script vague, relecture qui le refuse, réécriture qui tient la promesse."""

    def __init__(self, review: ScriptReview | Exception) -> None:
        self.review, self.calls = review, []

    def complete_json(self, system: str, user: str, schema: type) -> Any:
        self.calls.append((schema.__name__, user))
        if schema is ScriptReview:
            if isinstance(self.review, Exception):
                raise self.review
            return self.review
        writes = sum(1 for name, _ in self.calls if name == "ScriptV1")
        lines = list(LINES)
        if writes == 1:
            lines[1] = "Ce projet colossal reste très controversé pendant des décennies, sans que l'on sache pourquoi."
        return _script(lines)


def _prod() -> dict[str, Any]:
    return {"concept_id": None, "title": "Le canal", "hook": "h", "angle": None, "premise": "p", "category": "history",
            "visual_beats": [], "facts": [{"claim": "Inauguré en 1992", "source": 0}],
            "sources": [{"title": "Canal Rhin-Main-Danube", "url": "u", "lang": "fr", "kind": "wikipedia"}],
            "target_duration_s": 35, "format": "A_voiceover", "style_preset": "history_cinematic"}


def _settings(tmp_path: Path | None = None) -> Settings:
    extra = {"data_dir": tmp_path} if tmp_path else {}
    return Settings(database_url="postgresql://x", supabase_url="http://x", supabase_service_role_key="x", **extra)


def _ctx(tmp_path: Path) -> Context:
    job = Job(id=uuid.uuid4(), type="script", status="running", priority=100, created_at=datetime.now(UTC))
    return Context(job=job, db=FakeDb(), settings=_settings(tmp_path))  # type: ignore[arg-type]


def test_review_problems_send_the_script_back_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    llm = FakeLlm(ScriptReview(ok=False, problems=["scène 2 : dire pourquoi c'était controversé (vallée de l'Altmühl)"]))
    seen: dict[str, Any] = {}
    monkeypatch.setattr(script_step, "get_llm", lambda s, d, writer=False: seen.setdefault("writer", writer) and llm or llm)
    monkeypatch.setattr(script_step, "source_dossier", lambda *a, **k: "[1] Canal — la vallée de l'Altmühl sacrifiée")
    script, issues, _ = script_step.ScriptStep()._write(_ctx(tmp_path), _prod(), ["fr"])
    names = [n for n, _ in llm.calls]
    assert names == ["ScriptV1", "ScriptReview", "ScriptV1"] and seen["writer"] is True
    assert "controversé" not in script.scenes[1].narration["fr"] and issues == []
    assert "vallée de l'Altmühl" in llm.calls[2][1] and "DOSSIER" in llm.calls[0][1]


def test_an_approving_or_failing_review_keeps_the_first_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(script_step, "source_dossier", lambda *a, **k: "")
    for review in (ScriptReview(ok=True, problems=["détail"]), RuntimeError("quota")):
        llm = FakeLlm(review)
        monkeypatch.setattr(script_step, "get_llm", lambda s, d, writer=False, llm=llm: llm)
        script_step.ScriptStep()._write(_ctx(tmp_path), _prod(), ["fr"])
        assert [n for n, _ in llm.calls] == ["ScriptV1", "ScriptReview"]


def test_writer_model_goes_first_then_the_usual_model(monkeypatch: pytest.MonkeyPatch):
    import worker.providers.llm as llm_mod

    cfg = LlmConfig(provider="gemini", fallbacks=[], models={"gemini": "gemini-3.5-flash-lite"},
                    api_keys={"gemini": "k"}, writer_models={"gemini": "gemini-3.8-flash"})
    assert cfg.writer_model_for("gemini") == "gemini-3.8-flash"
    same = LlmConfig(provider="gemini", fallbacks=[], models={"gemini": "x"}, writer_models={"gemini": "x"})
    assert same.writer_model_for("gemini") is None
    monkeypatch.setattr(llm_mod, "load_llm_config", lambda s, d: cfg)
    writer = llm_mod.get_llm(_settings(), None, writer=True)
    assert [p.model for p in writer.chain] == ["gemini-3.8-flash", "gemini-3.5-flash-lite"]  # type: ignore[attr-defined]
    assert llm_mod.get_llm(_settings(), None).model == "gemini-3.5-flash-lite"  # type: ignore[attr-defined]


def test_the_watershed_is_not_a_call_to_action():
    lines = list(LINES)
    lines[2] = "Mais entre les deux, la ligne de partage des eaux culmine à quatre cent six mètres."
    assert not any("appel à l'action" in i for i in lint_script(_script(lines), ["fr"], 35))
    lines[6] = "Partagez cette vidéo pour que Charlemagne soit fier."
    assert any("appel à l'action" in i for i in lint_script(_script(lines), ["fr"], 35))
