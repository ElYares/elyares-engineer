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


class TiredView(unittest.TestCase):
    def test_scale_goes_once_at_the_root(self):
        from elyares import fonts
        old = fonts.tired, fonts.TIRED_SCALE
        try:
            fonts.use_tired(True)
            fonts.use_scale(150)
            css = fonts.css()
            self.assertIn('window, popover, tooltip { font-size: 150%; }', css)
            self.assertNotIn('label, button, entry, dropdown { font-size', css)     # se multiplicaba por dos
            self.assertEqual(fonts.view_scale(), 1.5)
            fonts.use_scale(200)
            self.assertIn('.elyares-segments, .elyares-pill { font-size: 75%; }', fonts.css())   # 75 % de 200 = 150
            fonts.use_tired(False)
            self.assertEqual(fonts.view_scale(), 1.0)
        finally:
            fonts.tired, fonts.TIRED_SCALE = old


class TypeScale(unittest.TestCase):
    def test_tokens_become_css(self):
        from elyares import fonts, windowframe
        css = fonts.type_css()
        for name in fonts.TYPE:
            self.assertIn(f'.elyares-{name} {{', css)
        self.assertIn('letter-spacing: 1px', fonts.type_rule('caption'))
        self.assertIn('"tnum"', fonts.type_rule('figure'))
        self.assertIn('.elyares-figure', windowframe.build_css())       # la ventana usa la escala

    def test_nothing_in_px_in_window_text_rules(self):
        from elyares import containerview
        import re
        self.assertEqual(re.findall(r'font-size: \d+px', containerview.build_css()), [])


if __name__ == '__main__':
    unittest.main()
