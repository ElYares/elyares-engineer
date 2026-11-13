"""La vista Pomodoro: lo que se entiende de `coffe` y el panel que lo muestra."""

import unittest

from elyares import pomodoro

try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    from elyares import windowframe
    HAVE_DISPLAY = Gtk.init_check()
except (ImportError, ValueError):
    HAVE_DISPLAY = False

LIST = """   1  pendiente —            alta    HU-002 - cotizacion por dis… [0/3] strapp / aang
  12  pendiente —            alta    CU-002 - Materializar silve… [0] data-science / acervo
 164  hecha     —            alta    HU-001 - Workspace y CI      [0/2] personal / geoda
"""


class Datos(unittest.TestCase):
    def test_solo_las_pendientes_con_su_proyecto(self):
        tasks = pomodoro.parse_tasks(LIST)
        self.assertEqual([t['id'] for t in tasks], ['1', '12'])
        self.assertEqual(tasks[0]['project'], 'strapp / aang')
        self.assertTrue(tasks[1]['title'].startswith('CU-002'))

    def test_el_reloj_se_escribe_en_minutos(self):
        self.assertEqual(pomodoro.clock(1500), '25:00')
        self.assertEqual(pomodoro.clock(65), '01:05')
        self.assertEqual(pomodoro.clock(None), '00:00')

    def test_describe_un_pomodoro_en_curso(self):
        got = pomodoro.describe({'phase': 'focus', 'remaining_secs': 754, 'task': {'title': 'HU-001'},
                                 'pomodoros_hoy': 2, 'completed_since_long_break': 2, 'long_break_every': 4})
        self.assertEqual((got['text'], got['clock'], got['task'], got['running']),
                         ('En foco', '12:34', 'HU-001', True))

    def test_parado_no_corre_y_sin_datos_es_none(self):
        self.assertFalse(pomodoro.describe({'phase': 'idle'})['running'])
        self.assertIsNone(pomodoro.describe(None))


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class Panel(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.handlers = dict(act=lambda *a: self.log.append(a))
        self.panel = windowframe.PomodoroPanel()

    def buttons(self, widget=None, found=None):
        found = [] if found is None else found
        widget = widget or self.panel
        if isinstance(widget, Gtk.Button):
            found.append(widget)
        child = widget.get_first_child()
        while child is not None:
            self.buttons(child, found)
            child = child.get_next_sibling()
        return found

    def status(self, **over):
        base = {'phase': 'idle', 'remaining_secs': 0, 'task': None, 'parked': None, 'pomodoros_hoy': 0,
                'completed_since_long_break': 0, 'long_break_every': 4}
        return pomodoro.describe({**base, **over})

    def test_una_tarea_pendiente_arranca_un_pomodoro(self):
        self.panel.set_pomodoro(self.status(), pomodoro.parse_tasks(LIST), self.handlers)
        self.buttons()[0].emit('clicked')
        self.assertEqual(self.log, [('start', '1')])

    def test_en_foco_se_puede_aparcar_tirar_o_terminar(self):
        self.panel.set_pomodoro(self.status(phase='focus', task={'title': 'HU-001'}), [], self.handlers)
        for btn in self.buttons():
            btn.emit('clicked')
        self.assertEqual(self.log, [('pause',), ('void',), ('done',)])

    def test_parado_no_ofrece_aparcar(self):
        self.panel.set_pomodoro(self.status(), [], self.handlers)
        self.assertEqual(self.buttons(), [])

    def test_con_una_tarea_en_el_refri_se_puede_sacar(self):
        self.panel.set_pomodoro(self.status(parked={'title': 'x'}), [], self.handlers)
        self.buttons()[0].emit('clicked')
        self.assertEqual(self.log, [('resume',)])

    def test_el_reloj_se_retoca_sin_reconstruir(self):
        self.panel.set_pomodoro(self.status(phase='focus', remaining_secs=90), [], self.handlers)
        first = self.buttons()[0]
        self.panel.set_pomodoro(self.status(phase='focus', remaining_secs=89), [], self.handlers)
        self.assertIs(self.buttons()[0], first)
        self.assertIn('01:29', self.panel.clock.get_label())

    def test_sin_reloj_no_hay_botones(self):
        self.panel.set_pomodoro(None, [], self.handlers)
        self.assertEqual(self.buttons(), [])

    def test_el_boton_con_agente_manda_tarea_y_carpeta(self):
        task = dict(id='7', title='HU-001', project='personal / apunte', repo='/r/apunte')
        self.panel.set_pomodoro(self.status(), [task], dict(self.handlers, agent=lambda *a: self.log.append(('agent',) + a)))
        [b for b in self.buttons() if b.get_label() == 'Con agente'][0].emit('clicked')
        self.assertEqual(self.log, [('agent', '7', '/r/apunte')])

    def test_sin_repo_no_hay_boton_con_agente(self):
        task = dict(id='7', title='HU-001', project='clientes / nutricore', repo='')
        self.panel.set_pomodoro(self.status(), [task], dict(self.handlers, agent=lambda *a: None))
        self.assertNotIn('Con agente', [b.get_label() for b in self.buttons()])


TREE = """[8] personal
  [15] apunte  ← /home/elyares/develop/personal/apunte
  [9] labs
    [20] vispyx  ← /home/elyares/develop/personal/labs/vispyx
[5] clientes
  [6] nutricore
"""


class Repos(unittest.TestCase):
    def test_la_ruta_del_arbol_da_la_carpeta_del_repo(self):
        found = pomodoro.parse_projects(TREE)
        self.assertEqual(found['personal / apunte'], '/home/elyares/develop/personal/apunte')
        self.assertEqual(found['personal / labs / vispyx'], '/home/elyares/develop/personal/labs/vispyx')

    def test_un_proyecto_sin_repo_no_entra(self):
        self.assertNotIn('clientes / nutricore', pomodoro.parse_projects(TREE))



@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class AvisoAlTerminar(unittest.TestCase):
    def done(self, repo, cwd, phase):
        from types import SimpleNamespace
        from unittest import mock
        from elyares import chatview
        isl = SimpleNamespace(pomo_repo=repo)
        with mock.patch.object(pomodoro, 'snapshot', return_value={'phase': phase}):
            return chatview.ChatView.pomodoro_done(isl, SimpleNamespace(cwd=cwd))

    def test_en_foco_y_en_su_carpeta_ofrece_tarea_hecha(self):
        got = self.done('/r/a', '/r/a', 'focus')
        self.assertEqual(got[0]['cmd'], ['coffe', 'done'])

    def test_otra_carpeta_o_sin_foco_no_ofrece_nada(self):
        self.assertEqual(self.done('/r/a', '/r/b', 'focus'), [])
        self.assertEqual(self.done('/r/a', '/r/a', 'break'), [])
        self.assertEqual(self.done('', '/r/a', 'focus'), [])
