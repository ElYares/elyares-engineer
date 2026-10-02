"""Lo que elyares-engineer hace fuera de sí mismo, sin lanzar nada de verdad."""

import types
import unittest
from unittest import mock

from elyares import actions


class Boton(unittest.TestCase):
    def popen(self, action, uwsm=False):
        which = (lambda name: '/usr/bin/uwsm-app') if uwsm else (lambda name: None)
        with mock.patch.object(actions.subprocess, 'Popen') as popen, \
                mock.patch.object(actions.shutil, 'which', which):
            actions.run(action)
        return popen.call_args.args[0] if popen.called else None

    def test_abre_una_url(self):
        with mock.patch.object(actions, '_run') as run:
            actions.run({'label': 'Abrir', 'url': 'http://x', 'cmd': ['no', 'corre']})
        run.assert_called_once_with('xdg-open', 'http://x', timeout=5.0)

    def test_comando_suelto(self):
        self.assertEqual(self.popen({'cmd': ['systemctl', '--user', 'start', 'x']}),
                         ['systemctl', '--user', 'start', 'x'])

    def test_en_una_terminal_que_espera(self):
        cmd = self.popen({'label': 'Logs', 'cmd': ['docker', 'logs', 'a b'], 'term': True,
                          'hold': True}, uwsm=True)
        self.assertEqual(cmd[:6], ['uwsm-app', '--', 'xdg-terminal-exec', '--title=Logs', '-e', 'bash'])
        # Los argumentos van entre comillas: un espacio no parte el comando.
        self.assertIn("docker logs 'a b';", cmd[-1])
        self.assertTrue(cmd[-1].startswith('trap : INT;'))

    def test_en_una_terminal_sin_esperar(self):
        cmd = self.popen({'label': 'x', 'cmd': ['ls'], 'term': True})
        self.assertEqual(cmd, ['xdg-terminal-exec', '--title=x', '-e', 'bash', '-c', 'ls'])

    def test_sin_nada_que_hacer(self):
        self.assertIsNone(self.popen({'label': 'x'}))


class Salto(unittest.TestCase):
    def test_una_alerta_con_url_la_abre(self):
        with mock.patch.object(actions, '_run') as run:
            actions.jump(types.SimpleNamespace(url='http://x', pane='%1', tmux=''))
        run.assert_called_once_with('xdg-open', 'http://x', timeout=5.0)

    def tmux(self, clients):
        """Un tmux de mentira: la sesión del pane es Work y hay estos clientes."""
        calls = []

        def run(*cmd, timeout=1.0):
            calls.append(cmd)
            if 'display-message' in cmd:
                return 'Work'
            if 'list-panes' in cmd:
                return '/dev/pts/9'
            if 'list-clients' in cmd:
                return '\n'.join('\t'.join(c) for c in clients)
            return ''

        with mock.patch.object(actions, '_run', run), \
                mock.patch.object(actions.shutil, 'which', lambda name: '/usr/bin/tmux'):
            actions.jump(types.SimpleNamespace(url='', pane='%4', tmux='/tmp/sock,1,0'))
        return [c[3:] for c in calls if c[:3] == ('tmux', '-S', '/tmp/sock')]

    def test_lleva_al_pane(self):
        calls = self.tmux([('10', '/dev/pts/1', 'Work')])
        self.assertEqual(calls[-2:], [('select-window', '-t', '%4'), ('select-pane', '-t', '%4')])
        self.assertFalse(any(c[0] == 'switch-client' for c in calls))

    def test_mueve_la_terminal_usada_al_ultimo_y_nunca_una_anidada(self):
        calls = self.tmux([('10', '/dev/pts/1', 'Otra'), ('30', '/dev/pts/2', 'Otra'),
                           ('99', '/dev/pts/9', 'Otra'),      # su tty es el de un pane
                           ('98', '/dev/pts/3', '_popup')])   # sesión oculta
        self.assertIn(('switch-client', '-c', '/dev/pts/2', '-t', 'Work'), calls)


class Panes(unittest.TestCase):
    def test_live_panes(self):
        def run(cmd, **kw):
            ok = cmd[2] == '/vivo'
            return types.SimpleNamespace(returncode=0 if ok else 1,
                                         stdout='10 %1\n10 %2\n' if ok else '')

        with mock.patch.object(actions.subprocess, 'run', run), \
                mock.patch.object(actions.shutil, 'which', lambda name: '/usr/bin/tmux'):
            live = actions.live_panes(['/vivo', '/muerto'])
        # Un servidor que ya no corre sale sin panes.
        self.assertEqual(live, {'/vivo': {('10', '%1'), ('10', '%2')}, '/muerto': set()})


if __name__ == '__main__':
    unittest.main()
