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
    from elyares import app, commands, paint, settings, sources
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
        isl.pin, isl.pointer, isl.buttons = '', None, {}
        isl.tab, isl.focus, isl.hits, isl.rows = '', None, [], []
        isl.look, isl.blink_until = [0.0, 0.0], 0.0
        isl.key_since = T
        isl.refresh = lambda: setattr(isl, 'view', isl.model.view(now=T, pin=isl.pin))
        isl.collapse_id = 0
        isl.check_panes = lambda: None
        isl.monitor = None
        isl.chat_init()
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
        self.assertEqual(keys, [key for key, _ in sources.SOURCES] + [app.CHAT_PILL, commands.HELP])
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
        for text in ('elyares-auditor', 'Ejecutando gitleaks git', 'esperando', 'libre'):
            self.assertIn(text, self.shown)
        self.assertNotIn('elyares-engineer', self.shown)

    def test_mide_lo_mismo_trabajen_uno_dos_o_los_cuatro(self):
        self.isl.expanded = True
        sizes, front = set(), []
        for kinds in ((), ('elyares-reviewer',), ('elyares-architect', 'elyares-auditor', 'elyares-reviewer')):
            self.isl.model.sessions.clear()
            self.work('a', *kinds)
            sizes.add(self.isl.goal())
            self.draw()
            front.append(len(self.hit('member')))
        self.assertEqual(front, [1, 2, 4])
        self.assertEqual(len(sizes), 1)
        # En reposo, los cuatro en fila y ninguno se abre.
        self.send('stop', now=T + 1)
        self.isl.refresh = lambda: setattr(self.isl, 'view', self.isl.model.view(
            now=T + 60, pin=self.isl.pin))
        for kind in ('architect', 'auditor', 'reviewer'):
            self.send('agent-stop', agent_id=f'a-elyares-{kind}')
        self.draw()
        self.assertEqual(self.hit('member'), [])
        self.assertEqual(self.shown.count('libre'), 3)

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
        patcher = mock.patch.object(app.chatview.chat, 'active_cwd', lambda: '/x/proj')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.isl.ensure_tick = lambda: None
        self.isl.expand = mock.Mock()

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

    def test_al_terminar_avisa_con_el_principio_de_la_respuesta(self):
        c = self.conversation()
        self.isl.chat_open = False
        c.session, c.busy = 's-chat', True
        c.entries.append(app.chatview.chat.Entry('claude', '## Hecho\nLas **22** pruebas pasan.'))
        self.isl.on_chat({'type': 'result', 'subtype': 'success', 'duration_ms': 1000})
        alert = self.isl.model.sessions['chat:s-chat']
        self.assertIn('ver respuesta', alert.detail)
        self.assertEqual(alert.lines, ['Hecho', 'Las 22 pruebas pasan.'])
        # Su botón abre el chat, y el aviso se va.
        self.isl.act(alert, 0)
        self.assertTrue(self.isl.chat_open)
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
        self.assertIs(self.isl.chats[''], engineer)

    def test_con_la_orden_y_desde_el_tablero_se_le_habla_a_uno(self):
        self.isl.on_control('chat', {'control': 'chat', 'agent': 'reviewer'})
        self.assertEqual(self.isl.chat.agent, 'elyares-reviewer')
        self.isl.close_chat()
        self.isl.on_hit('talk', 'elyares-auditor')
        self.assertTrue(self.isl.chat_open)
        self.assertEqual(self.isl.chat.agent, 'elyares-auditor')

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
        self.assertEqual(self.hit('brief'), [('a', 'architect'), ('a', 'reviewer')])   # las caritas libres

    def brief(self, role='auditor', text='audita el diff'):
        """Un clic en uno de los tres, libre, y un encargo en su mini chat."""
        self.isl.expanded = True
        self.draw()
        self.isl.on_hit('brief', ('a', role))
        self.isl.chat_text = lambda: text
        self.isl.on_chat_enter()
        return self.isl.chats.get(f'elyares-{role}')

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
        self.assertEqual(self.hit('brief'), [('a', 'architect'), ('a', 'auditor'), ('a', 'reviewer')])
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
        self.assertEqual(self.isl.chat_hosts, {'elyares-auditor': 'a'})
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
        self.assertEqual(self.hit('brief'), [('a', 'architect')])

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

    def test_ocupado_en_otro_proyecto_no_se_le_encarga_aqui(self):
        send = self.sending()
        self.work('a')
        self.work('b')
        self.isl.tab = 'a'
        c = self.brief()
        # Desde la pestaña de otro proyecto, mientras sigue con lo de este.
        self.isl.tab = 'b'
        self.draw()
        self.isl.on_hit('brief', ('b', 'auditor'))
        self.isl.on_chat_enter()
        self.assertEqual(send.call_count, 1)
        self.assertEqual(self.isl.chat_hosts, {'elyares-auditor': 'a'})
        self.draw()
        self.assertIn('ocupado en a: aquí, cuando acabe', self.shown)
        # Cuando acaba, sí: con una conversación nueva en la carpeta de aquí.
        c.busy, c.close = False, mock.Mock()
        self.isl.on_chat_enter()
        other = self.isl.chats['elyares-auditor']
        self.assertIsNot(other, c)
        c.close.assert_called_once_with()
        self.assertEqual((other.cwd, self.isl.chat_hosts), ('/x/b', {'elyares-auditor': 'b'}))

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
        c = self.isl.chats[''] = self.conversation()
        c.session, c.tokens, c.window = 's-chat', 88000, 1000000
        self.send('start', 's-chat', cwd='/x/proj')
        aud = self.isl.chat_for('elyares-auditor', '/x/proj')
        aud.session = 's-aud'
        self.isl.chat_hosts = {'elyares-auditor': 's-chat', 'elyares-reviewer': 's-ido'}
        self.isl.chat_save()
        saved = self.save_chats.call_args[0][0]
        self.isl.chat_save()
        self.save_chats.assert_called_once()        # sin cambios no se vuelve a escribir
        # Otra isla, recién arrancada, con las mismas sesiones.
        other = app.Island.__new__(app.Island)
        other.model, other.settings = self.isl.model, self.isl.settings
        other.chat_init()
        other.chat_restore(json.loads(json.dumps(saved)))
        self.assertEqual(sorted(other.chats), ['', 'elyares-auditor'])
        back = other.chat
        self.assertEqual((back.agent, back.cwd, back.session, back.context), ('', '/x/proj', 's-chat', 8.8))
        self.assertEqual([(e.kind, e.text) for e in back.entries], [(e.kind, e.text) for e in c.entries])
        self.assertIsNone(back.proc)
        self.assertTrue(other.chat_open)                        # estaba abierto: sigue abierto
        self.assertFalse(other.chat_typing)                     # pero sin tomar el teclado
        self.assertEqual(other.chat_sessions, {'s-chat', 's-aud'})
        self.assertEqual(other.chat_hosts, {'elyares-auditor': 's-chat'})   # el otro encargo ya no tiene a quién
        # Lo guardado a medias o roto no tumba el arranque.
        for bad in ({}, {'chats': 'x', 'hosts': []}, {'chats': [{}, 3, {'cwd': 7}], 'current': 9}):
            other.chat_init()
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
        self.isl.chats[''] = self.isl.chat = self.c

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
    """Los cuatro personajes de `mascot.py`."""

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


if __name__ == '__main__':
    unittest.main()
