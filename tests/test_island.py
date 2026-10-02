"""La isla sin pantalla: contestar un permiso con el teclado, los botones de
una ficha y su dibujo sobre una superficie de cairo.

Necesita gi (GTK 4 y gtk4-layer-shell), que solo trae el python del sistema:
con otro python estas pruebas se saltan. No abre ninguna ventana: la isla se
arma con `Island.__new__` y solo lo que cada prueba usa.
"""

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
        isl.key_since = T
        isl.refresh = lambda: setattr(isl, 'view', isl.model.view(now=T, pin=isl.pin))
        isl.collapse_id = 0
        isl.check_panes = lambda: None
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

    def test_al_irse_el_raton_suelta_la_alerta_elegida_en_la_lista(self):
        self.alert(lines=['uno'])
        self.isl.toggle_pinned()
        self.isl.pin = 'x:1'
        self.isl.set_hover(False)
        self.assertEqual(self.isl.pin, '')
        self.assertTrue(self.isl.expanded)

    def test_un_permiso_sigue_mostrando_sus_botones(self):
        self.isl.toggle_pinned()
        self.ask()
        self.assertEqual(self.isl.target(), 'ask')

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
        self.isl.tip_key, self.isl.tip_since, self.isl.tip_ref = None, 0.0, []
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
        self.assertEqual(keys, [key for key, _ in sources.SOURCES] + [commands.HELP])
        for (_, x, _, w, _), (_, nx, *_) in zip(self.isl.pills, self.isl.pills[1:]):
            self.assertLessEqual(x + w, nx)
        self.assertLessEqual(self.isl.pills[-1][1] + self.isl.pills[-1][3], 100 + width - 18)

    def test_la_de_los_atajos_no_se_apaga_con_un_clic(self):
        self.assertNotIn(commands.HELP, sources.PREFIXES)
        self.assertNotIn(commands.HELP, self.isl.settings)

    def test_la_burbuja_de_una_fuente_trae_sus_comandos(self):
        title, rows = self.bubble('coffe')
        self.assertEqual(title, 'coffe')
        self.assertEqual(rows[0][:2], ('text', 'Pomodoro: modo foco y descansos'))
        self.assertIn(('head', 'Comandos'), rows)
        self.assertTrue(any(r[0] == 'cmd' and r[1] == 'coffe pause' for r in rows))
        # Una fuente sin comandos se queda como estaba.
        self.assertTrue(all(r[0] == 'text' for r in self.bubble('github')[1]))

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

    def test_una_de_segundo_plano_lleva_su_marca_en_la_lista(self):
        shown = []
        layout = self.isl._layout
        self.isl._layout = lambda cr, text, *a, **kw: shown.append(text) or layout(cr, text, *a, **kw)
        for sid, extra in (('a', {}), ('b', {'kind': 'bg'})):
            self.isl.model.handle({'event': 'start', 'session_id': sid, 'cwd': '/x/proj', **extra}, now=T)
        self.isl.refresh()
        self.isl.rows = []
        self.isl.draw_rows(self.cr, 100, 440, app.OPEN_H, 1.0)
        self.assertEqual(len(self.isl.rows), 1)
        self.assertEqual(shown.count(app.BG_TAG), 1 if self.isl.rows[0][0].kind == 'bg' else 0)
        self.isl.view.others = list(self.isl.model.sessions.values())
        shown.clear()
        self.isl.draw_rows(self.cr, 100, 440, app.OPEN_H, 1.0)
        self.assertEqual(shown.count(app.BG_TAG), 1)

    def test_la_ventana_cabe_en_un_monitor_de_1080(self):
        self.assertLessEqual(app.WIN_H, 1080 - 30)


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
