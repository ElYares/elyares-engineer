"""La isla sin pantalla: contestar un permiso con el teclado, los botones de
una ficha y su dibujo sobre una superficie de cairo.

Necesita gi (GTK 4 y gtk4-layer-shell), que solo trae el python del sistema:
con otro python estas pruebas se saltan. No abre ninguna ventana: la isla se
arma con `Island.__new__` y solo lo que cada prueba usa.
"""

import json
import os
import threading
import time
import unittest
from unittest import mock

try:
    import cairo
    from elyares import app, chatview, commands, paint, settings, sources
except (ImportError, ValueError):       # sin gi o sin gtk4-layer-shell
    app = None

from elyares import state
from elyares.state import Model

T = 1000.0
HYPRLAND = ['elyares-ctl', 'Hyprland', 'systemd']
CLAUDE = ['elyares-ctl', 'bash', 'claude', 'bash', 'tmux: server', 'systemd']


class FakeReq:
    def __init__(self):
        self.done = False
        self.born = time.time()
        self.answers = []

    def reply(self, answer):
        self.done = True
        self.answers.append(answer)


@unittest.skipIf(app is None, 'sin gi: usa /usr/bin/python3')
class IslandCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(state, 'project_root', lambda cwd: cwd)
        patcher.start()
        self.addCleanup(patcher.stop)
        isl = app.Island.__new__(app.Island)
        isl.model = Model()
        isl.settings = dict(settings.DEFAULTS)
        isl.colors = paint.colors()
        isl.markups = {}
        isl.off = isl.hover = isl.expanded = False
        isl.pin, isl.reply_pick, isl.pointer, isl.buttons = '', '', None, {}
        isl.tab, isl.focus, isl.hits, isl.rows = '', None, [], []
        isl.tab_manual = False
        isl.look, isl.blink_until = [0.0, 0.0], 0.0
        isl.key_since = T
        isl.refresh = lambda: setattr(isl, 'view', isl.model.view(now=T, pin=isl.pin))
        isl.collapse_id = 0
        isl.check_panes = lambda: None
        isl.monitor = None
        isl.projects_init()
        isl.chat_init()
        # Ninguna prueba toca los workflows guardados de verdad.
        for name, value in (('load', lambda: []), ('save', mock.Mock())):
            flows = mock.patch.object(app.workflowview.workflows, name, value)
            flows.start()
            self.addCleanup(flows.stop)
        isl.workflows_init()
        isl.reloading = False
        # Ninguna prueba le pregunta a Hyprland de verdad.
        for name, value in (('focused_monitor', None), ('monitors', [])):
            hypr = mock.patch.object(app.hypr, name, lambda value=value: value)
            hypr.start()
            self.addCleanup(hypr.stop)
        # Ninguna prueba toca las conversaciones guardadas de verdad.
        chats = mock.patch.object(app.store, 'save_chats')
        self.save_chats = chats.start()
        self.addCleanup(chats.stop)
        # Ninguna prueba toca las preferencias de verdad.
        saver = mock.patch.object(app.settings, 'save')
        self.saved = saver.start()
        self.addCleanup(saver.stop)
        isl.ensure_tick = isl.collapse = lambda: None
        isl.refresh()
        self.isl = isl

    def ask(self, sid='a'):
        req = FakeReq()
        self.isl.model.handle({'event': 'ask', 'session_id': sid, 'cwd': '/x/proj', 'tool_name': 'Bash',
                               'tool_input': {'command': 'rm -rf build'}}, req, now=T)
        self.isl.refresh()
        return req

    def alert(self, **extra):
        self.isl.model.handle({'event': 'alert', 'session_id': 'x:1', 'name': 'api',
                               'message': 'se rompió', **extra}, now=T)
        self.isl.refresh()
        return self.isl.model.sessions['x:1']


class Teclado(IslandCase):
    def test_permitir(self):
        req = self.ask()
        self.assertEqual(self.isl.answer(True, HYPRLAND, now=T + 5), '')
        self.assertEqual(req.answers, [{'behavior': 'allow'}])
        self.assertFalse(self.isl.view.ask)

    def test_denegar(self):
        req = self.ask()
        self.assertEqual(self.isl.answer(False, HYPRLAND, now=T + 5), '')
        self.assertEqual(req.answers[0]['behavior'], 'deny')

    def test_claude_no_se_aprueba_a_si_mismo(self):
        req = self.ask()
        self.assertIn('Claude', self.isl.answer(True, CLAUDE, now=T + 5))
        # Sin saber quién lo pide, tampoco.
        self.assertTrue(self.isl.answer(True, [], now=T + 5))
        self.assertTrue(self.isl.answer(True, None, now=T + 5))
        self.assertEqual(req.answers, [])
        # Denegar no le da nada a nadie: eso sí puede.
        self.assertEqual(self.isl.answer(False, CLAUDE, now=T + 5), '')

    def test_sin_permiso_a_la_vista(self):
        self.assertIn('a la vista', self.isl.answer(True, HYPRLAND, now=T + 5))
        self.isl.model.handle({'event': 'permission', 'session_id': 'a', 'message': 'x'}, now=T)
        self.isl.refresh()
        # Un permiso sin hook esperando se contesta en la terminal.
        self.assertIn('a la vista', self.isl.answer(True, HYPRLAND, now=T + 5))

    def test_escondida_no_contesta(self):
        req = self.ask()
        self.isl.off = True
        self.assertIn('a la vista', self.isl.answer(True, HYPRLAND, now=T + 5))
        self.assertEqual(req.answers, [])

    def test_recien_salido_no_se_contesta(self):
        req = self.ask()
        self.assertIn('acaba de salir', self.isl.answer(True, HYPRLAND, now=T + .1))
        self.assertEqual(req.answers, [])
        self.assertEqual(self.isl.answer(True, HYPRLAND, now=T + app.ASK_GUARD_SECS), '')

    def test_la_orden_contesta_por_el_socket(self):
        self.ask()
        order = FakeReq()
        with mock.patch.object(app.time, 'monotonic', lambda: T + 5):
            self.isl.on_control('deny', {'control': 'deny', 'peer': CLAUDE}, order)
        self.assertEqual(order.answers, [{'ok': True, 'why': ''}])
        order = FakeReq()
        self.isl.on_control('allow', {'control': 'allow', 'peer': HYPRLAND}, order)
        self.assertFalse(order.answers[0]['ok'])


class Fijada(IslandCase):
    def setUp(self):
        super().setUp()
        # Aquí sí se cierra y se abre de verdad.
        self.isl.collapse = app.Island.collapse.__get__(self.isl)
        self.isl.expand = app.Island.expand.__get__(self.isl)

    def test_fijada_no_se_cierra_sola(self):
        self.isl.toggle_pinned()
        self.assertTrue(self.isl.expanded)
        self.saved.assert_called_once()
        self.assertTrue(self.saved.call_args.args[0]['pinned'])
        # El ratón se va, pasa el tiempo, se salta a un pane: sigue abierta.
        self.isl.set_hover(False)
        self.isl.on_collapse()
        self.isl.collapse()
        self.assertTrue(self.isl.expanded)
        self.assertEqual(self.isl.target(), 'open')
        # Abierta a mano: el detalle entero y las fuentes, sin ratón encima.
        self.assertEqual(self.isl.pills_h('open'), app.PILLS_H)

    def test_no_arranca_el_reloj_que_la_cerraria(self):
        self.isl.settings['pinned'] = True
        with mock.patch.object(app.GLib, 'timeout_add_seconds') as timer:
            self.isl.expand(app.KEY_OPEN_SECS)
        timer.assert_not_called()

    def test_soltarla_la_cierra(self):
        self.isl.toggle_pinned()
        self.isl.toggle_pinned()
        self.assertFalse(self.isl.expanded)
        self.assertFalse(self.isl.settings['pinned'])

    def test_cerrarla_con_open_la_desfija(self):
        self.isl.toggle_pinned()
        self.isl.on_control('open')
        self.assertFalse(self.isl.expanded)
        self.assertFalse(self.isl.settings['pinned'])

    def test_fijarla_la_saca_de_escondida(self):
        self.isl.off = True
        self.isl.toggle_pinned()
        self.assertFalse(self.isl.off)
        self.assertEqual(self.isl.target(), 'open')

    def monitors(self, focused='DP-1', names=('DP-1', 'HDMI-A-1')):
        """Hyprland con estos monitores y este enfocado; la isla, sin moverse de verdad."""
        mons = [{'name': n, 'focused': n == focused} for n in names]
        for name, value in (('monitors', mons), ('focused_monitor', next(m for m in mons if m['focused']))):
            patcher = mock.patch.object(app.hypr, name, lambda value=value: value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.isl._set_monitor = mock.Mock(return_value=True)
        self.isl.region, self.isl.update_region = None, lambda: None
        return mons

    def test_fijada_se_queda_en_su_monitor(self):
        mons = self.monitors()
        self.isl.monitor = mons[0]
        self.isl.toggle_pinned()
        self.assertEqual(self.isl.settings['pinned_monitor'], 'DP-1')
        # Se enfoca el otro monitor: la isla no se mueve.
        self.isl.on_focused_monitor('HDMI-A-1')
        self.isl._set_monitor.assert_not_called()
        self.assertEqual(self.isl.monitor['name'], 'DP-1')

    def test_suelta_vuelve_al_monitor_enfocado(self):
        mons = self.monitors(focused='HDMI-A-1')
        self.isl.monitor = mons[0]
        self.isl.toggle_pinned()
        self.isl.toggle_pinned()
        self.assertEqual(self.isl.settings['pinned_monitor'], '')
        self.isl._set_monitor.assert_called_once_with('HDMI-A-1')
        self.assertEqual(self.isl.monitor['name'], 'HDMI-A-1')
        # Y sigue al enfocado como siempre.
        self.isl.on_focused_monitor('DP-1')
        self.assertEqual(self.isl.monitor['name'], 'DP-1')

    def test_fijada_en_un_monitor_que_se_desconecta_se_va_al_enfocado(self):
        self.monitors(focused='HDMI-A-1', names=('HDMI-A-1',))
        self.isl.monitor = {'name': 'DP-1'}
        self.isl.settings.update(pinned=True, pinned_monitor='DP-1')
        self.isl.on_focused_monitor('HDMI-A-1')
        self.assertEqual(self.isl.monitor['name'], 'HDMI-A-1')
        self.assertEqual(self.isl.settings['pinned_monitor'], 'HDMI-A-1')

    def test_si_su_monitor_se_apaga_y_vuelve_la_isla_regresa_a_el(self):
        self.monitors(focused='HDMI-A-1')
        self.isl.monitor = {'name': 'HDMI-A-1'}
        self.isl.settings.update(pinned=True, pinned_monitor='HDMI-A-1')
        with mock.patch.object(app.GLib, 'timeout_add', return_value=7) as timer:
            self.isl.on_monitors_changed()
            self.isl.on_monitors_changed()      # se fue y volvió: un solo reloj
        timer.assert_called_once_with(app.MONITORS_SETTLE_MS, self.isl.settle_monitor)
        # El compositor la dejó en otro: se vuelve a poner en el suyo.
        self.isl.settle_monitor()
        self.isl._set_monitor.assert_called_once_with('HDMI-A-1')
        self.assertEqual(self.isl.settings['pinned_monitor'], 'HDMI-A-1')
        self.assertEqual(self.isl.monitors_id, 0)

    def test_si_su_monitor_ya_no_esta_se_va_al_enfocado(self):
        self.monitors(focused='DP-1', names=('DP-1',))
        self.isl.monitor = {'name': 'HDMI-A-1'}
        self.isl._set_monitor = mock.Mock(side_effect=lambda name: name == 'DP-1')
        self.isl.settle_monitor()
        self.assertEqual(self.isl.monitor['name'], 'DP-1')

    def test_fijada_arranca_en_el_monitor_donde_se_fijo(self):
        self.monitors(focused='HDMI-A-1')
        self.isl.settings.update(pinned=True, pinned_monitor='DP-1')
        self.assertEqual(self.isl.start_monitor()['name'], 'DP-1')
        # Si ya no está conectado, o no está fijada, arranca en el enfocado.
        self.isl.settings['pinned_monitor'] = 'DP-9'
        self.assertEqual(self.isl.start_monitor()['name'], 'HDMI-A-1')
        self.isl.settings.update(pinned=False, pinned_monitor='DP-1')
        self.assertEqual(self.isl.start_monitor()['name'], 'HDMI-A-1')

    def test_al_irse_el_raton_suelta_la_alerta_elegida_en_la_lista(self):
        self.alert(lines=['uno'])
        self.isl.toggle_pinned()
        self.isl.pin = 'x:1'
        self.isl.set_hover(False)
        self.assertEqual(self.isl.pin, '')
        self.assertTrue(self.isl.expanded)

    def test_un_permiso_se_contesta_en_el_tablero(self):
        self.isl.toggle_pinned()
        req = self.ask()
        # Fijada no pasa a la cabecera de siempre: los botones van en la tarjeta del que pide.
        self.assertEqual(self.isl.target(), 'board')
        self.assertIs(self.isl.asking(), self.isl.model.sessions['a'])
        self.assertEqual(self.isl.answer(False, HYPRLAND, now=T + 5), '')
        self.assertEqual(req.answers[0]['behavior'], 'deny')

    def test_sin_fijar_el_raton_la_cierra(self):
        self.isl.expand()
        self.isl.set_hover(False)
        self.assertFalse(self.isl.expanded)


class Consulta(IslandCase):
    """Las pastillas y sus burbujas, con los comandos para consultar."""

    def setUp(self):
        super().setUp()
        self.isl.sources = {key: {'ok': True, 'note': '', 'tip': [], 'since': 0, 'polled': 0}
                            for key in sources.LABELS}
        self.isl.pills, self.isl.tip = [], None
        self.isl.tip_key, self.isl.tip_ref, self.isl.tip_last = None, [], None
        self.isl.tip_pop, self.isl.tip_at, self.isl.tip_cx = 0.0, 0.0, None
        binds = mock.patch.object(app.hypr, 'binds', lambda: [
            {'modmask': 72, 'key': key, 'description': f'Engineer: orden {key}'} for key in 'YUA'])
        binds.start()
        self.addCleanup(binds.stop)
        self.cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, app.WIN_W, app.WIN_H))

    def bubble(self, key):
        self.isl.tip = (key, app.WIN_W / 2, 1.0)
        self.isl.draw_tip(self.cr, app.WIN_W, 0, 100.0)
        return self.isl.source_tip(key)

    def test_las_pastillas_caben_en_la_isla_mas_estrecha(self):
        width = app.SIZES['open'][0]
        self.isl.draw_pills(self.cr, 100, width, 50, 1.0)
        keys = [key for key, *_ in self.isl.pills]
        self.assertEqual(keys, [key for key, _ in sources.SOURCES]
                         + [app.workflowview.WF_PILL, app.projectview.PROJECTS_PILL, app.CHAT_PILL,
                            commands.HELP])
        for (_, x, _, w, _), (_, nx, *_) in zip(self.isl.pills, self.isl.pills[1:]):
            self.assertLessEqual(x + w, nx)
        self.assertLessEqual(self.isl.pills[-1][1] + self.isl.pills[-1][3], 100 + width - 18)

    def test_la_de_los_atajos_no_se_apaga_con_un_clic(self):
        self.assertNotIn(commands.HELP, sources.PREFIXES)
        self.assertNotIn(commands.HELP, self.isl.settings)

    def test_la_burbuja_de_una_fuente_trae_sus_comandos(self):
        title, rows = self.bubble('coffe')
        self.assertEqual(title, 'coffe')
        self.assertEqual(rows[0], ('status', 'Conectada', 'pass'))
        self.assertEqual(rows[1][:2], ('text', 'Pomodoro: modo foco y descansos'))
        self.assertIn(('head', 'Comandos'), rows)
        self.assertTrue(any(r[0] == 'cmd' and r[1] == 'coffe pause' for r in rows))
        # Una fuente sin comandos se queda como estaba.
        self.assertFalse(any(r[0] in ('head', 'cmd') for r in self.bubble('github')[1]))

    def test_lo_que_trae_una_fuente_va_en_etiquetas_y_fichas(self):
        self.isl.sources['coffe'].update(note='parado', tip=[
            '1 pomodoro(s) hoy · 2 para el descanso largo · 33 taza(s) en el bote',
            'Tarea: Arreglar el flaky'])
        self.isl.model.handle({'event': 'alert', 'session_id': 'coffe', 'name': 'coffe',
                               'message': 'Descanso'}, now=T)
        rows = self.bubble('coffe')[1]
        # Lo que se sabe de ella, en etiquetas; la alerta que tiene, en ámbar.
        self.assertIn(('chips', [('parado', 'cmd'), ('1 alerta', 'pct2')]), rows)
        # Sus cifras, en fichas: todas, también la tercera.
        self.assertIn(('stats', [('1', 'pomodoro(s) hoy'), ('2', 'para el descanso largo'),
                                 ('33', 'taza(s) en el bote')]), rows)
        # Y lo que no es una cifra con su nombre, una frase.
        self.assertTrue(any(r[:2] == ('text', 'Tarea: Arreglar el flaky') for r in rows))
        w, h = self.isl.tip_size
        self.assertLessEqual(h, app.TIP_ROOM - app.TIP_GAP)
        # Apagada no dice nada de eso.
        self.isl.settings['coffe'] = False
        rows = self.bubble('coffe')[1]
        self.assertEqual(rows[0], ('status', 'Apagada', 'dim'))
        self.assertFalse(any(r[0] in ('chips', 'stats') for r in rows))

    def test_la_de_github_dice_de_que_proyecto_es_cada_pr(self):
        self.shown, layout = [], self.isl._layout
        self.isl._layout = lambda cr, text, *a, **kw: self.shown.append(text) or layout(cr, text, *a, **kw)
        found =[{'where': f'org/proyecto-{i}', 'number': i, 'title': f'Cambio {i}', 'who': 'cuenta',
                  'note': 'en verde', 'tone': 'ok'} for i in range(1, 8)]
        self.isl.on_source({'name': 'github', 'ok': True, 'note': '1 cuenta', 'items': found,
                            'tip': ['7 PRs abiertos: 7 en verde', 'Sin revisiones pendientes']})
        rows = self.bubble('github')[1]
        lines = [r[1] for r in rows if r[0] == 'text']
        at = [r[0] for r in rows].index('items')
        # Justo debajo de la línea que los cuenta: los primeros, y de los demás cuántos son.
        self.assertEqual(rows[at - 1][1], '7 PRs abiertos: 7 en verde')
        self.assertEqual(rows[at], ('items', found[:app.TIP_ITEMS], 2))
        self.assertIn('Sin revisiones pendientes', lines)
        for text in ('org/proyecto-1 #1', 'Cambio 1 · cuenta', 'en verde', 'y 2 más'):
            self.assertIn(text, self.shown)
        self.assertLessEqual(self.isl.tip_size[1], app.TIP_ROOM - app.TIP_GAP)

    def test_la_de_los_atajos_los_lee_de_hyprland(self):
        title, rows = self.bubble(commands.HELP)
        self.assertEqual(title, 'Atajos de elyares-engineer')
        self.assertIn(('cmd', 'SUPER ALT + U', 'Orden U'), rows)
        self.assertEqual([r[1] for r in rows if r[0] == 'head'], ['Teclado', 'Ratón', 'Terminal'])

    def test_todas_caben_en_el_hueco_de_la_ventana(self):
        for key in list(sources.LABELS) + [commands.HELP]:
            self.bubble(key)
            w, h = self.isl.tip_size
            self.assertLessEqual(h, app.TIP_ROOM - app.TIP_GAP, key)
            self.assertLessEqual(w, app.WIN_W - 8, key)

    def test_si_no_caben_se_recorta_y_se_dice(self):
        many = {'coffe': [(f'coffe orden-{i}', 'hace algo') for i in range(60)]}
        with mock.patch.object(app.commands, 'load', lambda: many):
            self.bubble('coffe')
        self.assertLessEqual(self.isl.tip_size[1], app.TIP_ROOM - app.TIP_GAP)

    def frames(self, tip, start, count=60):
        """Dibuja la burbuja un segundo, cuadro a cuadro, con el cursor en `tip`."""
        for i in range(count):
            self.isl.tip = tip
            self.isl.draw_tip(self.cr, app.WIN_W, 0, start + i / 60)

    def test_la_burbuja_sale_y_se_va_poco_a_poco(self):
        over = ('coffe', app.WIN_W / 2, 1.0)
        self.frames(over, 100.0, count=1)
        self.assertTrue(0 < self.isl.tip_pop < 1)
        self.frames(over, 100.0)
        self.assertEqual(self.isl.tip_pop, 1.0)
        # Sin el cursor se va encogiendo, con lo último que decía.
        self.frames(None, 101.0, count=1)
        self.assertTrue(0 < self.isl.tip_pop < 1)
        self.assertEqual(self.isl.tip_key, 'coffe')
        self.frames(None, 101.0)
        self.assertEqual((self.isl.tip_pop, self.isl.tip_key, self.isl.tip_cx), (0.0, None, None))

    def test_de_una_pastilla_a_otra_la_burbuja_se_desliza(self):
        self.frames(('coffe', 300.0, 1.0), 100.0)
        self.frames(('github', 400.0, 1.0), 101.0, count=1)
        # No vuelve a salir de cero, y su flecha va de camino a la otra pastilla.
        self.assertGreaterEqual(self.isl.tip_pop, app.TIP_SWAP)
        self.assertTrue(300 < self.isl.tip_cx < 400)
        self.frames(('github', 400.0, 1.0), 101.0)
        self.assertAlmostEqual(self.isl.tip_cx, 400, delta=1)

    def test_la_ventana_cabe_en_un_monitor_de_1080(self):
        self.assertLessEqual(app.WIN_H, 1080 - 30)

    def test_agente_y_proyecto_con_el_agente_en_su_color(self):
        mascot = app.mascot
        cases = (('elyares-auditor', 'a & b', mascot.accent('auditor'), mascot.ACCENTS['auditor']),
                 # El engineer va con el color del tema.
                 (state.MAIN_AGENT, 'p', mascot.accent(state.MAIN_ROLE), mascot.COLORS['accent']),
                 # Uno que no es de la familia va sin color propio, y su nombre llega de fuera.
                 ('a<b', 'p', None, None))
        for name, project, color, expected in cases:
            with self.subTest(agent=name):
                text, markup = self.isl.who(name, project, color)
                self.assertEqual(text, f'{name} | {project}')
                # Lo que se pinta es lo mismo que el texto, y el marcado es válido.
                self.assertEqual(app.Pango.parse_markup(markup, -1, '\0')[2], text)
                self.assertEqual(f'foreground="{expected}">' in markup.split('|')[0], bool(expected))

    def test_la_cabecera_dice_que_pide_permiso(self):
        self.isl.model.handle({'event': 'start', 'session_id': 'a', 'cwd': '/x/a'}, now=T)
        self.isl.refresh()
        self.assertNotIn('pide permiso', [text for text, _color in self.isl.head_notes()])
        # Sin el hook `ask` no hay botones: la nota y la antena son lo único que lo dice.
        self.isl.model.handle({'event': 'permission', 'session_id': 'a', 'cwd': '/x/a'}, now=T)
        self.isl.refresh()
        self.assertFalse(self.isl.view.ask)
        self.assertEqual(self.isl.head_notes()[-1][0], 'pide permiso')
        self.isl.settings['pinned'] = True
        self.assertEqual(self.isl.head_notes()[0][0], 'fijada')

class Dibujo(IslandCase):
    """La isla dibujada fuera de pantalla, con eventos simulados."""

    def setUp(self):
        super().setUp()
        isl = self.isl
        isl.sources = {key: {'ok': True, 'note': '', 'tip': [], 'since': 0, 'polled': 0}
                       for key in sources.LABELS}
        isl.pills, isl.tip, isl.card_span = [], None, None
        isl.tip_key, isl.tip_ref, isl.tip_last = None, [], None
        isl.tip_pop, isl.tip_at, isl.tip_cx = 0.0, 0.0, None
        isl.override, isl.pet_state, isl.pet_since = None, 'idle', 0.0
        isl.title = isl.detail = isl.agent_name = ''
        isl.role, isl.list_layout, isl.wrap = state.MAIN_ROLE, False, (None, 0)
        isl.go = mock.Mock()
        isl.da = mock.Mock(get_width=lambda: app.WIN_W)
        isl.settings['compact'] = False     # asomada, y no en la pastilla
        self.shown = []
        layout = isl._layout
        isl._layout = lambda cr, text, *a, **kw: self.shown.append(text) or layout(cr, text, *a, **kw)
        self.cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, app.WIN_W, app.WIN_H))

    def send(self, event, sid='a', now=T, **extra):
        self.isl.model.handle({'event': event, 'session_id': sid, 'cwd': f'/x/{sid}', **extra}, now=now)
        self.isl.refresh()

    def work(self, sid, *kinds, now=T):
        """Una sesión trabajando, con un subagente en segundo plano de cada tipo."""
        self.send('start', sid, now=now)
        for i, kind in enumerate(kinds):
            self.send('agent-start', sid, now=now + i, agent_id=f'{sid}-{kind}', agent_type=kind)
            self.send('tool', sid, now=now + i, agent_id=f'{sid}-{kind}', agent_type=kind,
                      tool_name='Grep', tool_input={'pattern': kind})

    def draw(self):
        """La isla entera, a su tamaño. Devuelve los clics que deja armados."""
        self.shown.clear()
        self.isl.w, self.isl.h = self.isl.goal()
        self.isl.draw(None, self.cr, app.WIN_W, app.WIN_H)
        return self.isl.hits

    def hit(self, kind):
        return [key for k, key, *_ in self.isl.hits if k == kind]


class Tablero(Dibujo):
    """Abierta a mano: una pestaña por sesión y, dentro, sus cuatro."""

    def test_abierta_a_mano_con_una_sesion_es_el_tablero(self):
        self.isl.expanded = True
        self.assertEqual(self.isl.target(), 'open')      # sin sesiones, la cabecera y las fuentes
        self.isl.expanded = False
        self.work('a')
        self.assertEqual(self.isl.target(), 'peek')      # sin abrirla, asomada como siempre
        self.isl.hover = True
        self.assertEqual(self.isl.target(), 'board')
        self.isl.hover, self.isl.expanded = False, True
        self.assertEqual(self.isl.target(), 'board')
        self.assertEqual(self.isl.goal()[0], app.BOARD_W)

    def reply(self, agent, tint, proj, at=0):
        self.isl.model.handle({'event': 'alert', 'session_id': f'chat:{agent}', 'name': proj, 'tone': 'ok',
                               'message': f'{agent} terminó', 'where': agent, 'note': 'Sonnet 5.5', 'tint': tint,
                               'ttl': app.chatview.CHAT_REPLY_SECS, 'lines': [f'Respuesta de {tint}:', '- uno'],
                               'actions': [{'label': 'Ver respuesta', 'chat': f'chat:{agent}', 'after': 'clear'}]},
                              now=T + at)
        self.isl.refresh()

    def test_las_respuestas_de_los_agentes_se_ven_siempre_en_el_tablero(self):
        self.work('a')
        self.isl.expanded = True
        self.reply('elyares-reviewer', 'reviewer', 'api')
        self.assertEqual(self.isl.target(), 'board')
        self.isl.hover = self.isl.expanded = False
        self.isl.hover = True                       # basta con tener el tablero a la vista
        self.draw()
        self.assertIn('Respuesta de reviewer:', self.shown)
        self.assertIn('Ver respuesta', self.shown)
        self.assertNotIn('rp:0', self.isl.buttons)                  # con una sola, sin fila de nombres
        height = app.PREVIEW_HEAD + 2 * app.CODE_LINE_H + 2 * app.PREVIEW_PAD + app.CARD_BUTTONS
        self.assertEqual(self.isl.card_h('board'), height)

    def test_con_varias_respuestas_hay_una_fila_para_pasar_de_una_a_otra(self):
        self.work('a')
        self.isl.hover = True
        self.reply('elyares-reviewer', 'reviewer', 'api', at=1)
        self.reply('elyares-auditor', 'auditor', 'web', at=2)
        self.reply('elyares-designer', 'designer', 'app', at=3)
        self.draw()
        self.assertEqual([k for k in self.isl.buttons if str(k).startswith('rp:')], ['rp:0', 'rp:1', 'rp:2'])
        self.assertIn('Respuesta de designer:', self.shown)            # la última, al frente
        self.assertEqual(self.isl.rows_for('board'), [])               # no se repiten como filas
        self.assertIn('designer · app', self.shown)
        self.assertIn('reviewer · api', self.shown)
        self.assertEqual(self.isl.card_h('board'),
                         app.PREVIEW_HEAD + 2 * app.CODE_LINE_H + 2 * app.PREVIEW_PAD + app.CARD_BUTTONS
                         + app.REPLY_CHIPS_H)
        x, y, w, h = self.isl.buttons['rp:2']                          # la más vieja: el reviewer
        self.isl.on_click(None, 1, x + w / 2, y + h / 2)
        self.draw()
        self.assertIn('Respuesta de reviewer:', self.shown)
        # Descartar quita la que se ve; las demás se quedan.
        x, y, w, h = self.isl.buttons['dismiss']
        self.isl.on_click(None, 1, x + w / 2, y + h / 2)
        self.assertEqual([s.tint for s in self.isl.replies()], ['designer', 'auditor'])

    def test_la_mas_alta_de_las_respuestas_con_su_fila_cabe_en_el_tablero(self):
        room = app.BOARD_MAX - (app.TABS_H + app.BOARD_H + app.BOARD_PAD)
        tallest = (app.PREVIEW_HEAD + app.REPLY_LINES * app.CODE_LINE_H + 2 * app.PREVIEW_PAD + app.CARD_BUTTONS
                   + app.REPLY_CHIPS_H)
        self.assertLessEqual(tallest, room - app.ALERT_ROWS * app.ROW_H - app.LIST_PAD)

    def test_descartar_una_respuesta_no_silencia_la_siguiente_de_esa_conversacion(self):
        self.reply('elyares-reviewer', 'reviewer', 'api')
        s = self.isl.model.sessions['chat:elyares-reviewer']
        self.isl.act(s, 'dismiss')
        self.assertEqual(self.isl.model.sessions, {})
        self.reply('elyares-reviewer', 'reviewer', 'api', at=5)
        self.assertIn('chat:elyares-reviewer', self.isl.model.sessions)    # sigue saliendo

    def test_los_que_trabajan_al_frente_y_los_libres_a_la_banca(self):
        self.isl.expanded = True
        self.send('start')
        self.send('tool', tool_name='Agent', tool_input={})
        self.send('agent-start', agent_id='s1', agent_type='elyares-auditor')
        self.send('tool', agent_id='s1', agent_type='elyares-auditor', tool_name='Bash',
                  tool_input={'command': 'gitleaks git'})
        self.draw()
        # Solo el auditor está al frente; el engineer espera en la banca.
        self.assertEqual(self.hit('member'), [('a', 'auditor')])
        # Con siete en la banca no caben uno debajo de otro: van las caras en
        # cuadrícula y, al pie, quién espera.
        for text in ('elyares-auditor', 'Ejecutando gitleaks git', 'engineer esperando'):
            self.assertIn(text, self.shown)
        self.assertNotIn('elyares-engineer', self.shown)
        briefs = [(key, x, y, w, h) for kind, key, x, y, w, h in self.isl.hits if kind == 'brief']
        self.assertEqual([key for key, *_ in briefs], [('a', role) for role in state.TEAM[1:] if role != 'auditor'])
        self.assertEqual(len({x for _, x, *_ in briefs}), 2)            # dos columnas
        # Con el cursor encima de uno, el pie dice quién es.
        key, x, y, w, h = next(b for b in briefs if b[0] == ('a', 'devops'))
        self.isl.pointer = (x + w / 2, y + h / 2)
        self.draw()
        self.assertIn('devops ›', self.shown)

    def test_en_el_desglose_caben_todos_los_demas_y_nada_se_monta(self):
        self.isl.expanded = True
        self.send('start')
        self.send('tool', tool_name='Bash', tool_input={'command': 'make test'})
        self.isl.chat_sessions.add('a')                 # del chat: tres enlaces a la izquierda
        self.isl.tab, self.isl.focus = 'a', ('a', 'engineer')
        positions = {}
        put = self.isl.put
        self.isl.put = lambda cr, text, font, x, y, *a, **kw: positions.setdefault(text, y) and 0 or put(
            cr, text, font, x, y, *a, **kw)
        self.draw()
        bottom = app.TABS_H + app.FOCUS_H
        # Los demás de la familia, en miniatura, dentro del desglose.
        minis = [(y, h) for kind, key, x, y, w, h in self.isl.hits if kind == 'brief' and x > 500]
        self.assertEqual(len(minis), len(state.TEAM) - 1)
        self.assertTrue(all(app.TABS_H <= y and y + h <= bottom for y, h in minis))
        # A la izquierda, los enlaces no pisan cuántos pasos lleva.
        steps = next(y for text, y in positions.items() if 'paso' in text)
        self.assertLess(steps + 16, min(positions[link] for link in ('ir a su tmux ›', 'hablarle ›', '‹ volver')))

    def test_con_pocos_libres_la_banca_es_una_lista(self):
        self.isl.expanded = True
        self.work('a', 'elyares-architect', 'elyares-auditor')
        self.draw()
        self.assertEqual(len(self.hit('member')), 3)
        # Cinco en la banca: uno debajo de otro, con su nombre y «libre».
        briefs = [x for kind, _, x, *_ in self.isl.hits if kind == 'brief']
        self.assertEqual((len(briefs), len(set(briefs))), (5, 1))
        self.assertEqual(self.shown.count('libre'), 5)

    def test_mide_lo_mismo_trabajen_uno_dos_o_todos(self):
        self.isl.expanded = True
        sizes, front = set(), []
        everyone = tuple(state.ROLE_AGENTS[role] for role in state.TEAM[1:])
        for kinds in ((), ('elyares-reviewer',), everyone[:3], everyone):
            self.isl.model.sessions.clear()
            self.work('a', *kinds)
            sizes.add(self.isl.goal())
            self.draw()
            front.append(len(self.hit('member')))
        self.assertEqual(front, [1, 2, 4, len(state.TEAM)])
        self.assertEqual(len(sizes), 1)
        # Todos trabajando caben en dos filas, y cada uno con su nombre.
        self.assertEqual(len({y for kind, _, _, y, _, _ in self.isl.hits if kind == 'member'}), 2)
        for role in state.TEAM:
            self.assertIn(role, self.shown)
        # En reposo, todos en fila, con el nombre de su personaje, y ninguno se abre.
        self.send('stop', now=T + 1)
        self.isl.refresh = lambda: setattr(self.isl, 'view', self.isl.model.view(
            now=T + 60, pin=self.isl.pin))
        for agent in everyone:
            self.send('agent-stop', agent_id=f'a-{agent}')
        self.draw()
        self.assertEqual(self.hit('member'), [])
        self.assertEqual(self.shown.count('libre'), len(state.TEAM) - 1)
        for role in state.TEAM:
            self.assertIn(role, self.shown)
        # Más de seis no caben en una fila con su nombre: van en dos.
        self.assertEqual(len({y for kind, _, _, y, _, _ in self.isl.hits if kind == 'brief'}), 2)

    def test_un_clic_en_uno_abre_su_desglose(self):
        self.isl.expanded = True
        self.send('start')
        for i, name in enumerate(('uno', 'dos', 'tres')):
            self.send('tool', now=T + 1 + i * 4, tool_name='Bash', tool_input={'command': name})
        self.isl.model.sessions['a'].pane = '%3'
        board = self.isl.goal()
        self.draw()
        self.isl.on_hit('member', self.hit('member')[0])
        self.assertEqual(self.isl.focus, ('a', 'engineer'))
        self.assertEqual(self.isl.goal()[1] - board[1], app.FOCUS_H - app.BOARD_H)
        self.draw()
        # Todos sus pasos, y lo que tardó cada uno menos el de ahora.
        for text in ('Pensando…', 'Ejecutando uno', 'Ejecutando dos', 'Ejecutando tres', '1 s', '4 s',
                     'ahora', '‹ volver', 'ir al pane ›'):
            self.assertIn(text, self.shown)
        self.assertTrue(any(text.startswith('4 pasos · ') for text in self.shown))
        self.isl.on_hit('jump', self.hit('jump')[0])
        self.isl.go.assert_called_once_with(self.isl.model.sessions['a'])
        self.isl.on_hit('back', None)
        self.assertIsNone(self.isl.focused())

    def test_el_desglose_recuerda_cuantos_pasos_hubo_antes(self):
        self.isl.expanded = True
        self.send('start')
        for i in range(app.FOCUS_STEPS + 3):
            self.send('tool', now=T + i, tool_name='Bash', tool_input={'command': f'paso-{i}'})
        self.isl.focus = ('a', 'engineer')
        self.draw()
        self.assertIn('⋯ 5 pasos antes', self.shown)
        self.assertEqual(sum(text.startswith('Ejecutando paso-') for text in self.shown),
                         app.FOCUS_STEPS - 1)

    def test_las_pestanas_van_por_nombre_y_un_clic_elige(self):
        self.isl.expanded = True
        self.work('zeta')
        self.work('alfa')
        self.draw()
        self.assertEqual(self.hit('tab'), ['alfa', 'zeta'])
        chosen = self.isl.tab
        other = 'alfa' if chosen == 'zeta' else 'zeta'
        self.isl.focus = (chosen, 'engineer')
        self.isl.on_hit('tab', other)
        self.assertEqual((self.isl.tab, self.isl.focus), (other, None))
        self.isl.go.assert_not_called()
        # Un clic en la que ya está elegida lleva a su pane.
        self.isl.on_hit('tab', other)
        self.isl.go.assert_called_once_with(self.isl.model.sessions[other])

    def test_con_el_teclado_la_pestana_y_el_desglose_que_siguen(self):
        self.isl.expand = mock.Mock()
        self.work('alfa', 'elyares-auditor')
        self.work('zeta')
        self.isl.tab = 'alfa'
        self.isl.on_control('tab')
        self.assertEqual(self.isl.tab, 'zeta')
        self.isl.on_control('tab')
        self.assertEqual(self.isl.tab, 'alfa')      # de la última vuelve a la primera
        # El desglose de cada uno que tiene pasos, y después de vuelta al tablero.
        seen = []
        for _ in range(3):
            self.isl.on_control('steps')
            seen.append(self.isl.focus)
        self.assertEqual(seen, [('alfa', 'engineer'), ('alfa', 'auditor'), None])
        self.assertEqual(self.isl.expand.call_count, 5)

    def test_una_sesion_recuperada_dice_lo_que_hacia(self):
        self.send('start')
        self.send('tool', tool_name='Bash', tool_input={'command': 'make test'})
        other = Model()
        other.restore(self.isl.model.dump(), now=T)
        engineer = other.sessions['a'].team()[0]
        self.assertEqual((engineer.state, engineer.detail), ('working', 'Ejecutando make test'))

    def test_la_pestana_elegida_no_brinca_con_la_urgencia(self):
        self.isl.expanded = True
        self.work('a')
        self.assertEqual(self.isl.tab_session().sid, 'a')
        # Otra sesión se mueve después y pasa a ser la más urgente.
        self.send('start', 'b', now=T + 5)
        self.assertEqual(self.isl.view.session.sid, 'b')
        self.assertEqual(self.isl.tab_session().sid, 'a')
        # Si la elegida se va, se queda con la que haya.
        self.send('session-end', 'a')
        self.assertEqual(self.isl.tab_session().sid, 'b')

    def test_la_pestana_sigue_al_que_pide_permiso_o_termina(self):
        self.work('a')
        self.work('b')
        self.isl.tab, self.isl.focus = 'a', ('a', 'engineer')
        old = self.isl.view
        self.isl.model.handle({'event': 'stop', 'session_id': 'b', 'cwd': '/x/b'}, now=T + 3)
        new = self.isl.model.view(now=T + 3)
        self.isl.follow(new)
        self.assertEqual((self.isl.tab, self.isl.focus), ('b', None))
        # Sin novedad no se mueve, aunque la más urgente sea otra.
        self.isl.view, self.isl.tab = new, 'a'
        self.isl.follow(self.isl.model.view(now=T + 3))
        self.assertEqual(self.isl.tab, 'a')
        self.assertNotEqual(old.key, new.key)

    def test_la_pestana_no_se_queda_en_una_en_reposo_si_otra_trabaja(self):
        # `a` termina mientras `b` sigue trabajando: la pestaña se va a `a`…
        self.work('b')
        self.work('a')
        self.isl.model.handle({'event': 'stop', 'session_id': 'a', 'cwd': '/x/a'}, now=T + 3)
        done = self.isl.model.view(now=T + 3)
        self.isl.follow(done)
        self.assertEqual(self.isl.tab, 'a')
        # …y cuando `a` pasa a reposo, vuelve sola a la que trabaja.
        self.isl.view = done
        rest = self.isl.model.view(now=T + 3 + state.DONE_OPEN_SECS + 1)
        self.isl.follow(rest)
        self.assertEqual(self.isl.model.sessions['a'].state, 'idle')
        self.assertEqual(self.isl.tab, 'b')
        # Elegida a mano una en reposo, se queda mientras no haya novedad.
        self.isl.view, self.isl.tab = rest, 'a'
        self.isl.follow(self.isl.model.view(now=T + 20))
        self.assertEqual(self.isl.tab, 'a')

    def test_la_pestana_que_elegiste_se_queda_aunque_otra_trabaje_o_termine(self):
        self.work('a')
        self.work('b')
        self.isl.tab, self.isl.tab_manual = 'a', True
        self.isl.view = self.isl.model.view(now=T + 1)
        # `b` termina: la pestaña elegida a mano no se va tras ella.
        self.isl.model.handle({'event': 'stop', 'session_id': 'b', 'cwd': '/x/b'}, now=T + 3)
        self.isl.follow(self.isl.model.view(now=T + 3))
        self.assertEqual(self.isl.tab, 'a')
        # Un permiso sí: no debe quedarse tapado.
        self.isl.view = self.isl.model.view(now=T + 3)
        self.isl.model.handle({'event': 'ask', 'session_id': 'b', 'cwd': '/x/b', 'tool_name': 'Bash',
                               'tool_input': {'command': 'ls'}}, FakeReq(), now=T + 4)
        self.isl.follow(self.isl.model.view(now=T + 4))
        self.assertEqual((self.isl.tab, self.isl.tab_manual), ('b', False))

    def test_el_permiso_va_en_la_tarjeta_del_que_lo_pide(self):
        self.isl.expanded = True
        self.work('b')
        req = self.ask('a')
        self.isl.tab = 'a'
        self.draw()
        self.assertEqual(set(self.isl.buttons), {'allow', 'deny'})
        self.assertIn('Ejecutando rm -rf build', self.shown)
        x, y, w, h = self.isl.buttons['allow']
        self.isl.on_click(None, 1, x + w / 2, y + h / 2)
        self.assertEqual(req.answers, [{'behavior': 'allow'}])

    def test_el_permiso_de_otra_pestana_no_se_contesta_desde_esta(self):
        self.isl.expanded = True
        self.work('b')
        req = self.ask('a')
        self.isl.tab = 'b'
        self.draw()
        self.assertEqual(self.isl.buttons, {})
        self.assertEqual(self.isl.answer(False, HYPRLAND, now=T + 5), 'no hay ningún permiso a la vista')
        self.assertEqual(req.answers, [])
        # Pero su pestaña lo dice, en rojo.
        self.assertEqual(self.isl.tab_dot(self.isl.model.sessions['a']), 'red')

    def test_el_punto_de_la_pestana_dice_como_esta_la_sesion(self):
        self.work('a', 'elyares-reviewer')
        a = self.isl.model.sessions['a']
        self.assertEqual(self.isl.tab_dot(a), app.mascot.accent('reviewer'))
        self.send('agent-stop', agent_id='a-elyares-reviewer')
        self.assertEqual(self.isl.tab_dot(a), app.mascot.accent('engineer'))
        self.send('stop')
        self.assertEqual(self.isl.tab_dot(a), 'green')
        self.send('idle')
        self.assertEqual(self.isl.tab_dot(a), 'yellow')

    def test_una_de_segundo_plano_lo_dice_en_su_pestana(self):
        self.send('start', 'a', kind='bg')
        self.send('start', 'b', kind='bg', label='Mejoras')
        self.send('start', 'c')
        labels = {sid: self.isl.tab_label(s) for sid, s in self.isl.model.sessions.items()}
        self.assertEqual(labels, {'a': f'a · {app.BG_TAG}', 'b': 'b · Mejoras', 'c': 'c'})

    def test_dos_sesiones_de_la_misma_carpeta_se_numeran(self):
        for sid in ('uno', 'dos', 'tres'):
            self.isl.model.handle({'event': 'start', 'session_id': sid, 'cwd': '/x/proj'}, now=T)
        self.isl.model.handle({'event': 'start', 'session_id': 'otra', 'cwd': '/x/api'}, now=T)
        self.isl.refresh()
        self.assertEqual(sorted(self.isl.tab_labels().values()), ['api', 'proj', 'proj 2', 'proj 3'])

    def test_las_alertas_van_debajo_del_tablero(self):
        self.isl.expanded = True
        self.work('a')
        bare = self.isl.goal()[1]
        self.alert(lines=['uno', 'dos'], actions=[state.JUMP])
        self.assertEqual([s.sid for s in self.isl.rows_for('board')], ['x:1'])
        # Recién llegada manda en la vista, pero el tablero no se va: lleva su ficha debajo.
        self.assertEqual(self.isl.view.session.sid, 'x:1')
        self.assertEqual(self.isl.target(), 'board')
        card = self.isl.card_h('board')
        self.assertEqual(self.isl.goal()[1], bare + card + app.LIST_PAD + app.ROW_H)
        self.draw()
        self.assertEqual([s.sid for s, _y, _h in self.isl.rows], ['x:1'])
        self.assertEqual(set(self.isl.buttons), {'dismiss', 0})
        # Con un desglose abierto, la ficha le deja el sitio.
        self.isl.focus = ('a', 'engineer')
        self.assertEqual(self.isl.card_h('board'), 0)

    def test_asomada_salen_las_caritas_de_los_demas(self):
        self.work('a')
        alone = self.isl.goal()
        self.assertEqual((self.isl.target(), self.isl.minis(), alone), ('peek', [], app.SIZES['peek']))
        self.work('b', 'elyares-auditor', 'elyares-reviewer', now=T + 5)
        big = (self.isl.view.session.sid, self.isl.view.role)
        self.assertEqual(big, ('b', 'reviewer'))
        # Los demás que trabajan, sin el que ya es la mascota grande.
        self.assertEqual(sorted(self.isl.minis()),
                         [('auditor', 'working'), ('engineer', 'working'), ('engineer', 'working')])
        self.assertGreater(self.isl.goal()[0], alone[0])
        self.draw()

    def test_se_dibuja_en_todos_sus_estados(self):
        self.isl.expanded = True
        self.work('a', 'elyares-architect', 'elyares-auditor')
        self.work('b')
        self.send('stop', 'b', now=T + 1)
        for tab, focus in (('a', None), ('b', None), ('a', ('a', 'auditor')), ('b', ('b', 'engineer'))):
            with self.subTest(tab=tab, focus=focus):
                self.isl.tab, self.isl.focus = tab, focus
                self.isl.pointer = (app.WIN_W / 2, app.TABS_H + 40)
                self.assertTrue(self.draw())
        self.assertLessEqual(self.isl.goal()[1], app.BOARD_MAX + app.PILLS_H + 8)


@unittest.skipIf(app is None, 'sin gi: usa /usr/bin/python3')
class Chat(Dibujo):
    """El chat dentro de la isla."""

    def setUp(self):
        super().setUp()
        self.tmux_cwd = '/x/proj'           # la carpeta de la sesión de tmux en la que se está (None: sin tmux)
        patcher = mock.patch.object(app.chatview.projects, 'listing', self.listing)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.isl.projects = self.listing()
        self.isl.ensure_tick = lambda: None
        self.isl.expand = mock.Mock()

    def listing(self):
        """Los proyectos, como los daría tmux ahora: se está en el de `tmux_cwd`."""
        P = app.projectview.projects.Project
        found = [P('proj', '/x/proj', 'personal', 'proj', 50, key='proj'),
                 P('aang-server', '/x/aang', 'work', key='aang-server'),
                 P('tl-mas-server', '/x/tl', 'work', 'tl-mas-server', 90, key='tl-mas-server')]
        for p in found:
            p.here = p.path == self.tmux_cwd
        return found

    def conversation(self):
        c = app.chatview.chat.Chat('/x/proj', lambda ev: None, spawn=mock.Mock())
        c.commands = {'contexto': 'Carga el contexto', 'commit': 'Hace los commits', 'compact': ''}
        E = app.chatview.chat.Entry
        c.entries = [E('you', 'haz /contexto'),
                     E('claude', '## Listo\n- **tl-mas-server** en `sprint-021026`')]
        self.isl.chat, self.isl.chat_open = c, True
        return c

    def test_con_la_orden_se_abre_y_se_cierra(self):
        self.isl.on_control('chat')
        self.assertTrue(self.isl.chat_open and self.isl.chat_typing)
        self.assertEqual(self.isl.target(), 'chat')
        self.assertEqual(self.isl.goal(), (app.chatview.CHAT_W, app.chatview.CHAT_H))
        self.assertEqual(self.isl.chat.cwd, '/x/proj')
        chat = self.isl.chat
        self.isl.on_control('chat')
        self.assertFalse(self.isl.chat_open or self.isl.chat_typing)
        self.assertNotEqual(self.isl.target(), 'chat')
        # Cerrar no termina la conversación: al abrirlo, ahí sigue.
        self.isl.on_control('chat')
        self.assertIs(self.isl.chat, chat)

    def test_sin_teclear_suelta_el_teclado_solo(self):
        self.isl.on_control('chat')
        self.isl.chat_tick(self.isl.chat_keyed + app.chatview.CHAT_IDLE_SECS - 1)
        self.assertTrue(self.isl.chat_typing)
        self.isl.chat_tick(self.isl.chat_keyed + app.chatview.CHAT_IDLE_SECS + 1)
        self.assertFalse(self.isl.chat_typing)
        self.assertTrue(self.isl.chat_open)          # el chat sigue a la vista

    def test_la_pastilla_del_chat_lo_abre(self):
        self.isl.expanded = True
        self.draw()
        key, x, y, w, h = next(p for p in self.isl.pills if p[0] == app.CHAT_PILL)
        self.isl.on_click(None, 1, x + w / 2, y + h / 2)
        self.assertTrue(self.isl.chat_open)

    def test_se_dibuja_la_conversacion(self):
        self.conversation()
        self.draw()
        for text in ('haz /contexto', 'Listo', 'Cerrar', 'Nuevo'):
            self.assertIn(text, self.shown)
        self.assertEqual({k for _, k, *_ in self.isl.hits} >= {'close', 'new', 'type'}, True)
        self.assertIsNotNone(self.isl.chat_box)

    def test_el_permiso_se_contesta_en_su_tarjeta(self):
        c = self.conversation()
        c.busy = True
        c.asking = {'id': 'r-1', 'tool': 'Bash', 'input': {'command': 'make test'}, 'text': 'Ejecutando make test'}
        c.answer = mock.Mock()
        self.draw()
        self.assertIn('Pide permiso', self.shown)
        self.assertIn('Detener', self.shown)
        x, y, w, h = self.isl.buttons['chat-allow']
        self.isl.on_click(None, 1, x + w / 2, y + h / 2)
        c.answer.assert_called_once_with(True)

    def ask_questions(self, *questions):
        c = self.conversation()
        c.busy = True
        c.asking = {'id': 'r-9', 'tool': 'AskUserQuestion', 'text': 'Pregunta',
                    'input': {'questions': list(questions)}}
        c.answer_questions = mock.Mock()
        c.answer = mock.Mock()
        self.draw()
        return c

    def click(self, key):
        x, y, w, h = self.isl.buttons[key]
        self.isl.on_click(None, 1, x + w / 2, y + h / 2)
        self.draw()

    def reviewer(self, agent='elyares-reviewer'):
        """La conversación de uno de la familia, ya registrada y a la vista."""
        E = app.chatview.chat.Entry
        c = app.chatview.chat.Chat('/x/proj', lambda ev: None, spawn=mock.Mock(), agent=agent)
        c.entries = [E('you', 'revisa el PR 12 por favor'), E('claude', 'Va')]
        self.isl.chats[self.isl.chat_key(agent, '/x/proj')] = c
        self.isl.chat, self.isl.chat_open = c, True
        return c

    def test_un_agente_de_solo_lectura_abre_otra_conversacion_sin_esperar(self):
        first = self.reviewer()
        first.busy = True
        self.draw()
        self.assertIn('Otra', self.shown)
        self.assertNotIn('1 · revisa el PR 12', ' '.join(self.shown))     # con una sola no hay fila
        self.assertIn('split', self.hit('chat'))
        self.isl.on_chat_hit('split')
        second = self.isl.chat
        self.assertIsNot(second, first)
        self.assertTrue(first.busy)                         # la que trabajaba sigue como estaba
        self.assertEqual((second.agent, second.cwd, second.entries), ('elyares-reviewer', '/x/proj', []))
        self.assertEqual(self.isl.chat_family(), [first, second])
        self.assertTrue(self.isl.chat_busy())
        self.draw()
        self.assertIn('● 1 · revisa el PR 12…', self.shown)  # la que trabaja lleva su punto
        self.assertIn('2 · nueva', self.shown)
        self.assertEqual({'conv:0', 'conv:1', 'drop:1'} - set(self.hit('chat')), set())
        self.assertNotIn('drop:0', self.hit('chat'))        # la de siempre no se cierra
        self.isl.on_chat_hit('conv:0')
        self.assertIs(self.isl.chat, first)

    def test_el_mobile_sigue_con_una_sola_y_el_engineer_y_el_devops_ya_pueden_tener_otra(self):
        c = self.reviewer('elyares-mobile')
        self.draw()
        self.assertNotIn('Otra', self.shown)
        self.isl.chat_split()
        self.assertEqual(self.isl.chat_family(), [c])
        for agent in ('', 'elyares-devops'):
            c = self.reviewer(agent)
            self.draw()
            self.assertIn('Otra', self.shown)
            self.isl.chat_split()
            self.assertEqual(len(self.isl.chat_family()), 2)

    def test_avisa_si_otro_que_modifica_el_repo_trabaja_en_la_misma_carpeta(self):
        first = self.reviewer('')
        self.isl.chat_split()
        second = self.isl.chat
        self.assertEqual(self.isl.chat_clash(), [])
        first.busy = True
        self.assertEqual(self.isl.chat_clash(), ['otra conversación suya'])
        self.assertEqual(self.isl.chat_clash(first), [])           # ella misma no cuenta
        self.draw()
        self.assertIn('⚠ otra conversación suya trabaja en esta carpeta: pueden pisarse', self.shown)
        # Otro agente que también modifica el repo, en la misma carpeta.
        devops = app.chatview.chat.Chat('/x/proj', lambda ev: None, spawn=mock.Mock(), agent='elyares-devops')
        devops.busy = True
        self.isl.chats[self.isl.chat_key('elyares-devops', '/x/proj')] = devops
        self.assertEqual(self.isl.chat_clash(second), ['otra conversación suya', 'elyares-devops'])
        # Otro proyecto no cuenta, y uno de solo lectura no avisa ni se le avisa.
        devops.cwd = '/y/otro'
        self.assertEqual(self.isl.chat_clash(second), ['otra conversación suya'])
        second.agent = 'elyares-reviewer'
        self.assertEqual(self.isl.chat_clash(second), [])

    def test_hay_un_tope_de_conversaciones_por_agente(self):
        self.reviewer()
        for _ in range(10):
            self.isl.chat_split()
        self.assertEqual(len(self.isl.chat_family()), app.chatview.chat.MAX_CHATS)
        self.draw()
        self.assertNotIn('Otra', self.shown)

    def test_una_de_las_otras_se_cierra_con_su_x_salvo_si_trabaja(self):
        first = self.reviewer()
        self.isl.chat_split()
        second = self.isl.chat
        second.busy = True
        self.isl.chat_drop(1)
        self.assertEqual(self.isl.chat_family(), [first, second])
        second.busy = False
        self.isl.chat_drop(0)                               # la de siempre se queda
        self.assertEqual(self.isl.chat_family(), [first, second])
        self.isl.chat_drop(1)
        self.assertEqual(self.isl.chat_family(), [first])
        self.assertIs(self.isl.chat, first)                 # a la vista queda la anterior

    def test_nuevo_en_una_de_las_otras_la_empieza_de_cero_en_su_lugar(self):
        first = self.reviewer()
        self.isl.chat_split()
        second = self.isl.chat
        second.entries.append(app.chatview.chat.Entry('you', 'otro tema'))
        self.isl.new_chat()
        self.assertIsNot(self.isl.chat, second)
        self.assertEqual(self.isl.chat_family(), [first, self.isl.chat])
        self.assertEqual(self.isl.chat.entries, [])

    def test_las_conversaciones_de_la_fila_sobreviven_a_un_reinicio(self):
        first = self.reviewer()
        self.isl.chat_split()
        second = self.isl.chat
        second.entries.append(app.chatview.chat.Entry('you', 'otro tema'))
        data = self.isl.chat_dump()
        self.assertEqual([bool(c.get('extra')) for c in data['chats']], [False, True])
        self.isl.chats.clear()
        self.isl.chat_extra.clear()
        self.isl.chat = None
        self.isl.chat_restore(data)
        family = self.isl.chat_family(self.isl.chat)
        self.assertEqual([c.entries[0].text for c in family], ['revisa el PR 12 por favor', 'otro tema'])
        self.assertIs(self.isl.chat, family[1])             # la que se veía

    def test_una_pregunta_de_opciones_se_contesta_con_un_clic(self):
        one = {'question': '¿Qué base?', 'header': 'Base', 'multiSelect': False,
               'options': [{'label': 'Postgres', 'description': 'relacional'}, {'label': 'SQLite'}]}
        c = self.ask_questions(one)
        for text in ('Te pregunta', 'Base', '¿Qué base?', 'Postgres', 'relacional', 'SQLite', 'Omitir'):
            self.assertIn(text, self.shown)
        self.assertNotIn('Permitir', self.shown)
        self.click('chat-opt:1')
        c.answer_questions.assert_called_once_with({'¿Qué base?': 'SQLite'})
        c.answer.assert_not_called()

    def test_en_una_pregunta_de_varias_opciones_se_marca_y_listo_las_manda(self):
        many = {'question': '¿Qué incluir?', 'header': 'Incluir', 'multiSelect': True,
                'options': [{'label': 'Tests'}, {'label': 'Docs'}, {'label': 'CI'}]}
        c = self.ask_questions(many)
        self.assertNotIn('Listo', self.shown)
        self.click('chat-opt:0')
        self.click('chat-opt:2')
        self.assertIn('Listo', self.shown)
        c.answer_questions.assert_not_called()
        self.click('chat-opt:0')                    # se desmarca
        self.click('chat-next')
        c.answer_questions.assert_called_once_with({'¿Qué incluir?': 'CI'})

    def test_varias_preguntas_van_una_a_una_y_se_mandan_juntas(self):
        a = {'question': 'Uno', 'options': [{'label': 'a1'}, {'label': 'a2'}]}
        b = {'question': 'Dos', 'options': [{'label': 'b1'}, {'label': 'b2'}]}
        c = self.ask_questions(a, b)
        self.assertIn('Te pregunta · 1 de 2', self.shown)
        self.click('chat-opt:1')
        c.answer_questions.assert_not_called()
        self.assertIn('Te pregunta · 2 de 2', self.shown)
        self.click('chat-opt:0')
        c.answer_questions.assert_called_once_with({'Uno': 'a2', 'Dos': 'b1'})

    def test_lo_escrito_con_una_pregunta_delante_es_otra_respuesta(self):
        c = self.ask_questions({'question': '¿Qué base?', 'options': [{'label': 'Postgres'}, {'label': 'SQLite'}]})
        self.isl.chat_text = lambda: ' Mongo '
        self.isl.chat_set_text = mock.Mock()
        self.isl.on_chat_enter()
        c.answer_questions.assert_called_once_with({'¿Qué base?': 'Mongo'})
        self.isl.chat_set_text.assert_called_once_with('')

    def test_omitir_una_pregunta_la_deniega(self):
        c = self.ask_questions({'question': '¿Qué base?', 'options': [{'label': 'Postgres'}, {'label': 'SQLite'}]})
        self.click('chat-deny')
        c.answer.assert_called_once_with(False)
        c.answer_questions.assert_not_called()

    def test_al_mandar_se_cierra_y_se_ve_trabajar_en_el_tablero(self):
        c = self.conversation()
        c.send = mock.Mock(return_value=True)
        self.isl.chat_text = lambda: 'corre las pruebas'
        self.isl.chat_set_text = mock.Mock()
        self.isl.on_chat_enter()
        c.send.assert_called_once_with('corre las pruebas', [])
        self.assertFalse(self.isl.chat_open)
        self.assertTrue(self.isl.chat_watch)
        self.isl.expand.assert_called_once()
        # En cuanto Claude dice qué sesión es, la pestaña la sigue.
        self.isl.on_chat({'type': 'system', 'subtype': 'init', 'session_id': 's-chat'})
        self.assertEqual(self.isl.tab, 's-chat')
        self.send('start', 's-chat', cwd='/x/proj')
        self.assertEqual(self.isl.tab_label(self.isl.model.sessions['s-chat']), 'proj · chat')

    def test_el_permiso_del_chat_se_contesta_en_el_tablero(self):
        c = self.conversation()
        self.isl.chat_open = False
        c.session = 's-chat'
        c.answer = mock.Mock()
        self.isl.on_chat({'type': 'control_request', 'request_id': 'r', 'request': {
            'subtype': 'can_use_tool', 'tool_name': 'Bash', 'input': {'command': 'make test'}}})
        self.assertFalse(self.isl.chat_open)        # el chat no se abre: se ve en el tablero
        s = self.isl.model.sessions['s-chat']
        self.assertEqual(s.state, 'permission')
        self.assertEqual(self.isl.tab, 's-chat')
        self.isl.expanded = True
        self.draw()
        x, y, w, h = self.isl.buttons['allow']
        self.isl.on_click(None, 1, x + w / 2, y + h / 2)
        c.answer.assert_called_once_with(True)

    def test_una_pregunta_del_chat_abre_el_chat_y_no_va_al_tablero(self):
        c = self.conversation()
        self.isl.chat_open = False
        c.session = 's-chat'
        self.isl.on_chat({'type': 'control_request', 'request_id': 'r', 'request': {
            'subtype': 'can_use_tool', 'tool_name': 'AskUserQuestion',
            'input': {'questions': [{'question': '¿Cuál?', 'options': [{'label': 'A'}, {'label': 'B'}]}]}}})
        self.assertTrue(self.isl.chat_open)         # Permitir no es una respuesta: se contesta en el chat
        self.assertIsNone(self.isl.model.sessions['s-chat'].ask if 's-chat' in self.isl.model.sessions else None)
        self.draw()
        self.assertIn('¿Cuál?', self.shown)

    def test_al_terminar_avisa_con_el_principio_de_la_respuesta(self):
        c = self.conversation()
        self.isl.chat_open = False
        c.session, c.busy = 's-chat', True
        c.entries.append(app.chatview.chat.Entry('claude', '## Hecho\nLas **22** pruebas pasan.'))
        self.isl.on_chat({'type': 'result', 'subtype': 'success', 'duration_ms': 1000})
        alert = self.isl.model.sessions['chat:s-chat']
        self.assertIn('ver respuesta', alert.detail)
        self.assertEqual(alert.lines, ['Hecho', 'Las 22 pruebas pasan.'])
        # Su botón, con un clic de verdad, abre el chat, y el aviso se va.
        self.isl.chats['', '/x/proj'] = c
        self.isl.expanded, self.isl.pin = True, 'chat:s-chat'
        self.isl.refresh()
        self.draw()
        self.assertIs(self.isl.view.session, alert)
        self.assertIn('Ver respuesta', self.shown)
        x, y, w, h = self.isl.buttons[0]
        self.assertGreater(w, app.BUTTON_W)             # tan ancho como su texto: no se corta
        self.isl.on_click(None, 1, x + w / 2, y + h / 2)
        self.assertTrue(self.isl.chat_open)
        self.assertIs(self.isl.chat, c)
        self.assertNotIn('chat:s-chat', self.isl.model.sessions)

    def test_el_aviso_de_terminado_se_va_cuando_empieza_otro_turno(self):
        c = self.conversation()
        self.isl.chat_open = False
        c.session, c.busy = 's-chat', True
        c.entries.append(app.chatview.chat.Entry('claude', 'Listo.'))
        self.isl.on_chat({'type': 'result', 'subtype': 'success', 'duration_ms': 1000})
        self.assertIn('chat:s-chat', self.isl.model.sessions)
        # Se le manda otra cosa: el «terminó» de antes ya no es verdad.
        c.busy = True
        self.isl.on_chat({'type': 'system', 'subtype': 'init', 'session_id': 's-chat'})
        self.assertNotIn('chat:s-chat', self.isl.model.sessions)

    def test_cada_agente_tiene_su_conversacion(self):
        self.isl.settings['chat_model'] = 'haiku'
        self.isl.open_chat()
        engineer = self.isl.chat
        self.assertEqual((engineer.agent, engineer.model), ('', 'haiku'))
        self.isl.on_chat_hit('agent:elyares-architect')
        architect = self.isl.chat
        # La del agente corre como él, con su modelo, no con el elegido para el engineer.
        self.assertEqual((architect.agent, architect.model, architect.cwd), ('elyares-architect', '', '/x/proj'))
        self.draw()
        self.assertIn('Pídele algo a elyares-architect', self.shown)
        self.isl.on_chat_hit('agent:')
        self.assertIs(self.isl.chat, engineer)       # la del engineer sigue ahí
        # «Nuevo» empieza otra solo con el que tienes a la vista.
        self.isl.on_chat_hit('agent:elyares-architect')
        self.isl.on_chat_hit('new')
        self.assertIsNot(self.isl.chat, architect)
        self.assertIs(self.isl.chats['', '/x/proj'], engineer)

    def test_cada_proyecto_tiene_su_conversacion_y_el_chat_sigue_a_tmux(self):
        self.isl.on_control('chat')
        proj = self.isl.chat
        self.assertEqual(proj.cwd, '/x/proj')
        proj.entries.append(app.chatview.chat.Entry('you', 'hola'))
        self.isl.on_control('chat')                 # se cierra
        # En tmux se pasa a otra sesión: el chat abre la conversación de ese proyecto.
        self.tmux_cwd = '/x/tl'
        self.isl.on_control('chat')
        tl = self.isl.chat
        self.assertEqual((tl.cwd, tl.entries), ('/x/tl', []))
        self.assertIsNot(tl, proj)
        # Con el panel abierto, cambiar de agente no cambia de proyecto.
        self.tmux_cwd = '/x/otro'
        self.isl.on_chat_hit('agent:elyares-auditor')
        self.assertEqual((self.isl.chat.agent, self.isl.chat.cwd), ('elyares-auditor', '/x/tl'))
        # De vuelta en el primero, su conversación sigue ahí; «Nuevo» solo empieza otra en ese.
        self.isl.close_chat()
        self.tmux_cwd = '/x/proj'
        self.isl.on_control('chat', {'agent': 'engineer'})
        self.assertIs(self.isl.chat, proj)
        self.isl.on_chat_hit('new')
        self.assertEqual((self.isl.chat.cwd, self.isl.chat.entries), ('/x/proj', []))
        self.assertIs(self.isl.chats['', '/x/tl'], tl)
        # Aunque se haya visto otra (con "#" o con «Ver respuesta»), al abrirlo manda tmux:
        # sale la del proyecto en el que estás.
        self.isl.show_chat(tl)
        self.isl.close_chat()
        self.isl.on_control('chat')
        self.assertEqual(self.isl.chat.cwd, '/x/proj')
        # Sin tmux, la última que se tuvo a la vista.
        self.isl.show_chat(tl)
        self.isl.close_chat()
        self.tmux_cwd = None
        self.isl.on_control('chat')
        self.assertIs(self.isl.chat, tl)

    def test_cada_pestana_manda_sobre_su_chat(self):
        send = self.sending()
        # Dos proyectos en el tablero: una conversación empezada en /x/tl, cuyo Claude
        # anda ahora por la carpeta de /x/proj, y una sesión de terminal en /x/proj.
        tl = self.isl.chat_for('', '/x/tl')
        tl.session = 's-tl'
        self.isl.chat_sessions.add('s-tl')
        self.send('start', 's-tl', cwd='/x/proj/sub')
        self.send('start', 'term', cwd='/x/proj')
        self.isl.expanded = True
        self.tmux_cwd = '/x/aang'                   # en tmux se está en un tercero: no cuenta
        # Con el tablero a la vista, el botón Chat abre el de la pestaña elegida.
        self.isl.tab = 's-tl'
        self.isl.open_chat()
        self.assertIs(self.isl.chat, tl)
        self.isl.close_chat()
        # En la pestaña de una sesión de terminal, el chat de ese proyecto.
        self.isl.tab = 'term'
        self.isl.open_chat()
        self.assertEqual((self.isl.chat.agent, self.isl.chat.cwd), ('', '/x/proj'))
        self.isl.close_chat()
        # Un encargo desde la pestaña de /x/tl va a la conversación de ese proyecto,
        # no a la del proyecto por el que anda su Claude.
        self.isl.tab = 's-tl'
        self.draw()
        self.isl.on_hit('brief', ('s-tl', 'auditor'))
        self.isl.chat_text = lambda: 'audita esto'
        self.isl.on_chat_enter()
        self.assertEqual(sorted(k for k in self.isl.chats if k[0]), [('elyares-auditor', '/x/tl')])
        self.assertEqual(self.isl.chat_hosts, {('elyares-auditor', '/x/tl'): 's-tl'})
        send.assert_called_once()
        # Y su proyecto ya tiene Claude: no se ofrece como si estuviera sin empezar.
        self.tmux_cwd = '/x/tl'
        self.isl.projects = self.listing()
        self.assertIsNone(self.isl.project_start())
        by = {p.name: p for p in self.isl.projects}
        self.assertEqual([s.sid for s in self.isl.project_sessions(by['tl-mas-server'])], ['s-tl'])
        self.assertEqual([s.sid for s in self.isl.project_sessions(by['proj'])], ['term'])

    def test_la_pestana_de_un_chat_abre_su_conversacion(self):
        # Una conversación empezada en /x/tl cuyo Claude anda ahora por otra carpeta.
        tl = self.isl.chat_for('', '/x/tl')
        tl.session = 's-tl'
        self.isl.chat_sessions.add('s-tl')
        self.send('start', 's-tl', cwd='/x/proj/sub')
        self.work('a')
        self.isl.expanded = True
        self.draw()
        # Su pestaña lleva el nombre del proyecto en el que se empezó, no el de por donde anda.
        self.assertIn('tl-mas-server · chat', self.shown)
        # Un clic la elige; otro, ya elegida, abre su conversación (no la del proyecto de tmux).
        self.isl.tab = 'a'
        self.isl.on_hit('tab', 's-tl')
        self.assertFalse(self.isl.chat_open)
        self.isl.on_hit('tab', 's-tl')
        self.assertTrue(self.isl.chat_open)
        self.assertIs(self.isl.chat, tl)
        self.isl.go.assert_not_called()
        # Y «hablarle ›» en su desglose, lo mismo.
        self.isl.close_chat()
        self.isl.on_hit('talk', '')
        self.assertIs(self.isl.chat, tl)
        # La de una sesión de terminal sigue llevando a su pane.
        self.isl.close_chat()
        self.isl.on_hit('tab', 'a')
        self.isl.on_hit('tab', 'a')
        self.isl.go.assert_called_once()
        self.assertFalse(self.isl.chat_open)

    def test_con_dir_se_abre_en_esa_carpeta(self):
        with mock.patch.object(app.os.path, 'isdir', lambda path: path == '/x/aang'):
            self.isl.on_control('chat', {'cwd': '/x/aang'})
            self.assertEqual((self.isl.chat.agent, self.isl.chat.cwd), ('', '/x/aang'))
            # No alterna: otra vez con otra carpeta, pasa a esa sin cerrar el panel.
            self.isl.on_control('chat', {'cwd': '/no/existe'})
        self.assertFalse(self.isl.chat_open)        # una carpeta que no existe es la orden de siempre

    def test_la_almohadilla_elige_proyecto(self):
        self.conversation()
        self.isl.chats['', '/x/proj'] = self.isl.chat
        self.isl.chat_whom = 'chat'             # la caja ya es del chat: lo escrito no se pierde
        self.write('#')
        # Los abiertos en tmux primero, el usado más recientemente arriba; luego los cerrados.
        self.assertEqual(self.isl.suggestions(), [('tl-mas-server', '● work · /x/tl'),
                                                  ('proj', '◆ personal · /x/proj · con conversación'),
                                                  ('aang-server', '○ work · /x/aang')])
        self.draw()
        self.assertIn('#tl-mas-server', self.shown)
        self.write('mira esto #aa')
        self.assertEqual([n for n, _ in self.isl.suggestions()], ['aang-server'])
        # Enter no escribe el nombre: pasa a la conversación de ese proyecto, con lo demás escrito.
        self.isl.on_chat_enter()
        self.isl.chat_set_text.assert_called_once_with('mira esto ', 10)
        self.assertEqual((self.isl.chat.cwd, self.isl.chat_open, self.isl.chat_typing), ('/x/aang', True, True))
        # Un clic en la carpeta de la cabecera pone la almohadilla en la caja.
        self.write('hola')
        self.isl.on_chat_hit('project')
        self.isl.chat_set_text.assert_called_once_with('hola #')
        self.draw()
        self.assertIn('project', [key for kind, key, *_ in self.isl.hits if kind == 'chat'])

    def test_la_que_no_se_usa_suelta_su_proceso(self):
        sleep = app.chatview.CHAT_SLEEP_SECS
        self.isl.on_control('chat')
        seen = self.isl.chat
        other = self.isl.chat_for('', '/x/tl')
        busy = self.isl.chat_for('', '/x/aang')
        for c in (seen, other, busy):
            c.proc, c.touched, c.close = mock.Mock(poll=lambda: None), 100.0, mock.Mock()
        busy.busy = True
        self.isl.chat_tick(100.0 + sleep - 1)
        other.close.assert_not_called()
        self.isl.chat_tick(100.0 + sleep + 1)
        other.close.assert_called_once_with()
        seen.close.assert_not_called()              # la que se tiene a la vista
        busy.close.assert_not_called()              # la que trabaja
        self.isl.close_chat()
        self.isl.chat_tick(100.0 + sleep + 2)
        seen.close.assert_called_once_with()

    def test_los_menus_de_la_linea_de_estado_se_eligen_con_un_clic(self):
        c = self.conversation()
        self.isl.chats['', '/x/proj'] = c
        self.isl.chat_whom = 'chat'
        self.isl.chat_images = [b'png']                 # con algo pegado encima de la caja
        self.isl.chat_text = lambda: 'una\ndos\ntres'   # y la caja crecida

        def click(menu, option):
            """Abre el menú y pulsa esa opción, con un clic de verdad."""
            self.isl.show_chat(c)
            self.isl.on_chat_hit(menu)
            self.draw()
            hits = [h for h in self.isl.hits if h[0] == 'chat']
            box = next(h for h in hits if h[1] == 'type')
            rows = [h for h in hits if str(h[1]).startswith(f'{menu}:')]
            # Ninguna opción cae sobre la caja: ahí manda el widget, no el dibujo.
            self.assertTrue(all(y + h <= box[3] for _, _, _, y, _, h in rows))
            _, _, x, y, w, h = next(r for r in rows if r[1] == option)
            self.isl.on_click(None, 1, x + w / 2, y + h / 2)

        # Los cuatro agentes, también el de más abajo, que antes caía sobre la caja.
        for agent in ('elyares-architect', 'elyares-auditor', 'elyares-reviewer', ''):
            click('agent', f'agent:{agent}')
            self.assertEqual(self.isl.chat.agent, agent)
            self.assertIsNone(self.isl.chat_menu)
        for alias, _ in app.chatview.chat.MODELS:
            click('model', f'model:{alias}')
            self.assertEqual(c.model, alias)
        for level in app.chatview.chat.EFFORTS:
            click('effort', f'effort:{level}')
            self.assertEqual(c.effort, level)

    def test_con_la_orden_y_desde_el_tablero_se_le_habla_a_uno(self):
        self.isl.on_control('chat', {'control': 'chat', 'agent': 'reviewer'})
        self.assertEqual(self.isl.chat.agent, 'elyares-reviewer')
        self.isl.close_chat()
        # Desde un desglose: su conversación del proyecto de esa pestaña, no el de tmux.
        self.work('a')
        self.isl.tab = 'a'
        self.isl.on_hit('talk', 'elyares-auditor')
        self.assertTrue(self.isl.chat_open)
        self.assertEqual((self.isl.chat.agent, self.isl.chat.cwd), ('elyares-auditor', '/x/a'))

    def test_el_desglose_lleva_a_su_chat(self):
        self.isl.expanded = True
        self.work('a', 'elyares-auditor')
        self.isl.tab, self.isl.focus = 'a', ('a', 'auditor')
        self.draw()
        # Uno de los tres ya tiene ahí su mini chat: el enlace es para leerlo.
        self.assertIn('ver su chat ›', self.shown)
        self.assertEqual(self.hit('talk'), ['elyares-auditor'])
        self.isl.focus = ('a', 'engineer')
        self.draw()
        self.assertIn('hablarle ›', self.shown)
        self.assertEqual(self.hit('talk'), [''])
        # Las caritas libres: todos menos el del desglose y el auditor, que trabaja.
        self.assertEqual(self.hit('brief'), [('a', role) for role in state.TEAM[1:] if role != 'auditor'])

    def brief(self, role='auditor', text='audita el diff'):
        """Un clic en uno de los tres, libre, y un encargo en su mini chat."""
        self.isl.expanded = True
        self.draw()
        self.isl.on_hit('brief', ('a', role))
        self.isl.chat_text = lambda: text
        self.isl.on_chat_enter()
        return self.isl.chats.get((f'elyares-{role}', '/x/a'))

    def sending(self):
        """Mandar sin abrir ningún Claude: el turno queda en curso."""
        def send(c, text, images=()):
            c.busy = bool(text.strip())
            return c.busy
        patcher = mock.patch.object(app.chatview.chat.Chat, 'send', autospec=True, side_effect=send)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_un_clic_en_uno_libre_abre_su_mini_chat(self):
        self.isl.expanded = True
        self.work('a')
        board = self.isl.goal()
        self.draw()
        self.assertEqual(self.hit('brief'), [('a', role) for role in state.TEAM[1:]])
        self.isl.on_hit('brief', ('a', 'auditor'))
        # Cambia al desglose de ese, con el teclado listo y sin abrir el panel del chat.
        self.assertEqual(self.isl.focus, ('a', 'auditor'))
        self.assertTrue(self.isl.chat_typing)
        self.assertFalse(self.isl.chat_open)
        self.assertEqual(self.isl.target(), 'board')
        self.assertEqual(self.isl.goal()[1] - board[1], app.FOCUS_H + app.chatview.MINI_H - app.BOARD_H)
        self.draw()
        for text in ('elyares-auditor está libre', 'Dile a elyares-auditor qué hacer', 'Enter manda · Esc suelta'):
            self.assertIn(text, self.shown)
        self.assertIsNotNone(self.isl.chat_box)
        self.assertEqual(self.isl.chats, {})         # hasta que se le manda algo no hay conversación
        # Esc suelta el teclado; el desglose sigue ahí, con su caja.
        self.isl.on_chat_key(None, app.Gdk.KEY_Escape, 0, 0)
        self.assertFalse(self.isl.chat_typing)
        self.draw()
        self.assertIn('Clic aquí para encargarle algo a elyares-auditor', self.shown)
        self.isl.on_hit('brief', None)               # un clic en la caja lo vuelve a tomar
        self.assertTrue(self.isl.chat_typing)

    def test_el_engineer_no_tiene_mini_chat(self):
        self.isl.expanded = True
        self.work('a')
        self.isl.focus = ('a', 'engineer')
        self.assertIsNone(self.isl.briefing())
        self.assertEqual(self.isl.goal()[1], app.TABS_H + app.FOCUS_H + app.BOARD_PAD + app.PILLS_H)
        self.isl.chat_type(True)
        self.assertFalse(self.isl.chat_typing)

    def test_al_encargarle_trabaja_al_lado_de_los_demas(self):
        send = self.sending()
        self.work('a')
        c = self.brief()
        send.assert_called_once_with(c, 'audita el diff', [])
        # En la carpeta de la pestaña, y de vuelta al tablero, sin el teclado.
        self.assertEqual((c.agent, c.cwd), ('elyares-auditor', '/x/a'))
        self.assertEqual(self.isl.chat_hosts, {('elyares-auditor', '/x/a'): 'a'})
        self.assertEqual((self.isl.focus, self.isl.chat_typing, self.isl.chat_open), (None, False, False))
        # Aún sin noticias de Claude ya sale trabajando, al lado del engineer.
        self.draw()
        self.assertEqual(self.hit('member'), [('a', 'engineer'), ('a', 'auditor')])
        self.assertIn('Arrancando…', self.shown)
        # Su sesión no saca pestaña: sus pasos van en su tarjeta de esta.
        self.isl.on_chat({'type': 'system', 'subtype': 'init', 'session_id': 's-aud'}, c)
        self.send('start', 's-aud', cwd='/x/a', agent_type='elyares-auditor')
        self.send('tool', 's-aud', cwd='/x/a', agent_type='elyares-auditor', tool_name='Bash',
                  tool_input={'command': 'semgrep scan'})
        self.assertEqual([s.sid for s in self.isl.tabs()], ['a'])
        self.isl.tab = 's-aud'
        self.assertEqual(self.isl.tab_session().sid, 'a')
        self.draw()
        self.assertEqual(self.hit('tab'), ['a'])
        self.assertEqual(self.hit('member'), [('a', 'engineer'), ('a', 'auditor')])
        self.assertIn('Ejecutando semgrep scan', self.shown)
        # Y otro más: los tres a la vez.
        self.brief('reviewer', 'revisa el diff')
        self.draw()
        self.assertEqual(self.hit('member'), [('a', 'engineer'), ('a', 'auditor'), ('a', 'reviewer')])
        self.assertEqual(self.hit('brief'), [('a', role) for role in state.TEAM[1:]
                                             if role not in ('auditor', 'reviewer')])

    def test_el_punto_de_la_pestana_es_del_encargo_si_la_sesion_descansa(self):
        self.sending()
        self.work('a')
        self.send('stop', now=T + 1)
        self.isl.refresh = lambda: setattr(self.isl, 'view', self.isl.model.view(now=T + 60, pin=self.isl.pin))
        self.isl.refresh()
        self.brief()
        a = self.isl.model.sessions['a']
        self.assertEqual(self.isl.tab_dot(a), app.mascot.accent('auditor'))
        self.assertTrue(self.isl.busy(a))

    def test_el_permiso_de_un_encargo_se_contesta_en_su_tarjeta(self):
        self.sending()
        self.work('a')
        c = self.brief()
        c.answer = mock.Mock()
        self.isl.on_chat({'type': 'system', 'subtype': 'init', 'session_id': 's-aud'}, c)
        self.send('start', 's-aud', cwd='/x/a', agent_type='elyares-auditor')
        self.isl.on_chat({'type': 'control_request', 'request_id': 'r', 'request': {
            'subtype': 'can_use_tool', 'tool_name': 'Bash', 'input': {'command': 'git push'}}}, c)
        self.assertEqual(self.isl.tab_session().sid, 'a')
        self.draw()
        self.assertIn('Ejecutando git push', self.shown)
        x, y, w, h = self.isl.buttons['allow']
        self.isl.on_click(None, 1, x + w / 2, y + h / 2)
        c.answer.assert_called_once_with(True)

    def test_sin_su_pestana_el_encargo_saca_la_suya(self):
        self.sending()
        self.work('a')
        c = self.brief()
        self.isl.on_chat({'type': 'system', 'subtype': 'init', 'session_id': 's-aud'}, c)
        self.send('start', 's-aud', cwd='/x/a', agent_type='elyares-auditor')
        self.send('session-end', 'a')
        self.assertEqual([s.sid for s in self.isl.tabs()], ['s-aud'])
        self.assertEqual(self.isl.tab_session().sid, 's-aud')

    def test_ocupado_en_un_proyecto_se_le_encarga_tambien_en_otro(self):
        send = self.sending()
        self.work('a')
        self.work('b')
        self.isl.tab = 'a'
        c = self.brief()
        # Desde la pestaña de otro proyecto, mientras sigue con lo de este:
        # ahí tiene otra conversación, y trabaja en las dos a la vez.
        self.isl.tab = 'b'
        self.draw()
        self.isl.on_hit('brief', ('b', 'auditor'))
        self.isl.on_chat_enter()
        self.assertEqual(send.call_count, 2)
        other = self.isl.chats['elyares-auditor', '/x/b']
        self.assertIsNot(other, c)
        self.assertTrue(c.busy and other.busy)
        self.assertEqual(self.isl.chat_hosts, {('elyares-auditor', '/x/a'): 'a', ('elyares-auditor', '/x/b'): 'b'})
        for tab in ('a', 'b'):
            self.isl.tab = tab
            self.draw()
            self.assertEqual(self.hit('member'), [(tab, 'engineer'), (tab, 'auditor')])

    def test_lo_escrito_para_uno_no_se_le_manda_a_otro(self):
        self.work('a')
        self.isl.expanded = True
        self.isl.chat_images = [b'png']
        self.isl.on_hit('brief', ('a', 'auditor'))
        self.assertEqual((self.isl.chat_whom, self.isl.chat_images), ('elyares-auditor', []))
        self.isl.chat_images = [b'png']
        self.isl.on_hit('brief', None)               # el mismo: lo pegado sigue
        self.assertEqual(self.isl.chat_images, [b'png'])
        self.isl.open_chat()
        self.assertEqual((self.isl.chat_whom, self.isl.chat_images), ('chat', []))

    def test_escribiendo_en_el_mini_chat_la_isla_no_se_mueve(self):
        self.work('a')
        self.work('b')
        self.isl.expanded = True
        self.isl.tab = 'a'
        self.isl.on_hit('brief', ('a', 'auditor'))
        self.isl.model.handle({'event': 'stop', 'session_id': 'b', 'cwd': '/x/b'}, now=T + 3)
        self.isl.follow(self.isl.model.view(now=T + 3))
        self.assertEqual((self.isl.tab, self.isl.focus), ('a', ('a', 'auditor')))
        # Ni se cierra con el ratón fuera.
        del self.isl.collapse
        self.isl.collapse()
        self.assertEqual(self.isl.focus, ('a', 'auditor'))
        # Si el desglose se va, el teclado no se queda tomado.
        self.isl.on_hit('back', None)
        self.isl.chat_place(300)
        self.assertFalse(self.isl.chat_typing)

    def test_la_pestana_del_chat_de_un_agente_lo_dice(self):
        self.isl.chat_sessions.add('s-arq')
        self.send('start', 's-arq', agent_type='elyares-architect')
        self.assertEqual(self.isl.tab_label(self.isl.model.sessions['s-arq']), 's-arq · chat architect')

    def test_la_linea_de_estado_cambia_modelo_esfuerzo_y_plan(self):
        c = self.conversation()
        c.model_id = 'claude-opus-5-5'
        c.set_model, c.set_effort, c.toggle_plan = mock.Mock(), mock.Mock(), mock.Mock()
        self.draw()
        self.assertIn('Opus 5.5', self.shown)
        self.assertIn('sin plan', self.shown)
        self.isl.on_chat_hit('model')
        self.assertEqual(self.isl.chat_menu, 'model')
        self.draw()
        self.assertIn('   Sonnet 5.5', self.shown)
        self.isl.on_chat_hit('model:sonnet')
        c.set_model.assert_called_once_with('sonnet')
        self.assertEqual(self.isl.settings['chat_model'], 'sonnet')
        self.assertIsNone(self.isl.chat_menu)
        self.isl.on_chat_hit('effort:max')
        c.set_effort.assert_called_once_with('max')
        # Shift+Tab, como en la terminal.
        self.isl.on_chat_key(None, app.Gdk.KEY_ISO_Left_Tab, 0, app.Gdk.ModifierType.SHIFT_MASK)
        c.toggle_plan.assert_called_once_with()

    def test_las_imagenes_pegadas_van_en_etiquetas(self):
        self.conversation()
        self.isl.chat_images = [b'uno', b'dos']
        self.draw()
        self.assertIn('imagen 2  ×', self.shown)
        self.isl.on_chat_hit('img:0')
        self.assertEqual(self.isl.chat_images, [b'dos'])

    def test_al_escribir_una_barra_salen_los_comandos(self):
        self.conversation()
        self.isl.chat_text = lambda: '/co'
        self.assertEqual([n for n, _ in self.isl.suggestions()], ['commit', 'compact', 'contexto'])
        self.draw()
        self.assertIn('/commit', self.shown)
        self.assertIn('Hace los commits', self.shown)
        # Con espacio ya no es un comando a medias.
        self.isl.chat_text = lambda: '/commit ahora'
        self.assertEqual(self.isl.suggestions(), [])

    def write(self, text, cursor=None):
        """Lo escrito en la caja, con el cursor en `cursor` (o al final)."""
        self.isl.chat_text = lambda: text
        self.isl.chat_cursor = lambda: len(text) if cursor is None else cursor
        self.isl.chat_set_text = mock.Mock()

    def test_la_barra_vale_con_texto_antes_y_despues(self):
        self.conversation()
        self.write('sube los cambios con /co')
        self.assertEqual([n for n, _ in self.isl.suggestions()], ['commit', 'compact', 'contexto'])
        # Enter elige de la lista, y lo de antes se queda como estaba.
        self.isl.on_chat_enter()
        self.isl.chat_set_text.assert_called_once_with('sube los cambios con /commit ', 29)
        # Con el cursor en medio del texto, lo de después tampoco se toca.
        self.write('primero /con y luego el PR', cursor=12)
        self.assertEqual([n for n, _ in self.isl.suggestions()], ['contexto'])
        self.isl.complete('contexto')
        self.isl.chat_set_text.assert_called_once_with('primero /contexto y luego el PR', 18)
        # Una ruta o una fracción no son un comando.
        for text in ('abre /home/yared/notas', 'y/o', 'el 10/02'):
            self.write(text)
            self.assertEqual(self.isl.suggestions(), [], text)

    def test_el_comando_ya_escrito_se_manda_con_enter(self):
        c = self.conversation()
        c.send = mock.Mock(return_value=True)
        self.write('luego corre /commit')
        self.isl.on_chat_enter()
        c.send.assert_called_once_with('luego corre /commit', [])

    def test_el_pie_de_una_respuesta_la_copia(self):
        c = self.conversation()
        E = app.chatview.chat.Entry
        c.entries.append(E('foot', 'elyares-engineer · Opus · 3 s'))
        self.draw()
        self.assertEqual(self.hit('chat').count('copy:2'), 1)
        self.assertNotIn('pass:2', self.hit('chat'))       # al engineer no se le pasa lo suyo
        _, key, x, y, w, h = next(hit for hit in self.isl.hits if hit[1] == 'copy:2')
        with mock.patch.object(app.chatview.subprocess, 'run') as run:
            self.isl.on_click(None, 1, x + w / 2, y + h / 2)
        # Entera y con su markdown, que es lo que se pega en otro lado.
        self.assertEqual(run.call_args.kwargs['input'].decode(), c.entries[1].text)
        self.draw()
        self.assertIn('copiado ✓', self.shown)
        # Sin wl-copy, por el portapapeles de GTK.
        with mock.patch.object(app.chatview.subprocess, 'run', side_effect=FileNotFoundError):
            self.isl.on_chat_hit('copy:2')
        self.isl.da.get_clipboard().set.assert_called_once_with(c.entries[1].text)
        # Un turno cortado sin respuesta no tiene qué copiar.
        c.entries += [E('you', 'otra cosa'), E('foot', 'elyares-engineer · Opus · 1 s')]
        self.draw()
        self.assertNotIn('copy:4', self.hit('chat'))

    def test_un_enlace_de_la_respuesta_se_copia_solo(self):
        c = self.conversation()
        E = app.chatview.chat.Entry
        c.entries[1].text = 'Para verlo: https://claude.ai/code/artifact/abc-1.'
        c.entries.append(E('foot', 'elyares-designer · Sonnet · 3 s'))
        self.draw()
        self.assertIn('copiar enlace', self.shown)
        with mock.patch.object(app.chatview.subprocess, 'run') as run:
            self.isl.on_chat_hit('url:2:0')
        # Solo el enlace, sin la frase ni el punto con el que acaba.
        self.assertEqual(run.call_args.kwargs['input'].decode(), 'https://claude.ai/code/artifact/abc-1')
        self.draw()
        self.assertIn('enlace copiado ✓', self.shown)
        # Con dos, cada uno con su número.
        c.entries[1].text = 'a https://a.dev/x y https://b.dev/y'
        self.draw()
        self.assertIn('copiar enlace 2', self.shown)

    def test_lo_de_un_agente_se_le_pasa_al_engineer(self):
        self.isl.open_chat()
        engineer = self.isl.chat
        self.isl.on_chat_hit('agent:elyares-designer')
        E = app.chatview.chat.Entry
        self.isl.chat.entries = [E('you', 'propón el panel'), E('claude', '## Panel\nA la derecha.'),
                                 E('foot', 'elyares-designer · Sonnet · 20 s')]
        self.draw()
        self.assertIn('al engineer ›', self.shown)
        self.isl.chat_set_text = mock.Mock()
        self.isl.on_chat_hit('pass:2')
        # No se manda sola: queda en la caja del engineer, en el mismo proyecto.
        self.assertIs(self.isl.chat, engineer)
        self.assertTrue(self.isl.chat_typing)
        self.isl.chat_set_text.assert_called_with('De elyares-designer:\n\n## Panel\nA la derecha.\n\n')
        self.assertEqual(engineer.entries, [])

    def test_la_arroba_nombra_agentes_y_archivos(self):
        c = self.conversation()
        c.files, c.files_at = ['elyares/chat.py', 'README.md'], float('inf')
        self.write('que lo revise @rev')
        self.assertEqual(self.isl.suggestions(), [('elyares-reviewer', 'agente')])
        self.draw()
        self.assertIn('@elyares-reviewer', self.shown)
        self.isl.on_chat_hit('@elyares-reviewer')
        self.isl.chat_set_text.assert_called_once_with('que lo revise @elyares-reviewer ', 32)
        self.write('mira @chat y dime')
        self.isl.chat_cursor = lambda: 10
        self.assertEqual(self.isl.suggestions(), [('elyares/chat.py', '')])
        # Un correo no nombra a nadie.
        self.write('escríbele a yared@ejemplo.mx')
        self.assertEqual(self.isl.suggestions(), [])

    def test_las_conversaciones_vuelven_al_arrancar_la_isla(self):
        c = self.isl.chats['', '/x/proj'] = self.conversation()
        c.session, c.tokens, c.window = 's-chat', 88000, 1000000
        self.send('start', 's-chat', cwd='/x/proj')
        aud = self.isl.chat_for('elyares-auditor', '/x/proj')
        aud.session = 's-aud'
        tl = self.isl.chat_for('', '/x/tl')
        tl.session = 's-tl'
        self.isl.chat_hosts = {('elyares-auditor', '/x/proj'): 's-chat', ('elyares-reviewer', '/x/proj'): 's-ido'}
        self.isl.chat_save()
        saved = self.save_chats.call_args[0][0]
        self.isl.chat_save()
        self.save_chats.assert_called_once()        # sin cambios no se vuelve a escribir
        # Otra isla, recién arrancada, con las mismas sesiones.
        other = app.Island.__new__(app.Island)
        other.model, other.settings = self.isl.model, self.isl.settings
        other.chat_init()
        other.workflows_init()
        other.chat_restore(json.loads(json.dumps(saved)))
        self.assertEqual(sorted(other.chats), [('', '/x/proj'), ('', '/x/tl'), ('elyares-auditor', '/x/proj')])
        back = other.chat
        self.assertEqual((back.agent, back.cwd, back.session, back.context), ('', '/x/proj', 's-chat', 8.8))
        self.assertEqual([(e.kind, e.text) for e in back.entries], [(e.kind, e.text) for e in c.entries])
        self.assertIsNone(back.proc)
        self.assertTrue(other.chat_open)                        # estaba abierto: sigue abierto
        self.assertFalse(other.chat_typing)                     # pero sin tomar el teclado
        self.assertEqual(other.chat_sessions, {'s-chat', 's-aud', 's-tl'})
        # El otro encargo ya no tiene a quién.
        self.assertEqual(other.chat_hosts, {('elyares-auditor', '/x/proj'): 's-chat'})
        # Lo que se guardó cuando había una sola conversación por agente se sigue leyendo.
        old = {'chats': [c.dump(), aud.dump()], 'current': '', 'open': False, 'hosts': {'elyares-auditor': 's-chat'}}
        other.chat_init()
        other.workflows_init()
        other.chat_restore(json.loads(json.dumps(old)))
        self.assertEqual((other.chat.session, other.chat_open), ('s-chat', False))
        # Un aviso viejo, que no dice de qué conversación es, abre la que se tenía a la vista...
        self.tmux_cwd = '/x/tl'
        other.ensure_tick = other.chat_type = lambda *a: None
        other.target = lambda: 'open'               # sin tablero a la vista
        other.chat_show(True)
        self.assertEqual(other.chat.session, 's-chat')
        # ...y el botón del chat, la del proyecto en el que estás en tmux.
        other.close_chat()
        other.open_chat()
        self.assertEqual(other.chat.cwd, '/x/tl')
        self.assertEqual(other.chat_hosts, {('elyares-auditor', '/x/proj'): 's-chat'})
        # Lo guardado a medias o roto no tumba el arranque.
        for bad in ({}, {'chats': 'x', 'hosts': []}, {'chats': [{}, 3, {'cwd': 7}], 'current': 9}):
            other.chat_init()
            other.workflows_init()
            other.chat_restore(bad)
            self.assertEqual((other.chats, other.chat, other.chat_open), ({}, None, False))

    def test_el_contexto_sale_en_la_linea_de_estado_y_en_el_tablero(self):
        c = self.conversation()
        self.draw()
        self.assertFalse([t for t in self.shown if t.startswith('contexto')])
        c.session = 's-chat'
        self.send('start', 's-chat', cwd='/x/proj')
        self.isl.on_chat({'type': 'control_response', 'response': {
            'subtype': 'success', 'response': {'totalTokens': 88000, 'maxTokens': 1000000}}})
        self.draw()
        self.assertIn('contexto 9% · 88k', self.shown)
        # A la sesión del tablero, que lo muestra junto a sus pestañas.
        self.assertAlmostEqual(self.isl.model.sessions['s-chat'].context, 8.8)
        self.isl.close_chat()
        self.isl.expanded, self.isl.tab = True, 's-chat'
        self.draw()
        self.assertIn('contexto 9%', self.shown)


@unittest.skipIf(app is None, 'sin gi: usa /usr/bin/python3')
class Proyectos(Dibujo):
    """El panel de proyectos y los atajos para empezar en uno sin abrir `claude` en una terminal."""

    def setUp(self):
        super().setUp()
        self.isl.ensure_tick = lambda: None
        self.isl.close_chat = mock.Mock()
        P = app.projectview.projects.Project
        self.isl.projects = [P('patio', '/d/clients/patio', 'clients', key='patio'),
                             P('devherd', '/d/personal/devherd', 'personal', 'devherd', 10, key='devherd'),
                             P('sonda', '/d/personal/sonda', 'personal', key='sonda'),
                             P('aang', '/d/work/aang', 'work', 'aang', 20, key='aang'),
                             P('tl', '/d/work/tl', 'work', 'tl', 90, True, key='tl'),
                             P('main', '/home/yo', '', 'main', 5, key='main')]

    def rows(self):
        return [(kind, value if kind == 'h' else value.name, count) for kind, value, count in self.isl.project_items()]

    def test_el_panel_es_el_sidebar_de_tmux(self):
        self.isl.on_control('projects')
        self.assertEqual(self.isl.target(), 'projects')
        # Solo lo abierto, por workspace, con abiertos/total; las sueltas al final.
        self.assertEqual(self.rows(), [('h', 'personal', '1/2'), ('p', 'devherd', None),
                                       ('h', 'work', '2/2'), ('p', 'aang', None), ('p', 'tl', None),
                                       ('h', 'otras', ''), ('p', 'main', None)])
        self.draw()
        for text in ('Proyectos', '4 abiertos en tmux, de 6', 'todos ›', 'personal', '1/2', 'devherd', 'tl'):
            self.assertIn(text, self.shown)
        self.assertNotIn('sonda', self.shown)
        # «todos ›», como ctrl-t en el sidebar: también los cerrados.
        self.isl.on_hit('projects', 'all')
        self.assertEqual(self.rows()[:2], [('h', 'clients', '0/1'), ('p', 'patio', None)])
        self.draw()
        self.assertIn('sonda', self.shown)
        self.assertIn('solo abiertos ›', self.shown)
        self.assertEqual(self.isl.goal()[0], app.projectview.PROJ_W)
        self.isl.on_control('projects')
        self.assertFalse(self.isl.projects_open)

    def test_un_clic_en_un_proyecto_abre_su_chat(self):
        self.isl.open_chat = mock.Mock()
        self.isl.on_control('projects')
        self.isl.projects_all = True
        self.draw()
        key, x, y, w, h = next((k, x, y, w, h) for kind, k, x, y, w, h in self.isl.hits
                               if kind == 'project' and k == '/d/personal/sonda')
        self.isl.on_click(None, 1, x + w / 2, y + h / 2)
        self.isl.open_chat.assert_called_once_with(typing=True, cwd='/d/personal/sonda')
        self.assertFalse(self.isl.projects_open)

    def test_dice_como_va_el_claude_de_cada_uno(self):
        self.send('start', 's1', cwd='/d/work/aang/app')
        self.send('tool', 's1', cwd='/d/work/aang/app', tool_name='Bash', tool_input={'command': 'make'})
        self.isl.chats['', '/d/personal/sonda'] = app.chatview.chat.Chat('/d/personal/sonda', None)
        self.isl.chats['', '/d/personal/sonda'].session = 's-viejo'
        by = {p.name: p for p in self.isl.projects}
        self.assertEqual(self.isl.project_claude(by['aang']), ('trabaja', 'cmd'))
        self.assertEqual(self.isl.project_claude(by['sonda']), ('chat', 'text'))
        self.assertIsNone(self.isl.project_claude(by['tl']))
        # Cerrado en tmux pero con conversación: sale aunque solo se vean los abiertos.
        self.assertIn(('p', 'sonda', None), self.rows())
        # Una sesión de tmux abierta en la carpeta personal no se queda con lo de los demás...
        self.isl.projects[-1].path = '/d'
        self.assertIsNone(self.isl.project_claude(by['main']))
        self.assertEqual(self.isl.project_claude(by['aang']), ('trabaja', 'cmd'))
        # ...pero sí con lo que corre en ella y no es de ningún proyecto.
        self.send('start', 's9', cwd='/d/notas')
        self.assertEqual(self.isl.project_claude(by['main']), ('trabaja', 'cmd'))

    def test_muchos_proyectos_caben_en_sus_columnas(self):
        P = app.projectview.projects.Project
        self.isl.projects = [P(f'p{i:02}', f'/d/w{i % 7}/p{i:02}', f'w{i % 7}', 's', key=f'p{i:02}') for i in range(70)]
        self.isl.projects.sort(key=lambda p: (p.ws, p.name))
        columns, per = self.isl.project_columns()
        self.assertEqual(sum(len(c) for c in columns), 77)
        self.assertEqual(len(columns), app.projectview.PROJ_COLS)
        self.assertFalse([c for c in columns if c[-1][0] == 'h'])       # ninguna cabecera sola al pie
        self.assertLessEqual(self.isl.projects_goal()[1], app.projectview.PROJ_MAX_H)
        self.isl.projects_open = True
        self.assertTrue(self.draw())

    def test_en_el_tablero_la_pestana_fantasma_de_donde_estas(self):
        self.isl.open_chat = mock.Mock()
        self.isl.expanded = True
        self.work('s1')                                 # una sesión de otro proyecto (/x/s1)
        self.draw()
        self.assertIn('+ tl', self.shown)
        self.assertEqual(self.hit('start'), ['/d/work/tl'])
        self.isl.on_hit('start', '/d/work/tl')
        self.isl.open_chat.assert_called_once_with(typing=True, cwd='/d/work/tl')
        # Cuando ese proyecto ya tiene un Claude, la fantasma sobra.
        self.send('start', 's2', cwd='/d/work/tl')
        self.draw()
        self.assertNotIn('+ tl', self.shown)
        self.assertEqual(self.hit('start'), [])

    def test_sin_sesiones_la_cabecera_ofrece_empezar_donde_estas(self):
        self.isl.expanded, self.isl.dnd = True, False
        self.isl.extra = lambda mode: 0             # sin pantalla no se mide el detalle
        self.isl.refresh = app.Island.refresh.__get__(self.isl)
        with mock.patch.object(app.store, 'save'):
            self.isl.saved = None
            self.isl.refresh()
            self.assertEqual((self.isl.title, self.isl.detail), ('Sin sesiones', 'Estás en tl · empezar ›'))
            self.draw()
            self.assertEqual(self.hit('start'), ['/d/work/tl'])
            # Fuera de tmux no hay nada que ofrecer.
            self.isl.projects[4].here = False
            self.isl.refresh()
        self.assertEqual(self.isl.detail, 'Nada corriendo ahora')

    def test_la_pastilla_mas_abre_el_panel(self):
        self.isl.expanded = True
        self.draw()
        key, x, y, w, h = next(p for p in self.isl.pills if p[0] == app.projectview.PROJECTS_PILL)
        self.isl.on_click(None, 1, x + w / 2, y + h / 2)
        self.assertTrue(self.isl.projects_open)

    def test_la_lista_se_refresca_sola_sin_frenar_la_isla(self):
        self.isl.refresh = mock.Mock()
        found = list(self.isl.projects)
        self.isl.on_projects(found)
        self.isl.refresh.assert_not_called()            # igual que antes: nada que redibujar
        self.isl.on_projects(found[:2])
        self.isl.refresh.assert_called_once()
        with mock.patch.object(app.projectview.threading, 'Thread') as thread:
            self.isl.projects_tick(0)
            self.isl.projects_tick(1)
            self.isl.projects_tick(app.projectview.PROJECTS_SECS)
        self.assertEqual(thread.call_count, 2)


@unittest.skipIf(app is None, 'sin gi: usa /usr/bin/python3')
class Mover(IslandCase):
    """`elyares-ctl move`: la isla se corre a lo ancho de la pantalla."""

    def setUp(self):
        super().setUp()
        self.isl.ensure_tick = lambda: None
        self.isl.win, self.isl.screen_w = object(), 3440
        shell = mock.patch.object(app, 'LayerShell')
        self.shell = shell.start()
        self.addCleanup(shell.stop)

    def placed(self):
        """Cómo quedó la ventana: (anclada a la izquierda, su margen)."""
        return self.shell.set_anchor.call_args[0][2], self.shell.set_margin.call_args[0][2]

    def test_su_sitio_de_siempre_es_el_centro(self):
        self.assertEqual(self.isl.position(), 50)
        self.isl.place()
        # Anclada solo arriba: la centra el compositor, como antes.
        self.assertEqual(self.placed(), (False, 0))

    def test_se_corre_de_sitio_en_sitio_y_vuelve_al_centro(self):
        room = 3440 - app.WIN_W
        seen = []
        for where in ('right', 'right', 'right', 'left', 'center', 'left', 'left', 'left'):
            self.isl.on_control('move', {'where': where})
            seen.append((self.isl.settings['position'], *self.placed()))
        self.assertEqual(seen, [(75, True, round(room * .75)), (100, True, room), (100, True, room),
                                (75, True, round(room * .75)), (50, False, 0),
                                (25, True, round(room * .25)), (0, True, 0), (0, True, 0)])
        # Se guarda: al volver a arrancar sigue donde se dejó.
        self.assertEqual(app.settings.save.call_args[0][0]['position'], 0)

    def test_sube_baja_y_vuelve_arriba_al_centro(self):
        self.isl.screen_h = 1440
        top = lambda: self.shell.set_margin.call_args_list[-2][0][2]
        for where, want in (('down', app.STEP_Y), ('down', 2 * app.STEP_Y), ('up', app.STEP_Y), ('up', 0), ('up', 0)):
            self.isl.on_control('move', {'where': where})
            self.assertEqual((self.isl.settings['position_y'], top()), (want, want))
        self.isl.on_control('move', {'where': 'right'})
        self.isl.on_control('move', {'where': 'down'})
        self.isl.on_control('move', {'where': 'reset'})
        self.assertEqual((self.isl.settings['position'], self.isl.settings['position_y'], top()), (50, 0, 0))

    def test_clic_derecho_con_el_chat_abierto_lo_cierra_y_achica_la_isla(self):
        self.isl.chat_open, self.isl.settings['compact'] = True, False
        with mock.patch.object(chatview, 'LayerShell'):
            self.isl.toggle_compact()
        self.assertEqual((self.isl.chat_open, self.isl.settings['compact']), (False, True))

    def test_el_arrastre_no_guarda_un_sitio_fuera_de_la_pantalla(self):
        self.isl.screen_h = 1440
        self.isl.dragging = True
        for dy in (-90, -90, 5000):
            self.isl.on_drag_update(None, 0, dy)
            self.assertTrue(0 <= self.isl.settings['position_y'] <= 1440 - app.WIN_H)

    def drag(self, button, start, *moves, alt=False):
        """Un arrastre con el ratón en la pantalla: parte de `start` y pasa por `moves`."""
        gesture = mock.Mock()
        gesture.get_current_button.return_value = button
        gesture.get_current_event_state.return_value = app.DRAG_MASK if alt else 0
        with mock.patch.object(app.hypr, 'cursor_pos', return_value=start):
            self.isl.on_drag_begin(gesture, 0, 0)
        for (x, y), (dx, dy) in moves:
            with mock.patch.object(app.hypr, 'cursor_pos', return_value=(x, y)):
                self.isl.on_drag_update(gesture, dx, dy)
        return gesture

    def test_el_arrastre_sigue_al_ratón_en_la_pantalla_aunque_la_ventana_vaya_atrasada(self):
        self.isl.screen_h, self.isl.screen_w = 1440, 3440
        self.isl.settings['position'], self.isl.settings['position_y'] = 50, 100
        first, y0 = self.isl.offset(), self.isl.top()
        # El compositor aún no movió la ventana: el gesto sigue diciendo lo mismo en cada
        # evento, y la isla no se pasa de largo.
        self.drag(app.Gdk.BUTTON_PRIMARY, (1000, 500), ((1100, 530), (100, 30)), ((1100, 530), (100, 30)),
                  ((1100, 530), (100, 30)), alt=True)
        self.assertEqual(self.isl.top(), y0 + 30)
        self.assertEqual(self.isl.offset(), first + 100)

    def test_el_botón_del_medio_arrastra_sin_alt_pero_un_clic_no_mueve_nada(self):
        self.isl.screen_h, self.isl.screen_w = 1440, 3440
        before = (self.isl.settings['position'], self.isl.settings['position_y'])
        gesture = self.drag(app.Gdk.BUTTON_MIDDLE, (1000, 500), ((1002, 501), (2, 1)))
        self.assertFalse(self.isl.dragging)
        self.assertEqual((self.isl.settings['position'], self.isl.settings['position_y']), before)
        gesture.set_state.assert_not_called()
        self.drag(app.Gdk.BUTTON_MIDDLE, (1000, 500), ((1040, 560), (40, 60)))
        self.assertTrue(self.isl.dragging)
        self.assertEqual(self.isl.top(), 60)

    def test_el_botón_izquierdo_sin_alt_no_arrastra(self):
        gesture = self.drag(app.Gdk.BUTTON_PRIMARY, (1000, 500), ((1040, 560), (40, 60)))
        self.assertFalse(self.isl.dragging)
        gesture.set_state.assert_called_once_with(app.Gtk.EventSequenceState.DENIED)

    def test_no_baja_mas_de_lo_que_cabe_en_la_pantalla(self):
        self.isl.screen_h = app.WIN_H + 100
        self.isl.settings['position_y'] = 90
        self.isl.on_control('move', {'where': 'down'})
        self.assertEqual(self.isl.settings['position_y'], 100)

    def test_tambien_a_un_punto_cualquiera(self):
        self.isl.on_control('move', {'where': '10'})
        self.assertEqual((self.isl.settings['position'], self.placed()), (10, (True, round((3440 - app.WIN_W) * .1))))
        # Desde ahí, al sitio que sigue de cada lado.
        self.isl.on_control('move', {'where': 'right'})
        self.assertEqual(self.isl.settings['position'], 25)
        for bad in ('arriba', None, ''):
            self.isl.on_control('move', {'where': bad})
            self.assertEqual(self.isl.settings['position'], 25)

    def test_en_otra_pantalla_el_mismo_sitio_es_otro_margen(self):
        self.isl.settings['position'] = 100
        self.isl.place()
        self.assertEqual(self.placed(), (True, 3440 - app.WIN_W))
        self.isl.screen_w = 1920
        self.isl.place()
        self.assertEqual(self.placed(), (True, 1920 - app.WIN_W))
        # Una preferencia rota no la saca de su sitio.
        self.isl.settings['position'] = 'derecha'
        self.assertEqual(self.isl.position(), 50)


@unittest.skipIf(app is None, 'sin gi: usa /usr/bin/python3')
class Recarga(IslandCase):
    """`elyares-ctl reload`: la isla se vuelve a arrancar con el código de su carpeta."""

    def setUp(self):
        super().setUp()
        self.isl.reload_check = lambda: ''
        self.isl.is_service = lambda: True
        self.isl.ensure_tick = lambda: None
        timer = mock.patch.object(app.GLib, 'timeout_add', side_effect=lambda ms, fn: fn())
        self.timer = timer.start()
        self.addCleanup(timer.stop)
        popen = mock.patch.object(app.subprocess, 'Popen')
        self.popen = popen.start()
        self.addCleanup(popen.stop)
        save = mock.patch.object(app.store, 'save')
        self.save = save.start()
        self.addCleanup(save.stop)
        self.c = app.chatview.chat.Chat('/x/proj', lambda ev: None, spawn=mock.Mock())
        self.c.session = 's-chat'
        self.isl.chats['', '/x/proj'] = self.isl.chat = self.c

    def reply(self):
        req = mock.Mock()
        self.isl.on_control('reload', {}, req)
        return req.reply.call_args[0][0]

    def test_sin_turnos_en_curso_se_recarga_ya(self):
        self.assertEqual(self.reply(), {'ok': True, 'note': 'la isla se recarga ya'})
        self.popen.assert_called_once_with(['systemctl', '--user', '--no-block', 'restart', app.UNIT])
        self.save.assert_called_once()
        self.save_chats.assert_called_once()        # las conversaciones quedan guardadas antes

    def test_con_un_turno_en_curso_espera_a_que_acabe(self):
        self.c.busy = True
        self.assertEqual(self.reply()['note'], 'la isla se recarga al acabar el turno en curso')
        self.popen.assert_not_called()
        self.isl.on_chat({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Listo.'}]}})
        self.popen.assert_not_called()
        self.isl.on_chat({'type': 'result', 'subtype': 'success'})
        self.popen.assert_called_once()
        self.assertEqual(self.save_chats.call_args[0][0]['chats'][0]['entries'][-1][:2], ['claude', 'Listo.'])

    def test_con_el_codigo_roto_la_isla_se_queda(self):
        self.isl.reload_check = lambda: "SyntaxError: '(' was never closed"
        answer = self.reply()
        self.assertFalse(answer['ok'])
        self.assertIn('SyntaxError', answer['why'])
        self.assertFalse(self.isl.reloading)
        self.popen.assert_not_called()

    def test_a_mano_se_vuelve_a_lanzar_el_mismo_proceso(self):
        self.isl.is_service = lambda: False
        with mock.patch.object(app.os, 'execv') as execv:
            self.reply()
        execv.assert_called_once_with(app.LAUNCHER, [app.LAUNCHER])
        self.popen.assert_not_called()



@unittest.skipIf(app is None, 'sin gi: usa /usr/bin/python3')
class Arranque(unittest.TestCase):
    def test_el_codigo_de_la_carpeta_arranca(self):
        # Lo que comprueba `reload` antes de volver a arrancar la isla.
        self.assertEqual(app.Island.reload_check(), '')
        self.assertTrue(os.access(app.LAUNCHER, os.X_OK))


class Familia(unittest.TestCase):
    """Los personajes de `mascot.py`."""

    STATES = ('idle', 'working', 'permission', 'done', 'confused', 'annoyed', 'dizzy', 'sleep')

    def pixels(self, state, **kw):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 300, 320)
        cr = cairo.Context(surface)
        cr.translate(150, 170)
        app.mascot.draw(cr, state, .36, .42, **kw)
        return bytes(surface.get_data())

    def test_cada_uno_tiene_todos_los_gestos(self):
        for role in app.mascot.ROLES:
            for st in self.STATES:
                with self.subTest(role=role, state=st):
                    self.assertTrue(any(self.pixels(st, role=role)))

    def test_cada_uno_se_distingue_de_los_demas(self):
        for st in ('idle', 'working'):
            drawn = {self.pixels(st, role=role) for role in app.mascot.ROLES}
            self.assertEqual(len(drawn), len(app.mascot.ROLES))

    def test_sin_personaje_o_con_uno_desconocido_es_el_engineer(self):
        engineer = self.pixels('working', role='engineer')
        self.assertEqual(self.pixels('working'), engineer)
        self.assertEqual(self.pixels('working', role='Explore'), engineer)

    def test_todos_tienen_sus_capas(self):
        for table in (app.mascot.HATS, app.mascot.PROPS):
            self.assertEqual(set(table), set(app.mascot.ROLES))
        # El engineer usa el color del tema; los demás, el suyo.
        self.assertEqual(set(app.mascot.ACCENTS), set(app.mascot.ROLES) - {'engineer'})
        self.assertEqual(set(state.AGENT_ROLES.values()), set(app.mascot.ACCENTS))
        # Cada uno el suyo, y ninguno el de un aviso: ni rojo, ni verde, ni amarillo.
        colors = list(app.mascot.ACCENTS.values())
        self.assertEqual(len(set(colors)), len(colors))
        self.assertFalse(set(colors) & {app.mascot.COLORS[name] for name in ('red', 'green', 'yellow')})


class Ficha(IslandCase):
    def test_por_el_socket_un_boton_no_corre_comandos(self):
        seen = []
        self.isl.on_message = lambda msg, req: seen.append(msg)
        self.isl.on_socket({'event': 'alert', 'actions': [
            {'label': 'Logs', 'cmd': ['rm', '-rf', '/']}, {'label': 'Abrir', 'url': 'http://x'},
            {'label': 'Ir', 'jump': True}, 'basura']}, None)
        self.assertEqual([a['label'] for a in seen[0]['actions']], ['Abrir', 'Ir'])

    def test_ir_al_pane_salta_y_descarta(self):
        s = self.alert(pane='%3', tmux='/s,1,0', actions=[state.JUMP])
        done = threading.Event()
        with mock.patch.object(app.actions, 'jump', lambda session: done.set()), \
                mock.patch.object(app.actions, 'run') as run:
            self.isl.act(s, 0)
            self.assertTrue(done.wait(2))
        run.assert_not_called()
        self.assertEqual(self.isl.model.sessions, {})

    def test_un_boton_con_comando_lo_corre(self):
        action = {'label': 'Iniciar', 'cmd': ['true'], 'after': 'clear'}
        s = self.alert(actions=[action])
        done = threading.Event()
        with mock.patch.object(app.actions, 'run', lambda a: done.set()):
            self.isl.act(s, 0)
            self.assertTrue(done.wait(2))
        # 'clear' la quita sin silenciarla: puede volver enseguida.
        self.assertEqual(self.isl.model.sessions, {})
        self.assertEqual(self.isl.model.dismissed, {})

    def test_descartar_la_silencia(self):
        s = self.alert(lines=['uno'])
        self.isl.act(s, 'dismiss')
        self.assertIn('x:1', self.isl.model.dismissed)

    def test_sin_ficha_no_hay_botones(self):
        s = self.alert()
        self.isl.act(s, 'dismiss')
        self.assertIn('x:1', self.isl.model.sessions)

    def test_la_de_unas_pruebas_se_ve_sin_pedirla(self):
        self.isl.model.handle({'event': 'cmd-start', 'session_id': 'cmd:%3', 'cwd': '/x/proj',
                               'command': 'make test', 'pane': '%3',
                               'results': {'ran': True, 'passed': 1, 'failed': 1,
                                           'lines': ['✗ resta', '✓ suma']}}, now=T)
        self.isl.refresh()
        self.assertEqual(self.isl.view.mode, 'open')
        height = self.isl.card_h('open')
        self.assertEqual(height, app.PREVIEW_HEAD + 2 * app.CODE_LINE_H + 2 * app.PREVIEW_PAD
                         + app.CARD_BUTTONS)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, app.WIN_W, app.WIN_H)
        self.isl.draw_card(cairo.Context(surface), 20, app.PREVIEW_W, app.OPEN_H, height, 1)
        self.assertEqual(set(self.isl.buttons), {'dismiss', 0})

    def reply_card(self, tint):
        self.isl.model.handle({'event': 'alert', 'session_id': 'chat:s1', 'name': 'proj', 'tone': 'ok',
                               'message': 'terminó', 'where': 'elyares-reviewer', 'note': 'Sonnet 5.5',
                               'tint': tint, 'lines': ['Revisé el PR 12:', '- falta un test', '- el nombre engaña'],
                               'actions': [{'label': 'Ver respuesta', 'chat': 's1'}]}, now=T)
        self.isl.refresh()
        return self.isl.model.sessions['chat:s1']

    def test_la_respuesta_de_un_agente_tiñe_su_ficha_con_su_color(self):
        self.assertEqual(self.reply_card('reviewer').tint, 'reviewer')
        self.assertEqual(self.reply_card('no-existe').tint, '')       # un personaje que no hay: sin tinte
        s = self.reply_card('reviewer')
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, app.WIN_W, app.WIN_H)
        cr = cairo.Context(surface)
        height = app.PREVIEW_HEAD + 3 * app.CODE_LINE_H + 2 * app.PREVIEW_PAD + app.CARD_BUTTONS
        self.isl.draw_card(cr, 20, app.PREVIEW_W, app.OPEN_H, height, 1)
        # La barra del agente, en el borde derecho de la ficha, con el color del reviewer.
        r, g, b, _ = app.mascot.rgba(app.mascot.accent('reviewer'))
        x, y = int(20 + app.PREVIEW_W - 14 - 1), int(app.OPEN_H + 20)
        data = surface.get_data()
        px = surface.get_stride() * y + 4 * x
        blue, green, red = data[px], data[px + 1], data[px + 2]
        self.assertAlmostEqual(red / 255, r, delta=.05)
        self.assertAlmostEqual(green / 255, g, delta=.05)
        self.assertAlmostEqual(blue / 255, b, delta=.05)

    def test_la_ficha_mas_alta_cabe_en_la_ventana(self):
        tallest = (app.PREVIEW_HEAD + state.CARD_LINES * app.CODE_LINE_H + 2 * app.PREVIEW_PAD
                   + app.CARD_BUTTONS)
        self.assertLessEqual(tallest, app.PREVIEW_MAX)

    def test_las_pruebas_de_una_terminal_se_siguen_y_vuelven_con_resultados(self):
        calls = []
        self.isl.tests = mock.Mock()
        self.isl.tests.start.side_effect = lambda msg: calls.append('start') or True
        self.isl.tests.finish.side_effect = lambda msg: calls.append('finish') or True
        self.isl.focus_seen = False
        with mock.patch.object(app.GLib, 'SOURCE_REMOVE', False):
            self.isl.on_message({'event': 'cmd-start', 'session_id': 'cmd:%3', 'pane': '%3'}, None)
            self.assertIn('cmd:%3', self.isl.model.sessions)
            # El final espera a sus resultados: todavía no toca la alerta.
            self.isl.on_message({'event': 'cmd-done', 'session_id': 'cmd:%3', 'pane': '%3'}, None)
            self.assertEqual(self.isl.model.sessions['cmd:%3'].tone, 'run')
            self.isl.on_message({'event': 'cmd-done', 'session_id': 'cmd:%3', 'pane': '%3',
                                 'results': {'ran': True, 'passed': 2}}, None)
        self.assertEqual(self.isl.model.sessions['cmd:%3'].tone, 'ok')
        self.assertEqual(calls, ['start', 'finish'])

    def test_alto_y_dibujo(self):
        self.alert(where='~/proj', note='código 2 · 40 s', lines=['uno', 'dos'],
                   actions=[state.JUMP])
        self.isl.title, self.isl.detail = self.isl.view.title, self.isl.view.detail
        # Solo se ve cuando alguien la está leyendo.
        self.assertEqual(self.isl.card_h('open'), 0)
        self.isl.expanded = True
        height = self.isl.card_h('open')
        self.assertEqual(height, app.PREVIEW_HEAD + 2 * app.CODE_LINE_H + 2 * app.PREVIEW_PAD
                         + app.CARD_BUTTONS)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, app.WIN_W, app.WIN_H)
        self.isl.draw_card(cairo.Context(surface), 20, app.PREVIEW_W, app.OPEN_H, height, 1)
        self.assertEqual(set(self.isl.buttons), {'dismiss', 0})
        # Descartar a la izquierda; el botón de la alerta, a la derecha.
        self.assertLess(self.isl.buttons['dismiss'][0], self.isl.buttons[0][0])
        self.assertEqual(self.isl.card_span, (app.OPEN_H, app.OPEN_H + height))
        # Se pintó algo.
        self.assertTrue(any(surface.get_data()))


class Flujos(IslandCase):
    """Un workflow en marcha: cada paso, en el chat de su agente."""

    def setUp(self):
        super().setUp()
        isdir = mock.patch.object(app.workflowview.os.path, 'isdir', lambda path: path == '/x/proj')
        isdir.start()
        self.addCleanup(isdir.stop)
        W = app.workflowview.workflows
        self.flow = W.Workflow('revisar', '/x/proj', [W.Step('elyares-designer', 'propón'),
                                                      W.Step('elyares-engineer', 'hazlo')])
        self.chats = {}
        self.isl.chat_for = self.chat_for

    def chat_for(self, agent, cwd):
        """El chat de cada agente, de mentira: apunta lo que se le manda."""
        if agent not in self.chats:
            c = mock.Mock(busy=False, agent=agent, cwd=cwd, cut=False, asking=None, session='', model_id='',
                          project='proj', context=0)
            c.name = agent or state.MAIN_AGENT
            c.send.return_value = True
            c.feed.return_value = True
            c.reply.return_value = f'lo de {agent or "engineer"}'
            self.chats[agent] = c
        return self.chats[agent]

    def done(self, agent, **event):
        self.isl.on_chat({'type': 'result', **event}, self.chats[agent])

    def test_cada_paso_va_al_chat_de_su_agente_con_lo_del_anterior(self):
        self.isl.workflow_launch(self.flow)
        run = self.isl.wf_run
        designer = self.chats['elyares-designer']
        designer.send.assert_called_once_with('propón' + app.workflowview.workflows.RULE,
                                              shown='propón\n\n**Paso 1 de 2** · workflow «revisar»', kind='flow')
        self.assertEqual((run.index, self.isl.wf_screen), (0, 'run'))
        self.assertNotIn('', self.chats)                # el engineer aún no sabe nada
        # Lo que llega de otro chat no mueve el workflow.
        self.isl.on_chat({'type': 'result'}, self.chat_for('elyares-auditor', '/x/proj'))
        self.assertEqual(run.index, 0)
        with mock.patch.object(self.isl, 'chat_notice') as notice:
            self.done('elyares-designer')
        notice.assert_not_called()                      # un paso intermedio no avisa: sigue el siguiente
        sent = self.chats[''].send.call_args.args[0]
        shown = self.chats[''].send.call_args.kwargs['shown']
        self.assertTrue(sent.startswith('hazlo'))
        self.assertIn('lo de elyares-designer', sent)
        # En el chat se ve la instrucción y de qué paso es, no las reglas para el agente.
        self.assertIn('Recibe lo que dejó el paso 1 (**elyares-designer**)', shown)
        self.assertNotIn('PASO FALLIDO', shown)
        self.assertEqual(run.index, 1)
        self.done('')
        self.assertTrue(run.done)
        self.assertIsNone(run.failed)
        # Con el panel cerrado, un aviso que lo abre en la ejecución.
        alert = self.isl.model.sessions['workflow:revisar']
        self.assertIn('terminó', alert.detail)
        self.isl.open_workflows = mock.Mock()
        self.isl.expanded = True
        self.isl.refresh()
        self.isl.act(alert, 0)
        self.isl.open_workflows.assert_called_once_with('run')

    def test_si_un_paso_falla_se_queda_ahi_y_se_reintenta(self):
        self.isl.workflow_launch(self.flow)
        run = self.isl.wf_run
        self.done('elyares-designer', is_error=True, result='sin red')
        self.assertEqual((run.failed, run.running), (0, False))
        self.assertNotIn('', self.chats)
        self.assertEqual(self.isl.workflow_trouble(0), 'El paso 1 (elyares-designer) falló: sin red.')
        self.assertEqual(self.isl.model.sessions['workflow:revisar'].tone, 'bad')
        self.isl.workflow_step(0)                       # «Reintentar paso 1»
        self.assertEqual(self.chats['elyares-designer'].send.call_count, 2)
        self.done('elyares-designer')
        self.assertEqual(run.index, 1)

    def test_si_el_agente_dice_que_no_salio_el_paso_falla(self):
        self.isl.workflow_launch(self.flow)
        run = self.isl.wf_run
        self.chats['elyares-designer'].reply.return_value = 'No pude.\n\nPASO FALLIDO: develop no está al día.'
        self.done('elyares-designer')                   # el turno acabó sin error, pero el paso no salió
        self.assertEqual((run.failed, run.running), (0, False))
        self.assertNotIn('', self.chats)                # el siguiente no corre
        self.assertEqual(self.isl.workflow_trouble(0),
                         'El paso 1 (elyares-designer) no salió: develop no está al día.')

    def test_un_agente_ocupado_no_empieza_y_con_seguir_pasa_al_siguiente(self):
        self.chat_for('elyares-designer', '/x/proj').busy = True
        self.isl.workflow_launch(self.flow)
        run = self.isl.wf_run
        self.chats['elyares-designer'].send.assert_not_called()
        self.assertEqual(run.why[0], 'no pudo empezar: está ocupado con otro turno')
        self.assertFalse(run.running)
        self.flow.on_fail = app.workflowview.workflows.GO
        self.isl.workflow_launch(self.flow)
        run = self.isl.wf_run
        self.assertEqual((run.failed, run.index), (0, 1))
        self.chats[''].send.assert_called_once_with('hazlo' + app.workflowview.workflows.RULE,
                                                    shown='hazlo\n\n**Paso 2 de 2** · workflow «revisar»', kind='flow')

    def test_detener_corta_el_turno_y_no_sigue(self):
        self.isl.workflow_launch(self.flow)
        run = self.isl.wf_run
        self.isl.workflow_launch(self.flow)             # con uno en curso, otro no arranca
        self.assertIs(self.isl.wf_run, run)
        self.isl.workflow_stop()
        designer = self.chats['elyares-designer']
        designer.interrupt.assert_called_once_with()
        designer.cut = True
        self.done('elyares-designer')
        self.assertEqual((run.running, run.status()), (False, 'Lo detuviste.'))
        self.assertNotIn('', self.chats)
        self.assertNotIn('workflow:revisar', self.isl.model.sessions)     # lo paraste tú: no hay aviso

    def test_el_de_cualquier_proyecto_corre_donde_estas(self):
        self.flow.project = ''
        P = app.projectview.projects.Project
        self.isl.projects = [P('proj', '/x/proj', here=True, session='proj'), P('otro', '/x/otro')]
        self.isl.workflow_launch(self.flow)
        self.assertEqual(self.isl.wf_run.w.project, '/x/proj')
        self.assertEqual(self.chats['elyares-designer'].cwd, '/x/proj')
        self.assertEqual(self.flow.project, '')         # el guardado sigue sin proyecto: vale para el siguiente
        # Sin tmux ni chat no hay dónde: lo dice y no empieza.
        self.isl.projects, self.isl.wf_run = [], None
        self.isl.workflow_launch(self.flow)
        self.assertEqual(self.isl.wf_run.why[0],
                         'no pudo empezar: no estás en ningún proyecto; entra a uno en tmux o abre su chat')

    def test_sin_la_carpeta_del_proyecto_no_empieza(self):
        self.flow.project = '/x/borrado'
        self.isl.workflow_launch(self.flow)
        self.assertEqual(self.chats, {})
        self.assertEqual(self.isl.wf_run.why[0], 'no pudo empezar: la carpeta del proyecto ya no existe')

    def test_guardar_y_lanzar_y_lo_que_no_se_pudo_guardar(self):
        W = app.workflowview.workflows
        self.isl.wf_draft, self.isl.wf_screen = W.Draft(self.flow), 'edit'
        self.isl.wf_draft.saved_as = None               # como uno nuevo
        self.isl.workflows_save(launch=True)
        W.save.assert_called_once()
        self.assertEqual([w.name for w in self.isl.workflows], ['revisar'])
        self.assertTrue(self.isl.wf_run.running)
        self.assertIsNone(self.isl.wf_draft)
        # Si no se puede guardar, lo dice con su referencia y los pasos siguen ahí.
        draft = self.isl.wf_draft = W.Draft(project='/x/proj')
        draft.w.name = 'otro'
        draft.add()
        with mock.patch.object(W, 'save', side_effect=PermissionError(13, 'no')):
            self.isl.workflows_save()
        what, ref, again = self.isl.wf_error
        self.assertEqual((what, ref), ('No pudimos guardar «otro». Tus pasos siguen aquí; vuelve a intentarlo.',
                                       'EACCES'))
        self.assertIs(self.isl.wf_draft, draft)
        self.assertEqual([w.name for w in self.isl.workflows], ['revisar'])
        again()                                         # «Reintentar»
        self.assertIsNone(self.isl.wf_error)
        self.assertEqual([w.name for w in self.isl.workflows], ['revisar', 'otro'])

    def test_cerrar_no_pierde_lo_que_se_edita_y_cancelar_pregunta(self):
        W = app.workflowview.workflows
        self.isl.open_workflows()
        self.assertTrue(self.isl.wf_open)
        self.isl.on_wf_hit('new')
        draft = self.isl.wf_draft
        self.isl.wf_typed('a medias')                   # se escribe en el campo del nombre
        self.assertEqual((self.isl.wf_field, draft.w.name), ('name', 'a medias'))
        # Cerrar la isla de los flujos no pierde nada: al volver, ahí sigue. Y el chat es aparte.
        self.isl.on_wf_hit('close')
        self.assertFalse(self.isl.wf_open)
        self.isl.open_chat()
        self.assertTrue(self.isl.chat_open)
        self.isl.toggle_workflows()
        self.assertTrue(self.isl.chat_open and self.isl.wf_open)    # conviven
        self.assertEqual((self.isl.target(), self.isl.wf_screen), ('chat', 'edit'))
        self.assertIs(self.isl.wf_draft, draft)
        # Cancelar sí lo pierde: antes pregunta.
        self.isl.on_wf_hit('cancel')
        self.assertEqual(self.isl.wf_confirm, ('discard', None))
        self.isl.on_wf_hit('keep')                      # «Seguir editando»
        self.assertIs(self.isl.wf_draft, draft)
        self.isl.on_wf_hit('cancel')
        self.isl.on_wf_hit('confirm')                   # «Descartar cambios»
        self.assertEqual((self.isl.wf_draft, self.isl.wf_screen), (None, 'list'))
        # Sin cambios, cancelar no pregunta.
        self.isl.workflows = [self.flow]
        self.isl.on_wf_hit('edit:0')
        self.isl.on_wf_hit('cancel')
        self.assertEqual((self.isl.wf_confirm, self.isl.wf_screen), (None, 'list'))
        self.assertEqual(W.save.call_count, 0)

    def test_el_editor_con_clics_y_teclas(self):
        self.isl.open_workflows()
        self.isl.on_wf_hit('new')
        draft = self.isl.wf_draft
        self.isl.wf_typed('revisar')
        self.isl.on_wf_hit('add')                       # el paso nuevo, listo para escribir
        self.assertEqual(self.isl.wf_field, 0)
        self.isl.wf_typed('propón\nla pantalla')        # un campo va en una línea
        self.assertEqual(draft.w.steps[0].text, 'propón la pantalla')
        self.isl.on_wf_hit('agent:0')
        self.assertEqual((self.isl.wf_menu, self.isl.wf_field), (('agent', 0), None))
        self.isl.on_wf_hit(f'pick:{app.workflowview.AGENTS.index("elyares-designer")}')
        self.assertEqual((draft.w.steps[0].agent, self.isl.wf_menu), ('elyares-designer', None))
        self.isl.on_wf_hit('add')
        self.isl.wf_typed('hazlo')
        self.isl.on_wf_hit('up:1')
        self.assertEqual([s.text for s in draft.w.steps], ['hazlo', 'propón la pantalla'])
        self.isl.on_wf_hit('fail:go')
        self.assertEqual(draft.w.on_fail, 'go')
        # Tab y Enter pasan al campo que sigue; Shift+Tab, al anterior; Esc suelta.
        Gdk = app.Gdk
        self.isl.on_wf_hit('field:name')
        self.isl.on_wf_key(Gdk.KEY_Tab, False)
        self.assertEqual(self.isl.wf_field, 0)
        self.isl.on_wf_key(Gdk.KEY_Return, False)
        self.assertEqual(self.isl.wf_field, 1)
        self.isl.on_wf_key(Gdk.KEY_ISO_Left_Tab, True)
        self.assertEqual(self.isl.wf_field, 0)
        self.isl.on_wf_key(Gdk.KEY_Escape, False)
        self.assertIsNone(self.isl.wf_field)
        self.isl.on_wf_hit('drop:0')
        self.assertEqual(len(draft.w.steps), 1)
        # No se pasa de los pasos que caben en la isla.
        for _ in range(20):
            self.isl.on_wf_hit('add')
        self.assertEqual(len(draft.w.steps), app.workflowview.WF_MAX_STEPS)


class FlujosDibujo(IslandCase):
    """La isla de los flujos, dibujada fuera de pantalla junto a la de siempre."""

    WIDTH = 1920                    # la pantalla

    def setUp(self):
        super().setUp()
        W = app.workflowview.workflows
        self.flow = W.Workflow('revisar', '/x/proj', [W.Step('elyares-designer', 'propón'),
                                                      W.Step('elyares-engineer', 'hazlo')])
        isl = self.isl
        isl.screen_w, isl.w, isl.h = self.WIDTH, 600, 88        # la isla de siempre, abierta
        isl.colors = paint.colors()
        isl.markups = {}
        isl.pointer = None
        isl.da = mock.Mock(get_width=lambda: app.WIN_W)
        isl.pills, isl.card_span, isl.go = [], None, mock.Mock()
        self.shown = []
        layout = isl._layout
        isl._layout = lambda cr, text, *a, **kw: self.shown.append(text) or layout(cr, text, *a, **kw)
        self.cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, self.WIDTH, app.workflowview.WF_WIN_H))

    def draw(self):
        """La isla de los flujos ya asentada en su tamaño, dibujada."""
        isl = self.isl
        isl.fw, isl.fh = isl.flows_goal() if isl.wf_open else (isl.fw, 0)
        self.shown.clear()
        isl.flows_draw(None, self.cr, self.WIDTH, 0)
        return isl.wf_hits

    def click(self, key):
        """Un clic de verdad en lo que quedó dibujado con esa clave."""
        isl = self.isl
        isl.flows_da = mock.Mock(get_width=lambda: self.WIDTH)
        if f'wf-{key}' in isl.wf_buttons:
            x, y, w, h = isl.wf_buttons[f'wf-{key}']
        else:
            _, _, x, y, w, h = next(hit for hit in isl.wf_hits if hit[:2] == ('wf', key))
        isl.on_flows_click(None, 1, x + w / 2, y + h / 2)

    def test_sale_a_la_izquierda_de_la_isla_y_del_otro_lado_si_no_cabe(self):
        isl = self.isl
        isl.open_workflows()
        isl.fw, isl.fh = isl.flows_goal()
        win_left = (self.WIDTH - app.WIN_W) / 2
        ix0, iw, _ = isl.island_rect(app.WIN_W)
        # Con la isla en el centro: a su izquierda, pegada, y de su misma altura de arriba.
        x0, w, h = isl.flows_rect(self.WIDTH)
        self.assertEqual((isl.wf_side, w), ('left', app.workflowview.WF_W))
        self.assertEqual(x0 + w + app.workflowview.WF_GAP, win_left + ix0)
        # Corrida hasta la izquierda de la pantalla: no cabe, sale a su derecha.
        isl.settings['position'] = 0
        x0, w, h = isl.flows_rect(self.WIDTH)
        self.assertEqual(isl.wf_side, 'right')
        self.assertEqual(x0, isl.offset() + ix0 + iw + app.workflowview.WF_GAP)
        isl.settings['position'] = 25
        isl.flows_rect(self.WIDTH)
        self.assertEqual(isl.wf_side, 'right')
        # Corrida a la derecha sí cabe a su izquierda.
        for position in (75, 100):
            isl.settings['position'] = position
            isl.flows_rect(self.WIDTH)
            self.assertEqual(isl.wf_side, 'left')
        # Colapsada o creciendo no cambia de lado: se decide con la ventana de la isla.
        isl.settings['position'] = 25
        isl.fw = app.workflowview.WF_PILL_W
        isl.flows_rect(self.WIDTH)
        self.assertEqual(isl.wf_side, 'right')
        # Nunca se sale de la pantalla.
        isl.settings['position'] = 0
        isl.fw = app.workflowview.WF_W
        x0, w, _ = isl.flows_rect(1100)
        self.assertTrue(0 <= x0 and x0 + w <= 1100)

    def test_se_abre_con_su_pastilla_sin_tocar_la_isla(self):
        isl = self.isl
        isl.expanded = True
        before = isl.target()
        isl.pills, isl.tip = [], None
        isl.tip_key, isl.tip_ref, isl.tip_last = None, [], None
        isl.tip_pop, isl.tip_at, isl.tip_cx = 0.0, 0.0, None
        isl.sources = {key: {'ok': True, 'note': '', 'tip': [], 'since': 0, 'polled': 0} for key in sources.LABELS}
        isl.draw_pills(self.cr, 100, 560, 50, 1.0)
        _, x, y, w, h = next(pill for pill in isl.pills if pill[0] == app.workflowview.WF_PILL)
        isl.on_click(None, 1, x + w / 2, y + h / 2)
        self.assertTrue(isl.wf_open)
        self.assertEqual(isl.target(), before)                          # la isla de siempre sigue igual
        self.assertEqual(isl.flows_goal(), (app.workflowview.WF_W, isl.workflows_goal()[1]))
        self.draw()
        self.assertIn('Crear workflow', self.shown)
        self.assertTrue(any('Todavía no guardaste ningún workflow' in text for text in self.shown))
        self.click('new')
        self.draw()
        for text in ('Nuevo workflow', 'Nombre', 'Proyecto', 'Pasos', 'Añadir primer paso', 'Si un paso falla',
                     'Añade al menos un paso para lanzarlo', 'Guardar y lanzar'):
            self.assertIn(text, self.shown)
        self.assertIsNotNone(isl.wf_box)                # la caja de texto, sobre el campo del nombre
        self.click('close')
        self.assertFalse(isl.wf_open)
        self.assertEqual(isl.flows_goal()[1], 0)        # se encoge hasta irse

    def test_se_colapsa_en_una_pastilla_y_se_abre_con_un_clic(self):
        isl = self.isl
        isl.workflows = [self.flow]
        isl.open_workflows()
        self.draw()
        self.assertIn('colapsar ›', self.shown)         # a la izquierda se colapsa hacia la isla
        self.click('collapse')
        self.assertTrue(isl.wf_collapsed)
        self.assertTrue(isl.settings['flows_collapsed'])        # se acuerda
        self.saved.assert_called()
        self.assertEqual(isl.flows_goal(), (app.workflowview.WF_PILL_W, app.workflowview.WF_PILL_H))
        self.draw()
        self.assertIn('Flujos', self.shown)
        self.assertIn('1', self.shown)                  # cuántos guardados hay
        self.assertNotIn('lanzar ›', self.shown)
        # Con algo corriendo, la pastilla lo dice.
        isl.wf_run = run = app.workflowview.workflows.Run(self.flow)
        run.begin(0)
        self.draw()
        self.assertIn('paso 1/2', self.shown)
        # Un clic en cualquier parte de ella la abre.
        isl.flows_da = mock.Mock(get_width=lambda: self.WIDTH)
        x0, w, h = isl.flows_rect(self.WIDTH)
        isl.on_flows_click(None, 1, x0 + w / 2, h / 2)
        self.assertFalse(isl.wf_collapsed)
        self.assertFalse(isl.settings['flows_collapsed'])
        # Un clic fuera de la isla no hace nada.
        isl.wf_collapse(True)
        self.draw()
        isl.on_flows_click(None, 1, 5, 5)
        self.assertTrue(isl.wf_collapsed)

    def test_un_aviso_abre_la_isla_colapsada_para_verlo(self):
        isl = self.isl
        isl.wf_collapsed = True
        isl.wf_run = app.workflowview.workflows.Run(self.flow)
        isl.open_workflows('run')
        self.assertFalse(isl.wf_collapsed)
        self.assertEqual(isl.wf_screen, 'run')

    def test_lo_que_manda_un_workflow_se_ve_en_markdown(self):
        isl = self.isl
        c = app.chatview.chat.Chat('/x/proj', lambda ev: None, spawn=mock.Mock())
        E = app.chatview.chat.Entry
        c.entries = [E('flow', 'ejecuta /pr\n\n**Paso 2 de 4** · workflow «close-work»\n\n'
                               'Recibe lo que dejó el paso 1 (**elyares-devops**):\n\n- un `commit` nuevo'),
                     E('foot', 'x')]
        isl.chat, isl.chat_open = c, True
        isl.chat_cache = {}
        layout, _, _ = isl.chat_layout(self.cr, 0, c.entries[0], 560)
        markup = layout.get_attributes()
        self.assertIsNotNone(markup)                    # tiene negritas y código: no es texto plano
        self.assertIn('•', layout.get_text())            # la viñeta, no el guion
        self.assertNotIn('**', layout.get_text())
        self.assertNotIn('`', layout.get_text())
        # Lo que escribes tú sigue siendo texto tal cual.
        plain, _, _ = isl.chat_layout(self.cr, 1, E('you', 'haz **esto**'), 560)
        self.assertIn('**', plain.get_text())
        # «copiar» de la respuesta de un agente no se lleva lo que mandó el workflow.
        c.entries = [E('flow', 'x'), E('claude', 'hecho'), E('foot', 'y')]
        self.assertEqual(isl.chat_reply_at(2), 'hecho')

    def test_la_lista_el_editor_y_sus_menus(self):
        isl = self.isl
        isl.workflows = [self.flow]
        isl.open_workflows()
        self.draw()
        for text in ('Workflows', '1 guardado', 'revisar', 'lanzar ›', 'editar', 'borrar'):
            self.assertIn(text, self.shown)
        short = isl.workflows_goal()[1]
        self.click('delete:0')
        self.draw()
        self.assertIn('¿Borrar el workflow «revisar» y sus 2 pasos? No se puede deshacer.', self.shown)
        self.assertGreater(isl.workflows_goal()[1], short)         # la isla crece para la pregunta
        self.click('keep')
        self.assertEqual(isl.workflows, [self.flow])
        self.draw()
        self.click('edit:0')
        self.draw()
        for text in ('Editar workflow', 'elyares-designer', 'propón', '+ Añadir paso'):
            self.assertIn(text, self.shown)
        self.assertNotIn('Sin guardar', self.shown)
        # El menú de agentes sale encima de lo demás, y un clic en uno lo elige.
        self.click('agent:1')
        self.draw()
        self.assertTrue(isl.wf_hits[0][1].startswith('pick:'))
        self.click(f'pick:{app.workflowview.AGENTS.index("elyares-reviewer")}')
        self.assertEqual(isl.wf_draft.w.steps[1].agent, 'elyares-reviewer')
        self.draw()
        self.assertIn('Sin guardar', self.shown)
        # Un nombre repetido lo dice, y no deja guardar.
        isl.workflows.append(app.workflowview.workflows.Workflow('otro', '/x/proj'))
        isl.wf_draft.w.name = 'Otro'
        self.draw()
        self.assertIn('Ya existe un workflow con ese nombre. Elige otro.', self.shown)
        self.click('save')
        self.assertEqual(isl.wf_screen, 'edit')

    def test_la_ejecucion_dice_como_va_cada_paso(self):
        isl = self.isl
        isl.wf_run = run = app.workflowview.workflows.Run(self.flow)
        run.begin(0)
        run.finish(True, 'un panel')
        run.begin(1)
        isl.open_workflows()
        self.assertEqual(isl.wf_screen, 'run')
        self.draw()
        for text in ('revisar', '✓', '●', 'elyares-engineer', 'hazlo', 'Corriendo el paso 2 de 2…', 'Detener'):
            self.assertIn(text, self.shown)
        run.finish(False, why='falló: sin red')
        self.draw()
        self.assertIn('✗', self.shown)
        self.assertIn('El paso 2 (elyares-engineer) falló: sin red. Ábrelo y reintenta desde ese paso.', self.shown)
        self.assertIn('Reintentar paso 2', self.shown)
        isl.workflow_step = mock.Mock()
        self.click('retry')
        isl.workflow_step.assert_called_once_with(1)
        isl.open_chat = mock.Mock()
        self.click('chat')
        isl.open_chat.assert_called_once_with(typing=True, agent='', cwd='/x/proj')

    def test_en_vidrio_la_isla_se_lee_igual(self):
        isl = self.isl
        isl.workflows = [self.flow]
        isl.open_workflows()
        isl.settings['glass'] = True
        shadows = []
        tip_text = isl.tip_text
        isl.tip_text = lambda cr, layout, x, y, color, alpha, shadow: (
            shadows.append(shadow), tip_text(cr, layout, x, y, color, alpha, shadow))[1]
        self.draw()
        # Cada texto lleva su sombra, y sigue estando todo lo de siempre.
        self.assertTrue(shadows and all(shadows))
        for text in ('Workflows', 'revisar', 'lanzar ›', 'editar', 'borrar'):
            self.assertIn(text, self.shown)
        self.click('edit:0')
        self.draw()
        self.click('agent:0')
        shadows.clear()
        self.draw()
        self.assertTrue(shadows and all(shadows))
        # Sin vidrio, ninguna.
        isl.settings['glass'] = False
        shadows.clear()
        self.draw()
        self.assertFalse(any(shadows))

    def test_la_isla_de_siempre_no_pierde_sus_clics(self):
        isl = self.isl
        isl.hits, isl.buttons, isl.pointer = [('chat', 'x', 0, 0, 1, 1)], {'allow': (0, 0, 1, 1)}, (3, 4)
        isl.open_workflows()
        isl.wf_pointer = (500, 20)
        self.draw()
        # Dibujar la de los flujos deja lo pulsable de cada una en su sitio.
        self.assertEqual((isl.hits, isl.buttons, isl.pointer), ([('chat', 'x', 0, 0, 1, 1)], {'allow': (0, 0, 1, 1)}, (3, 4)))
        self.assertTrue(isl.wf_hits)


if __name__ == '__main__':
    unittest.main()
