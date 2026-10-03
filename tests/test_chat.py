"""El chat con Claude: lo que se le manda y cómo se lee lo que contesta."""

import io
import json
import os
import tempfile
import unittest
from unittest import mock

from elyares import chat, paint, state


class FakeProc:
    """Un `claude -p` de mentira: guarda lo que se le escribe y no lee nada."""

    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.stdin = io.StringIO()
        self.stdout = io.StringIO('')
        self.alive = True

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.alive = False

    def sent(self):
        return [json.loads(line) for line in self.stdin.getvalue().splitlines()]


class ChatCase(unittest.TestCase):
    """Un chat con un `claude -p` de mentira."""

    def setUp(self):
        patcher = mock.patch.object(state, 'project_root', lambda cwd: cwd)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.procs = []

        def spawn(*args, **kwargs):
            self.procs.append(FakeProc(*args, **kwargs))
            return self.procs[-1]

        self.events = []
        self.c = chat.Chat('/x/proj', self.events.append, spawn=spawn)
        self.c.commands = {}


class Conversacion(ChatCase):
    def test_mandar_arranca_a_claude_en_su_carpeta(self):
        self.assertTrue(self.c.send('  haz /contexto  '))
        proc = self.procs[0]
        self.assertEqual(proc.kwargs['cwd'], '/x/proj')
        cmd = proc.args[0]
        for flag in ('-p', '--input-format', '--permission-prompt-tool'):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index('--permission-mode') + 1], 'bypassPermissions')
        self.assertNotIn('--resume', cmd)
        self.assertEqual(proc.sent(), [{'type': 'user', 'message': {'role': 'user', 'content': 'haz /contexto'}}])
        self.assertEqual((self.c.entries[-1].kind, self.c.entries[-1].text), ('you', 'haz /contexto'))
        self.assertTrue(self.c.busy)
        self.assertFalse(self.c.send('   '))

    def test_la_respuesta_se_va_escribiendo_y_el_bloque_final_manda(self):
        self.c.send('hola')
        self.c.feed({'type': 'stream_event', 'event': {'type': 'content_block_start',
                                                        'content_block': {'type': 'text'}}})
        for piece in ('Ho', 'la, ', 'Yared'):
            self.c.feed({'type': 'stream_event', 'event': {'type': 'content_block_delta',
                                                            'delta': {'type': 'text_delta', 'text': piece}}})
        self.assertEqual(self.c.entries[-1].text, 'Hola, Yared')
        self.assertTrue(self.c.streaming)
        self.c.feed({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'Hola, Yared.'}]}})
        self.assertEqual([(e.kind, e.text) for e in self.c.entries], [('you', 'hola'), ('claude', 'Hola, Yared.')])
        self.assertFalse(self.c.streaming)
        self.c.feed({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'Hola, Yared.'})
        self.assertFalse(self.c.busy)

    def test_solo_queda_la_respuesta_no_lo_que_hace_por_el_camino(self):
        self.c.send('lee')
        text = lambda t: {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': t}]}}
        tool = {'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': '/x/proj/docs/INDEX.md'}}]}}
        self.c.feed(text('Voy a leer el índice.'))
        self.assertEqual(self.c.entries[-1].text, 'Voy a leer el índice.')
        # Sigue trabajando: eso no era la respuesta, y la herramienta no se apunta.
        self.c.feed(tool)
        self.assertEqual([(e.kind, e.text) for e in self.c.entries], [('you', 'lee')])
        self.c.feed(text('El índice tiene tres documentos.'))
        self.c.feed({'type': 'result', 'subtype': 'success', 'duration_ms': 1200})
        self.assertEqual([e.kind for e in self.c.entries], ['you', 'claude', 'foot'])
        self.assertEqual(self.c.reply(), 'El índice tiene tres documentos.')
        # La respuesta de un turno ya acabado no se toca en el siguiente.
        self.c.send('y ahora el README')
        self.c.feed(tool)
        self.assertEqual([e.kind for e in self.c.entries], ['you', 'claude', 'foot', 'you'])

    def test_lo_que_dice_un_subagente_no_es_la_respuesta(self):
        self.c.send('audita')
        self.c.feed({'type': 'assistant', 'parent_tool_use_id': 'toolu_1', 'message': {
            'usage': {'input_tokens': 900}, 'content': [{'type': 'text', 'text': 'Reviso el diff.'}]}})
        self.c.feed({'type': 'stream_event', 'parent_tool_use_id': 'toolu_1', 'event': {
            'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': 'Reviso'}}})
        self.assertEqual([e.kind for e in self.c.entries], ['you'])
        self.assertEqual(self.c.tokens, 0)

    def test_el_init_da_la_sesion_y_los_comandos(self):
        self.c.commands = {'commit': 'Convierte el working tree…'}
        self.c.feed({'type': 'system', 'subtype': 'init', 'session_id': 's-1',
                     'slash_commands': ['commit', 'compact'], 'skills': ['commit', 'pr']})
        self.assertEqual(self.c.session, 's-1')
        self.assertEqual(self.c.commands, {'commit': 'Convierte el working tree…', 'compact': '', 'pr': ''})

    def test_el_permiso_se_contesta_desde_la_isla(self):
        self.c.send('escribe')
        self.c.feed({'type': 'control_request', 'request_id': 'r-1', 'request': {
            'subtype': 'can_use_tool', 'tool_name': 'Write',
            'input': {'file_path': '/x/proj/a.txt', 'content': 'hola'}}})
        self.assertEqual(self.c.asking['text'], 'Escribiendo a.txt')
        self.assertTrue(self.c.answer(True))
        self.assertIsNone(self.c.asking)
        reply = self.procs[0].sent()[-1]
        self.assertEqual(reply['type'], 'control_response')
        self.assertEqual(reply['response']['request_id'], 'r-1')
        self.assertEqual(reply['response']['response'],
                         {'behavior': 'allow', 'updatedInput': {'file_path': '/x/proj/a.txt', 'content': 'hola'}})
        self.assertFalse(self.c.answer(True))       # ya no hay nada que contestar

    def test_denegar_lo_dice_en_la_conversacion(self):
        self.c.send('escribe')
        self.c.feed({'type': 'control_request', 'request_id': 'r-2', 'request': {
            'subtype': 'can_use_tool', 'tool_name': 'Bash', 'input': {'command': 'rm -rf build'}}})
        self.c.answer(False)
        self.assertEqual(self.procs[0].sent()[-1]['response']['response']['behavior'], 'deny')
        self.assertEqual(self.c.entries[-1].text, 'Denegado: Ejecutando rm -rf build')

    def test_cortar_el_turno(self):
        self.assertFalse(self.c.interrupt())        # sin turno no hay nada que cortar
        self.c.send('cuenta hasta mil')
        self.assertTrue(self.c.interrupt())
        self.assertEqual(self.procs[0].sent()[-1]['request'], {'subtype': 'interrupt'})
        self.c.feed({'type': 'result', 'subtype': 'error_during_execution', 'is_error': True})
        self.assertEqual(self.c.entries[-1].text, 'Turno cortado')
        self.assertFalse(self.c.busy)

    def test_si_claude_se_cierra_lo_siguiente_lo_retoma(self):
        self.c.send('hola')
        self.c.feed({'type': 'system', 'subtype': 'init', 'session_id': 's-9'})
        first = self.procs[0]
        first.alive = False
        self.c.feed({'type': 'exit', 'proc': first})
        self.assertIn('se cerró', self.c.entries[-1].text)
        self.c.send('sigue')
        self.assertEqual(len(self.procs), 2)
        cmd = self.procs[1].args[0]
        self.assertEqual(cmd[cmd.index('--resume') + 1], 's-9')

    def test_el_fin_de_un_proceso_viejo_no_cuenta(self):
        self.c.send('hola')
        self.assertFalse(self.c.feed({'type': 'exit', 'proc': object()}))
        self.assertTrue(self.c.busy)

    def test_un_error_de_claude_se_ve(self):
        self.c.send('hola')
        self.c.feed({'type': 'result', 'subtype': 'error_max_turns', 'is_error': True, 'result': ''})
        self.assertEqual((self.c.entries[-1].kind, self.c.entries[-1].text), ('error', 'error_max_turns'))


class EntreReinicios(ChatCase):
    """La conversación se guarda y vuelve cuando la isla se arranca de nuevo."""

    def test_vuelve_como_estaba_y_lo_siguiente_la_retoma(self):
        c = chat.Chat('/x/proj', None, agent='elyares-auditor', model='opus', effort='high')
        c.session, c.model_id, c.plan, c.tokens, c.window = 's-1', 'claude-opus-5-5', True, 88000, 1000000
        c.entries = [chat.Entry('you', 'audita', 1), chat.Entry('claude', 'Sin hallazgos.'),
                     chat.Entry('foot', 'elyares-auditor · Opus 5.5 · 4.0 s')]
        saved = json.loads(json.dumps(c.dump()))
        back = chat.Chat.restore(saved, self.events.append, spawn=lambda *a, **kw: FakeProc(*a, **kw))
        self.assertEqual(back.dump(), saved)
        self.assertFalse(back.alive or back.busy)
        self.assertEqual(back.commands, chat.local_commands('/x/proj'))
        back.spawn = mock.Mock(side_effect=lambda *a, **kw: FakeProc(*a, **kw))
        back.send('y el README')
        cmd = back.spawn.call_args[0][0]
        self.assertEqual(cmd[cmd.index('--resume') + 1], 's-1')
        self.assertEqual(cmd[cmd.index('--permission-mode') + 1], 'plan')

    def test_un_turno_cortado_por_el_reinicio_lo_dice(self):
        self.c.send('hola')
        back = chat.Chat.restore(self.c.dump(), None)
        self.assertFalse(back.busy)
        self.assertEqual((back.entries[-1].kind, back.entries[-1].text), ('note', chat.CUT_NOTE))

    def test_solo_se_guarda_lo_ultimo(self):
        self.c.entries = [chat.Entry('you', str(i)) for i in range(chat.SAVED_ENTRIES + 20)]
        self.assertEqual(len(self.c.dump()['entries']), chat.SAVED_ENTRIES)
        self.assertEqual(self.c.dump()['entries'][-1], ['you', str(chat.SAVED_ENTRIES + 19), 0])

    def test_lo_guardado_que_no_sirve_no_vuelve(self):
        self.assertIsNone(chat.Chat.restore({}, None))
        back = chat.Chat.restore({'cwd': '/x', 'entries': [['you'], 'x', ['you', 3, 0], ['you', 'vale', 0]],
                                  'tokens': 'muchos', 'plan': 'sí'}, None)
        self.assertEqual([(e.kind, e.text) for e in back.entries], [('you', 'vale')])
        self.assertEqual((back.tokens, back.plan, back.session), (0, False, ''))


class Permisos(ChatCase):
    """El chat trabaja sin pedir permiso, salvo en modo plan."""

    def modes(self):
        return [m['request']['mode'] for m in self.procs[0].sent()
                if m.get('type') == 'control_request' and m['request']['subtype'] == 'set_permission_mode']

    def test_al_aprobar_un_plan_vuelve_a_trabajar_sin_preguntar(self):
        self.c.send('planea')
        self.c.feed({'type': 'system', 'subtype': 'init', 'session_id': 's-1', 'permissionMode': 'plan'})
        self.assertTrue(self.c.plan)
        self.assertEqual(self.modes(), [])
        # Aprobado el plan, Claude sale al modo de preguntar por todo: se le devuelve al del chat.
        self.c.feed({'type': 'system', 'subtype': 'status', 'permissionMode': 'default'})
        self.assertFalse(self.c.plan)
        self.assertEqual(self.modes(), ['bypassPermissions'])
        self.c.feed({'type': 'system', 'subtype': 'status', 'permissionMode': 'bypassPermissions'})
        self.assertEqual(self.modes(), ['bypassPermissions'])       # ya está: no se insiste

    def test_una_conversacion_retomada_en_otro_modo_tambien(self):
        self.c.send('sigue')
        self.c.feed({'type': 'system', 'subtype': 'init', 'session_id': 's-1', 'permissionMode': 'acceptEdits'})
        self.assertEqual(self.modes(), ['bypassPermissions'])

    def test_arranca_pudiendo_pasar_a_bypass_aunque_empiece_en_plan(self):
        self.c.plan = True
        self.c.send('planea')
        cmd = self.procs[0].args[0]
        self.assertIn('--allow-dangerously-skip-permissions', cmd)
        self.assertEqual(cmd[cmd.index('--permission-mode') + 1], 'plan')


class Contexto(ChatCase):
    """Cuánto lleva lleno el contexto de la conversación."""

    def asked(self):
        return [m['request']['subtype'] for m in self.procs[0].sent() if m.get('type') == 'control_request']

    def test_claude_lo_cuenta_al_arrancar_y_al_acabar_cada_turno(self):
        self.c.send('hola')
        self.c.feed({'type': 'system', 'subtype': 'init', 'session_id': 's-1'})
        self.assertEqual(self.asked(), ['get_context_usage'])
        self.assertEqual((self.c.tokens, self.c.context), (0, 0.0))
        self.assertTrue(self.c.feed({'type': 'control_response', 'response': {
            'subtype': 'success', 'request_id': 'isla-1',
            'response': {'totalTokens': 14000, 'maxTokens': 1000000, 'percentage': 1}}}))
        self.assertEqual((self.c.tokens, self.c.window), (14000, 1000000))
        self.assertAlmostEqual(self.c.context, 1.4)
        self.c.feed({'type': 'result', 'subtype': 'success'})
        self.assertEqual(self.asked(), ['get_context_usage'] * 2)

    def test_entre_medias_sale_de_lo_que_gasta_cada_respuesta(self):
        self.c.send('hola')
        self.c.window = 200000
        self.assertTrue(self.c.feed({'type': 'assistant', 'message': {'content': [], 'usage': {
            'input_tokens': 4, 'cache_read_input_tokens': 86000, 'cache_creation_input_tokens': 1996,
            'output_tokens': 1291}}}))
        self.assertEqual(self.c.tokens, 88000)
        self.assertAlmostEqual(self.c.context, 44.0)

    def test_otra_respuesta_de_control_no_es_la_cuenta(self):
        self.assertFalse(self.c.feed({'type': 'control_response', 'response': {
            'subtype': 'success', 'request_id': 'isla-2', 'response': {'mode': 'plan'}}}))
        self.assertFalse(self.c.feed({'type': 'control_response', 'response': {'subtype': 'error'}}))
        self.assertEqual(self.c.context, 0.0)

    def test_los_tokens_se_leen_de_un_vistazo(self):
        self.assertEqual([chat.tokens_text(n) for n in (812, 87767, 1250000)], ['812', '88k', '1.2M'])


class Menciones(ChatCase):
    """Lo que se nombra con "@": los agentes y los archivos del proyecto."""

    FILES = ['README.md', 'elyares/chat.py', 'elyares/chatview.py', 'tests/test_chat.py']

    def test_primero_los_agentes_y_luego_los_archivos_que_empiezan_asi(self):
        files = mock.Mock(return_value=self.FILES)
        self.assertEqual(self.c.mentions('chat', files, now=0),
                         [('elyares/chat.py', ''), ('elyares/chatview.py', ''), ('tests/test_chat.py', '')])
        self.assertEqual(self.c.mentions('aud', files, now=1), [('elyares-auditor', 'agente')])
        self.assertEqual(self.c.mentions('', files, now=2)[:3], [(a, 'agente') for a in state.AGENT_ROLES][:3])
        # Los archivos no se listan a cada tecla.
        files.assert_called_once_with('/x/proj')
        self.c.mentions('x', files, now=chat.FILES_SECS + 1)
        self.assertEqual(files.call_count, 2)

    def test_los_agentes_son_los_que_dice_claude(self):
        self.c.feed({'type': 'system', 'subtype': 'init', 'session_id': 's-1',
                     'agents': ['Explore', 'elyares-reviewer']})
        self.assertEqual(self.c.mentions('e', lambda cwd: [], now=0),
                         [('Explore', 'agente'), ('elyares-reviewer', 'agente')])


class ModeloEsfuerzoPlan(ChatCase):
    def test_arranca_con_lo_elegido(self):
        self.c.agent, self.c.model, self.c.effort, self.c.plan = 'elyares-reviewer', 'sonnet', 'low', True
        self.c.send('revisa')
        cmd = self.procs[0].args[0]
        for flag, value in (('--agent', 'elyares-reviewer'), ('--model', 'sonnet'), ('--effort', 'low'),
                            ('--permission-mode', 'plan')):
            self.assertEqual(cmd[cmd.index(flag) + 1], value)

    def test_el_modelo_y_el_plan_cambian_en_caliente(self):
        self.c.set_model('haiku')                   # sin Claude abierto: solo se apunta
        self.assertEqual(self.c.model, 'haiku')
        self.c.send('hola')
        self.c.set_model('sonnet')
        self.assertEqual(self.procs[0].sent()[-1]['request'], {'subtype': 'set_model', 'model': 'sonnet'})
        self.c.toggle_plan()
        self.assertEqual(self.procs[0].sent()[-1]['request'], {'subtype': 'set_permission_mode', 'mode': 'plan'})
        self.c.toggle_plan()
        self.assertEqual(self.procs[0].sent()[-1]['request']['mode'], chat.BASE_MODE)
        # Claude confirma el modo con su estado.
        self.c.feed({'type': 'system', 'subtype': 'status', 'permissionMode': 'plan'})
        self.assertTrue(self.c.plan)

    def test_el_esfuerzo_cierra_entre_turnos_y_lo_siguiente_retoma(self):
        self.c.send('hola')
        self.c.feed({'type': 'system', 'subtype': 'init', 'session_id': 's-1', 'model': 'claude-opus-5-5'})
        self.c.set_effort('max')                    # con un turno en curso: al acabarlo
        self.assertTrue(self.c.restart and self.procs[0].alive)
        self.c.feed({'type': 'result', 'subtype': 'success', 'duration_ms': 2300})
        self.assertFalse(self.procs[0].alive)
        self.c.send('sigue')
        cmd = self.procs[1].args[0]
        self.assertEqual(cmd[cmd.index('--effort') + 1], 'max')
        self.assertEqual(cmd[cmd.index('--resume') + 1], 's-1')

    def test_cada_turno_cierra_con_su_pie(self):
        self.c.send('hola')
        self.c.feed({'type': 'system', 'subtype': 'init', 'session_id': 's', 'model': 'claude-opus-5-5',
                     'permissionMode': 'bypassPermissions'})
        self.c.feed({'type': 'result', 'subtype': 'success', 'duration_ms': 22900})
        self.assertEqual((self.c.entries[-1].kind, self.c.entries[-1].text),
                         ('foot', 'elyares-engineer · Opus 5.5 · 22.9 s'))

    def test_las_imagenes_van_antes_del_texto(self):
        self.assertTrue(self.c.send('', [b'png-1', b'png-2']))
        content = self.procs[0].sent()[0]['message']['content']
        self.assertEqual([b['type'] for b in content], ['image', 'image', 'text'])
        self.assertEqual(content[0]['source']['media_type'], 'image/png')
        self.assertEqual(content[2]['text'], 'Mira la imagen.')
        self.assertEqual(self.c.entries[-1].images, 2)

    def test_nombres_y_esfuerzo_por_defecto(self):
        self.assertEqual(chat.model_name('claude-haiku-4-5-20251001'), 'Haiku 4.5')
        self.assertEqual(chat.model_name('otro'), 'otro')
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump({'effortLevel': 'xhigh', 'modelSettings': {'claude-opus-5-5': {'effortLevel': 'high'}}}, f)
        self.addCleanup(os.unlink, f.name)
        self.assertEqual(chat.default_effort('claude-opus-5-5', f.name), 'high')
        self.assertEqual(chat.default_effort('claude-sonnet-5-5', f.name), 'xhigh')


class Carpeta(unittest.TestCase):
    def test_la_del_pane_de_tmux_usado_al_ultimo(self):
        with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
            out = f'100\tWork\t{old}\n300\ttl-mas-server\t{new}\n200\tx\t/no/existe\n'
            with mock.patch.object(chat.glob, 'glob', lambda pattern: ['/tmp/tmux-1000/default']), \
                    mock.patch.object(chat.subprocess, 'run', lambda *a, **k: mock.Mock(stdout=out)):
                self.assertEqual(chat.active_cwd(), new)
            # Un cliente anidado (la terminal flotante, en su sesión oculta) no cuenta.
            out = f'100\tWork\t{old}\n900\t_flotante\t{new}\n'
            with mock.patch.object(chat.glob, 'glob', lambda pattern: ['/tmp/tmux-1000/default']), \
                    mock.patch.object(chat.subprocess, 'run', lambda *a, **k: mock.Mock(stdout=out)):
                self.assertEqual(chat.active_cwd(), old)

    def test_sin_tmux_la_carpeta_personal(self):
        with mock.patch.object(chat.glob, 'glob', lambda pattern: []):
            self.assertEqual(chat.active_cwd(), os.path.expanduser('~'))
            self.assertEqual(chat.active_cwd('/x/ultimo'), '/x/ultimo')

    def test_los_comandos_locales_con_su_descripcion(self):
        with tempfile.TemporaryDirectory() as home:
            skill = os.path.join(home, '.claude', 'skills', 'bitacora')
            os.makedirs(skill)
            with open(os.path.join(skill, 'SKILL.md'), 'w') as f:
                f.write('---\nname: bitacora\ndescription: >\n  Registra la sesión\n  en el vault.\n'
                        'otra: cosa\n---\n# /bitacora\n')
            with mock.patch.object(chat.os.path, 'expanduser', lambda p: p.replace('~', home)):
                self.assertEqual(chat.local_commands(), {'bitacora': 'Registra la sesión en el vault.'})


class Markdown(unittest.TestCase):
    def test_lo_justo_para_leerlo(self):
        out = paint.markdown('## Hecho **ya**\n- uno `a<b`\n```\nx <y>\n```\n| a | b |\nfin & listo',
                             code='#111111', head='#ffffff')
        lines = out.split('\n')
        self.assertIn('weight="bold"', lines[0])
        self.assertIn('<b>ya</b>', lines[0])
        self.assertTrue(lines[1].startswith('• uno <span font_family="monospace" foreground="#111111">a&lt;b'))
        self.assertEqual(lines[2], '<span font_family="monospace" foreground="#111111">x &lt;y&gt;</span>')
        self.assertTrue(lines[3].endswith('>a  b</span>'))   # una sola fila no es cabecera
        self.assertEqual(lines[4], 'fin &amp; listo')

    def test_con_colores_tiene_jerarquia(self):
        src = ('## Hecho\n\nSe hizo **todo** con *cuidado* y `a_b_c **x**`, ver [el PR](https://x.mx/1).\n\n\n\n'
               '1. uno\n2) dos\n- punto\n  - hijo\n> una nota\n---\nfin\n')
        out = paint.markdown(src, code='#111111', head='#222222', bold='#ffffff', dim='#999999', accent='#00ff00')
        lines = out.split('\n')
        self.assertTrue(lines[0].startswith('<span foreground="#222222" weight="bold" size="large">Hecho'))
        self.assertEqual(lines[1], '')                                   # una sola línea en blanco
        self.assertIn('<span weight="bold" foreground="#ffffff">todo</span>', lines[2])
        self.assertIn('<i>cuidado</i>', lines[2])
        self.assertIn('<u>el PR</u>', lines[2])
        self.assertNotIn('https://x.mx', lines[2])
        # Lo que va entre acentos graves queda tal cual: ni cursivas ni negritas.
        self.assertIn('foreground="#111111">a_b_c **x**</span>', lines[2])
        self.assertEqual(lines[3], '')
        self.assertEqual(lines[4], '<span foreground="#00ff00" weight="bold">1.</span> uno')
        self.assertEqual(lines[5], '<span foreground="#00ff00" weight="bold">2.</span> dos')
        self.assertEqual(lines[6], '<span foreground="#00ff00">•</span> punto')
        self.assertEqual(lines[7], '  <span foreground="#00ff00">◦</span> hijo')
        self.assertTrue(lines[8].startswith('<span foreground="#00ff00">▎</span>'))
        self.assertIn('─' * 10, lines[9])
        self.assertEqual(lines[10], 'fin')
        self.assertEqual(len(lines), 11)                                 # sin línea en blanco al final
        # Un título tras un párrafo lleva su respiro; y un guion_bajo suelto no es cursiva.
        out = paint.markdown('texto\n## Título\nuna_variable_larga y snake_case', bold='#fff', dim='#999')
        self.assertEqual(out.split('\n')[1], '')
        self.assertIn('una_variable_larga y snake_case', out)

    def test_una_tabla_va_alineada_por_columnas(self):
        out = paint.markdown('| Rama | Estado |\n|---|:---:|\n| sprint-021026 | al día |\n| main | atrás |')
        rows = [line.split('">', 1)[1].rsplit('</span>', 1)[0] for line in out.split('\n')]
        self.assertEqual(rows, ['<b>Rama           Estado</b>', 'sprint-021026  al día', 'main           atrás'])


if __name__ == '__main__':
    unittest.main()
