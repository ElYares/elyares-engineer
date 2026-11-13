"""La terminal de la ventana: sesión de tmux por proyecto en su propio servidor."""

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from elyares import terminal

HAVE_TMUX = shutil.which('tmux') is not None


class Nombres(unittest.TestCase):
    def test_un_nombre_que_tmux_acepta(self):
        name = terminal.session_name('/home/yo/mi proyecto.v2/api')
        self.assertRegex(name, r'^[A-Za-z0-9_-]+$')
        self.assertTrue(name.startswith('api-'))

    def test_dos_carpetas_con_el_mismo_nombre_no_comparten_sesion(self):
        self.assertNotEqual(terminal.session_name('/a/api'), terminal.session_name('/b/api'))

    def test_el_mismo_proyecto_siempre_la_misma_sesion(self):
        self.assertEqual(terminal.session_name('/a/api'), terminal.session_name('/a/api/'))

    def test_la_sesion_de_nvim_es_otra_de_la_misma_carpeta(self):
        plain, nvim = terminal.session_name('/a/api'), terminal.session_name('/a/api', terminal.NVIM)
        self.assertNotEqual(plain, nvim)
        self.assertTrue(nvim.startswith(plain))
        self.assertRegex(nvim, r'^[A-Za-z0-9_-]+$')

    def test_engancha_con_el_servidor_propio(self):
        argv = terminal.attach_argv('api-1')
        self.assertEqual(argv[:3], ['tmux', '-L', terminal.SOCKET])
        self.assertIn('=api-1', argv)


@unittest.skipUnless(HAVE_TMUX, 'sin tmux')
class Sesion(unittest.TestCase):
    def setUp(self):
        self.sock = mock.patch.object(terminal, 'SOCKET', f'elyares-test-{os.getpid()}')
        self.sock.start()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        subprocess.run(['tmux', '-L', terminal.SOCKET, 'kill-server'], capture_output=True)
        self.sock.stop()
        self.tmp.cleanup()

    def test_crea_la_sesion_una_sola_vez(self):
        name, why = terminal.ensure(self.tmp.name)
        self.assertEqual(why, '')
        self.assertTrue(terminal.has(name))
        self.assertEqual(terminal.ensure(self.tmp.name), (name, ''))

    def test_la_sesion_nace_en_la_carpeta_del_proyecto(self):
        name, _ = terminal.ensure(self.tmp.name)
        want, got = os.path.realpath(self.tmp.name), ''
        for _ in range(40):         # el shell del panel tarda un instante en arrancar y fijar su carpeta
            out = subprocess.run(['tmux', '-L', terminal.SOCKET, 'list-panes', '-t', f'={name}', '-F',
                                  '#{pane_current_path}'], capture_output=True, text=True)
            got = os.path.realpath(out.stdout.strip())
            if got == want:
                break
            time.sleep(0.1)
        self.assertEqual(got, want)

    @unittest.skipUnless(shutil.which('nvim'), 'sin nvim')
    def test_nvim_arranca_escuchando_y_abre_un_archivo_a_peticion(self):
        name, why = terminal.ensure(self.tmp.name, terminal.NVIM)
        self.assertEqual(why, '')
        sock = terminal.nvim_socket(name)
        for _ in range(60):                 # nvim tarda un instante en crear su socket
            if os.path.exists(sock):
                break
            time.sleep(0.1)
        target = os.path.join(self.tmp.name, 'a.txt')
        with open(target, 'w') as fh:
            fh.write('hola\n')
        self.assertEqual(terminal.open_in_nvim(self.tmp.name, 'a.txt'), (True, ''))
        got = subprocess.run(['nvim', '--server', sock, '--remote-expr', 'expand("%:p")'],
                             capture_output=True, text=True).stdout.strip()
        self.assertEqual(os.path.realpath(got), os.path.realpath(target))

    def test_no_abre_nada_fuera_del_proyecto(self):
        ok, why = terminal.open_in_nvim(self.tmp.name, '../etc/passwd')
        self.assertEqual((ok, why), (False, 'Fuera del proyecto'))

    def test_sin_nvim_escuchando_se_dice(self):
        self.assertEqual(terminal.open_in_nvim(self.tmp.name, 'a.txt'), (False, 'nvim aún no está listo'))

    def test_una_carpeta_que_no_existe_se_avisa(self):
        _, why = terminal.ensure('/no/existe/de/verdad')
        self.assertIn('ya no existe', why)


if __name__ == '__main__':
    unittest.main()


try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Vte', '3.91')
    from gi.repository import Gtk
    from elyares import terminalpanel
    HAVE_DISPLAY = Gtk.init_check()
except (ImportError, ValueError):
    HAVE_DISPLAY = False


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi, Vte o pantalla')
class Panel(unittest.TestCase):
    def setUp(self):
        self.panel = terminalpanel.TerminalPanel()
        self.opened = []
        patch = mock.patch.object(terminal, 'ensure', side_effect=lambda root, kind='': (terminal.session_name(root, kind), ''))
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(terminalpanel.TerminalPanel, 'spawn', lambda _s, root, name: self.opened.append(name))
        patch.start()
        self.addCleanup(patch.stop)

    def settle(self):
        from gi.repository import GLib
        ctx = GLib.MainContext.default()
        for _ in range(50):
            while ctx.iteration(False):
                pass
            time.sleep(0.01)

    def test_sin_proyecto_no_abre_nada_y_lo_dice(self):
        self.panel.set_terminal('', True)
        self.settle()
        self.assertEqual(self.opened, [])
        self.assertTrue(self.panel.note.get_visible())

    def test_se_engancha_una_vez_y_otra_al_cambiar_de_proyecto(self):
        self.panel.set_terminal('/tmp', True)
        self.settle()
        self.panel.set_terminal('/tmp', True)
        self.settle()
        self.assertEqual(len(self.opened), 1)
        self.panel.set_terminal('/usr', True)
        self.settle()
        self.assertEqual(len(self.opened), 2)

    def test_escondida_no_hace_nada(self):
        self.panel.set_terminal('/tmp', False)
        self.settle()
        self.assertEqual(self.opened, [])

    def test_si_tmux_falla_se_dice_y_se_puede_reintentar(self):
        with mock.patch.object(terminal, 'ensure', return_value=('x', 'No está instalado tmux')):
            self.panel.set_terminal('/tmp', True)
            self.settle()
        self.assertIn('No está instalado tmux', self.panel.note.get_text())
        self.assertTrue(self.panel.again.get_visible())

    def test_la_app_no_puede_escribir_en_la_terminal(self):
        public = [n for n in dir(terminalpanel.TerminalPanel) if not n.startswith('_')]
        self.assertFalse([n for n in public if 'feed' in n or 'send' in n or 'write' in n or 'paste' in n])
