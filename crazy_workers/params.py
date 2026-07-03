"""Worker-side parsing of the JSON parameters the daemon passes on argv.

The manager spawns every worker as ``python -m crazy_workers._bootstrap
<worker_path> <json_params>`` and the bootstrap restores ``sys.argv`` to
``[worker_path, json_params]``. This module is the worker-side counterpart of
that contract: call :func:`parse_params` at the top of a worker's ``main()``
instead of re-implementing the argv/JSON boilerplate in every worker script.
"""

import json
import sys


def parse_params(argv=None, required=()):
  """Return the parameters dict the daemon passed to this worker.

  Without ``required`` a worker launched with no parameters gets ``{}`` — the
  lenient mode for workers whose parameters are all optional. With ``required``
  a missing argv, malformed JSON, or a missing/empty required key aborts the
  worker with a message on stderr (``SystemExit``, exit code 1) before it does
  any real work. A key counts as missing when it is absent, ``None``, or an
  empty string; a falsy-but-present value like ``0`` or ``False`` is kept.

  ``argv`` defaults to ``sys.argv``; pass a list explicitly in tests.
  """
  argv = sys.argv if argv is None else argv

  if len(argv) < 2:
    if required:
      raise SystemExit(f'Missing required parameters: {", ".join(required)}')
    return {}

  try:
    params = json.loads(argv[1])
  except json.JSONDecodeError as error:
    raise SystemExit(f'Invalid JSON parameters: {error}')

  if not isinstance(params, dict):
    raise SystemExit('Invalid JSON parameters: expected a JSON object')

  missing = [key for key in required if key not in params or params[key] in (None, '')]
  if missing:
    raise SystemExit(f'Missing required parameters: {", ".join(missing)}')

  return params
