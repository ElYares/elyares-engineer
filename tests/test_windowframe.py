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
class Temporada(unittest.TestCase):
    def tearDown(self):
        from elyares import themes
        themes.use(themes.DEFAULT)
        windowframe.use_theme()

    def test_la_guirnalda_es_solo_de_navidad(self):
        from elyares import themes
        themes.use('navidad')
        windowframe.use_theme()
        self.assertIn('repeating-linear-gradient', windowframe.CSS)
        themes.use('omarchy')
        windowframe.use_theme()
        self.assertNotIn('repeating-linear-gradient', windowframe.CSS)

    def test_las_luces_rodean_el_borde_y_los_clics_pasan(self):
        luces = windowframe.Lights()
        puntos = windowframe.Lights.points(300, 200)
        self.assertGreater(len(puntos), 20)
        self.assertTrue(all(0 <= x <= 300 and 0 <= y <= 200 for x, y in puntos))
        self.assertFalse(luces.get_can_target())
        self.assertFalse(luces.get_visible())


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class Marco(unittest.TestCase):

    def setUp(self):
        self.clicks = []
        self.frame = windowframe.Frame(self.clicks.append)

    def test_al_volver_la_isla_se_esconde_todo_panel_de_la_ventana(self):
        # Un panel que se quedara visible taparía la isla suelta (la capa) al cerrar la ventana.
        extra = Gtk.Box()
        self.frame.extra.append(extra)
        panels = (self.frame.sources, self.frame.alerts, self.frame.settings, self.frame.tmux,
                  self.frame.pomodoro, extra)
        for panel in panels:
            panel.set_visible(True)
        self.frame.hide_panels()
        self.assertEqual([p.get_visible() for p in panels], [False] * len(panels))

    def test_los_estilos_se_leen_sin_errores(self):
        errors = []
        css = Gtk.CssProvider()
        css.connect('parsing-error', lambda _p, _sec, err: errors.append(err.message))
        css.load_from_string(windowframe.CSS)
        self.assertEqual(errors, [])

    def test_los_botones_miden_24_px_al_menos(self):
        """WCAG 2.5.8: nada pulsable por debajo de 24x24."""
        self.assertNotIn('min-height: 0', windowframe.CSS)
        self.assertGreaterEqual(windowframe.CSS.count('min-height: 24px; min-width: 24px'), 3)

    def test_el_foco_se_ve_en_todos_los_controles(self):
        for selector in ('entry:focus-within', 'dropdown:focus-within', 'switch:focus-visible', '.elyares-pill:focus-visible'):
            self.assertIn(selector, windowframe.CSS)

    def test_ajustes_ofrece_los_tres_tamanos_de_la_vista_cansada(self):
        picked = []
        handlers = dict(toggle=lambda k: None, move=lambda v: None, theme=lambda: None, font=lambda f: None,
                        pick_theme=lambda t: None, tired_scale=picked.append)
        self.frame.settings.set_rows([], None, handlers, tired_scale=150)
        drops = []
        child = self.frame.settings.page.get_first_child()
        while child is not None:
            if isinstance(child, Gtk.DropDown):
                drops.append(child)
            child = child.get_next_sibling()
        sizes = drops[0]                      # el primero, antes del tema y de la letra
        self.assertEqual(sizes.get_selected(), 1)
        sizes.set_selected(2)
        self.assertEqual(picked, [200])

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
        self.assertEqual(list(self.frame.buttons), [key for key, _ in windowframe.VIEWS] + ['alerts'])

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

    def test_cambiar_el_tiempo_retoca_el_texto_y_conserva_la_fila(self):
        self.frame.set_sessions(self.ROWS, 'a')
        first = self.frame.sidebar.get_first_child()
        rows = [(self.ROWS[0][0], self.ROWS[0][1], self.ROWS[0][2], 'Trabaja · 9 min')] + self.ROWS[1:]
        self.frame.set_sessions(rows, 'b')
        self.assertIs(self.frame.sidebar.get_first_child(), first)
        self.assertEqual(self.frame.session_refs['a']['sub'].get_label(), 'Trabaja · 9 min')
        self.assertEqual(self.frame.sidebar.get_selected_row().sid, 'b')

    def test_a_480_la_barra_lateral_se_pliega_y_a_lo_ancho_vuelve(self):
        self.frame.fold(windowframe.FOLD_W - 1)
        self.assertFalse(self.frame.side_box.get_visible())
        self.frame.fold(windowframe.FOLD_W)
        self.assertTrue(self.frame.side_box.get_visible())

    def test_el_orden_de_tab_es_el_de_lectura_barra_lateral_y_contenido(self):
        order = [self.frame.header, self.frame.body]
        self.assertIs(self.frame.body.get_first_child(), self.frame.side_box)
        self.assertIs(self.frame.side_box.get_next_sibling(), self.frame.slot)
        self.assertTrue(all(b.get_focusable() for b in self.frame.buttons.values()))
        self.assertTrue(order)

    def test_al_volver_la_isla_los_paneles_se_esconden(self):
        self.frame.board.place(200)
        self.frame.chat_head.place(52)
        self.frame.sources.set_visible(True)
        self.frame.hide_panels()
        self.assertFalse(any(w.get_visible() for w in (self.frame.board, self.frame.chat_head,
                                                       self.frame.sources, self.frame.alerts,
                                                       self.frame.settings)))

    def test_el_contenido_llena_el_hueco(self):
        area = Gtk.DrawingArea()
        self.frame.set_content(area)
        self.assertTrue(area.get_hexpand() and area.get_vexpand())
        self.assertEqual(area.get_halign(), Gtk.Align.FILL)

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

    def test_cambiar_solo_el_texto_no_reconstruye_ni_pierde_el_foco(self):
        cards = [self.card('architect')]
        self.board.set_cards(cards, [], self.handlers)
        first = self.board.page.get_first_child()
        again = [dict(cards[0], state='Trabaja · 1 min 06 s', steps=['otro paso'])]
        self.board.set_cards(again, [], self.handlers)
        self.assertIs(self.board.page.get_first_child(), first)
        self.assertEqual(self.board.refs['architect']['state'].get_label(), 'Trabaja · 1 min 06 s')
        self.assertEqual(self.board.refs['architect']['steps'][0].get_label(), 'otro paso')

    def test_cambiar_quien_pide_permiso_si_reconstruye(self):
        self.board.set_cards([self.card('architect')], [], self.handlers)
        first = self.board.page.get_first_child()
        self.board.set_cards([self.card('architect', ask=True)], [], self.handlers)
        self.assertIsNot(self.board.page.get_first_child(), first)

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
                    project='api', status='Listo', where='~/api', busy=False, can_split=True, edited=0)
        return {**base, **kw}

    def labels(self):
        return [b.get_label() for b in _buttons(self.head)]

    def test_sus_enlaces_en_orden(self):
        self.head.set_info(self.info(), self.handlers)
        self.assertEqual(self.labels(), ['Otra', 'Nuevo', 'Cerrar'])

    def test_detener_solo_si_trabaja_y_otra_solo_si_cabe(self):
        self.head.set_info(self.info(busy=True, can_split=False), self.handlers)
        self.assertEqual(self.labels(), ['Nuevo', 'Detener', 'Cerrar'])

    def test_con_archivos_tocados_sale_su_boton_con_la_cuenta(self):
        self.head.set_info(self.info(edited=3), self.handlers)
        self.assertEqual(self.labels(), ['Archivos · 3', 'Otra', 'Nuevo', 'Cerrar'])
        _buttons(self.head)[0].emit('clicked')
        self.assertEqual(self.log, ['files'])

    def test_la_cuenta_de_archivos_se_retoca_sin_reconstruir(self):
        self.head.set_info(self.info(edited=1), self.handlers)
        first = _buttons(self.head)[0]
        self.head.set_info(self.info(edited=2), self.handlers)
        self.assertIs(_buttons(self.head)[0], first)
        self.assertEqual(first.get_label(), 'Archivos · 2')

    def test_sin_archivos_tocados_no_hay_boton(self):
        self.head.set_info(self.info(edited=0), self.handlers)
        self.assertNotIn('Archivos · 0', self.labels())

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


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class Fuentes(unittest.TestCase):

    ROWS = [('claude', 'Claude', '#34d399', 'Conectada · 1 sesión'),
            ('github', 'GitHub', '#ff6b6b', 'Con problemas'),
            ('coffe', 'coffe', None, 'Apagada')]

    def setUp(self):
        self.log = []
        self.panel = windowframe.SourcesPanel()
        self.handlers = dict(pick=lambda k: self.log.append(('pick', k)),
                             toggle=lambda k: self.log.append(('toggle', k)))

    @staticmethod
    def detail(**kw):
        base = dict(key='github', title='GitHub', status='Con problemas desde hace 3 min',
                    about='Checks de tus PRs', lines=[], why='falta gh', fix='instala gh',
                    toggle=True, on=True, cmds=[('gh auth login', 'inicia sesión')])
        return {**base, **kw}

    def test_una_fila_por_fuente_con_su_estado_en_texto(self):
        self.panel.set_data(self.ROWS, 'github', self.detail(), self.handlers)
        keys = []
        row = self.panel.list.get_first_child()
        while row is not None:
            keys.append(row.key)
            row = row.get_next_sibling()
        self.assertEqual(keys, ['claude', 'github', 'coffe'])
        self.assertEqual(self.panel.list.get_selected_row().key, 'github')

    def test_elegir_una_fila_avisa(self):
        self.panel.set_data(self.ROWS, 'claude', self.detail(), self.handlers)
        self.panel.list.emit('row-activated', self.panel.list.get_row_at_index(2))
        self.assertEqual(self.log, [('pick', 'coffe')])

    def test_el_interruptor_prende_o_apaga_y_la_sincronizacion_no(self):
        self.panel.set_data(self.ROWS, 'github', self.detail(on=True), self.handlers)
        switches = []

        def walk(w):
            if isinstance(w, Gtk.Switch):
                switches.append(w)
            c = w.get_first_child()
            while c is not None:
                walk(c)
                c = c.get_next_sibling()
        walk(self.panel.detail)
        self.assertEqual(len(switches), 1)
        self.assertTrue(switches[0].get_active())
        self.assertEqual(self.log, [])                  # armarlo no es un clic
        switches[0].set_active(False)
        self.assertEqual(self.log, [('toggle', 'github')])

    def test_reintentar_y_abrir_pr_avisan(self):
        self.handlers.update(retry=lambda k: self.log.append(('retry', k)),
                             open=lambda u: self.log.append(('open', u)))
        d = self.detail(retry=True, items=[dict(label='api#7 arregla', note='en rojo', url='https://x/7')])
        self.panel.set_data(self.ROWS, 'github', d, self.handlers)
        buttons = {b.get_label(): b for b in _buttons(self.panel)}
        buttons['Reintentar'].emit('clicked')
        buttons['Abrir PR'].emit('clicked')
        self.assertEqual(self.log, [('retry', 'github'), ('open', 'https://x/7')])

    def test_claude_no_trae_interruptor(self):
        self.panel.set_data(self.ROWS, 'claude', self.detail(key='claude', toggle=False), self.handlers)
        found = []

        def walk(w):
            if isinstance(w, Gtk.Switch):
                found.append(w)
            c = w.get_first_child()
            while c is not None:
                walk(c)
                c = c.get_next_sibling()
        walk(self.panel.detail)
        self.assertEqual(found, [])


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class Bandeja(unittest.TestCase):

    def setUp(self):
        self.log = []
        self.handlers = dict(act=lambda sid, key: self.log.append((sid, key)),
                             toggle=lambda k: self.log.append(('toggle', k)),
                             move=lambda v: self.log.append(('move', v)),
                             theme=lambda: self.log.append('theme'))

    def test_cuatro_alertas_cuatro_tarjetas_con_sus_botones(self):
        panel = windowframe.AlertsPanel()
        alerts = [dict(sid=f'a{i}', title=f'alerta {i}', color='#ff6b6b', lines=['detalle'], where='', note='',
                       buttons=[('dismiss', 'Descartar'), (0, 'Logs')]) for i in range(4)]
        panel.set_alerts(alerts, self.handlers)
        labels = [b.get_label() for b in _buttons(panel)]
        self.assertEqual(labels, ['Descartar', 'Logs'] * 4)
        _buttons(panel)[0].emit('clicked')
        _buttons(panel)[1].emit('clicked')
        self.assertEqual(self.log, [('a0', 'dismiss'), ('a0', 0)])

    def test_sin_alertas_lo_dice(self):
        panel = windowframe.AlertsPanel()
        panel.set_alerts([], self.handlers)
        self.assertEqual(_buttons(panel), [])

    def test_la_campana_cuenta_y_no_dispara_al_sincronizar(self):
        clicks = []
        frame = windowframe.Frame(clicks.append)
        frame.set_bell(4)
        self.assertEqual(frame.bell.get_label(), 'Alertas · 4')
        frame.sync('alerts')
        self.assertTrue(frame.bell.get_active())
        self.assertEqual(clicks, [])
        frame.sync('board')
        self.assertFalse(frame.bell.get_active())
        self.assertTrue(frame.buttons['board'].get_active())

    def test_ajustes_cada_interruptor_cambia_su_clave(self):
        panel = windowframe.SettingsPanel()
        rows = [('glass', 'Vidrio', False, ''), ('github', 'Fuente: GitHub', True, '')]
        panel.set_rows(rows, 50, self.handlers)
        switches = []

        def walk(w):
            if isinstance(w, Gtk.Switch):
                switches.append(w)
            c = w.get_first_child()
            while c is not None:
                walk(c)
                c = c.get_next_sibling()
        walk(panel.page)
        self.assertEqual(len(switches), 2)
        self.assertEqual(self.log, [])
        switches[0].set_active(True)
        switches[1].set_active(False)
        self.assertEqual(self.log, [('toggle', 'glass'), ('toggle', 'github')])


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class Sesiones(unittest.TestCase):

    def test_un_boton_por_ventana_y_el_clic_salta(self):
        log = []
        panel = windowframe.TmuxPanel()
        wins = [dict(index='1', name='edit', state='', path='/p'),
                dict(index='2', name='claude', state='working', path='/p')]
        panel.set_sessions([dict(name='api', state='working', claudes=1, windows=wins)],
                           dict(jump=lambda s, w: log.append((s, w))))
        self.assertEqual(len(_buttons(panel)), 2)
        _buttons(panel)[1].emit('clicked')
        self.assertEqual(log, [('api', '2')])

    def test_sin_tmux_y_sin_respuesta_no_hay_botones(self):
        panel = windowframe.TmuxPanel()
        panel.set_sessions([], {})
        self.assertEqual(_buttons(panel), [])
        panel.set_sessions(None, {})
        self.assertEqual(_buttons(panel), [])


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class Ayuda(unittest.TestCase):

    def setUp(self):
        self.dialog = windowframe.HelpDialog(None, None)
        self.dialog.set_items([('Teclado', 'SUPER ALT + C', 'abre el chat'),
                               ('coffe', 'coffe start', 'arranca un pomodoro'),
                               ('Ratón', 'botón del medio', 'arrastra la isla')])

    def test_escribir_coffe_deja_solo_lo_que_lo_contiene(self):
        self.assertEqual(len(self.dialog.shown()), 3)
        self.dialog.search.set_text('coffe')
        self.assertEqual(len(self.dialog.shown()), 1)

    def test_esc_cierra_y_devuelve_el_foco_al_icono(self):
        opener = Gtk.Button(label='?')
        dialog = windowframe.HelpDialog(None, opener)
        focused = []
        opener.grab_focus = lambda: focused.append(True) or True
        self.assertTrue(dialog._key(None, windowframe.Gdk.KEY_Escape, 0, 0))
        self.assertEqual(focused, [True])


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi o sin pantalla')
class Desglose(unittest.TestCase):

    def test_pasos_enlaces_y_los_demas_avisan(self):
        panel = windowframe.FocusPanel()
        log = []
        d = dict(role='auditor', name='auditor', color='#9a6bff', pet='working', busy=True,
                 label='api · chat', summary='2 pasos · 13 s',
                 steps=[('✓', '#34d399', 'git status', '3 s'), ('›', '#f2f5ff', 'git add -A', 'ahora')],
                 links=[('talk', 'elyares-auditor', 'Ver su chat'), ('back', None, '‹ Volver')],
                 others=[('reviewer', 'idle', False)], hidden=0, empty='')
        panel.set_focus(d, dict(face=lambda *a: None, link=lambda k, v: log.append((k, v)),
                                other=lambda r, b: log.append(('other', r, b))))
        buttons = _buttons(panel)
        self.assertEqual([b.get_label() for b in buttons[:2]], ['Ver su chat', '‹ Volver'])
        buttons[0].emit('clicked')
        buttons[1].emit('clicked')
        buttons[2].emit('clicked')
        self.assertEqual(log, [('talk', 'elyares-auditor'), ('back', None), ('other', 'reviewer', False)])
        self.assertEqual(len(panel.faces), 1)       # solo el que trabaja se anima

    def test_un_paso_se_abre_abajo_con_su_texto_entero(self):
        panel = windowframe.FocusPanel()
        picks = []
        d = dict(role='auditor', name='auditor', color='#9a6bff', pet='working', busy=True,
                 label='api · chat', summary='2 pasos', links=[], others=[], hidden=0, empty='',
                 steps=[('✓', '#34d399', 'git status ' + 'x' * 300, '3 s'), ('›', '#f2f5ff', 'git add -A', 'ahora')])
        panel.set_focus(d, dict(face=lambda *a: None, link=lambda *a: None, other=lambda *a: None,
                                pick=lambda: picks.append(True)))
        self.assertNotIn('detail', panel.refs)
        panel._pick(0)
        self.assertEqual(panel.refs['detail'][1].get_label(), d['steps'][0][2])
        self.assertEqual(panel.refs['detail'][0].get_label(), 'Paso 1 · 3 s')
        panel._pick(0)                              # el mismo clic lo cierra
        self.assertNotIn('detail', panel.refs)
        self.assertEqual(len(picks), 2)


class CaraQuieta(unittest.TestCase):
    """La cara quieta se dibuja una vez y después solo se estampa."""

    def test_se_reutiliza_la_misma_superficie(self):
        import cairo
        from elyares import mascot
        mascot._STATIC.clear()
        cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 100, 100))
        mascot.paint_static(cr, 'auditor', 'idle', 50, 50, 40)
        first = dict(mascot._STATIC)
        mascot.paint_static(cr, 'auditor', 'idle', 20, 20, 40, .5)
        self.assertEqual(len(mascot._STATIC), 1)
        self.assertIs(list(mascot._STATIC.values())[0], list(first.values())[0])
        mascot.paint_static(cr, 'auditor', 'working', 50, 50, 40)   # otro gesto: otra superficie
        self.assertEqual(len(mascot._STATIC), 2)

    def test_deja_pintura(self):
        import cairo
        from elyares import mascot
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 100, 100)
        mascot.paint_static(cairo.Context(surf), 'engineer', 'idle', 50, 50, 60)
        self.assertTrue(any(surf.get_data()))


if __name__ == '__main__':
    unittest.main()
