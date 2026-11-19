"""La vista Tareas: el ToDo por proyectos de `coffe`. El análisis es puro; los widgets piden pantalla."""

import unittest
from unittest import mock

try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    HAVE_DISPLAY = Gtk.init_check()
except (ImportError, ValueError):
    HAVE_DISPLAY = False

from elyares import pomodoro

LIST = """\
   1  pendiente —            alta    HU-002 - cotizacion por dis… [0/3] strapp / aang
  17  pendiente —            media   HU-001 - Borrador que sobre… [0] personal / apunte
 110  refri     —            alta    CU-001 - Recibir un aviso y… [0/6] personal / elyares-notify
 111  pendiente —            baja    CU-002 - Reemplazar un avis… [0/3] personal / elyares-notify
 150  en curso  —            alta    HU-004 - Capturar viajes de… [2/18] clientes / patio
 164  hecha     —            alta    HU-001 - Workspace y CI      [0/2] personal / geoda
  91  pendiente —            alta    HU-007 - CI con wheels y pu… [0/6] personal / labs / vispyx
"""


class Analisis(unittest.TestCase):
    def test_lee_todos_los_estados_y_los_proyectos_con_barra(self):
        tasks = pomodoro.parse_all(LIST)
        self.assertEqual(len(tasks), 7)
        live = next(t for t in tasks if t['id'] == '150')
        self.assertEqual((live['state'], live['done'], live['estimate'], live['project']),
                         ('en curso', 2, 18, 'clientes / patio'))
        self.assertEqual(next(t for t in tasks if t['id'] == '17')['estimate'], 0)          # «[0]» sin estimado
        self.assertEqual(next(t for t in tasks if t['id'] == '91')['project'], 'personal / labs / vispyx')

    def test_agrupa_por_proyecto_con_lo_que_corre_arriba_y_ordena_por_prioridad(self):
        groups = pomodoro.by_project(pomodoro.parse_all(LIST))
        self.assertEqual([name for name, _items in groups],
                         ['clientes / patio', 'personal / elyares-notify', 'personal / apunte',
                          'personal / labs / vispyx', 'strapp / aang'])                     # sin geoda: solo tiene una hecha
        notify = dict(groups)['personal / elyares-notify']
        self.assertEqual([t['id'] for t in notify], ['110', '111'])                         # el refri antes que la pendiente

    def test_las_hechas_y_la_busqueda_filtran(self):
        tasks = pomodoro.parse_all(LIST)
        self.assertEqual([n for n, _ in pomodoro.by_project(tasks, ('hecha',))], ['personal / geoda'])
        self.assertEqual([n for n, _ in pomodoro.by_project(tasks, query='VISPYX')], ['personal / labs / vispyx'])
        self.assertEqual(pomodoro.by_project(tasks, query='no existe'), [])


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class Panel(unittest.TestCase):
    def setUp(self):
        from elyares import taskpanel
        self.taskpanel = taskpanel
        self.panel = taskpanel.TasksPanel()
        self.calls = []
        self.handlers = dict(act=lambda *a: self.calls.append(a), agent=lambda *a: self.calls.append(('agent', *a)))
        self.tasks = [dict(t, repo='/r' if t['project'] == 'strapp / aang' else '')
                      for t in pomodoro.parse_all(LIST)]

    def buttons(self, widget, out=None):
        out = [] if out is None else out
        child = widget.get_first_child()
        while child is not None:
            if isinstance(child, Gtk.Button) and not isinstance(child, (Gtk.ToggleButton, Gtk.CheckButton)):
                out.append(child)
            self.buttons(child, out)
            child = child.get_next_sibling()
        return out

    def test_resume_y_pliega_un_proyecto(self):
        self.panel.set_tasks(self.tasks, self.handlers)
        self.assertEqual(self.panel.summary.get_label(), '6 tareas en 5 proyectos')
        before = len(self.buttons(self.panel.page))
        self.panel._fold('personal / elyares-notify')
        self.assertLess(len(self.buttons(self.panel.page)), before)

    def test_empezar_y_con_agente_llaman_a_sus_handlers(self):
        self.panel.set_tasks(self.tasks, self.handlers)
        for btn in self.buttons(self.panel.page):
            if btn.get_label() == 'Empezar con agente':
                btn.emit('clicked')
        self.assertEqual(self.calls, [('agent', '1', '/r')])
        self.calls.clear()
        for btn in self.buttons(self.panel.page):
            if btn.get_label() == '▶':
                btn.emit('clicked')
        self.assertIn(('start', '1'), self.calls)
        self.assertNotIn(('start', '150'), self.calls)              # la que ya corre no se vuelve a empezar

    def test_otro_filtro_cambia_la_lista(self):
        self.panel.set_tasks(self.tasks, self.handlers)
        self.panel.mode = 'done'
        self.panel._again()
        self.assertEqual(self.panel.summary.get_label(), '1 tarea en 1 proyecto')

    def labels(self, widget, out=None):
        out = [] if out is None else out
        child = widget.get_first_child()
        while child is not None:
            if isinstance(child, Gtk.Label):
                out.append(child.get_label())
            self.labels(child, out)
            child = child.get_next_sibling()
        return out

    def test_el_repo_que_llega_despues_trae_empezar_con_agente(self):
        bare = [dict(t, repo='') for t in self.tasks]                        # `coffe project list` aún no contesta
        self.panel.set_tasks(bare, self.handlers)
        self.assertNotIn('Empezar con agente', [b.get_label() for b in self.buttons(self.panel.page)])
        self.panel.set_tasks(self.tasks, self.handlers)
        self.assertIn('Empezar con agente', [b.get_label() for b in self.buttons(self.panel.page)])

    def test_otra_prioridad_o_estimado_rehace_la_fila(self):
        self.panel.set_tasks(self.tasks, self.handlers)
        changed = [dict(t, estimate=9) if t['id'] == '1' else t for t in self.tasks]
        self.panel.set_tasks(changed, self.handlers)
        self.assertIn('0/9', self.labels(self.panel.page))

    def test_la_casilla_manda_hecha_o_reabrir_y_se_corrige_si_coffe_se_niega(self):
        self.panel.mode = 'all'
        self.panel.set_tasks(self.tasks, self.handlers)
        checks = self.panel.focusables
        checks[('check', '1')].set_active(True)
        self.assertEqual(self.calls[-1], ('task', 'done', '1'))
        checks[('check', '164')].set_active(False)
        self.assertEqual(self.calls[-1], ('task', 'reopen', '164'))
        self.panel.set_tasks(self.tasks, self.handlers)                      # coffe no la cambió: vuelve atrás
        self.assertFalse(self.panel.focusables[('check', '1')].get_active())

    def test_mientras_coffe_no_contesta_no_dice_nada_pendiente(self):
        self.panel.set_tasks([], self.handlers, ('loading', ''))
        self.assertIn(self.taskpanel.LOADING, self.labels(self.panel.page))
        self.assertNotIn(self.taskpanel.EMPTY['open'], self.labels(self.panel.page))

    def test_si_coffe_falla_lo_dice_y_reintentar_vuelve_a_preguntar(self):
        retry = mock.Mock()
        self.panel.set_tasks([], dict(self.handlers, retry=retry), ('error', 'connection refused'))
        self.assertTrue(any('coffe no contesta' in t for t in self.labels(self.panel.page)))
        again = [b for b in self.buttons(self.panel.page) if b.get_label() == 'Reintentar']
        again[0].emit('clicked')
        retry.assert_called_once()

    def test_el_gris_de_la_cuenta_es_el_del_tema_de_ahora(self):
        with mock.patch.object(self.taskpanel.windowframe, 'MUTED', '#123456'):
            self.panel.set_tasks(self.tasks, self.handlers)
        heads = [b for b in self.buttons(self.panel.page) if b.has_css_class('elyares-pill')]
        self.assertIn('#123456', heads[0].get_child().get_label())

    def test_plegar_un_proyecto_deja_el_foco_en_su_cabecera(self):
        win = Gtk.Window()
        win.set_child(self.panel)
        self.panel.set_tasks(self.tasks, self.handlers)
        head = self.panel.focusables[('fold', 'strapp / aang')]
        head.grab_focus()
        head.emit('clicked')
        self.assertIsNot(self.panel.focusables[('fold', 'strapp / aang')], head)     # se rehízo
        self.assertEqual(win.get_focus(), self.panel.focusables[('fold', 'strapp / aang')])


if __name__ == '__main__':
    unittest.main()
