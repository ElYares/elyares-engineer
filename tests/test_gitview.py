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

    def test_el_diff_de_un_modificado_y_el_de_un_nuevo(self):
        self.put('a.py', 'uno\ndos\n')
        self.put('b.py', 'nuevo\n')
        self.assertIn('+dos', gitview.diff(self.root, 'a.py'))
        self.assertIn('+nuevo', gitview.diff(self.root, 'b.py', '?'))

    def test_sin_repositorio_no_hay_cambios(self):
        with tempfile.TemporaryDirectory() as plain:
            self.assertIsNone(gitview.changed(plain))
            self.assertEqual(gitview.branch(plain), '')

    def test_lee_un_archivo_y_avisa_de_lo_que_no_muestra(self):
        self.assertEqual(gitview.read(self.root, 'a.py'), ('uno\n', ''))
        self.assertEqual(gitview.read(self.root, 'no.py')[1], 'El archivo ya no existe')
        with open(os.path.join(self.root, 'bin'), 'wb') as fh:
            fh.write(b'\0\1\2')
        self.assertEqual(gitview.read(self.root, 'bin')[1], 'Archivo binario')

    def test_no_sale_de_la_carpeta_del_proyecto(self):
        self.assertEqual(gitview.read(self.root, '../etc/passwd')[1], 'Fuera del proyecto')


if __name__ == '__main__':
    unittest.main()


try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('GtkSource', '5')
    from gi.repository import Gtk
    from elyares import editorpanel
    HAVE_DISPLAY = Gtk.init_check()
except (ImportError, ValueError):
    HAVE_DISPLAY = False


@unittest.skipUnless(HAVE_DISPLAY, 'sin gi, GtkSource o pantalla')
class Panel(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.panel = editorpanel.EditorPanel()
        self.handlers = dict(choose=self.log.append)

    def buttons(self, widget=None, found=None):
        found = [] if found is None else found
        widget = widget or self.panel
        if isinstance(widget, Gtk.Button):
            found.append(widget)
        child = widget.get_first_child()
        while child is not None:
            self.buttons(child, found)
            child = child.get_next_sibling()
        return found

    def state(self, **over):
        base = dict(branch='main', files=[('M', 'a.py'), ('?', 'b.py')], root='/p/x', chosen='a.py',
                    text='print(1)\n', note='', diff='+print(1)\n')
        return gitview.State(**{**base, **over})

    def text(self, view):
        buf = view.get_buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

    def test_un_boton_por_archivo_y_el_clic_lo_elige(self):
        self.panel.set_editor(self.state(), self.handlers)
        self.assertEqual(len(self.buttons()), 2)
        self.buttons()[1].emit('clicked')
        self.assertEqual(self.log, ['b.py'])

    def test_muestra_el_archivo_y_su_diff_con_sintaxis(self):
        self.panel.set_editor(self.state(), self.handlers)
        self.assertEqual(self.text(self.panel.file_view), 'print(1)\n')
        self.assertEqual(self.text(self.panel.diff_view), '+print(1)\n')
        self.assertEqual(self.panel.diff_view.get_buffer().get_language().get_id(), 'diff')
        self.assertEqual(self.panel.file_view.get_buffer().get_language().get_id(), 'python3')

    def test_es_un_visor_no_se_puede_escribir(self):
        self.assertFalse(self.panel.file_view.get_editable())
        self.assertFalse(self.panel.diff_view.get_editable())

    def test_cambia_el_texto_cuando_el_agente_edita(self):
        self.panel.set_editor(self.state(), self.handlers)
        self.panel.set_editor(self.state(text='print(2)\n'), self.handlers)
        self.assertEqual(self.text(self.panel.file_view), 'print(2)\n')

    def test_sin_repositorio_o_sin_cambios_no_hay_botones(self):
        self.panel.set_editor(self.state(files=None, chosen='', text='', diff=''), self.handlers)
        self.assertEqual(self.buttons(), [])
        self.panel.set_editor(self.state(files=[], chosen='', text='', diff=''), self.handlers)
        self.assertEqual(self.buttons(), [])
