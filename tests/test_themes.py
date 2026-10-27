import unittest

from elyares import paint, themes

try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    from elyares import windowframe
    HAVE_DISPLAY = Gtk.init_check()
except (ImportError, ValueError):
    HAVE_DISPLAY = False


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4 for v in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]


def contrast(a, b):
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + .05) / (lo + .05)


class Temas(unittest.TestCase):
    def tearDown(self):
        themes.use(themes.DEFAULT)
        paint.ISLAND = themes.get()['island']
        if HAVE_DISPLAY:
            windowframe.use_theme()

    def test_con_vidrio_y_vista_cansada_el_texto_se_lee_sobre_el_peor_fondo(self):
        """El vidrio de la vista cansada (casi opaco) sobre el peor fondo: blanco tras un tema oscuro, negro tras uno claro."""
        from elyares import fonts
        for name, look in themes.THEMES.items():
            themes.use(name)
            worst = '#000000' if themes.is_light() else '#ffffff'
            bg = paint.mix(worst, look['surface'][0], fonts.TIRED_GLASS)
            for ink in (look['ink'], look['muted'], look['tired']):
                self.assertGreaterEqual(contrast(ink, bg), 4.5, (name, ink, bg))

    def test_uno_que_no_existe_cae_en_el_de_siempre(self):
        self.assertEqual(themes.use('no-existe'), themes.DEFAULT)
        self.assertEqual(themes.use('moonfly'), 'moonfly')

    def test_el_texto_de_cada_tema_contrasta_4_5_con_cada_superficie(self):
        for name, look in themes.THEMES.items():
            for ink in (look['ink'], look['muted'], look['tired'], look['chat_ink']):
                for surface in look['surface']:
                    self.assertGreaterEqual(contrast(ink, surface), 4.5, (name, ink, surface))

    def test_el_boton_primario_y_el_de_peligro_se_leen_sobre_su_color(self):
        for name, look in themes.THEMES.items():
            for fill in (look['accent'], look['danger']):
                self.assertGreaterEqual(contrast(look['surface'][0], fill), 4.5, (name, fill))

    def test_la_paleta_fija_pinta_todos_los_papeles(self):
        themes.use('moonfly')
        colors = paint.colors(themes.palette())
        self.assertEqual(set(colors), set(paint.colors({})))
        self.assertNotEqual(colors['cmd'], paint.colors({})['cmd'])

    def test_los_colores_de_aviso_no_son_del_tema(self):
        themes.use('moonfly')
        self.assertEqual(paint.colors(themes.palette())['bad'], paint.RED)

    @unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
    def test_los_estilos_de_cada_tema_se_leen_sin_errores(self):
        for name in themes.keys():
            themes.use(name)
            windowframe.use_theme()
            errors = []
            css = Gtk.CssProvider()
            css.connect('parsing-error', lambda _p, _s, err: errors.append(err.message))
            css.load_from_string(windowframe.CSS)
            self.assertEqual(errors, [], name)
            self.assertIn(f'background: {themes.get()["surface"][1]}', windowframe.CSS)


if __name__ == '__main__':
    unittest.main()
