"""El lado de git del editor: qué cambió, su diff y el archivo."""

import os
import subprocess
import tempfile
import unittest

from elyares import gitview


def git(root, *args):
    subprocess.run(['git', '-C', root, '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                   check=True, capture_output=True)


class Estado(unittest.TestCase):
    def test_parsea_modificado_nuevo_y_renombrado(self):
        text = ' M a.py\0?? b.py\0R  nuevo.py\0viejo.py\0 D c.py\0'
        self.assertEqual(gitview.parse_status(text),
                         [('M', 'a.py'), ('?', 'b.py'), ('R', 'nuevo.py'), ('D', 'c.py')])

    def test_un_conflicto_se_marca_aparte(self):
        self.assertEqual(gitview.parse_status('UU x.py\0'), [('U', 'x.py')])

    def test_texto_vacio_no_trae_archivos(self):
        self.assertEqual(gitview.parse_status(''), [])


class Repositorio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        git(self.root, 'init', '-q', '-b', 'main')
        self.put('a.py', 'uno\n')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'base')

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name, text):
        with open(os.path.join(self.root, name), 'w') as fh:
            fh.write(text)

    def test_la_rama_y_los_cambios(self):
        self.put('a.py', 'uno\ndos\n')
        self.put('b.py', 'nuevo\n')
        self.assertEqual(gitview.branch(self.root), 'main')
        self.assertEqual(sorted(gitview.changed(self.root)), [('?', 'b.py'), ('M', 'a.py')])

    def test_git_corre_sin_fsmonitor_y_sin_bloqueos_opcionales(self):
        # Un repositorio de fuera puede traer `core.fsmonitor` (ejecuta un comando en cada `status`).
        from unittest import mock
        with mock.patch.object(gitview.subprocess, 'run') as run:
            run.return_value = mock.Mock(returncode=0, stdout='')
            gitview.changed(self.root)
        args, kwargs = run.call_args
        self.assertIn('core.fsmonitor=false', args[0])
        self.assertEqual(kwargs['env']['GIT_OPTIONAL_LOCKS'], '0')

    def test_sin_repositorio_no_hay_cambios(self):
        with tempfile.TemporaryDirectory() as plain:
            self.assertIsNone(gitview.changed(plain))
            self.assertEqual(gitview.branch(plain), '')


try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Vte', '3.91')
    from gi.repository import Gtk
    from elyares import editorpanel, terminal
    HAVE_DISPLAY = Gtk.init_check()
except (ImportError, ValueError):
    HAVE_DISPLAY = False


class Ayudas:
    """Lo que comparten las pruebas de los paneles con widgets."""

    def buttons(self, widget, found=None):
        found = [] if found is None else found
        if isinstance(widget, Gtk.Button):
            found.append(widget)
        child = widget.get_first_child()
        while child is not None:
            self.buttons(child, found)
            child = child.get_next_sibling()
        return found

    def state(self, **over):
        base = dict(branch='main', files=[('M', 'a.py'), ('?', 'b.py')], root='/p/x', chosen='a.py')
        return gitview.State(**{**base, **over})


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi, Vte o pantalla')
class Lista(Ayudas, unittest.TestCase):
    def setUp(self):
        self.log = []
        self.panel = editorpanel.FileList()

    def test_un_boton_por_archivo_y_el_clic_lo_elige(self):
        self.panel.set_files(self.state(), self.log.append)
        self.assertEqual(len(self.buttons(self.panel)), 2)
        self.buttons(self.panel)[1].emit('clicked')
        self.assertEqual(self.log, ['b.py'])

    def test_sin_repositorio_o_sin_cambios_no_hay_botones(self):
        self.panel.set_files(self.state(files=None, chosen=''), self.log.append)
        self.assertEqual(self.buttons(self.panel), [])
        self.panel.set_files(self.state(files=[], chosen=''), self.log.append)
        self.assertEqual(self.buttons(self.panel), [])

    def test_sin_cambios_no_reconstruye_los_botones(self):
        self.panel.set_files(self.state(), self.log.append)
        first = self.buttons(self.panel)[0]
        self.panel.set_files(self.state(), self.log.append)
        self.assertIs(self.buttons(self.panel)[0], first)


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi, Vte o pantalla')
class Editor(Ayudas, unittest.TestCase):
    """El Editor: la lista a un lado y nvim al otro."""

    def setUp(self):
        self.panel = editorpanel.EditorPanel()

    def test_la_lista_a_la_izquierda_y_nvim_a_la_derecha(self):
        self.assertIs(self.panel.get_start_child(), self.panel.files)
        self.assertIs(self.panel.get_end_child(), self.panel.nvim)
        self.assertEqual(self.panel.nvim.kind, terminal.NVIM)

    def test_empieza_escondido_pero_nvim_se_ve_con_el_panel(self):
        self.assertFalse(self.panel.get_visible())
        self.assertTrue(self.panel.nvim.get_visible())


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi, Vte o pantalla')
class Taller(Ayudas, unittest.TestCase):
    """El Taller: el editor (lista y nvim) arriba y la terminal abajo."""

    def setUp(self):
        from elyares import tallerpanel
        self.panel = tallerpanel.TallerPanel()

    def test_el_editor_arriba_y_la_terminal_abajo(self):
        self.assertEqual(self.panel.get_orientation(), Gtk.Orientation.VERTICAL)
        self.assertIsInstance(self.panel.get_start_child(), editorpanel.EditorPanel)
        self.assertIs(self.panel.get_end_child(), self.panel.terminal)
        self.assertEqual(self.panel.terminal.kind, '')

    def test_las_mitades_se_ven_cuando_se_ve_el_taller(self):
        self.assertTrue(self.panel.editor.get_visible())
        self.assertTrue(self.panel.terminal.get_visible())
        self.assertFalse(self.panel.get_visible())

    def test_el_divisor_se_coloca_una_sola_vez(self):
        self.panel.fit(800)
        first = self.panel.get_position()
        self.panel.fit(400)
        self.assertEqual(self.panel.get_position(), first)
        self.assertGreater(first, 0)

    def test_se_esconde_con_los_demas_al_volver_la_isla(self):
        from elyares import windowframe
        frame = windowframe.Frame(lambda _k: None)
        frame.extra.append(self.panel)
        self.panel.set_visible(True)
        frame.hide_panels()
        self.assertFalse(self.panel.get_visible())


if __name__ == '__main__':
    unittest.main()
