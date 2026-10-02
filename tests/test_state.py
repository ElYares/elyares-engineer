"""El modelo: qué hace cada evento con las sesiones y qué muestra la isla."""

import os
import time
import unittest
from unittest import mock

from elyares import state
from elyares.state import Model

T = 1000.0      # un "ahora" fijo: el modelo recibe el reloj por parámetro
CWD = '/x/proj'


class FakeReq:
    """El hook que espera respuesta, sin socket."""

    def __init__(self):
        self.done = False
        self.born = time.time()
        self.answers = []

    def reply(self, answer):
        self.done = True
        self.answers.append(answer)


class ModelCase(unittest.TestCase):
    def setUp(self):
        # Sin git: la raíz del proyecto es la carpeta tal cual.
        patcher = mock.patch.object(state, 'project_root', lambda cwd: cwd)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.m = Model()

    def send(self, event, now=T, req=None, sid='a', **extra):
        self.m.handle({'event': event, 'session_id': sid, 'cwd': CWD, **extra}, req, now=now)

    def alert(self, sid='x:1', now=T, **extra):
        self.m.handle({'event': 'alert', 'session_id': sid, 'name': 'api',
                       'message': 'se rompió', **extra}, now=now)


class Sessions(ModelCase):
    def test_start_asoma_trabajando(self):
        self.send('start')
        v = self.m.view(now=T)
        self.assertEqual((v.mode, v.pet, v.title, v.detail), ('peek', 'working', 'proj', 'Pensando…'))
        self.assertEqual(v.count, 1)

    def test_tool_dice_que_hace(self):
        self.send('tool', tool_name='Bash', tool_input={'command': 'ls -la\necho fin'})
        self.assertEqual(self.m.view(now=T).detail, 'Ejecutando ls -la')
        self.send('tool', tool_name='Read', tool_input={'file_path': '/x/proj/src/a.py'})
        self.assertEqual(self.m.view(now=T).detail, 'Leyendo src/a.py')

    def test_stop_abre_y_luego_reposa(self):
        self.send('start')
        self.send('stop', now=T + 5)
        v = self.m.view(now=T + 5)
        self.assertEqual((v.mode, v.pet, v.detail), ('open', 'done', 'Listo en 5 s'))
        v = self.m.view(now=T + 5 + state.DONE_OPEN_SECS + 1)
        self.assertEqual(v.mode, 'hidden')
        # En reposo no asoma la isla, pero sigue en la lista.
        self.assertEqual([s.sid for s in v.others], ['a'])

    def test_stop_de_un_subagente_no_termina_el_turno(self):
        self.send('start')
        self.send('stop', now=T + 5, agent_id='sub1')
        self.assertEqual(self.m.sessions['a'].state, 'working')

    def test_idle_espera_y_deja_de_asomarse(self):
        self.send('idle')
        self.assertEqual(self.m.view(now=T).mode, 'open')
        self.assertEqual(self.m.view(now=T + state.WAITING_OPEN_SECS + 1).mode, 'peek')
        self.assertEqual(self.m.view(now=T + state.WAITING_PEEK_SECS + 1).mode, 'hidden')

    def test_session_end_la_olvida(self):
        self.send('start')
        self.send('session-end')
        self.assertEqual(self.m.sessions, {})

    def test_la_mas_urgente_va_primero(self):
        self.send('start', sid='a')
        self.send('idle', sid='b')
        self.send('permission', sid='c', message='permiso')
        v = self.m.view(now=T)
        self.assertEqual(v.session.sid, 'c')
        self.assertEqual([s.sid for s in v.others], ['b', 'a'])
        self.assertEqual(v.count, 3)

    def test_en_foco_solo_un_permiso_abre_la_isla(self):
        self.m.handle({'event': 'focus', 'on': True})
        self.send('idle')
        self.assertEqual(self.m.view(now=T).mode, 'peek')
        self.send('permission', sid='b', message='permiso')
        self.assertEqual(self.m.view(now=T).mode, 'open')


class Subagentes(ModelCase):
    def agents(self):
        return {a.aid: a for a in self.m.sessions['a'].agents.values()}

    def test_arranca_trabaja_y_termina(self):
        self.send('start')
        self.send('agent-start', agent_id='s1', agent_type='Explore')
        self.send('tool', agent_id='s1', agent_type='Explore', tool_name='Read',
                  tool_input={'file_path': '/x/proj/a.py'})
        a = self.agents()['s1']
        self.assertEqual((a.name, a.detail, a.started), ('Explore', 'Leyendo a.py', T))
        # Lo que hace el subagente es lo que dice la cabecera.
        self.assertEqual(self.m.view(now=T).detail, 'Leyendo a.py')
        self.send('agent-stop', agent_id='s1', agent_type='Explore')
        self.assertEqual(self.agents(), {})
        self.assertEqual(self.m.sessions['a'].state, 'working')

    def test_uno_de_la_familia_le_cambia_la_cara_a_la_mascota(self):
        self.send('start')
        self.assertEqual(self.m.view(now=T).role, 'engineer')
        self.send('agent-start', agent_id='s1', agent_type='elyares-auditor')
        self.assertEqual(self.m.view(now=T).role, 'auditor')
        self.assertEqual(self.agents()['s1'].name, 'elyares-auditor')
        self.send('agent-stop', agent_id='s1')
        self.assertEqual(self.m.view(now=T).role, 'engineer')

    def test_la_sesion_se_nombra_por_quien_trabaja(self):
        self.send('start')
        v = self.m.view(now=T)
        self.assertEqual((v.agent_name, v.title), ('elyares-engineer', 'proj'))
        self.send('agent-start', agent_id='s1', agent_type='elyares-auditor')
        self.assertEqual(self.m.view(now=T).agent_name, 'elyares-auditor')
        # Uno que no es de la familia no le quita el nombre al engineer.
        self.send('agent-stop', agent_id='s1')
        self.send('agent-start', agent_id='s2', agent_type='Explore')
        self.assertEqual(self.m.view(now=T).agent_name, 'elyares-engineer')

    def test_una_alerta_no_es_de_ningun_agente(self):
        self.alert()
        self.assertEqual(self.m.view(now=T).agent_name, '')
        self.assertEqual(self.m.sessions['x:1'].agent_name, '')

    def test_manda_el_de_la_familia_que_arranco_al_ultimo(self):
        self.send('start')
        self.send('agent-start', agent_id='s1', agent_type='elyares-architect', now=T)
        self.send('agent-start', agent_id='s2', agent_type='elyares-reviewer', now=T + 1)
        # Uno que no es de la familia no le quita la cara al que sí.
        self.send('agent-start', agent_id='s3', agent_type='Explore', now=T + 2)
        self.assertEqual(self.m.view(now=T + 2).role, 'reviewer')
        self.send('agent-stop', agent_id='s2', now=T + 3)
        self.assertEqual(self.m.view(now=T + 3).role, 'architect')

    def test_sin_haber_visto_su_arranque_tambien_sale(self):
        self.send('tool', agent_id='s1', agent_type='elyares-reviewer', tool_name='Grep',
                  tool_input={'pattern': 'TODO'})
        self.assertEqual(self.agents()['s1'].detail, 'Buscando TODO')
        self.assertEqual(self.m.view(now=T).role, 'reviewer')

    def test_el_agente_de_la_sesion_no_es_un_subagente(self):
        # Con `claude --agent` todo trae agent_type, pero solo un subagente trae agent_id.
        self.send('tool', agent_type='elyares-auditor', tool_name='Bash', tool_input={'command': 'ls'})
        self.assertEqual(self.agents(), {})

    def test_el_que_se_queda_callado_se_olvida(self):
        self.send('start')
        self.send('agent-start', agent_id='s1', agent_type='elyares-auditor')
        self.m.view(now=T + state.AGENT_STALE_SECS - 1)
        self.assertIn('s1', self.agents())
        self.m.view(now=T + state.AGENT_STALE_SECS + 1)
        self.assertEqual(self.agents(), {})

    def test_su_permiso_se_suelta_si_termina(self):
        req = FakeReq()
        self.send('ask', req=req, agent_id='s1', agent_type='elyares-auditor', tool_name='Bash',
                  tool_input={'command': 'semgrep scan'})
        self.assertEqual(self.agents()['s1'].detail, 'Ejecutando semgrep scan')
        self.send('agent-stop', agent_id='s1')
        self.assertEqual(req.answers, [None])

    def test_no_se_guardan_entre_reinicios(self):
        self.send('start')
        self.send('agent-start', agent_id='s1', agent_type='elyares-auditor')
        other = Model()
        other.restore(self.m.dump(), now=T)
        self.assertEqual(other.sessions['a'].agents, {})


class Equipo(ModelCase):
    """Cómo están los cuatro de la familia en una sesión: lo que dibuja el tablero."""

    def team(self):
        return {m.role: m for m in self.m.sessions['a'].team()}

    def states(self):
        return [m.state for m in self.m.sessions['a'].team()]

    def tool(self, name='Read', now=T, **extra):
        self.send('tool', now=now, tool_name=name, tool_input={'file_path': f'/x/proj/{name}.py'}, **extra)

    def test_son_los_cuatro_en_el_orden_de_la_familia(self):
        self.send('start')
        self.assertEqual([m.role for m in self.m.sessions['a'].team()], list(state.TEAM))
        self.assertEqual([m.name for m in self.m.sessions['a'].team()],
                         ['elyares-engineer', 'elyares-architect', 'elyares-auditor', 'elyares-reviewer'])
        self.assertEqual(self.states(), ['working', 'idle', 'idle', 'idle'])

    def test_los_pasos_del_engineer_son_los_del_turno(self):
        self.send('start')
        self.tool('Read', now=T + 1)
        self.tool('Edit', now=T + 4)
        self.assertEqual(self.team()['engineer'].steps,
                         [('Pensando…', T), ('Leyendo Read.py', T + 1), ('Editando Edit.py', T + 4)])
        self.assertEqual(self.team()['engineer'].detail, 'Editando Edit.py')
        # Otro turno empieza de cero.
        self.send('start', now=T + 9)
        self.assertEqual(self.team()['engineer'].steps, [('Pensando…', T + 9)])

    def test_la_herramienta_y_su_permiso_son_un_solo_paso(self):
        self.send('start')
        tool = {'tool_name': 'Bash', 'tool_input': {'command': 'rm -rf build'}}
        self.send('tool', now=T + 1, **tool)
        self.send('ask', now=T + 1, req=FakeReq(), **tool)
        self.assertEqual([text for text, _at in self.team()['engineer'].steps],
                         ['Pensando…', 'Ejecutando rm -rf build'])
        self.assertEqual(self.states(), ['permission', 'idle', 'idle', 'idle'])

    def test_no_se_recuerdan_pasos_sin_fin(self):
        self.send('start')
        for i in range(state.STEPS_KEPT + 5):
            self.send('tool', now=T + i, tool_name='Bash', tool_input={'command': f'echo {i}'})
        steps = self.team()['engineer'].steps
        self.assertEqual(len(steps), state.STEPS_KEPT)
        self.assertEqual(steps[-1][0], f'Ejecutando echo {state.STEPS_KEPT + 4}')

    def test_mientras_espera_a_uno_de_la_familia_el_engineer_esta_libre(self):
        self.send('start')
        self.send('tool', now=T + 1, tool_name='Agent', tool_input={'subagent_type': 'elyares-auditor'})
        self.send('agent-start', now=T + 1, agent_id='s1', agent_type='elyares-auditor')
        self.tool('Grep', now=T + 2, agent_id='s1', agent_type='elyares-auditor')
        self.assertEqual(self.states(), ['idle', 'idle', 'working', 'idle'])
        auditor = self.team()['auditor']
        self.assertEqual((auditor.name, auditor.since), ('elyares-auditor', T + 1))
        self.assertEqual([text for text, _at in auditor.steps], ['Buscando'])
        # Lo del auditor no es un paso del engineer.
        self.assertNotIn('Buscando', [text for text, _at in self.team()['engineer'].steps])
        # Vuelve el subagente y el engineer sigue.
        self.send('agent-stop', now=T + 5, agent_id='s1')
        self.send('tool-done', now=T + 5, tool_name='Agent')
        self.assertEqual(self.states(), ['working', 'idle', 'idle', 'idle'])

    def test_con_uno_en_segundo_plano_trabajan_los_dos(self):
        self.send('start')
        self.send('tool', now=T + 1, tool_name='Agent', tool_input={})
        self.send('agent-start', now=T + 1, agent_id='s1', agent_type='elyares-reviewer')
        # Lanzarlo en segundo plano devuelve el control enseguida.
        self.send('tool-done', now=T + 1, tool_name='Agent')
        self.tool('Read', now=T + 2)
        self.assertEqual(self.states(), ['working', 'idle', 'idle', 'working'])

    def test_lo_de_uno_que_no_es_de_la_familia_es_trabajo_del_engineer(self):
        self.send('start')
        self.send('tool', now=T + 1, tool_name='Agent', tool_input={'description': 'buscar'})
        self.send('agent-start', now=T + 1, agent_id='s1', agent_type='Explore')
        self.tool('Read', now=T + 2, agent_id='s1', agent_type='Explore')
        self.assertEqual(self.states(), ['working', 'idle', 'idle', 'idle'])
        self.assertEqual(self.team()['engineer'].detail, 'Leyendo Read.py')

    def test_pide_permiso_el_que_lo_pidio(self):
        self.send('start')
        self.send('tool', now=T + 1, tool_name='Agent', tool_input={})
        self.send('agent-start', now=T + 1, agent_id='s1', agent_type='elyares-auditor')
        self.send('ask', now=T + 2, req=FakeReq(), agent_id='s1', agent_type='elyares-auditor',
                  tool_name='Bash', tool_input={'command': 'semgrep scan'})
        # El aviso de la terminal llega después y sin decir de quién es.
        self.send('permission', now=T + 2)
        self.assertEqual(self.states(), ['idle', 'idle', 'permission', 'idle'])
        self.assertEqual(self.team()['auditor'].detail, 'Ejecutando semgrep scan')

    def test_un_aviso_de_permiso_sin_mas_es_del_engineer(self):
        self.send('start')
        self.send('permission', now=T + 1, message='Claude necesita permiso')
        self.assertEqual(self.states(), ['permission', 'idle', 'idle', 'idle'])

    def test_al_terminar_y_al_esperar_el_engineer_lo_dice(self):
        self.send('start')
        self.tool('Read', now=T + 1)
        self.send('stop', now=T + 5)
        engineer = self.team()['engineer']
        self.assertEqual((engineer.state, engineer.detail), ('done', 'Listo en 5 s'))
        # Lo que hizo sigue ahí, para su desglose.
        self.assertEqual(len(engineer.steps), 3)
        self.send('idle', now=T + 6)
        engineer = self.team()['engineer']
        self.assertEqual((engineer.state, engineer.detail), ('waiting', 'Esperando tu respuesta'))

    def test_tras_un_reinicio_sigue_esperando_al_que_lanzo(self):
        self.send('start')
        self.send('tool', now=T + 1, tool_name='Agent', tool_input={})
        self.send('agent-start', now=T + 1, agent_id='s1', agent_type='elyares-reviewer')
        self.m, old = Model(), self.m
        self.m.restore(old.dump(), now=T + 2)
        # Ni los subagentes ni los pasos se guardan; vuelven con lo siguiente que haga.
        self.assertEqual(self.states(), ['working', 'idle', 'idle', 'idle'])
        self.tool('Read', now=T + 3, agent_id='s1', agent_type='elyares-reviewer')
        self.assertEqual(self.states(), ['idle', 'idle', 'idle', 'working'])
        # Lo que hace el reviewer no pasa por un paso del engineer.
        self.assertEqual(self.team()['engineer'].steps, [])
        self.assertEqual(self.team()['reviewer'].detail, 'Leyendo Read.py')

    def test_en_reposo_estan_los_cuatro_libres(self):
        self.send('start')
        self.send('stop', now=T + 1)
        self.m.view(now=T + 1 + state.DONE_OPEN_SECS + 1)
        self.assertEqual(self.states(), ['idle'] * 4)
        self.assertFalse(any(m.busy for m in self.m.sessions['a'].team()))


class SegundoPlano(ModelCase):
    def test_la_de_repuesto_no_sale_hasta_que_se_usa(self):
        # Claude Code tiene lista una sesión que solo pinta su barra de estado.
        self.send('start', sid='a')
        self.send('status', sid='repuesto', context_pct=0, limit_pct=10)
        v = self.m.view(now=T)
        self.assertEqual((v.count, v.others), (1, []))
        self.assertEqual(self.m.limit, 10)
        # En cuanto hace algo, es una sesión más.
        self.send('start', sid='repuesto', now=T + 1)
        self.assertEqual(self.m.view(now=T + 1).count, 2)

    def test_una_usada_en_reposo_si_sale(self):
        self.send('start')
        self.send('stop', now=T + 1)
        v = self.m.view(now=T + 60)
        self.assertEqual([s.sid for s in v.others], ['a'])

    def test_el_nombre_distingue_a_dos_del_mismo_repo(self):
        self.send('idle', sid='terminal')
        self.send('idle', sid='fondo', now=T + 1, kind='bg', label='Mejoras e integración',
                  proc='778688:829925')
        v = self.m.view(now=T + 1)
        self.assertEqual(v.title, 'proj · Mejoras e integración')
        s = self.m.sessions['fondo']
        self.assertEqual((s.kind, s.proc), ('bg', '778688:829925'))
        self.assertEqual(v.others[0].kind, '')
        self.send('permission', sid='fondo', now=T + 2, message='x')
        self.assertEqual(self.m.view(now=T + 2).title, 'proj · Mejoras e integración')

    def test_olvida_las_de_un_proceso_que_ya_no_existe(self):
        self.send('start', sid='viva', proc='10:1')
        self.send('start', sid='muerta', proc='11:1')
        self.send('start', sid='sin-proceso')
        self.alert(sid='x:1')
        self.assertTrue(self.m.reap(lambda proc: proc == '10:1'))
        self.assertEqual(sorted(self.m.sessions), ['sin-proceso', 'viva', 'x:1'])
        self.assertFalse(self.m.reap(lambda proc: proc == '10:1'))

    def test_el_proceso_y_el_nombre_sobreviven_al_reinicio(self):
        self.send('start', kind='bg', label='Mejoras', proc='10:1')
        self.send('status', sid='repuesto', context_pct=0)
        other = Model()
        other.restore(self.m.dump(), now=T)
        s = other.sessions['a']
        self.assertEqual((s.kind, s.label, s.proc, s.used), ('bg', 'Mejoras', '10:1', True))
        self.assertFalse(other.sessions['repuesto'].used)

    def test_lo_guardado_por_una_version_anterior_se_da_por_usado(self):
        other = Model()
        other.restore([{'sid': 'a', 'state': 'idle'}], now=T)
        self.assertEqual([s.sid for s in other.view(now=T).others], ['a'])


class Permisos(ModelCase):
    def ask(self, **extra):
        req = FakeReq()
        self.send('ask', req=req, tool_name='Bash', tool_input={'command': 'rm -rf build'}, **extra)
        return req

    def test_ask_muestra_los_botones(self):
        self.ask()
        v = self.m.view(now=T)
        self.assertTrue(v.ask)
        self.assertEqual((v.mode, v.pet, v.title), ('open', 'permission', 'proj'))
        self.assertEqual(v.detail, 'Ejecutando rm -rf build')

    def test_ask_sin_hook_esperando_no_hace_nada(self):
        self.send('ask', tool_name='Bash', tool_input={'command': 'ls'})
        self.assertEqual(self.m.sessions['a'].state, 'idle')

    def test_permitir(self):
        req = self.ask()
        self.assertTrue(self.m.decide(self.m.sessions['a'], True, now=T))
        self.assertEqual(req.answers, [{'behavior': 'allow'}])
        self.assertEqual(self.m.sessions['a'].state, 'working')
        self.assertFalse(self.m.view(now=T).ask)

    def test_denegar_corta_el_turno(self):
        req = self.ask()
        self.m.decide(self.m.sessions['a'], False, now=T)
        self.assertEqual(req.answers, [{'behavior': 'deny', 'message': state.DENY_MESSAGE,
                                        'interrupt': True}])
        # Un turno cortado no manda stop: queda esperando.
        self.assertEqual(self.m.sessions['a'].state, 'waiting')

    def test_decidir_sin_permiso_pendiente(self):
        self.send('start')
        self.assertFalse(self.m.decide(self.m.sessions['a'], True))
        self.assertFalse(self.m.decide(None, True))

    def test_contestado_en_la_terminal_suelta_el_hook(self):
        req = self.ask()
        self.send('tool-done', tool_name='Bash')
        self.assertEqual(req.answers, [None])
        self.assertEqual(self.m.sessions['a'].state, 'working')

    def test_otra_herramienta_no_suelta_el_hook(self):
        req = self.ask()
        self.send('tool-done', tool_name='Read')
        self.assertEqual(req.answers, [])

    def test_el_hook_se_fue_sin_respuesta(self):
        req = self.ask()
        self.m.gone(req, now=T)
        s = self.m.sessions['a']
        self.assertIsNone(s.ask)
        self.assertEqual(s.state, 'waiting')

    def test_ask_de_una_edicion_trae_vista_previa(self):
        req = FakeReq()
        self.send('ask', req=req, tool_name='Edit',
                  tool_input={'file_path': '/x/proj/a.py', 'old_string': 'a', 'new_string': 'b'})
        self.assertIsNotNone(self.m.sessions['a'].preview)


class Alertas(ModelCase):
    def test_recien_llegada_abre_y_luego_se_asoma(self):
        self.alert()
        v = self.m.view(now=T)
        self.assertEqual((v.mode, v.pet, v.title, v.detail), ('open', 'annoyed', 'api', 'se rompió'))
        self.assertEqual(v.count, 0)        # "N sesiones" cuenta las de Claude
        self.assertEqual(self.m.view(now=T + state.ALERT_OPEN_SECS + 1).mode, 'peek')

    def test_el_tono_cambia_a_la_mascota(self):
        self.alert(tone='ok')
        self.assertEqual(self.m.view(now=T).pet, 'done')
        self.alert(sid='x:2', tone='info')
        self.assertEqual(self.m.sessions['x:2'].tone, 'info')

    def test_vieja_queda_debajo_de_una_sesion_activa(self):
        self.alert()
        self.send('start', now=T + 20)
        self.assertEqual(self.m.view(now=T + 20).session.sid, 'a')

    def test_caduca_sola(self):
        self.alert()
        self.alert(sid='x:2', ttl=20)
        self.m.view(now=T + 21)
        self.assertEqual(list(self.m.sessions), ['x:1'])
        self.m.view(now=T + state.ALERT_SECS + 1)
        self.assertEqual(self.m.sessions, {})

    def test_descartada_no_vuelve_en_un_rato(self):
        self.alert()
        self.m.dismiss(self.m.sessions['x:1'], now=T)
        self.alert(now=T + 60)
        self.assertEqual(self.m.sessions, {})
        self.alert(now=T + state.ALERT_COOLDOWN_SECS + 1)
        self.assertIn('x:1', self.m.sessions)

    def test_quitada_sin_silenciar_vuelve_enseguida(self):
        self.alert()
        self.m.dismiss(self.m.sessions['x:1'], now=T, cooldown=False)
        self.alert(now=T + 1)
        self.assertIn('x:1', self.m.sessions)

    def test_alert_clear(self):
        self.alert()
        self.m.handle({'event': 'alert-clear', 'session_id': 'x:1'})
        self.assertEqual(self.m.sessions, {})

    def test_la_elegida_en_la_lista_sube_a_la_cabecera(self):
        self.alert()
        self.send('permission', now=T + 20, message='permiso')
        self.assertEqual(self.m.view(now=T + 20).session.sid, 'a')
        self.assertEqual(self.m.view(now=T + 20, pin='x:1').session.sid, 'x:1')

    def test_ficha(self):
        self.alert(where='app.py:10', note='2 eventos', lines=['uno', '\x1b[31mdos\x1b[0m', ''],
                   actions=[{'label': 'Abrir', 'url': 'http://x'}])
        s = self.m.sessions['x:1']
        self.assertTrue(s.card)
        self.assertEqual((s.where, s.note, s.lines), ('app.py:10', '2 eventos', ['uno', 'dos']))
        self.alert(sid='x:2')
        self.assertFalse(self.m.sessions['x:2'].card)


class Fichas(unittest.TestCase):
    def test_lineas_las_ultimas_y_sin_colores(self):
        lines = [f'l{i}' for i in range(20)] + [7, '\x1b[1;32mfin\x1b[0m  ']
        self.assertEqual(state.card_lines(lines),
                         [f'l{i}' for i in range(21 - state.CARD_LINES, 20)] + ['fin'])
        self.assertEqual(state.card_lines('no es una lista'), [])

    def test_botones_validos(self):
        ok = [{'label': 'Logs', 'cmd': ['docker', 'logs']}, {'label': 'Abrir', 'url': 'http://x'},
              {'label': 'Ir', 'jump': True}]
        bad = [{'cmd': ['x']}, {'label': 'x'}, {'label': 'x', 'cmd': 'rm -rf'},
               {'label': 'x', 'cmd': []}, {'label': 'x', 'jump': 'sí'}, 'nada']
        self.assertEqual(state.card_actions(bad + ok), ok[:state.CARD_ACTIONS])
        self.assertEqual(state.card_actions(None), [])


class ComandoLargo(ModelCase):
    def done(self, **extra):
        self.send('cmd-done', sid='cmd:%3', command='make  test', seconds=65, **extra)
        return self.m.sessions['cmd:%3']

    def test_fallo(self):
        s = self.done(exit_code=2, pane='%3', tmux='/tmp/tmux,1,0', output=['FAILED a', 'make: *** Error 2'])
        self.assertEqual(s.detail, 'Falló (código 2) en 1 min 05 s: make test')
        self.assertEqual((s.name, s.tone, s.ttl), ('proj', '', 0))
        # La ficha: dónde, cuánto, lo último que imprimió y el salto a su pane.
        self.assertEqual((s.where, s.note), (CWD, 'código 2 · 1 min 05 s'))
        self.assertEqual(s.lines, ['FAILED a', 'make: *** Error 2'])
        self.assertEqual(s.actions, [state.JUMP])
        self.assertEqual((s.pane, s.tmux), ('%3', '/tmp/tmux,1,0'))

    def test_bien_es_buena_noticia_y_se_va_pronto(self):
        s = self.done(exit_code=0, pane='%3')
        self.assertEqual(s.detail, 'Terminó en 1 min 05 s: make test')
        self.assertEqual((s.tone, s.ttl, s.note), ('ok', state.CMD_OK_SECS, '1 min 05 s'))

    def test_fuera_de_tmux_no_hay_ficha(self):
        s = self.done(exit_code=1)
        self.assertFalse(s.card)


RES = {'ran': True, 'passed': 12, 'failed': 1, 'skipped': 2, 'lines': ['✗ resta', '✓ suma']}
GREEN = {'ran': True, 'passed': 13, 'failed': 0, 'skipped': 0, 'lines': ['✓ suma']}


class PruebasEnLaTerminal(ModelCase):
    def start(self, now=T, **extra):
        self.send('cmd-start', now=now, sid='cmd:%3', command='make  test', pane='%3',
                  tmux='/s,1,0', **extra)
        return self.m.sessions.get('cmd:%3')

    def done(self, now=T + 12, **extra):
        self.send('cmd-done', now=now, sid='cmd:%3', command='make test', seconds=12, pane='%3',
                  **extra)
        return self.m.sessions['cmd:%3']

    def test_al_empezar_abre_la_isla_y_se_queda_abierta(self):
        s = self.start()
        self.assertEqual((s.name, s.tone, s.detail), ('proj', 'run', 'Corriendo pruebas: make test'))
        self.assertTrue(s.tests)
        self.assertEqual((s.where, s.actions), ('make test', [state.JUMP]))
        for later in (0, 60, 600):
            v = self.m.view(now=T + later)
            self.assertEqual((v.mode, v.pet), ('open', 'working'), later)

    def test_va_diciendo_como_van(self):
        self.start()
        s = self.start(now=T + 3, results=RES)
        self.assertEqual(s.detail, 'Corriendo pruebas: 1 falló, 12 pasaron, 2 saltadas')
        self.assertEqual((s.note, s.lines), ('12 ✓ · 1 ✗ · 2 ○', ['✗ resta', '✓ suma']))
        # Sigue siendo la misma noticia: no vuelve a contar como recién llegada.
        self.assertEqual(s.changed, T)

    def test_va_sobre_una_sesion_trabajando_y_bajo_un_permiso(self):
        self.start()
        self.send('start', now=T + 30)
        self.assertEqual(self.m.view(now=T + 30).session.sid, 'cmd:%3')
        self.send('permission', now=T + 31, message='permiso')
        self.assertEqual(self.m.view(now=T + 31).session.sid, 'a')

    def test_en_foco_no_abre_la_isla(self):
        self.m.handle({'event': 'focus', 'on': True})
        self.start()
        self.assertEqual(self.m.view(now=T).mode, 'peek')

    def test_una_corrida_nueva_vuelve_aunque_se_haya_descartado(self):
        self.m.dismiss(self.start(), now=T)
        self.start(now=T + 1, results=RES)       # lo que quedaba de la descartada
        self.assertNotIn('cmd:%3', self.m.sessions)
        s = self.start(now=T + 20)
        self.assertEqual((s.changed, s.lines), (T + 20, []))

    def test_en_rojo(self):
        self.start()
        s = self.done(exit_code=1, results=RES)
        self.assertEqual(s.detail, 'Pruebas en rojo: 1 falló, 12 pasaron, 2 saltadas en 12 s')
        self.assertEqual((s.tone, s.ttl, s.where, s.note), ('', 0, 'make test', '12 ✓ · 1 ✗ · 2 ○'))
        self.assertEqual(s.lines, ['✗ resta', '✓ suma'])
        self.assertTrue(s.tests)
        # Es otra noticia: abre la isla y luego se asoma, como cualquier alerta.
        self.assertEqual(self.m.view(now=T + 12).mode, 'open')
        self.assertEqual(self.m.view(now=T + 12 + state.ALERT_OPEN_SECS + 1).mode, 'peek')

    def test_en_verde(self):
        self.start()
        s = self.done(exit_code=0, results=GREEN)
        self.assertEqual(s.detail, 'Pruebas en verde: 13 pasaron en 12 s')
        self.assertEqual((s.tone, s.ttl), ('ok', state.CMD_OK_SECS))

    def test_fallo_el_comando_sin_ninguna_prueba_en_rojo(self):
        s = self.done(exit_code=2, results=GREEN)
        self.assertEqual(s.detail, 'Falló (código 2) en 12 s: make test')
        self.assertEqual((s.tone, s.lines), ('', ['✓ suma']))

    def test_no_eran_pruebas(self):
        self.start()
        s = self.done(exit_code=2, results={'ran': False, 'lines': []}, output=['make: *** Error 2'])
        self.assertEqual(s.detail, 'Falló (código 2) en 12 s: make test')
        self.assertEqual((s.lines, s.tests), (['make: *** Error 2'], False))

    def test_resultados_rotos(self):
        for res in (None, 'x', {'ran': True, 'passed': 'muchas'}, {'ran': False, 'passed': 3}):
            self.assertIsNone(state.tests_card(res))
        self.assertEqual(state.tests_card({'ran': True})['counts'], 'ninguna')

    def test_a_medias_no_sobrevive_al_reinicio(self):
        self.start()
        self.alert()
        other = Model()
        other.restore(self.m.dump(), now=T)
        self.assertEqual(list(other.sessions), ['x:1'])


class PruebasDeClaude(ModelCase):
    OUT = ('test_a (m.Cuentas.test_a) ... ok\ntest_b (m.Cuentas.test_b) ... FAIL\n\n'
           'Ran 2 tests in 0.1s\n\nFAILED (failures=1)\n')

    def bash(self, event, output, command='make test', **extra):
        self.send('tool', tool_name='Bash', tool_input={'command': command}, pane='%1', tmux='/s,1,0')
        self.send(event, now=T + 5, tool_name='Bash', tool_input={'command': command},
                  output=output, **extra)
        return self.m.sessions.get('tests:a')

    def test_en_rojo(self):
        s = self.bash('tool-fail', self.OUT)
        self.assertEqual((s.name, s.tone, s.detail), ('proj', '', 'Pruebas en rojo: 1 falló, 1 pasó'))
        self.assertEqual((s.where, s.note), ('make test', '1 ✓ · 1 ✗'))
        self.assertEqual(s.lines, ['✗ Cuentas.test_b', '✓ Cuentas.test_a'])
        self.assertEqual((s.actions, s.pane, s.tests), ([state.JUMP], '%1', True))
        # Sale sobre la sesión que trabaja mientras es noticia.
        self.assertEqual(self.m.view(now=T + 5).session.sid, 'tests:a')
        self.assertEqual(self.m.sessions['a'].state, 'working')

    def test_en_verde(self):
        s = self.bash('tool-done', '..\n' + '-' * 70 + '\nRan 2 tests in 0.1s\n\nOK\n')
        self.assertEqual((s.tone, s.ttl, s.detail),
                         ('ok', state.CMD_OK_SECS, 'Pruebas en verde: 2 pasaron'))

    def test_el_comando_fallo_aunque_no_se_vea_ninguna_en_rojo(self):
        s = self.bash('tool-fail', 'Ran 2 tests in 0.1s\n\nOK\nerror: cobertura por debajo del 80%\n')
        self.assertEqual((s.tone, s.detail), ('', 'Pruebas en rojo: 2 pasaron'))

    def test_cada_corrida_vuelve_a_ser_noticia(self):
        self.bash('tool-fail', self.OUT)
        self.m.dismiss(self.m.sessions['tests:a'], now=T + 6)
        self.send('tool-fail', now=T + 60, tool_name='Bash', tool_input={'command': 'make test'},
                  output=self.OUT)
        self.assertEqual(self.m.sessions['tests:a'].changed, T + 60)

    def test_sin_pruebas_en_la_salida_no_hay_alerta(self):
        self.assertIsNone(self.bash('tool-fail', 'make: *** No rule to make target\n'))
        self.assertIsNone(self.bash('tool-done', None))

    def test_tool_fail_no_baja_el_permiso(self):
        self.send('permission', message='permiso')
        self.send('tool-fail', now=T + 1, tool_name='Bash')
        self.assertEqual(self.m.sessions['a'].state, 'permission')


class Uso(ModelCase):
    def status(self, context=0, limit=0, sid='a', **extra):
        self.send('status', sid=sid, context_pct=context, limit_pct=limit, **extra)

    def test_contexto_avisa_una_vez_al_cruzar(self):
        self.send('tool', tool_name='Bash', tool_input={'command': 'make'}, pane='%1', tmux='/s,1,0')
        self.status(context=89)
        self.assertNotIn('ctx:a', self.m.sessions)
        self.status(context=91)
        s = self.m.sessions['ctx:a']
        self.assertEqual((s.name, s.tone), ('proj', 'info'))
        self.assertEqual(s.detail, 'Contexto al 91%: se va a compactar pronto')
        # La ficha dice qué sesión es y lleva a ella.
        self.assertEqual((s.where, s.note), (CWD, '91% de contexto'))
        self.assertEqual(s.lines, ['Al llegar al 90%: Ejecutando make'])
        self.assertEqual((s.actions, s.pane), ([state.JUMP], '%1'))
        self.m.dismiss(s, now=T, cooldown=False)
        self.status(context=93)
        self.assertNotIn('ctx:a', self.m.sessions)
        self.assertEqual(self.m.sessions['a'].context, 93)

    def test_contexto_sin_pane_no_lleva_boton(self):
        self.status(context=95)
        self.assertEqual(self.m.sessions['ctx:a'].actions, [])

    def test_limite_avisa_en_cada_marca(self):
        self.status(limit=50)
        self.assertEqual(self.m.limit, 50)
        self.status(limit=81)
        self.assertEqual(self.m.sessions['limit:80'].tone, 'info')
        self.assertNotIn('limit:95', self.m.sessions)
        self.status(limit=96)
        self.assertEqual(self.m.sessions['limit:95'].tone, '')
        self.assertEqual(self.m.sessions['limit:95'].detail, 'Límite de 5 h al 96%')

    def test_la_ficha_del_limite_lista_las_sesiones(self):
        self.send('tool', sid='b', tool_name='Bash', tool_input={'command': 'make'})
        self.status(context=40, sid='b')
        self.status(context=70, limit=85)
        s = self.m.sessions['limit:80']
        self.assertEqual((s.where, s.note), ('Sesiones abiertas', '2 sesiones'))
        self.assertEqual(len(s.lines), 2)
        self.assertRegex(s.lines[0], r'^proj +70%  en reposo$')
        self.assertRegex(s.lines[1], r'^proj +40%  Ejecutando make$')
        self.assertEqual(s.actions, [])

    def test_dato_roto_se_ignora(self):
        self.status(context='mucho')
        self.assertEqual(self.m.sessions['a'].context, 0)


class Guardado(ModelCase):
    def test_ida_y_vuelta(self):
        self.send('tool', tool_name='Bash', tool_input={'command': 'make'}, pane='%1', tmux='/s,1,0')
        self.alert(url='http://x', tone='ok', ttl=30, lines=['uno'])
        other = Model()
        other.restore(self.m.dump(), now=T + 1)
        a, x = other.sessions['a'], other.sessions['x:1']
        self.assertEqual((a.state, a.detail, a.pane, a.tmux), ('working', 'Ejecutando make', '%1', '/s,1,0'))
        self.assertEqual((x.state, x.name, x.url, x.tone, x.ttl), ('alert', 'api', 'http://x', 'ok', 30))
        # La ficha no se guarda.
        self.assertEqual(x.lines, [])

    def test_un_permiso_vuelve_sin_botones(self):
        self.send('ask', req=FakeReq(), tool_name='Bash', tool_input={'command': 'ls'})
        other = Model()
        other.restore(self.m.dump(), now=T)
        v = other.view(now=T)
        self.assertEqual(v.pet, 'permission')
        self.assertFalse(v.ask)

    def test_datos_rotos(self):
        other = Model()
        other.restore([None, {}, {'sid': 'a', 'state': 'raro', 'changed': T + 500},
                       {'sid': 'b', 'updated': 'ayer'}], now=T)
        self.assertEqual(list(other.sessions), ['a'])
        self.assertEqual(other.sessions['a'].state, 'idle')
        # Nunca en el futuro: no caducaría.
        self.assertEqual(other.sessions['a'].changed, T)


class Panes(ModelCase):
    def test_olvida_las_de_un_pane_cerrado(self):
        self.send('start', sid='a', pane='%1', tmux='/s,10,0')
        self.send('start', sid='b', pane='%2', tmux='/s,10,0')
        self.send('start', sid='c', pane='%9', tmux='/otro,5,0')   # no se pudo preguntar
        self.send('start', sid='d')                                 # sin tmux
        self.assertTrue(self.m.prune({'/s': {('10', '%1')}}))
        self.assertEqual(sorted(self.m.sessions), ['a', 'c', 'd'])
        self.assertFalse(self.m.prune({'/s': {('10', '%1')}}))

    def test_un_servidor_nuevo_en_el_mismo_socket(self):
        self.send('start', pane='%1', tmux='/s,10,0')
        self.assertTrue(self.m.prune({'/s': {('11', '%1')}}))


class Texto(unittest.TestCase):
    def test_elapsed(self):
        self.assertEqual([state.elapsed(s) for s in (5, 65, 3725)],
                         ['5 s', '1 min 05 s', '1 h 02 min'])

    def test_short(self):
        self.assertEqual(state.short('  a \n b  '), 'a b')
        self.assertEqual(state.short('x' * 100, 10), 'x' * 9 + '…')
        self.assertEqual(state.short(None), '')

    def test_tilde(self):
        home = os.path.expanduser('~')
        self.assertEqual(state.tilde(home + '/dev/x'), '~/dev/x')
        self.assertEqual(state.tilde(home), '~')
        self.assertEqual(state.tilde(home + 'x/y'), home + 'x/y')
        self.assertEqual(state.tilde('/etc'), '/etc')

    def test_describe_tool(self):
        d = state.describe_tool
        self.assertEqual(d('Edit', {'file_path': '/r/a.py'}, '/r'), 'Editando a.py')
        self.assertEqual(d('Write', {'file_path': '/otro/a.py'}, '/r'), 'Escribiendo /otro/a.py')
        self.assertEqual(d('Grep', {'pattern': 'TODO'}, ''), 'Buscando TODO')
        self.assertEqual(d('Agent', {'description': 'revisar'}, ''), 'Subagente: revisar')
        self.assertEqual(d('mcp__docs__read', {}, ''), 'Usando docs')
        self.assertEqual(d('Bash', None, ''), 'Ejecutando un comando')


if __name__ == '__main__':
    unittest.main()
