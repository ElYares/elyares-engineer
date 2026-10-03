"""Los proyectos de ~/develop y cuáles están abiertos en tmux."""

import os
import tempfile
import unittest

from elyares import projects


class Listado(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.join(tmp.name, 'develop')
        for path in ('work/tl-mas-server/app', 'work/aang-server', 'work/.oculto', 'personal/devherd',
                     'personal/Apunte', 'labs/notas', 'docs/notas', '_viejo/x', 'privado/y', 'vacio'):
            os.makedirs(os.path.join(self.root, path))
        self.ignore = os.path.join(tmp.name, 'workspaces.ignore')
        with open(self.ignore, 'w') as f:
            f.write('privado\n')
        self.out = os.path.join(tmp.name, 'fuera')
        os.makedirs(self.out)

    def tmux(self, sessions, clients):
        def run(*args):
            return ['\t'.join(row) for row in (sessions if 'list-sessions' in args else clients)]
        return run

    def listing(self, sessions=(), clients=()):
        return projects.listing(self.root, self.ignore, self.tmux(sessions, clients))

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def test_los_proyectos_son_las_carpetas_de_cada_workspace(self):
        found = self.listing()
        # Por workspace y por nombre, sin mirar mayúsculas; sin los ocultos, los ignorados ni los vacíos.
        self.assertEqual([(p.ws, p.name) for p in found],
                         [('docs', 'notas'), ('labs', 'notas'), ('personal', 'Apunte'), ('personal', 'devherd'),
                          ('work', 'aang-server'), ('work', 'tl-mas-server')])
        self.assertFalse(any(p.open or p.here for p in found))
        # Dos que se llaman igual se nombran con su workspace.
        self.assertEqual([p.key for p in found][:3], ['docs/notas', 'labs/notas', 'Apunte'])

    def test_abierto_es_el_que_tiene_sesion_de_tmux_en_su_carpeta(self):
        found = self.listing(
            sessions=[('100', 'otro-nombre', self.path('work', 'aang-server')),
                      ('300', 'tl', self.path('work', 'tl-mas-server', 'app')),      # abierta más adentro
                      ('200', '_term-tl', self.path('work', 'tl-mas-server')),        # oculta: no cuenta
                      ('50', 'main', self.out)],
            clients=[('10', 'otro-nombre'), ('90', 'tl'), ('99', '_term-tl')])
        by = {p.key: p for p in found}
        self.assertEqual((by['aang-server'].session, by['aang-server'].here), ('otro-nombre', False))
        self.assertEqual((by['tl-mas-server'].session, by['tl-mas-server'].activity, by['tl-mas-server'].here),
                         ('tl', 300, True))
        self.assertFalse(by['devherd'].open)
        # La de fuera de ~/develop va al final, suelta.
        self.assertEqual((found[-1].name, found[-1].ws, found[-1].path, found[-1].open), ('main', '', self.out, True))

    def test_dos_sesiones_en_la_misma_carpeta_gana_en_la_que_estas(self):
        path = self.path('work', 'aang-server')
        found = self.listing(sessions=[('900', 'reciente', path), ('100', 'actual', path)], clients=[('5', 'actual')])
        p = next(p for p in found if p.name == 'aang-server')
        self.assertEqual((p.session, p.here), ('actual', True))

    def test_de_quien_es_una_carpeta(self):
        p = projects.Project('tl', '/x/tl')
        self.assertTrue(p.holds('/x/tl') and p.holds('/x/tl/app/Http'))
        self.assertFalse(p.holds('/x/tl-mas') or p.holds('') or p.holds('/x'))

    def test_sin_tmux_ni_carpeta_no_hay_nada(self):
        self.assertEqual(projects.listing(os.path.join(self.root, 'no-existe'), self.ignore, lambda *a: []), [])
