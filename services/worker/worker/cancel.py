"""Arrêt d'une tâche depuis le dashboard (gestionnaire de tâches, docs/16 §4).

Le dashboard passe les jobs de la production en `cancelled` (SQL cancel_production). Pendant qu'un job tourne,
main.run_job lit son statut toutes les 5 secondes et, s'il est arrêté, lève le drapeau du thread qui exécute le
step. Le step s'arrête au prochain point de contrôle : `Context.progress` et l'attente d'un prompt ComfyUI
(ComfyClient.wait, qui annule aussi le prompt côté ComfyUI pour libérer la carte graphique). Un appel LLM en cours
va jusqu'au bout, mais rien de ce qu'il produit n'est plus mis en file (claim_jobs annule les jobs d'une production
arrêtée).
"""

from __future__ import annotations

import threading

_local = threading.local()


class JobCancelled(RuntimeError):
    """La tâche a été arrêtée depuis le dashboard."""


def bind(event: threading.Event | None) -> None:
    """Associe (ou détache, avec None) le drapeau d'arrêt du job exécuté par le thread courant."""
    _local.event = event


def cancelled() -> bool:
    event = getattr(_local, "event", None)
    return bool(event and event.is_set())


def check() -> None:
    if cancelled():
        raise JobCancelled("tâche arrêtée depuis le dashboard")
