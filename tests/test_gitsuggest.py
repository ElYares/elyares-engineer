"""Sugerir el mensaje de un commit y hacerlo."""

import os
import subprocess
import tempfile
import unittest
from unittest import mock

from elyares import gitsuggest


def git(root, *args):
    subprocess.run(['git', '-C', root, '-c', 'user.name=t', '-c', 'user.email=t@t', *args], check=True, capture_output=True)


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        subprocess.run(['git', 'init', '-q', '-b', 'main', self.root], check=True)
        git(self.root, 'config', 'user.name', 't')
        git(self.root, 'config', 'user.email', 't@t')
        self.write('a.py', 'uno\n')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-qm', 'feat: base')

    def write(self, name, text):
        with open(os.path.join(self.root, name), 'w') as f:
            f.write(text)


class Cambios(Repo):
    def test_cuenta_archivos_y_lineas_y_aparta_los_riesgosos(self):
        self.write('a.py', 'uno\ndos\ntres\n')                  # +2 líneas
        self.write('nuevo.py', 'x\ny\n')                        # archivo nuevo, 2 líneas
        self.write('.env', 'TOKEN=1\n')
        self.write('id_rsa', 'k\n')
        found = gitsuggest.changes(self.root)
        self.assertEqual(sorted(found.files), ['a.py', 'nuevo.py'])
        self.assertEqual(sorted(found.risky), ['.env', 'id_rsa'])
        self.assertEqual(found.lines, 4)

    def test_riesgosos_por_nombre(self):
        for name in ('.env', '.env.local', 'a/clave.pem', 'server.key', 'credentials.json', 'my-secret.txt'):
            self.assertTrue(gitsuggest.is_risky(name), name)
        for name in ('envio.py', 'README.md', 'keyboard.py'):
            self.assertFalse(gitsuggest.is_risky(name), name)


class Sugerir(Repo):
    def run(self, text='feat: algo\n\n- porque sí', code=0):
        return mock.Mock(return_value=mock.Mock(stdout=text, returncode=code))

    def test_manda_el_prompt_con_el_estilo_y_el_diff_y_agrega_el_trailer(self):
        self.write('a.py', 'uno\ndos\n')
        run = self.run()
        got = gitsuggest.suggest(self.root, run=run)
        self.assertEqual(got.error, '')
        self.assertTrue(got.text.startswith('feat: algo'))
        self.assertTrue(got.text.endswith(gitsuggest.TRAILER))
        prompt = run.call_args.kwargs['input']
        self.assertIn('feat: base', prompt)                      # el estilo, de los commits de verdad
        self.assertIn('+dos', prompt)                            # y el diff
        self.assertEqual(run.call_args.kwargs['cwd'], '/tmp')    # fuera del repo
        self.assertEqual(run.call_args.kwargs['env']['XDG_RUNTIME_DIR'], '/nonexistent')   # sin avisarle a la isla
        self.assertIn('--tools', run.call_args.args[0])

    def test_sin_cambios_o_solo_riesgosos_no_llama_a_claude(self):
        run = self.run()
        self.assertIn('nada', gitsuggest.suggest(self.root, run=run).error)
        self.write('.env', 'x\n')
        self.assertIn('riesgosos', gitsuggest.suggest(self.root, run=run).error)
        run.assert_not_called()

    def test_un_fallo_de_claude_es_un_error_y_no_una_excepcion(self):
        self.write('a.py', 'x\n')
        self.assertTrue(gitsuggest.suggest(self.root, run=self.run('', code=1)).error)
        self.assertIn('no contestó', gitsuggest.suggest(self.root, run=mock.Mock(side_effect=OSError('no hay'))).error)

    def test_limpia_las_cercas_de_codigo_y_la_advertencia_de_la_sesion(self):
        self.assertEqual(gitsuggest.clean('Warning: algo\n```\nfix: a\n```'), 'fix: a')
        self.assertEqual(gitsuggest.clean('"fix: a"'), 'fix: a')


class Commitear(Repo):
    def test_commitea_solo_los_archivos_listados_y_nunca_un_riesgoso_ni_lo_que_ya_estaba_en_el_indice(self):
        self.write('a.py', 'uno\ndos\n')
        self.write('b.py', 'b\n')
        self.write('otro.py', 'o\n')
        self.write('.env', 'x\n')
        git(self.root, 'add', 'otro.py')                        # algo ajeno que ya estaba en el índice
        ok, said = gitsuggest.commit(self.root, 'feat: b\n\nporque', ['a.py', 'b.py', '.env'])
        self.assertTrue(ok, said)
        shown = subprocess.run(['git', '-C', self.root, 'show', '--name-only', '--format=%s', 'HEAD'],
                               capture_output=True, text=True).stdout.split()
        self.assertEqual(sorted(shown[2:]), ['a.py', 'b.py'])    # sin .env y sin otro.py
        status = subprocess.run(['git', '-C', self.root, 'status', '--porcelain'], capture_output=True, text=True).stdout
        self.assertIn('otro.py', status)                         # sigue pendiente

    def test_sin_mensaje_o_sin_archivos_no_commitea(self):
        self.assertFalse(gitsuggest.commit(self.root, '', ['a.py'])[0])
        self.assertFalse(gitsuggest.commit(self.root, 'feat: x', ['.env'])[0])


if __name__ == '__main__':
    unittest.main()
