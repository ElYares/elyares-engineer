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
        isl.tab, isl.focus, isl.hits, isl.rows = '', None, [], []
        isl.look, isl.blink_until = [0.0, 0.0], 0.0
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

class Tablero(IslandCase):
    """Abierta a mano: una pestaña por sesión y, dentro, sus cuatro."""

    def setUp(self):
        super().setUp()
        isl = self.isl
        isl.sources = {key: {'ok': True, 'note': '', 'tip': [], 'since': 0, 'polled': 0}
                       for key in sources.LABELS}
        isl.pills, isl.tip, isl.card_span = [], None, None
        isl.tip_key, isl.tip_since, isl.tip_ref = None, 0.0, []
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
