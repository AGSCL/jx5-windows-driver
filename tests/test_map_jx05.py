from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from tools.map_jx05 import DEFAULTS, load, save, main


class MappingTests(unittest.TestCase):
    def test_defaults_and_independent_buttons(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'buttons.json'
            mapping = load(path)
            self.assertEqual(mapping, DEFAULTS)
            mapping.update(left='next', upper='none', center='powerpoint')
            save(mapping, path)
            self.assertEqual(load(path), mapping)
            self.assertEqual(load(path)['right'], 'next')
            self.assertEqual(DEFAULTS['left'], 'previous')

    def test_invalid_mapping_is_not_saved(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'buttons.json'
            save(DEFAULTS, path)
            for bad in ({}, [], dict(DEFAULTS, extra='next'), dict(DEFAULTS, left=[]),
                        dict(DEFAULTS, left='bad'), dict(DEFAULTS, left='powerpoint')):
                with self.assertRaises(ValueError):
                    save(bad, path)
                self.assertEqual(load(path), DEFAULTS)

    def test_wizard_preserves_defaults_and_selects_central(self):
        with patch('sys.argv', ['map_jx05.py']), patch('builtins.input', side_effect=['bad', '0', '', '2', '', '4']), \
                patch('builtins.print'), patch('tools.map_jx05.load', return_value=DEFAULTS.copy()), \
                patch('tools.map_jx05.save') as save_map:
            main()
        save_map.assert_called_once_with(dict(DEFAULTS, upper='none', left='next', center='google'))
