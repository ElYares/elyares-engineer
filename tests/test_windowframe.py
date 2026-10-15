"""El marco de widgets de la ventana (decisión 009): vistas, foco y contenido.

Prueba estructura, no dibujo: un widget no sale en el PNG de la isla. Necesita
gi y una pantalla; sin ellas se salta.
"""

import unittest

try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    from elyares import windowframe
    HAVE_DISPLAY = Gtk.init_check()
except (ImportError, ValueError):
    HAVE_DISPLAY = False


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class Marco(unittest.TestCase):

    def setUp(self):
        self.clicks = []
        self.frame = windowframe.Frame(self.clicks.append)

    def test_los_estilos_se_leen_sin_errores(self):
        errors = []
        css = Gtk.CssProvider()
        css.connect('parsing-error', lambda _p, _sec, err: errors.append(err.message))
        css.load_from_string(windowframe.CSS)
        self.assertEqual(errors, [])

    def test_el_texto_contrasta_4_5_con_cada_superficie(self):
        def lum(h):
            c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            c = [v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4 for v in c]
            return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
        for ink in (windowframe.INK, windowframe.MUTED):
            for surface in windowframe.SURFACE:
                hi, lo = sorted((lum(ink), lum(surface)), reverse=True)
                self.assertGreaterEqual((hi + .05) / (lo + .05), 4.5, (ink, surface))

    def test_una_vista_por_boton_en_el_orden_de_la_barra(self):
        self.assertEqual(list(self.frame.buttons), [key for key, _ in windowframe.VIEWS])

    def test_un_clic_avisa_de_su_vista(self):
        self.frame.buttons['chat'].set_active(True)
        self.assertEqual(self.clicks, ['chat'])

    def test_sincronizar_marca_el_boton_sin_avisar(self):
        self.frame.sync('flows')
        self.assertTrue(self.frame.buttons['flows'].get_active())
        self.assertEqual(self.clicks, [])

    def test_solo_una_vista_marcada(self):
        self.frame.sync('flows')
        self.frame.sync('projects')
        marked = [k for k, b in self.frame.buttons.items() if b.get_active()]
        self.assertEqual(marked, ['projects'])

    def test_el_contenido_es_uno_y_se_quita(self):
        a, b = Gtk.DrawingArea(), Gtk.DrawingArea()
        self.frame.set_content(a)
        self.frame.set_content(b)
        self.assertIs(self.frame.slot.get_first_child(), b)
        self.assertIsNone(b.get_next_sibling())
        self.frame.set_content(None)
        self.assertIsNone(self.frame.slot.get_first_child())


if __name__ == '__main__':
    unittest.main()
