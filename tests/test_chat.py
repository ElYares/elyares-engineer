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

    def test_una_herramienta_es_un_paso(self):
        self.c.send('lee')
        self.c.feed({'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': '/x/proj/docs/INDEX.md'}}]}})
        self.assertEqual((self.c.entries[-1].kind, self.c.entries[-1].text), ('tool', 'Leyendo docs/INDEX.md'))

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
            out = f'100 {old}\n300 {new}\n200 /no/existe\n'
            with mock.patch.object(chat.glob, 'glob', lambda pattern: ['/tmp/tmux-1000/default']), \
                    mock.patch.object(chat.subprocess, 'run', lambda *a, **k: mock.Mock(stdout=out)):
                self.assertEqual(chat.active_cwd(), new)

    def test_sin_tmux_la_carpeta_personal(self):
        with mock.patch.object(chat.glob, 'glob', lambda pattern: []):
            self.assertEqual(chat.active_cwd(), os.path.expanduser('~'))

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

    def test_una_tabla_va_alineada_por_columnas(self):
        out = paint.markdown('| Rama | Estado |\n|---|:---:|\n| sprint-021026 | al día |\n| main | atrás |')
        rows = [line.split('">', 1)[1].rsplit('</span>', 1)[0] for line in out.split('\n')]
        self.assertEqual(rows, ['<b>Rama           Estado</b>', 'sprint-021026  al día', 'main           atrás'])


if __name__ == '__main__':
    unittest.main()
