"""Remettre un job à plus tard sans le compter comme un échec.

Un step lève `Postpone` quand il attend un service extérieur : vidéo demandée à Gemini et pas encore prête, quota
atteint (docs/17-gemini-en-ligne.md). La boucle du worker (main.run_job) remet alors le job en file pour
`delay_s` secondes sans consommer de tentative (Db.postpone) : la voie reste libre pour les autres jobs pendant
l'attente, et le libellé s'affiche dans le panneau Tâches.
"""

from __future__ import annotations


class Postpone(Exception):  # noqa: N818 — ce n'est pas une erreur : le job reviendra
    def __init__(self, reason: str, delay_s: float, *, label: str | None = None, error: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.delay_s = max(10.0, float(delay_s))
        self.label = label  # libellé d'étape affiché dans le panneau Tâches (jobs.progress_label)
        self.error = error  # message gardé dans jobs.error (ex. quota atteint) ; None = aucun problème
