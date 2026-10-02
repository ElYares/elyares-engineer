"""El socket de punta a punta: `ipc.serve` con `elyares-hook` y `elyares-ctl` de verdad."""

import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from elyares import actions, ipc

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin')


class Socket(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.addClassCleanup(shutil.rmtree, cls.dir, ignore_errors=True)
        cls.env = {**os.environ, 'XDG_RUNTIME_DIR': cls.dir}
        cls.env.pop('TMUX_PANE', None)
        cls.msgs, cls.gone = queue.Queue(), queue.Queue()
        cls.answer = None           # lo que se le contesta a quien espera
        with mock.patch.dict(os.environ, {'XDG_RUNTIME_DIR': cls.dir}):
            cls.path = ipc.serve(cls.on_message, cls.gone.put)

    @classmethod
    def on_message(cls, msg, req):
        cls.msgs.put((msg, req))
        if req and cls.answer is not None:
            req.reply(cls.answer)

    def setUp(self):
        type(self).answer = None

    def run_bin(self, name, *args, stdin=''):
        return subprocess.run([sys.executable, os.path.join(BIN, name), *args], input=stdin,
                              capture_output=True, text=True, env=self.env, timeout=10)

    def next(self):
        return self.msgs.get(timeout=5)

    def test_el_socket_es_solo_del_usuario(self):
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_el_hook_manda_lo_justo(self):
        payload = {'session_id': 's1', 'cwd': '/x', 'tool_name': 'Edit', 'transcript_path': '/t',
                   'tool_input': {'file_path': '/x/a.py', 'old_string': 'a' * 9000,
                                  'new_string': 'b', 'replace_all': True}}
        r = self.run_bin('elyares-hook', 'tool', stdin=json.dumps(payload))
        self.assertEqual((r.returncode, r.stdout), (0, ''))
        msg, req = self.next()
        self.assertIsNone(req)
        self.assertEqual((msg['event'], msg['session_id'], msg['cwd']), ('tool', 's1', '/x'))
        self.assertNotIn('transcript_path', msg)
        self.assertEqual(set(msg['tool_input']), {'file_path', 'old_string', 'new_string'})
        self.assertEqual(len(msg['tool_input']['old_string']), 6000)

    def test_el_hook_dice_que_proceso_es_la_sesion(self):
        self.run_bin('elyares-hook', 'start', stdin=json.dumps({'session_id': 's1'}))
        msg, _ = self.next()
        # Quien lanzó el hook es este proceso de pruebas: hace de Claude.
        pid, _, start = msg['proc'].partition(':')
        self.assertEqual(int(pid), os.getpid())
        self.assertTrue(actions.proc_alive(msg['proc']))
        self.assertFalse(actions.proc_alive(f'{pid}:{int(start) + 1}'))
        self.assertFalse(actions.proc_alive('no-es-un-pid'))
        self.assertEqual(msg['kind'], '')
        self.assertNotIn('label', msg)

    def test_el_hook_de_una_sesion_de_segundo_plano(self):
        # El nombre va en el entorno de la sesión, que no se lo pasa al hook:
        # un proceso de por medio hace de sesión y lanza el hook sin él.
        env = {**self.env, 'CLAUDE_CODE_SESSION_KIND': 'bg', 'CLAUDE_CODE_SESSION_NAME': 'Mejoras'}
        claude = ('import json, subprocess, sys; subprocess.run([sys.executable, sys.argv[1], "tool"],'
                  ' input=json.dumps({"session_id": sys.argv[2]}), text=True,'
                  f' env={self.env!r})')
        run = lambda sid: subprocess.run(
            [sys.executable, '-c', claude, os.path.join(BIN, 'elyares-hook'), sid], env=env, timeout=10)
        run('f67bcd7d-c4dc')
        msg, _ = self.next()
        self.assertEqual((msg['kind'], msg['label']), ('bg', 'Mejoras'))
        # Sin nombre propio, Claude Code le pone el principio de su id: no dice nada.
        run('Mejoras-1234')
        msg, _ = self.next()
        self.assertNotIn('label', msg)

    def test_la_barra_de_estado_no_dice_de_que_proceso_viene(self):
        self.run_bin('elyares-hook', 'status', stdin=json.dumps({'session_id': 's1', 'context_pct': 5}))
        msg, _ = self.next()
        self.assertNotIn('proc', msg)

    def test_el_hook_manda_lo_que_imprimio_un_comando_largo(self):
        payload = {'session_id': 'cmd:%1', 'cwd': '/x', 'command': 'make', 'exit_code': 2,
                   'seconds': 40, 'output': ['uno', 'dos']}
        self.run_bin('elyares-hook', 'cmd-done', stdin=json.dumps(payload))
        msg, _ = self.next()
        self.assertEqual((msg['exit_code'], msg['seconds'], msg['output']), (2, 40, ['uno', 'dos']))

    def test_el_hook_manda_lo_que_imprimieron_las_pruebas_de_claude(self):
        base = {'session_id': 's1', 'cwd': '/x', 'tool_name': 'Bash'}
        # Acabó bien: PostToolUse lo trae en tool_response.
        self.run_bin('elyares-hook', 'tool-done', stdin=json.dumps({
            **base, 'tool_input': {'command': 'make test'},
            'tool_response': {'stdout': 'Ran 2 tests in 0.1s\n\nOK', 'stderr': '', 'interrupted': False}}))
        msg, _ = self.next()
        self.assertEqual(msg['output'], 'Ran 2 tests in 0.1s\n\nOK')
        self.assertNotIn('tool_response', msg)
        # Acabó con error: PostToolUseFailure lo trae en error.
        self.run_bin('elyares-hook', 'tool-fail', stdin=json.dumps({
            **base, 'tool_input': {'command': 'cd api && go test ./...'},
            'error': 'Exit code 1\n--- FAIL: TestResta (0.00s)'}))
        msg, _ = self.next()
        self.assertEqual((msg['event'], msg['output']), ('tool-fail', 'Exit code 1\n--- FAIL: TestResta (0.00s)'))
        # Solo el final de una salida enorme.
        self.run_bin('elyares-hook', 'tool-done', stdin=json.dumps({
            **base, 'tool_input': {'command': 'pytest'}, 'tool_response': {'stdout': 'x' * 70000 + 'fin'}}))
        msg, _ = self.next()
        self.assertEqual((len(msg['output']), msg['output'][-3:]), (64000, 'fin'))

    def test_el_hook_no_manda_la_salida_de_lo_que_no_son_pruebas(self):
        for payload in ({'tool_name': 'Bash', 'tool_input': {'command': 'cat secretos.env'},
                         'tool_response': {'stdout': 'CLAVE=123'}},
                        {'tool_name': 'Read', 'tool_input': {'file_path': '/x/pytest'},
                         'tool_response': {'stdout': 'CLAVE=123'}},
                        {'tool_name': 'Bash', 'tool_response': {'stdout': 'CLAVE=123'}}):
            self.run_bin('elyares-hook', 'tool-done', stdin=json.dumps({'session_id': 's1', **payload}))
            msg, _ = self.next()
            self.assertNotIn('output', msg)
            self.assertNotIn('CLAVE', json.dumps(msg))

    def test_el_hook_sin_mascota_sale_callado(self):
        r = subprocess.run([sys.executable, os.path.join(BIN, 'elyares-hook'), 'tool'], input='{}',
                           capture_output=True, text=True, timeout=10,
                           env={**self.env, 'XDG_RUNTIME_DIR': os.path.join(self.dir, 'nada')})
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))

    def test_una_orden_llega_con_quien_la_mando(self):
        r = self.run_bin('elyares-ctl', 'open')
        self.assertEqual(r.returncode, 0)
        msg, req = self.next()
        self.assertEqual(msg['control'], 'open')
        self.assertIsNone(req)

    def test_quien_la_mando_no_se_puede_falsear(self):
        type(self).answer = {}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.path)
            s.sendall(b'{"control": "allow", "peer": ["Hyprland"], "reply": true}\n')
            msg, _ = self.next()
            s.recv(64)
        # Lo pone el socket, con el proceso de verdad: este mismo.
        self.assertNotEqual(msg['peer'], ['Hyprland'])
        with open(f'/proc/{os.getpid()}/comm') as f:
            self.assertEqual(msg['peer'][0], f.read().strip())

    def test_allow_espera_la_respuesta(self):
        type(self).answer = {'ok': True, 'why': ''}
        r = self.run_bin('elyares-ctl', 'allow')
        self.assertEqual((r.returncode, r.stderr), (0, ''))
        msg, req = self.next()
        self.assertEqual(msg['control'], 'allow')
        self.assertIsNotNone(req)
        self.assertTrue(msg['peer'])

    def test_deny_rechazado_dice_por_que(self):
        type(self).answer = {'ok': False, 'why': 'no hay ningún permiso a la vista'}
        r = self.run_bin('elyares-ctl', 'deny')
        self.assertEqual(r.returncode, 1)
        self.assertIn('no hay ningún permiso a la vista', r.stderr)
        self.next()

    def test_status(self):
        type(self).answer = {'sources': [{'key': 'github', 'label': 'GitHub', 'state': 'on',
                                          'note': '2 cuentas'}]}
        r = self.run_bin('elyares-ctl', 'status')
        self.assertEqual(r.stdout.split(), ['GitHub', 'conectada', '2', 'cuentas'])
        self.next()

    def test_orden_desconocida(self):
        self.assertEqual(self.run_bin('elyares-ctl', 'bailar').returncode, 2)
        self.assertEqual(self.run_bin('elyares-ctl', 'toggle', 'nada').returncode, 2)
        self.assertTrue(self.msgs.empty())

    def test_ctl_sin_mascota(self):
        r = subprocess.run([sys.executable, os.path.join(BIN, 'elyares-ctl'), 'open'],
                           capture_output=True, text=True, timeout=10,
                           env={**self.env, 'XDG_RUNTIME_DIR': os.path.join(self.dir, 'nada')})
        self.assertEqual(r.returncode, 1)

    def test_el_que_espera_y_se_va(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.path)
            s.sendall(b'{"event": "ask", "reply": true}\n')
            _, req = self.next()
        self.assertIs(self.gone.get(timeout=5), req)
        self.assertTrue(req.done)

    def test_basura_no_tumba_el_socket(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.path)
            s.sendall(b'no es json\n[1, 2]\n')
        self.run_bin('elyares-ctl', 'open')
        self.assertEqual(self.next()[0]['control'], 'open')


class Padres(unittest.TestCase):
    def test_peer_names(self):
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        names = ipc.peer_names(a)
        with open(f'/proc/{os.getpid()}/comm') as f:
            self.assertEqual(names[0], f.read().strip())
        self.assertEqual(ipc.peer_names(a, depth=1), names[:1])

    def test_sin_socket_de_verdad(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(s.close)
        self.assertEqual(ipc.peer_names(s), [])


if __name__ == '__main__':
    unittest.main()
