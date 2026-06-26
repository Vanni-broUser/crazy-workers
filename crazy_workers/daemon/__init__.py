"""The reconcile daemon: the single owner of worker processes for a context.

Clients (HTTP API, CLI, scripts) only write desired state to the shared DB; the
daemon runs a loop that drives the observed state toward it — starting,
stopping and crash-restarting processes. Exactly one daemon owns a given
workers_dir/DB at a time (enforced by a lock in ``crazy_workers.daemon.runner``).

Run it with ``python -m crazy_workers.daemon`` (a thin ``__main__`` shim over
:func:`crazy_workers.daemon.runner.main`).
"""

from .reconciler import Reconciler
from .runner import main


__all__ = ['Reconciler', 'main']
