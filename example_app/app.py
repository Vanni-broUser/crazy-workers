import os
import sys
from flask import Flask, jsonify, request
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError


# Add parent directory to path so we can import crazy_workers if not installed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from crazy_workers import WorkerManager


def create_app(config_override=None):
  # SECURITY: start_worker() executes the <worker_type>.py script of the
  # caller's choosing. Exposing it over HTTP — as below — turns it into a
  # privileged operation: anyone who can reach these routes can run any worker
  # script in the workers directory. This demo has NO authentication; put the
  # routes behind auth (and ideally restrict worker_type to a known set) before
  # using anything like this in production.
  app = Flask(__name__)

  config = config_override or {}
  workers_dir = config.get('WORKERS_DIR') or os.path.join(os.path.dirname(__file__), 'workers')

  if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path)

  # The backend's OWN database. We hand the engine to crazy_workers so its tables
  # are created here too (co-located), and we inject the same URL into every
  # worker via worker_env so a worker can open its own connection to it.
  db_url = config.get('DATABASE_URL') or os.environ.get('DATABASE_URL')
  if not db_url:
    db_url = f'sqlite:///{os.path.join(app.instance_path, "app.db")}'
  engine = create_engine(db_url)

  manager = WorkerManager(
    workers_dir,
    engine=engine,  # crazy_workers tables live in the app's database
    worker_env={'DATABASE_URL': db_url},  # injected into every worker process
    # auto_recover=True (default): when this app boots, workers left RUNNING with
    # a dead PID are restored automatically — no explicit recover call needed.
  )

  @app.route('/workers/start', methods=['POST'])
  def start():
    data = request.json
    key = data.get('worker_key')
    w_type = data.get('worker_type')
    params = data.get('parameters', {})

    if not w_type:
      return jsonify({'error': 'Missing worker_type'}), 400

    success, result = manager.start_worker(w_type, worker_key=key, parameters=params)
    if success:
      return jsonify(result), 200
    else:
      return jsonify({'error': result}), 400

  @app.route('/workers/stop', methods=['POST'])
  def stop():
    data = request.json
    key = data.get('worker_key')
    if not key:
      return jsonify({'error': 'Missing key'}), 400

    success, result = manager.stop_worker(key)
    if success:
      return jsonify({'message': result}), 200
    else:
      return jsonify({'error': result}), 400

  @app.route('/workers', methods=['GET'])
  def list_workers():
    workers = manager.list_workers()
    return jsonify(workers), 200

  @app.route('/workers/params/<key>', methods=['GET'])
  def get_params(key):
    workers = manager.list_workers()
    worker = next((w for w in workers if w['worker_key'] == key), None)
    if worker:
      return jsonify(worker['parameters']), 200
    else:
      return jsonify({'error': 'Worker not found'}), 404

  @app.route('/events', methods=['GET'])
  def events():
    # Rows written by the db_writer worker — proof it used the connection URL we
    # injected. The table only exists once a db_writer has run.
    try:
      with engine.connect() as conn:
        rows = conn.execute(text('SELECT worker_key, note FROM worker_events ORDER BY created_at')).fetchall()
      return jsonify([{'worker_key': r[0], 'note': r[1]} for r in rows]), 200
    except (OperationalError, ProgrammingError):
      return jsonify([]), 200

  return app, manager


if __name__ == '__main__':
  app, manager = create_app()
  app.run(debug=True)
