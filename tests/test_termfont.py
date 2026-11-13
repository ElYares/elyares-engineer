import os
import tempfile
import unittest
from unittest import mock

from elyares import terminalpanel as tp


class FontSizeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patch = mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': self.tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_default(self):
        self.assertEqual(tp.font_size(), tp.FONT_SIZE)

    def test_clamped_and_saved(self):
        self.assertEqual(tp.set_font_size(100), tp.FONT_MAX)
        self.assertEqual(tp.font_size(), tp.FONT_MAX)
        self.assertEqual(tp.set_font_size(1), tp.FONT_MIN)

    def test_zero_restores_default(self):
        tp.set_font_size(20)
        self.assertEqual(tp.set_font_size(0), tp.FONT_SIZE)


if __name__ == '__main__':
    unittest.main()
