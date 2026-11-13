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


CONF_DE_YARED = '''set -g prefix C-a
set -g status-right "#(tmux-claude bar)"
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'tmux-plugins/tmux-continuum'
set -g @continuum-restore 'on'
set -g @resurrect-capture-pane-contents 'on'
run-shell -b 'tmux-keys sync'
run '~/.config/tmux/plugins/tpm/tpm'
bind r source-file ~/.tmux.conf
'''


class ConfiguracionDelServidor(unittest.TestCase):
    def test_se_van_los_plugins_y_la_restauracion_automatica_y_se_queda_lo_demas(self):
        got = terminal.without_plugins(CONF_DE_YARED)
        for gone in ('@plugin', '@continuum', '@resurrect', 'tpm/tpm', 'tmux-keys sync'):
            self.assertNotIn(gone, got)
        self.assertIn('set -g prefix C-a', got)
        self.assertIn('tmux-claude bar', got)
        self.assertIn('bind r source-file', got)

    def test_sin_nada_que_quitar_queda_igual(self):
        self.assertEqual(terminal.without_plugins('set -g mouse on\n'), 'set -g mouse on\n')


class Entorno(unittest.TestCase):
    def test_la_terminal_no_hereda_lo_del_servicio(self):
        base = {'PATH': '/usr/bin', 'HOME': '/h', 'PYTHONPATH': '/repo', 'LD_PRELOAD': '/lib/x.so',
                'INVOCATION_ID': 'abc', 'JOURNAL_STREAM': '1:2'}
        self.assertEqual(terminal.clean_env(base), {'PATH': '/usr/bin', 'HOME': '/h'})


class NadieEscribeEnLaTerminal(unittest.TestCase):
    """La regla de diseño: la app nunca teclea en la terminal ni en nvim; lo que corre ahí lo teclea Yared."""

    def test_ningun_modulo_manda_texto_a_un_pty_ni_a_tmux(self):
        root = os.path.join(os.path.dirname(__file__), '..', 'elyares')
        for name in sorted(os.listdir(root)):
            if not name.endswith('.py'):
                continue
            with open(os.path.join(root, name), encoding='utf-8') as fh:
                text = fh.read()
            banned = ['feed_child', 'send-keys', 'paste-buffer', '--remote-send', '--remote-expr']
            if name != 'terminal.py':       # ahí `run-shell` solo corre los scripts de resurrect (`_script`, rutas fijas)
                banned.append('run-shell')
            for word in banned:
                self.assertNotIn(word, text, f'{name} usa {word}')


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
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, 'data')
        self.user_conf = os.path.join(self.tmp.name, 'user-tmux.conf')
        with open(self.user_conf, 'w') as fh:
            fh.write('set -g status off\n')
        # Nada de esto toca lo real: ni la carpeta de la app, ni la configuración de Yared.
        self.sock = mock.patch.multiple(terminal, SOCKET=f'elyares-test-{os.getpid()}', DATA_DIR=self.data,
                                        RESURRECT_DIR=os.path.join(self.data, 'resurrect'),
                                        CONF=os.path.join(self.data, 'tmux.conf'), USER_CONFS=(self.user_conf,))
        self.sock.start()

    def tearDown(self):
        subprocess.run(['tmux', '-L', terminal.SOCKET, 'kill-server'], capture_output=True)
        try:
            os.remove(f'/tmp/tmux-{os.getuid()}/{terminal.SOCKET}')     # `kill-server` deja el archivo del socket
        except OSError:
            pass
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
        self.addCleanup(lambda: os.path.exists(sock) and os.remove(sock))
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

    def test_el_servidor_de_la_app_arranca_sin_continuum_y_con_su_carpeta_de_guardado(self):
        with open(self.user_conf, 'w') as fh:
            fh.write(CONF_DE_YARED.replace('bind r source-file ~/.tmux.conf', 'set -g mouse on'))
        name, why = terminal.ensure(self.tmp.name)
        self.assertEqual(why, '')
        opts = subprocess.run(['tmux', '-L', terminal.SOCKET, 'show-options', '-g'], capture_output=True,
                              text=True).stdout
        self.assertIn('mouse on', opts)                          # lo de Yared sí entra
        self.assertNotIn('@continuum-restore on', opts)          # su restauración automática no
        self.assertNotIn('@continuum-save-interval', opts)
        if terminal._plugin():
            self.assertIn(os.path.join(self.data, 'resurrect'), opts)   # y guarda aparte de lo de Yared
        with open(terminal.CONF) as fh:
            self.assertNotIn('@continuum', fh.read())

    @unittest.skipUnless(terminal._plugin(), 'sin tmux-resurrect')
    def test_guarda_y_restaura_las_sesiones_tras_matar_el_servidor(self):
        a, b = os.path.join(self.tmp.name, 'a'), os.path.join(self.tmp.name, 'b')
        os.mkdir(a)
        os.mkdir(b)
        name_a, _ = terminal.ensure(a)
        name_b, _ = terminal.ensure(b)
        self.assertTrue(terminal.save())
        self.assertTrue(os.path.exists(os.path.join(self.data, 'resurrect', 'last')))
        subprocess.run(['tmux', '-L', terminal.SOCKET, 'kill-server'], capture_output=True)
        time.sleep(0.5)
        self.assertFalse(terminal.server_running())
        terminal.ensure(a)              # un servidor nuevo: sale con lo guardado
        for _ in range(60):
            if terminal.has(name_b):
                break
            time.sleep(0.1)
        self.assertTrue(terminal.has(name_a))
        self.assertTrue(terminal.has(name_b))

    def test_sin_servidor_no_hay_nada_que_guardar(self):
        self.assertFalse(terminal.save())

    @unittest.skipUnless(shutil.which('nvim'), 'sin nvim')
    def test_una_sesion_de_nvim_que_no_escucha_se_rehace(self):
        name, _ = terminal.ensure(self.tmp.name, terminal.NVIM)
        sock = terminal.nvim_socket(name)
        self.addCleanup(lambda: os.path.exists(sock) and os.remove(sock))
        for _ in range(60):
            if os.path.exists(sock):
                break
            time.sleep(0.1)
        os.remove(sock)                 # como una sesión restaurada: existe, pero sin socket
        terminal.ensure(self.tmp.name, terminal.NVIM)
        for _ in range(60):
            if os.path.exists(sock):
                break
            time.sleep(0.1)
        self.assertTrue(os.path.exists(sock))

    def test_un_comando_en_el_nombre_de_la_carpeta_no_se_ejecuta(self):
        # tmux pasa lo de `-c` por sus formatos: `#(comando)` en la ruta se ejecutaba (tmux 3.8).
        marca = f'MARCA-{os.getpid()}'
        carpeta = os.path.join(self.tmp.name, f'a#(touch {marca})')
        os.mkdir(carpeta)
        name, why = terminal.ensure(carpeta)
        self.assertEqual(why, '')
        self.assertTrue(terminal.has(name))
        time.sleep(0.5)
        for donde in (carpeta, self.tmp.name, os.getcwd(), os.path.expanduser('~')):
            self.assertFalse(os.path.exists(os.path.join(donde, marca)), f'se ejecutó en {donde}')

    def test_no_abre_un_enlace_que_sale_del_proyecto(self):
        os.symlink('/etc', os.path.join(self.tmp.name, 'enlace'))
        self.assertEqual(terminal.open_in_nvim(self.tmp.name, 'enlace/passwd'), (False, 'Fuera del proyecto'))

    def test_no_abre_un_nombre_con_caracteres_de_control(self):
        for name in ('a\nb.py', 'a\rb.py', 'a\x00b.py'):
            self.assertEqual(terminal.open_in_nvim(self.tmp.name, name), (False, 'Nombre de archivo no válido'))

    def test_no_abre_nada_fuera_del_proyecto(self):
        ok, why = terminal.open_in_nvim(self.tmp.name, '../etc/passwd')
        self.assertEqual((ok, why), (False, 'Fuera del proyecto'))

    def test_sin_nvim_escuchando_se_dice(self):
        self.assertEqual(terminal.open_in_nvim(self.tmp.name, 'a.txt'), (False, 'nvim aún no está listo'))

    def test_una_carpeta_que_no_existe_se_avisa(self):
        _, why = terminal.ensure('/no/existe/de/verdad')
        self.assertIn('ya no existe', why)


TEMA_A = '''background = "#112233"
foreground = "#ddeeff"
cursor = "#ff8800"
selection_background = "#334455"
selection_foreground = "#ffffff"
''' + ''.join(f'color{i} = "#{i:02x}{i:02x}{i:02x}"\n' for i in range(16))


class TemaDeLaTerminal(unittest.TestCase):
    """La terminal sigue la misma regla que la barra de tmux de Yared: su tema de terminal, y si no, el de omarchy."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': self.tmp.name})
        patch.start()
        self.addCleanup(patch.stop)

    def put(self, *parts, text=TEMA_A):
        path = os.path.join(self.tmp.name, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as fh:
            fh.write(text)
        return path

    def test_gana_el_tema_de_terminal_si_existe(self):
        from elyares import theme
        omarchy = self.put('omarchy', 'current', 'theme', 'colors.toml', text='background = "#000000"\n')
        self.assertEqual(theme.terminal_path(), omarchy)
        own = self.put('terminal-theme', 'colors.toml')
        self.assertEqual(theme.terminal_path(), own)
        self.assertEqual(theme.terminal_palette()['background'], '#112233')

    def test_sin_tema_de_terminal_sigue_a_omarchy(self):
        from elyares import theme
        self.put('omarchy', 'current', 'theme', 'colors.toml')
        self.assertEqual(theme.terminal_palette()['color15'], '#0f0f0f')

    def test_cambiar_de_tema_cambia_la_marca(self):
        from elyares import theme
        path = self.put('terminal-theme', 'colors.toml')
        before = theme.terminal_stamp()
        os.utime(path, ns=(1, 1))
        self.assertNotEqual(theme.terminal_stamp(), before)

    def test_sin_ningun_tema_la_paleta_queda_vacia_y_la_marca_no_falla(self):
        from elyares import theme
        self.assertEqual(theme.terminal_palette(), {})
        self.assertEqual(theme.terminal_stamp()[1], 0)


@unittest.skipUnless(shutil.which('tmux'), 'sin tmux')
class RecargaDeLaBarra(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.val = os.path.join(self.tmp.name, 'val')
        script = os.path.join(self.tmp.name, 'omarchy-theme.sh')
        with open(script, 'w') as fh:
            fh.write(f'tmux set -g @thm_probe "$(cat {self.val})"\n')
        self.user_conf = os.path.join(self.tmp.name, 'user.conf')
        with open(self.user_conf, 'w') as fh:
            fh.write(f'run-shell "bash {script}"\n')
        self.write('a')
        data = os.path.join(self.tmp.name, 'data')
        patch = mock.patch.multiple(terminal, SOCKET=f'elyares-theme-{os.getpid()}', DATA_DIR=data,
                                    RESURRECT_DIR=os.path.join(data, 'r'), CONF=os.path.join(data, 'tmux.conf'),
                                    USER_CONFS=(self.user_conf,))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.cleanup)
        terminal._themed[0] = None

    def cleanup(self):
        subprocess.run(['tmux', '-L', terminal.SOCKET, 'kill-server'], capture_output=True)
        try:
            os.remove(f'/tmp/tmux-{os.getuid()}/{terminal.SOCKET}')
        except OSError:
            pass
        terminal._themed[0] = None

    def write(self, text):
        with open(self.val, 'w') as fh:
            fh.write(text)

    def probe(self):
        return subprocess.run(['tmux', '-L', terminal.SOCKET, 'show-options', '-gv', '@thm_probe'],
                              capture_output=True, text=True).stdout.strip()

    def test_al_cambiar_el_tema_la_barra_carga_la_paleta_nueva(self):
        terminal.ensure(self.tmp.name)
        time.sleep(0.5)
        self.assertEqual(self.probe(), 'a')                 # al arrancar el servidor, con el tema de entonces
        self.assertFalse(terminal.reload_theme('v1'))       # la primera marca solo se anota
        self.write('b')
        self.assertTrue(terminal.reload_theme('v2'))
        self.assertEqual(self.probe(), 'b')

    def test_la_misma_marca_no_recarga_dos_veces(self):
        terminal.ensure(self.tmp.name)
        terminal.reload_theme('v1')
        self.write('b')
        self.assertTrue(terminal.reload_theme('v2'))
        self.write('c')
        self.assertFalse(terminal.reload_theme('v2'))
        self.assertEqual(self.probe(), 'b')

    def test_sin_servidor_no_hace_nada(self):
        terminal.reload_theme('v1')
        self.assertFalse(terminal.reload_theme('v2'))


try:
    import gi as _gi
    _gi.require_version('Gtk', '4.0')
    _gi.require_version('Vte', '3.91')
    from gi.repository import Gtk as _Gtk
    from elyares import terminalpanel as _terminalpanel
    _DISPLAY = _Gtk.init_check()
except (ImportError, ValueError):
    _DISPLAY = False


@unittest.skipUnless(_DISPLAY, 'sin gi, Vte o pantalla')
class ColoresDelPanel(unittest.TestCase):
    def setUp(self):
        self.panel = _terminalpanel.TerminalPanel()
        for target in ('ensure', 'reload_theme'):
            patch = mock.patch.object(terminal, target, return_value=('x', ''))
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(_terminalpanel.TerminalPanel, 'spawn', lambda *a: None)
        patch.start()
        self.addCleanup(patch.stop)

    def colors(self, pal):
        with mock.patch.object(_terminalpanel.theme, 'terminal_palette', return_value=pal), \
                mock.patch.object(self.panel.term, 'set_colors') as set_colors:
            self.panel._colors()
        return set_colors.call_args[0]

    @staticmethod
    def hexed(rgba):
        return '#%02x%02x%02x' % tuple(round(c * 255) for c in (rgba.red, rgba.green, rgba.blue))

    def test_texto_fondo_y_los_16_ansi_salen_del_tema_de_la_terminal(self):
        from elyares import theme
        pal = {'foreground': '#ddeeff', 'background': '#112233', **{f'color{i}': f'#{i:02x}{i:02x}{i:02x}' for i in range(16)}}
        fg, bg, ansi = self.colors(pal)
        self.assertEqual((self.hexed(fg), self.hexed(bg)), ('#ddeeff', '#112233'))
        self.assertEqual([self.hexed(c) for c in ansi], [pal[f'color{i}'] for i in range(16)])

    def test_con_una_paleta_incompleta_los_ansi_quedan_por_defecto(self):
        _fg, _bg, ansi = self.colors({'foreground': '#ddeeff', 'background': '#112233', 'color1': '#aa0000'})
        self.assertIsNone(ansi)

    def test_sin_tema_de_terminal_se_usan_los_de_la_app(self):
        from elyares import themes
        fg, bg, _ansi = self.colors({})
        self.assertEqual((self.hexed(fg), self.hexed(bg)), (themes.get()['ink'].lower(), themes.get()['surface'][0].lower()))

    def test_cambiar_de_tema_repinta_y_pide_recargar_la_barra(self):
        with mock.patch.object(_terminalpanel.theme, 'terminal_stamp', side_effect=[('t', 1), ('t', 1), ('t', 2)]), \
                mock.patch.object(self.panel, '_colors') as colors:
            self.panel.set_terminal('', True)
            self.panel.set_terminal('', True)       # misma marca: nada
            self.panel.set_terminal('', True)       # marca nueva: repinta
            for _ in range(50):                      # la recarga corre en un hilo
                if terminal.reload_theme.call_count >= 2:
                    break
                time.sleep(0.02)
        self.assertEqual(colors.call_count, 2)
        self.assertEqual([c[0][0] for c in terminal.reload_theme.call_args_list], [('t', 1), ('t', 2)])


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
