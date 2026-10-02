"""El texto de la isla: resaltado del detalle, vista previa del código y fuentes."""

import os
import tempfile
import unittest

from elyares import paint, preview, sources


class Resaltado(unittest.TestCase):
    def test_comando(self):
        self.assertEqual(paint.segments('Ejecutando FOO=1 git log -n 5 "a b" src/x.py | wc'), [
            ('Ejecutando ', 'dim'), ('FOO=1', 'var'), (' ', 'arg'), ('git', 'cmd'), (' ', 'arg'),
            ('log', 'arg'), (' ', 'arg'), ('-n', 'flag'), (' ', 'arg'), ('5', 'num'), (' ', 'arg'),
            ('"a b"', 'str'), (' ', 'arg'), ('src/x.py', 'path'), (' ', 'arg'), ('|', 'dim'),
            (' ', 'arg'), ('wc', 'cmd')])

    def test_ruta_y_busqueda(self):
        self.assertEqual(paint.segments('Editando src/app/x.py'),
                         [('Editando ', 'dim'), ('src/app/', 'dim'), ('x.py', 'path')])
        self.assertEqual(paint.segments('Leyendo x.py'), [('Leyendo ', 'dim'), ('x.py', 'path')])
        self.assertEqual(paint.segments('Buscando TODO|FIXME'),
                         [('Buscando ', 'dim'), ('TODO|FIXME', 'str')])

    def test_comando_largo_que_termino(self):
        segs = paint.segments('Falló (código 2) en 1 min 05 s: make test')
        self.assertEqual(segs[:3], [('Falló (código 2)', 'bad'), (' en 1 min 05 s: ', 'dim'),
                                    ('make', 'cmd')])
        self.assertEqual(paint.segments('Terminó en 40 s: ls')[0], ('Terminó', 'ok'))

    def test_pruebas(self):
        self.assertEqual(paint.segments('Pruebas en rojo: 1 falló, 12 pasaron en 12 s'),
                         [('Pruebas en rojo', 'bad'), (': 1 falló, 12 pasaron en 12 s', 'text')])
        self.assertEqual(paint.segments('Pruebas en verde: 3 pasaron')[0], ('Pruebas en verde', 'pass'))
        # Verde de verdad, aunque el "verde" del tema sea otro color.
        self.assertEqual(paint.colors({'color10': '#888888'})['pass'], paint.GREEN)
        self.assertEqual(paint.segments('Corriendo pruebas: make test')[0], ('Corriendo pruebas', 'cmd'))

    def test_lo_demas_es_texto(self):
        self.assertEqual(paint.segments('Pensando…'), [('Pensando…', 'text')])
        self.assertEqual(paint.segments(None), [('', 'text')])

    def test_el_resaltado_no_pierde_texto(self):
        for detail in ('Ejecutando a && (b; c) > "sin cerrar', 'Ejecutando $(x) \'y', 'Editando /'):
            self.assertEqual(''.join(text for text, _ in paint.segments(detail)), detail)

    def test_colores(self):
        self.assertEqual(paint.mix('#000000', '#ffffff', .5), '#808080')
        base = paint.colors()
        themed = paint.colors({'accent': '#ff0000', 'color10': 'verde'})
        self.assertEqual(set(base), set(themed))
        self.assertNotEqual(base['cmd'], themed['cmd'])
        # Un valor que no es #rrggbb se ignora.
        self.assertEqual(base['str'], themed['str'])
        self.assertEqual((base['pct2'], base['pct3']), (paint.AMBER, paint.RED))

    def test_color_del_contexto(self):
        self.assertEqual([paint.context_role(p) for p in (10, 50, 70, 90)],
                         ['pct0', 'pct1', 'pct2', 'pct3'])


class VistaPrevia(unittest.TestCase):
    def test_edit(self):
        p = preview.build('Edit', {'file_path': '/x/a.py', 'old_string': 'a\nb\nc\nd',
                                   'new_string': 'a\nB\nc\nd'})
        self.assertEqual(p.lines, [(' ', 'a'), ('-', 'b'), ('+', 'B'), (' ', 'c')])
        self.assertEqual((p.name, p.added, p.removed, p.more, p.line), ('a.py', 1, 1, 0, 0))

    def test_linea_del_archivo(self):
        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:
            f.write('uno\ndos\ntres\ncuatro\ncinco\n')
        self.addCleanup(os.unlink, f.name)
        p = preview.build('Edit', {'file_path': f.name, 'old_string': 'tres\ncuatro\ncinco',
                                   'new_string': 'tres\ncuatro\nCINCO'})
        # El fragmento empieza en la 3; lo que se muestra, una más abajo.
        self.assertEqual(p.line, 4)

    def test_write_es_todo_nuevo(self):
        p = preview.build('Write', {'file_path': 'a.txt', 'content': '\n'.join(map(str, range(20)))})
        self.assertEqual((p.added, p.removed), (20, 0))
        self.assertEqual((len(p.lines), p.more), (preview.MAX_LINES, 20 - preview.MAX_LINES))

    def test_multiedit_muestra_el_primero(self):
        p = preview.build('MultiEdit', {'file_path': 'a', 'edits': [
            {'old_string': 'a', 'new_string': 'b'}, {'old_string': 'c', 'new_string': 'd'}]})
        self.assertEqual((p.lines, p.edits), ([('-', 'a'), ('+', 'b')], 2))

    def test_lo_que_no_edita(self):
        self.assertIsNone(preview.build('Bash', {'command': 'ls'}))
        self.assertIsNone(preview.build('Edit', None))
        self.assertIsNone(preview.build('Edit', {'old_string': 'a', 'new_string': 'a'}))
        self.assertIsNone(preview.build('MultiEdit', {'edits': []}))


class Fuentes(unittest.TestCase):
    def test_de_donde_viene_un_mensaje(self):
        self.assertEqual(sources.source_of({'event': 'cmd-start', 'session_id': 'cmd:%1'}), 'terminal')
        cases = {'terminal': {'event': 'cmd-done', 'session_id': 'cmd:%1'},
                 'usage': {'event': 'status', 'session_id': 'abc'},
                 'coffe': {'event': 'focus'},
                 'devherd': {'event': 'alert', 'session_id': 'devherd:issue:1'},
                 'github': {'event': 'alert-clear', 'session_id': 'gh:ci:u'},
                 'claude': {'event': 'tool', 'session_id': 'abc'}}
        for source, msg in cases.items():
            self.assertEqual(sources.source_of(msg), source)
        self.assertEqual(sources.source_of({'event': 'alert', 'session_id': 'ctx:abc'}), 'usage')
        self.assertEqual(sources.source_of({'event': 'alert', 'session_id': 'coffe'}), 'coffe')

    def test_cada_fuente_apagable_tiene_prefijo_y_texto(self):
        keys = [key for key, _ in sources.SOURCES]
        self.assertEqual(set(keys) - {'claude'}, set(sources.PREFIXES))
        self.assertEqual(set(keys), set(sources.ABOUT))


if __name__ == '__main__':
    unittest.main()
