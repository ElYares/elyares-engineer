"""La vista Inicio: qué agentes se ven, en qué orden y qué pasa con un clic. Sin pantalla se salta lo de widgets."""

import unittest
from unittest import mock

try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    HAVE_DISPLAY = Gtk.init_check()
except (ImportError, ValueError):
    HAVE_DISPLAY = False

from elyares import homepanel


def card(role, busy=False, ask=False):
    return dict(role=role, name=role, color='#ffffff', state='Trabaja' if busy else 'libre',
                steps=['Edit app.py'] if busy else [], busy=busy, ask=ask, pet='idle')


ROLES = ('engineer', 'architect', 'auditor', 'reviewer', 'designer', 'mobile', 'devops', 'researcher')


class Orden(unittest.TestCase):
    def test_quien_pide_permiso_va_primero_y_luego_quien_trabaja(self):
        cards = [card(r) for r in ROLES]
        cards[5] = card('mobile', busy=True)
        cards[6] = card('devops', busy=True, ask=True)
        head, _ranked = homepanel.ordered(cards, '')
        self.assertEqual([c['role'] for c in head[:2]], ['devops', 'mobile'])
        self.assertEqual(len(head), homepanel.SHOWN)

    def test_el_elegido_nunca_se_queda_en_el_mas(self):
        cards = [card(r) for r in ROLES]
        head, _ranked = homepanel.ordered(cards, 'researcher')
        self.assertIn('researcher', [c['role'] for c in head])
        self.assertEqual(len(head), homepanel.SHOWN)


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class Panel(unittest.TestCase):
    def setUp(self):
        self.panel = homepanel.HomePanel()
        self.calls = []
        self.handlers = dict(face=mock.Mock(), decide=lambda a: self.calls.append(('decide', a)),
                             view=lambda k: self.calls.append(('view', k)),
                             chat=lambda r: self.calls.append(('chat', r)))

    def tiles(self):
        out, child = [], self.panel.grid.get_first_child()
        while child is not None:
            out.append(child)
            child = child.get_next_sibling()
        return out

    def test_muestra_cinco_y_un_mas_y_con_ver_todos_los_once(self):
        cards = [card(r) for r in ROLES]
        self.panel.set_data('elyares-engineer', cards, self.handlers)
        self.assertEqual(len(self.tiles()), homepanel.SHOWN + 1)           # 5 tarjetas + «+ 3 más»
        self.assertEqual(self.panel.title.get_label(), 'ELYARES-ENGINEER')
        self.panel._toggle_all(None)
        self.assertEqual(len(self.tiles()), len(cards) + 1)                # todas + «Ver menos»

    def test_el_contexto_sigue_a_quien_pide_permiso_y_se_decide_desde_ahi(self):
        cards = [card(r) for r in ROLES]
        cards[3] = card('reviewer', busy=True, ask=True)
        self.panel.set_data('x', cards, self.handlers)
        self.assertEqual(self.panel.picked, 'reviewer')
        labels = []
        child = self.panel.context.get_first_child()
        while child is not None:
            if isinstance(child, Gtk.Box):
                btn = child.get_first_child()
                while btn is not None:
                    labels.append(btn.get_label())
                    btn = btn.get_next_sibling()
            child = child.get_next_sibling()
        self.assertEqual(labels, ['Permitir', 'Denegar'])

    def test_habitos_es_un_panel_del_contexto_y_tareas_lleva_a_la_vista_pomodoro(self):
        cards = [card(r) for r in ROLES]
        self.panel.set_data('x', cards, self.handlers)
        self.panel._menu_click('habits', 'pane', self.handlers)
        self.assertEqual(self.panel.pane, 'habits')
        self.panel._menu_click('pomodoro', 'view', self.handlers)
        self.assertIn(('view', 'pomodoro'), self.calls)
        self.panel._pick('mobile')                                  # elegir un agente devuelve el contexto al agente
        self.assertEqual(self.panel.pane, 'agent')

    def test_elegir_otro_cambia_el_contexto(self):
        cards = [card(r) for r in ROLES]
        self.panel.set_data('x', cards, self.handlers)
        self.panel._pick('mobile')
        self.assertEqual(self.panel.picked, 'mobile')


if __name__ == '__main__':
    unittest.main()
