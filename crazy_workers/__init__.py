__all__ = ['WorkerManager', 'WorkerClient', 'WorkerStatus', 'DesiredStatus', 'parse_params']


# Resolve exports lazily (PEP 562) so a worker doing `from crazy_workers import
# parse_params` only imports the lightweight params module — not the control
# plane (WorkerClient/WorkerManager) and its heavy SQLAlchemy dependencies.
def __getattr__(name):
  if name == 'parse_params':
    from .params import parse_params

    return parse_params
  if name == 'WorkerManager':
    from .core.manager import WorkerManager

    return WorkerManager
  if name == 'WorkerClient':
    from .client import WorkerClient

    return WorkerClient
  if name in ('DesiredStatus', 'WorkerStatus'):
    from .database import schema

    return getattr(schema, name)
  raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
