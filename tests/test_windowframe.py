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

    ROWS = [('a', 'api · chat', '#ff6b6b', 'Pide permiso'), ('b', 'web', None, 'En reposo')]

    def test_la_barra_lateral_lista_las_sesiones_con_su_estado_en_texto(self):
        self.frame.set_sessions(self.ROWS, 'b')
        rows = []
        row = self.frame.sidebar.get_first_child()
        while row is not None:
            rows.append(row.sid)
            row = row.get_next_sibling()
        self.assertEqual(rows, ['a', 'b'])
        self.assertEqual(self.frame.sidebar.get_selected_row().sid, 'b')

    def test_elegir_una_fila_avisa_y_sincronizar_no(self):
        picked = []
        frame = windowframe.Frame(self.clicks.append, picked.append)
        frame.set_sessions(self.ROWS, 'a')
        self.assertEqual(picked, [])
        frame.sidebar.emit('row-activated', frame.sidebar.get_row_at_index(1))
        self.assertEqual(picked, ['b'])

    def test_sin_cambios_no_se_reconstruye(self):
        self.frame.set_sessions(self.ROWS, 'a')
        first = self.frame.sidebar.get_first_child()
        self.frame.set_sessions(list(self.ROWS), 'a')
        self.assertIs(self.frame.sidebar.get_first_child(), first)

    def test_a_480_la_barra_lateral_se_pliega_y_a_lo_ancho_vuelve(self):
        self.frame.fold(windowframe.FOLD_W - 1)
        self.assertFalse(self.frame.sidebar.get_visible())
        self.frame.fold(windowframe.FOLD_W)
        self.assertTrue(self.frame.sidebar.get_visible())

    def test_el_orden_de_tab_es_el_de_lectura_barra_lateral_y_contenido(self):
        order = [self.frame.header, self.frame.body]
        self.assertIs(self.frame.body.get_first_child(), self.frame.sidebar)
        self.assertIs(self.frame.sidebar.get_next_sibling(), self.frame.slot)
        self.assertTrue(all(b.get_focusable() for b in self.frame.buttons.values()))
        self.assertTrue(order)

    def test_el_contenido_es_uno_y_se_quita(self):
        a, b = Gtk.DrawingArea(), Gtk.DrawingArea()
        self.frame.set_content(a)
        self.frame.set_content(b)
        self.assertIs(self.frame.slot.get_first_child(), b)
        self.assertIsNone(b.get_next_sibling())
        self.frame.set_content(None)
        self.assertIsNone(self.frame.slot.get_first_child())


def _buttons(widget, found=None):
    """Todos los Gtk.Button debajo de un widget."""
    found = [] if found is None else found
    if isinstance(widget, Gtk.Button):
        found.append(widget)
    child = widget.get_first_child()
    while child is not None:
        _buttons(child, found)
        child = child.get_next_sibling()
    return found


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class Tablero(unittest.TestCase):

    def setUp(self):
        self.board = windowframe.BoardPanel()
        self.log = []
        self.handlers = dict(face=lambda *a: None,
                             pick=lambda role, busy: self.log.append(('pick', role, busy)),
                             decide=lambda allow: self.log.append(('decide', allow)))

    @staticmethod
    def card(role, busy=True, ask=False, state='Trabaja'):
        return dict(role=role, name=role, color='#22c7dd', state=state, steps=['leyendo'], busy=busy,
                    ask=ask, pet='working' if busy else 'idle')

    def test_sin_permiso_no_hay_botones(self):
        self.board.set_cards([self.card('architect')], [self.card('devops', busy=False)], self.handlers)
        self.assertEqual(_buttons(self.board), [])

    def test_con_permiso_hay_permitir_y_denegar_que_contestan(self):
        self.board.set_cards([self.card('auditor', ask=True, state='Pide permiso')], [], self.handlers)
        buttons = {b.get_label(): b for b in _buttons(self.board)}
        self.assertEqual(sorted(buttons), ['Denegar', 'Permitir'])
        buttons['Permitir'].emit('clicked')
        buttons['Denegar'].emit('clicked')
        self.assertEqual(self.log, [('decide', True), ('decide', False)])

    def test_sin_cambios_no_se_reconstruye(self):
        cards = [self.card('architect')]
        self.board.set_cards(cards, [], self.handlers)
        first = self.board.page.get_first_child()
        self.board.set_cards(list(cards), [], self.handlers)
        self.assertIs(self.board.page.get_first_child(), first)

    def test_solo_las_que_trabajan_se_animan(self):
        self.board.set_cards([self.card('architect')], [self.card('devops', busy=False)], self.handlers)
        self.assertEqual(len(self.board.faces), 1)

    def test_alto_cero_la_esconde(self):
        self.board.place(200)
        self.assertTrue(self.board.get_visible())
        self.board.place(0)
        self.assertFalse(self.board.get_visible())


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class CabeceraDelChat(unittest.TestCase):

    def setUp(self):
        self.head = windowframe.ChatHead()
        self.log = []
        self.handlers = dict(face=lambda *a: None, act=self.log.append)

    @staticmethod
    def info(**kw):
        base = dict(role='architect', pet='idle', name='elyares-architect', color='#22c7dd',
                    project='api', status='Listo', where='~/api', busy=False, can_split=True)
        return {**base, **kw}

    def labels(self):
        return [b.get_label() for b in _buttons(self.head)]

    def test_sus_enlaces_en_orden(self):
        self.head.set_info(self.info(), self.handlers)
        self.assertEqual(self.labels(), ['Otra', 'Nuevo', 'Cerrar'])

    def test_detener_solo_si_trabaja_y_otra_solo_si_cabe(self):
        self.head.set_info(self.info(busy=True, can_split=False), self.handlers)
        self.assertEqual(self.labels(), ['Nuevo', 'Detener', 'Cerrar'])

    def test_un_enlace_avisa_con_su_clave(self):
        self.head.set_info(self.info(), self.handlers)
        for btn in _buttons(self.head):
            btn.emit('clicked')
        self.assertEqual(self.log, ['split', 'new', 'close'])

    def test_los_agentes_en_la_barra_lateral_llevan_cara_y_eligen(self):
        picked = []
        frame = windowframe.Frame(lambda v: None, picked.append)
        faces = []
        rows = [('agent:', 'elyares-engineer', None, '', 'engineer'),
                ('agent:elyares-auditor', 'elyares-auditor', None, 'Trabaja', 'auditor')]
        frame.set_sessions(rows, 'agent:', lambda cr, role, w, h: faces.append(role))
        self.assertEqual(frame.sidebar.get_selected_row().sid, 'agent:')
        frame.sidebar.emit('row-activated', frame.sidebar.get_row_at_index(1))
        self.assertEqual(picked, ['agent:elyares-auditor'])


if __name__ == '__main__':
    unittest.main()
