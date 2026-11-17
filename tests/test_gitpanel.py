import unittest

try:
    from elyares import gitpanel
except ImportError:             # sin `gi` no hay GTK
    gitpanel = None


@unittest.skipIf(gitpanel is None, 'sin gi')
class Orden(unittest.TestCase):
    def test_lo_que_pide_atencion_va_arriba(self):
        items = [dict(tone='ok', n=1), dict(tone='', n=2), dict(tone='bad', n=3), dict(tone='info', n=4),
                 dict(tone='run', n=5)]
        self.assertEqual([i['n'] for i in gitpanel.order(items)], [3, 4, 5, 1, 2])

    def test_el_chip_dice_el_estado(self):
        self.assertEqual(gitpanel.chip(dict(tone='bad')), ('rojo', 2))
        self.assertEqual(gitpanel.chip(dict(tone='')), ('sin checks', None))
        self.assertEqual(gitpanel.chip(dict(tone='info')), ('revisión', None))


@unittest.skipIf(gitpanel is None, 'sin gi')
class Log(unittest.TestCase):
    def test_el_log_se_guarda_y_obliga_a_redibujar(self):
        panel = gitpanel.GitPanel()
        panel.signature = 'viejo'
        panel._got('u', ['falló x'])
        self.assertEqual(panel.logs['u'], ['falló x'])
        self.assertIsNone(panel.signature)

    def test_pedir_el_log_lo_marca_cargando(self):
        panel = gitpanel.GitPanel()
        asked = []
        panel._fetch(dict(url='u'), dict(log=lambda item, done: asked.append(item)))
        self.assertEqual(panel.logs['u'], 'cargando')
        self.assertEqual(len(asked), 1)


if __name__ == '__main__':
    unittest.main()
