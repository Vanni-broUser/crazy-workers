import unittest
from unittest.mock import patch

from crazy_workers import parse_params


class TestParseParams(unittest.TestCase):
  def test_no_argv_returns_empty_dict(self):
    self.assertEqual(parse_params(['worker.py']), {})

  def test_no_argv_with_required_exits(self):
    with self.assertRaises(SystemExit) as ctx:
      parse_params(['worker.py'], required=('device_id', 'output_dir'))
    self.assertEqual(ctx.exception.code, 'Missing required parameters: device_id, output_dir')

  def test_invalid_json_exits(self):
    with self.assertRaises(SystemExit) as ctx:
      parse_params(['worker.py', 'not json'])
    self.assertIn('Invalid JSON parameters', str(ctx.exception.code))

  def test_non_object_json_exits(self):
    with self.assertRaises(SystemExit) as ctx:
      parse_params(['worker.py', '[1, 2, 3]'])
    self.assertEqual(ctx.exception.code, 'Invalid JSON parameters: expected a JSON object')

  def test_returns_parsed_params(self):
    self.assertEqual(parse_params(['worker.py', '{"device_id": "7"}']), {'device_id': '7'})

  def test_required_present_returns_params(self):
    argv = ['worker.py', '{"device_id": "7", "output_dir": "/out"}']
    params = parse_params(argv, required=('device_id', 'output_dir'))
    self.assertEqual(params, {'device_id': '7', 'output_dir': '/out'})

  def test_required_missing_exits_naming_keys(self):
    with self.assertRaises(SystemExit) as ctx:
      parse_params(['worker.py', '{"device_id": "7"}'], required=('device_id', 'output_dir'))
    self.assertEqual(ctx.exception.code, 'Missing required parameters: output_dir')

  def test_required_empty_value_counts_as_missing(self):
    with self.assertRaises(SystemExit) as ctx:
      parse_params(['worker.py', '{"device_id": ""}'], required=('device_id',))
    self.assertEqual(ctx.exception.code, 'Missing required parameters: device_id')

  def test_required_falsy_but_present_value_is_kept(self):
    argv = ['worker.py', '{"retries": 0, "verbose": false}']
    params = parse_params(argv, required=('retries', 'verbose'))
    self.assertEqual(params, {'retries': 0, 'verbose': False})

  def test_defaults_to_sys_argv(self):
    with patch('sys.argv', ['worker.py', '{"interval": 5}']):
      self.assertEqual(parse_params(), {'interval': 5})
