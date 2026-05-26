from flask import Flask, request, jsonify
import os
import sys

# Add parent directory to path so we can import crazy_workers if not installed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from crazy_workers import WorkerManager


def create_app(config_override=None):
  app = Flask(__name__)

  # Configuration for the library
  db_path = os.path.join(app.instance_path, 'workers_internal.db')
  workers_dir = os.path.join(os.path.dirname(__file__), 'workers')

  if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path)

  manager = WorkerManager(db_path, workers_dir)
  log_dir = os.path.join(os.path.dirname(__file__), 'logs')

  @app.route('/workers/start', methods=['POST'])
  def start():
    data = request.json
    key = data.get('worker_key')
    w_type = data.get('worker_type')
    params = data.get('parameters', {})

    if not key or not w_type:
      return jsonify({'error': 'Missing key or type'}), 400

    success, result = manager.start_worker(key, w_type, params, log_dir=log_dir)
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

  return app, manager


if __name__ == '__main__':
  app, manager = create_app()
  # Automatic recovery on startup
  manager.recover_workers()
  app.run(debug=True)
