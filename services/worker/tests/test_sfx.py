from pathlib import Path

from worker.sfx import TAGS, parse_tags, pick_sfx, plan_cues, vocabulary_text


def test_parse_tags_maps_aliases_and_ignores_unknowns():
    assert parse_tags("Excavator, birds") == ["excavator", "birds"]
    assert parse_tags("digger; footsteps / mystery sound") == ["excavator", "footsteps_stone"]
    assert parse_tags("hammer, drill, saw, grinder") == ["hammer", "drill", "saw"]  # 3 au plus
    assert parse_tags(None) == [] and parse_tags("") == []
    assert "excavator (pelleteuse)" in vocabulary_text() and "whoosh" in vocabulary_text()


def test_pick_sfx_is_stable_per_key(tmp_path):
    folder = tmp_path / "birds"
    folder.mkdir()
    for name in ("a.wav", "b.flac", "c.mp3", "notes.txt"):
        (folder / name).write_bytes(b"x")
    first = pick_sfx(tmp_path, "birds", "video-1")
    assert first and first.suffix in {".wav", ".flac", ".mp3"} and pick_sfx(tmp_path, "birds", "video-1") == first
    assert pick_sfx(tmp_path, "rain", "video-1") is None


def test_plan_cues_places_beds_hits_and_transition_whooshes():
    def resolve(tag: str, key: str) -> Path | None:
        return Path(f"{tag}.wav") if tag != "rain" else None  # « rain » absent de la bibliothèque

    cues = plan_cues(
        [["excavator", "impact"], ["rain"], ["birds"]],
        starts=[0.0, 4.65, 9.3],
        durations=[5.0, 5.0, 4.0],
        transitions=[("whip", 0.35), ("cut", 0.0), ("cut", 0.0)],
        resolve=resolve,
    )
    by = {c.path.stem: c for c in cues}
    assert by["excavator"].loop and by["excavator"].start == 0.0 and by["excavator"].duration == 5.0
    assert by["excavator"].volume == TAGS["excavator"].volume
    assert not by["impact"].loop and by["impact"].start == 0.05
    assert by["birds"].start == 9.3 and by["birds"].duration == 4.0
    assert "rain" not in by  # étiquette sans fichier : ignorée
    assert by["whoosh"].start == round(4.65 + 0.35 / 2 - 0.45, 3)  # centré sur le passage d'une pièce à l'autre
    assert [c.start for c in cues] == sorted(c.start for c in cues)
