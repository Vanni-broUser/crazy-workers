import json
import os
import shutil
import sys
import tempfile
import unittest
from sqlalchemy import create_engine, text
from unittest.mock import patch

from example_app.workers import db_writer


class TestDbWriter(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

  def test_writes_events_using_injected_url(self):
    url = f'sqlite:///{os.path.join(self.tmp, "app.db")}'
    params = json.dumps({'worker_key': 'dbw', 'iterations': 2, 'interval': 0})
    with patch.dict(os.environ, {'DATABASE_URL': url}):
      with patch.object(sys, 'argv', ['db_writer', params]):
        db_writer.main()

    engine = create_engine(url)
    with engine.connect() as conn:
      rows = conn.execute(text('SELECT worker_key, note FROM worker_events')).fetchall()
    engine.dispose()

    self.assertEqual(len(rows), 2)
    self.assertTrue(all(r[0] == 'dbw' for r in rows))

  def test_exits_without_database_url(self):
    with patch.dict(os.environ, {'DATABASE_URL': ''}):
      with patch.object(sys, 'argv', ['db_writer', json.dumps({})]):
        with self.assertRaises(SystemExit):
          db_writer.main()
