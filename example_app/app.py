import os
import sys
from flask import Flask, jsonify, request


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

  # Configuration for the library
  workers_dir = os.path.join(os.path.dirname(__file__), 'workers')

  if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path)

  manager = WorkerManager(workers_dir)

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

  # Automatic recovery on startup
  manager.recover_workers()

  return app, manager


if __name__ == '__main__':
  app, manager = create_app()
  app.run(debug=True)
