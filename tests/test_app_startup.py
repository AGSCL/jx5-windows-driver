import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from tools import monitor_jx05


class StartupTests(unittest.TestCase):
    def test_task_flag_explicitly_enables_controls(self):
        for enabled in (False, True):
            argv = ['monitor_jx05.py', '--run'] + (['--enabled'] if enabled else [])
            with patch('sys.argv', argv), patch.object(monitor_jx05, 'run') as run:
                monitor_jx05.main()
            run.assert_called_once_with(enabled)

    def test_backend_marker_overrides_leftover_firmware(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'rtk-firmware').mkdir()
            for backend in ('raw-input', 'bumble'):
                (root / 'backend.txt').write_text(backend, encoding='ascii')
                with patch.object(monitor_jx05, 'ROOT', root), \
                     patch('sys.argv', ['monitor_jx05.py', '--run']), \
                     patch.object(monitor_jx05, 'run') as run:
                    monitor_jx05.main()
                run.assert_called_once_with(False, *([backend] if backend == 'bumble' else []))

    def test_enabled_is_rejected_for_readonly_status(self):
        with patch('sys.argv', ['monitor_jx05.py', '--status', '--enabled']), \
                patch('sys.stderr'), patch.object(monitor_jx05, 'run') as run:
            with self.assertRaises(SystemExit) as error:
                monitor_jx05.main()
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()
