"""Preferences must survive malformed data and partial UI updates."""
import json
from pathlib import Path
import tempfile
import unittest

from config import Config, DEFAULT_PINS
from styles import STYLES


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'tinyhand/config.json'

    def test_partial_updates_preserve_choices_and_roundtrip(self):
        config = Config(STYLES, self.path)
        self.assertIsNone(config.update(style='glove', size=.2, hand_sound=False))
        config.update(laser_sound=True)
        loaded = Config(STYLES, self.path)
        self.assertEqual(loaded.data['style'], 'glove')
        self.assertEqual(loaded.data['size'], .2)
        self.assertFalse(loaded.data['hand_sound'])
        self.assertTrue(loaded.data['laser_sound'])
        self.assertEqual(list(self.path.parent.glob('.config-*')), [])

    def test_malformed_fields_cannot_reach_renderer(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps(dict(style=[], pins=['glove', 'glove', {}, 'missing'],
                                             size=float('nan'), hand_sound='false')))
        config = Config(STYLES, self.path)
        self.assertEqual(config.data['style'], 'lavender')
        self.assertEqual(config.data['pins'], ['glove'])
        self.assertEqual(config.data['size'], .13)
        self.assertTrue(config.data['hand_sound'])
        config.update(pins=list(STYLES))
        self.assertEqual(len(config.data['pins']), 8)

    def test_corrupt_file_is_preserved(self):
        self.path.parent.mkdir()
        self.path.write_text('{bad json')
        config = Config(STYLES, self.path)
        self.assertIsNotNone(config.error)
        self.assertEqual(config.data['pins'], DEFAULT_PINS)
        backups = list(self.path.parent.glob('config.broken-*.json'))
        self.assertEqual(len(backups), 1)
        config.update(style='robot')
        self.assertEqual(backups[0].read_text(), '{bad json')
        self.assertEqual(Config(STYLES, self.path).data['style'], 'robot')


if __name__ == '__main__':
    unittest.main()
