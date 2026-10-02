"""Los comandos y atajos que la isla enseña para consultar."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from elyares import commands

BINDS = [
    {'modmask': 64, 'key': 'RETURN', 'description': 'Terminal', 'arg': 'x'},
    {'modmask': 72, 'key': 'Y', 'description': 'Engineer: abrir la isla', 'arg': 'elyares-ctl open'},
    {'modmask': 73, 'key': 'Y', 'description': 'Engineer: esconder o mostrar'},
    {'modmask': 76, 'key': 'Y', 'description': 'Engineer: modo compacto'},
    {'modmask': 72, 'key': 'BackSpace', 'description': 'Engineer: denegar'},
    {'modmask': 0, 'key': 'F9', 'description': 'Engineer:fijar'},
    {'modmask': 72, 'key': 'T'}, 'basura',
]


class Atajos(unittest.TestCase):
    def test_como_se_dice_un_atajo(self):
        self.assertEqual(commands.combo(72, 'Y'), 'SUPER ALT + Y')
        self.assertEqual(commands.combo(64 | 1 | 4 | 8, 'Y'), 'SUPER SHIFT CTRL ALT + Y')
        self.assertEqual(commands.combo(0, 'F9'), 'F9')

    def test_solo_los_de_engineer_y_en_su_orden(self):
        self.assertEqual(commands.shortcuts(BINDS), [
            ('SUPER ALT + Y', 'Abrir la isla'), ('SUPER SHIFT ALT + Y', 'Esconder o mostrar'),
            ('SUPER CTRL ALT + Y', 'Modo compacto'), ('SUPER ALT + BackSpace', 'Denegar'),
            ('F9', 'Fijar')])
        self.assertEqual(commands.shortcuts(None), [])


class Archivo(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        patcher = mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': self.dir})
        patcher.start()
        self.addCleanup(patcher.stop)

    def user(self, text):
        os.makedirs(os.path.join(self.dir, 'elyares-engineer'), exist_ok=True)
        with open(commands.user_path(), 'w') as f:
            f.write(text)

    def test_lo_del_repo(self):
        sections = commands.load()
        self.assertLessEqual({'devherd', 'coffe', 'raton', 'engineer'}, set(sections))
        self.assertIn(('coffe pause', 'Al refri: anula el pomodoro y aparca la tarea'), sections['coffe'])
        for name, items in sections.items():
            self.assertTrue(items, name)
            for cmd, text in items:
                # Tiene que caber en la burbuja, que es más estrecha que la ventana.
                self.assertLessEqual(len(cmd) + len(text), 75, (cmd, text))

    def test_una_seccion_del_usuario_reemplaza_a_la_del_repo(self):
        self.user('[coffe]\n"coffe start x" = "Lo mío"\n\n[proyecto]\n"make test" = "Las pruebas"\n')
        sections = commands.load()
        self.assertEqual(sections['coffe'], [('coffe start x', 'Lo mío')])
        self.assertEqual(sections['proyecto'], [('make test', 'Las pruebas')])
        self.assertIn('devherd', sections)

    def test_una_seccion_vacia_la_quita(self):
        self.user('[devherd]\n')
        self.assertEqual(commands.reference('devherd', commands.load()), [])

    def test_un_archivo_roto_se_ignora(self):
        self.user('esto no es toml [')
        self.assertIn('devherd', commands.load())
        self.user('[coffe]\n"x" = 3\nsuelto = "y"\n')
        self.assertEqual(commands.load()['coffe'], [('suelto', 'y')])


class Burbuja(unittest.TestCase):
    SECTIONS = {'coffe': [('coffe pause', 'Al refri')], 'raton': [('Clic derecho', 'Compacto')],
                'engineer': [('elyares-ctl status', 'Fuentes')]}

    def test_la_de_una_fuente_trae_sus_comandos(self):
        self.assertEqual(commands.reference('coffe', self.SECTIONS),
                         [('head', 'Comandos'), ('cmd', 'coffe pause', 'Al refri')])
        self.assertEqual(commands.reference('github', self.SECTIONS), [])

    def test_la_de_engineer_trae_teclado_raton_y_terminal(self):
        rows = commands.reference(commands.HELP, self.SECTIONS, BINDS)
        self.assertEqual([r[1] for r in rows if r[0] == 'head'], ['Teclado', 'Ratón', 'Terminal'])
        self.assertIn(('cmd', 'SUPER ALT + Y', 'Abrir la isla'), rows)
        self.assertEqual(rows[-1], ('cmd', 'elyares-ctl status', 'Fuentes'))

    def test_sin_atajos_en_hyprland_no_hay_bloque_de_teclado(self):
        rows = commands.reference(commands.HELP, self.SECTIONS, [])
        self.assertEqual([r[1] for r in rows if r[0] == 'head'], ['Ratón', 'Terminal'])


if __name__ == '__main__':
    unittest.main()
