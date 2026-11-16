"""Contraste de lo que se lee en la ventana, en los 12 temas (WCAG 1.4.3: 4.5:1)."""

import unittest

from elyares import mascot, themes

MIN = 4.5


class Contrast(unittest.TestCase):
    def setUp(self):
        self.old = themes.current

    def tearDown(self):
        themes.use(self.old)

    def each_theme(self):
        for name in themes.THEMES:
            themes.use(name)
            yield name, themes.get()

    def test_legible_reaches_the_ratio_and_keeps_dark_themes_intact(self):
        for name, look in self.each_theme():
            bg = look['surface'][1]
            for role, color in mascot.ACCENTS.items():
                ink = themes.ink_for(color)
                self.assertGreaterEqual(themes.contrast(ink, bg), MIN, (name, role))
                if not themes.is_light() and themes.contrast(color, bg) >= MIN:
                    self.assertEqual(ink, color, (name, role))

    def test_signal_and_muted_read_on_every_surface(self):
        for name, look in self.each_theme():
            for color in themes.signal():
                self.assertGreaterEqual(themes.contrast(color, look['surface'][1]), MIN, (name, color))
            for surface in look['surface']:
                self.assertGreaterEqual(themes.contrast(look['muted'], surface), MIN, (name, 'muted', surface))
                self.assertGreaterEqual(themes.contrast(look['ink'], surface), MIN, (name, 'ink', surface))

    def test_permission_buttons_read(self):
        for name, look in self.each_theme():
            self.assertGreaterEqual(themes.contrast(look['surface'][0], look['accent']), MIN, (name, 'Permitir'))


if __name__ == '__main__':
    unittest.main()
