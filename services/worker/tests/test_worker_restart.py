"""Relance automatique du worker quand son code change (worker/main.py : superviseur + enfant)."""

import os
import time
from pathlib import Path

from worker import main


def test_code_change_waits_until_the_edit_is_finished():
    t0 = 1_000_000.0
    assert not main.code_changed(t0, t0, t0 + 100)  # rien n'a bougé
    assert not main.code_changed(t0, t0 + 50, t0 + 60)  # modifié il y a 10 s : peut-être en cours d'écriture
    assert main.code_changed(t0, t0 + 50, t0 + 71)  # modifié il y a 21 s : on relance


def test_code_stamp_is_the_newest_python_file(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "sub").mkdir()
    newer = tmp_path / "sub" / "b.py"
    newer.write_text("y = 2")
    stamp = time.time() + 5
    os.utime(newer, (stamp, stamp))
    (tmp_path / "notes.txt").write_text("ignoré")
    assert main.code_stamp(tmp_path) == newer.stat().st_mtime


def test_supervisor_restarts_the_child_after_a_code_change_and_after_a_crash():
    codes = iter([main.RESTART_CODE, 1, main.RESTART_CODE, 0])
    calls: list[list[str]] = []

    def fake_call(cmd):
        calls.append(cmd)
        return next(codes)

    assert main.supervise(["--verbose"], call=fake_call, pause_s=0) == 0
    assert len(calls) == 4  # relance (code), relance (plantage), relance (code), arrêt normal
    assert calls[0][1:] == ["-m", "worker.main", "--child", "--verbose"]
