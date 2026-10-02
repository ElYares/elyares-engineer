"""Las corridas de pruebas: reconocer el comando, leer lo que imprime cada
programa y seguir una corrida en vivo.

Las muestras de `samples/` son lo que imprimieron de verdad go, cargo,
unittest, pytest y vitest con un proyecto de tres pruebas (una pasa, una falla,
una se salta). Las de pest, jest y phpunit están escritas a mano con su forma
conocida: no salieron de una corrida real.
"""

import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest import mock

from elyares import testrun
from elyares.testrun import FAIL, OK, SKIP

HERE = os.path.dirname(os.path.abspath(__file__))
BASH = os.path.join(os.path.dirname(HERE), 'shell', 'elyares.bash')


def sample(name):
    with open(os.path.join(HERE, 'samples', f'{name}.txt')) as f:
        return testrun.parse(testrun.clean(f.read()))


def counts(run):
    return run.passed, run.failed, run.skipped


class Comando(unittest.TestCase):
    YES = ['pytest', 'pytest -q tests/', 'uv run pytest -x', './vendor/bin/pest --parallel',
           'php artisan test', 'docker compose exec app php artisan test --filter=Order',
           'go test ./... -race', 'cargo test', 'npx vitest run', 'npm test', 'npm run test:unit',
           'pnpm test', 'make test', 'make test-unit', 'python -m unittest discover -s tests',
           'cd api && go test ./...', 'FOO=1 jest', '(cd web; yarn test)', 'vendor/bin/phpunit']
    NO = ['ls', 'cat pytest.ini', 'vim tests/test_a.py', 'git log', 'make build', 'go build ./...',
          'echo protest', 'npm run build', 'cd tests', 'pestcontrol', '']

    def test_python(self):
        for cmd in self.YES:
            self.assertTrue(testrun.is_test(cmd), cmd)
        for cmd in self.NO:
            self.assertFalse(testrun.is_test(cmd), cmd)
        self.assertFalse(testrun.is_test(None))

    def test_bash_dice_lo_mismo(self):
        # shell/elyares.bash decide en la terminal con su propio patrón.
        with open(BASH) as f:
            line = next(l for l in f if l.startswith('__ely_test_re='))
        script = line + 'for c in "$@"; do [[ $c =~ $__ely_test_re ]] && echo 1 || echo 0; done'
        out = subprocess.run(['bash', '-c', script, '_', *self.YES, *self.NO],
                             capture_output=True, text=True, timeout=10).stdout.split()
        self.assertEqual(out, ['1'] * len(self.YES) + ['0'] * len(self.NO))


class Programas(unittest.TestCase):
    def test_go_con_v(self):
        run = sample('go-v')
        self.assertEqual(run.items, {'TestSuma': OK, 'TestResta': FAIL, 'TestSaltada': SKIP,
                                     'TestSub': FAIL, 'TestSub/caso_uno': OK, 'TestSub/caso_dos': FAIL})
        self.assertEqual(counts(run), (2, 3, 1))

    def test_go_sin_v_solo_nombra_las_que_fallan(self):
        self.assertEqual(sample('go').items,
                         {'TestResta': FAIL, 'TestSub': FAIL, 'TestSub/caso_dos': FAIL})
        run = testrun.parse('ok  \tsample/api\t0.012s\nok  \tsample/web\t(cached)\n'
                            '?   \tsample/doc\t[no test files]\n')
        self.assertEqual(run.items, {'sample/api': OK, 'sample/web': OK})

    def test_cargo(self):
        run = sample('cargo')
        self.assertEqual(run.items, {'tests::saltada': SKIP, 'tests::resta': FAIL, 'tests::suma': OK})
        self.assertEqual(counts(run), (1, 1, 1))

    def test_cargo_suma_cada_binario(self):
        line = 'test result: ok. 3 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out\n'
        self.assertEqual(counts(testrun.parse(line * 2)), (6, 0, 2))

    def test_unittest_con_v(self):
        run = sample('unittest-v')
        # test_con_doc trae docstring: su resultado viene en la línea siguiente.
        self.assertEqual(run.items, {'Cuentas.test_con_doc': OK, 'Cuentas.test_error': FAIL,
                                     'Cuentas.test_resta': FAIL, 'Cuentas.test_saltada': SKIP,
                                     'Cuentas.test_suma': OK})
        self.assertEqual(counts(run), (2, 2, 1))

    def test_unittest_con_puntos(self):
        run = sample('unittest')
        self.assertEqual(run.items, {'Cuentas.test_error': FAIL, 'Cuentas.test_resta': FAIL})
        self.assertEqual(counts(run), (2, 2, 1))

    def test_unittest_en_verde(self):
        run = testrun.parse('.....\n' + '-' * 70 + '\nRan 5 tests in 0.002s\n\nOK (skipped=1)\n')
        self.assertEqual(counts(run), (4, 0, 1))
        self.assertEqual(counts(testrun.parse('Ran 1 test in 0.001s\n\nOK\n')), (1, 0, 0))

    def test_pytest(self):
        for name in ('pytest', 'pytest-q'):
            run = sample(name)
            self.assertEqual(counts(run), (3, 3, 1), name)
            self.assertEqual(run.items, {'test_a.py::Cuentas::test_error': FAIL,
                                         'test_a.py::Cuentas::test_resta': FAIL,
                                         'test_a.py::test_funcion_falla': FAIL}, name)

    def test_pytest_con_v(self):
        run = sample('pytest-v')
        self.assertEqual(counts(run), (3, 3, 1))
        self.assertEqual(len(run.items), 7)
        self.assertEqual(run.items['test_a.py::Cuentas::test_saltada'], SKIP)
        self.assertEqual(run.items['test_a.py::test_funcion'], OK)

    def test_vitest(self):
        run = sample('vitest')
        self.assertEqual(counts(run), (2, 1, 1))
        self.assertEqual(run.items, {'b.test.js (1 test)': OK, 'cuentas > resta': FAIL})
        run = sample('vitest-v')
        self.assertEqual(counts(run), (2, 1, 1))
        self.assertEqual(run.items, {'b.test.js > otra que pasa': OK, 'a.test.js > cuentas > suma': OK,
                                     'a.test.js > cuentas > resta': FAIL})

    def test_pest(self):
        run = sample('pest')
        self.assertEqual(counts(run), (3, 1, 1))
        self.assertEqual(run.items, {'that true is true': OK, 'it lists the orders': OK,
                                     'it creates an order': FAIL, 'it cancels an order': OK})

    def test_jest(self):
        run = sample('jest')
        self.assertEqual(counts(run), (2, 1, 1))
        self.assertEqual(run.items, {'suma': OK, 'resta': FAIL, 'saltada': SKIP})

    def test_phpunit(self):
        run = sample('phpunit')
        self.assertEqual(counts(run), (6, 1, 1))
        self.assertEqual(run.items, {'Tests\\Feature\\OrderTest::test_creates_an_order': FAIL})
        self.assertEqual(counts(testrun.parse('...\n\nOK (3 tests, 5 assertions)\n')), (3, 0, 0))


class AMedias(unittest.TestCase):
    def test_puntos_sin_terminar(self):
        # unittest y pytest van soltando letras en una línea que aún no acaba.
        run = testrun.parse('..F.s')
        self.assertEqual(counts(run), (3, 1, 1))
        run = testrun.parse('tests/test_a.py ..F.                          [ 40%]\ntests/test_b.py ..')
        self.assertEqual(counts(run), (5, 1, 0))

    def test_sin_resumen_cuentan_las_lineas(self):
        run = testrun.parse('  ✓ uno   0.01s\n  ⨯ dos   0.20s\n  ✓ tres')
        self.assertEqual(counts(run), (2, 1, 0))
        self.assertTrue(run.ran)

    def test_lo_que_no_son_pruebas(self):
        for text in ('', None, 'compilando...\nlisto\n', 'E\n', 'make: *** No rule to make target\n',
                     'OK\n', '- Expected\n+ Received\n- 3\n'):
            self.assertFalse(testrun.parse(text).ran, text)

    def test_una_prueba_que_se_repite_cuenta_una_vez(self):
        # Un programa que redibuja la pantalla repite sus líneas.
        run = testrun.parse(' ✓ uno\n ✓ uno\n × dos\n ✓ uno\n')
        self.assertEqual(run.items, {'uno': OK, 'dos': FAIL})

    def test_clean(self):
        raw = '\x1b[32m  ✓ uno\x1b[39m \x1b[2m0.01s\x1b[22m\r\n\x1b]0;título\x07avance 1\ravance 2\x1b[2K\n'
        self.assertEqual(testrun.clean(raw), '  ✓ uno 0.01s\navance 1\navance 2\n')
        self.assertEqual(testrun.clean(None), '')


class Listado(unittest.TestCase):
    def test_primero_las_que_fallaron_luego_las_ultimas(self):
        run = testrun.Run({f't{i}': OK for i in range(20)} | {'roto': FAIL, 'saltada': SKIP})
        lines = testrun.listing(run, 5)
        self.assertEqual(lines, ['✗ roto', '✓ t17', '✓ t18', '✓ t19', '○ saltada'])

    def test_mas_fallas_de_las_que_caben(self):
        run = testrun.Run({f't{i}': FAIL for i in range(9)} | {'bien': OK})
        self.assertEqual(testrun.listing(run, 4), ['✗ t0', '✗ t1', '✗ t2', '✗ … y 6 más que fallaron'])
        self.assertEqual(testrun.listing(run, 9)[-1], '✗ t8')

    def test_results(self):
        self.assertEqual(testrun.results(sample('cargo')), {
            'ran': True, 'passed': 1, 'failed': 1, 'skipped': 1,
            'lines': ['✗ tests::resta', '○ tests::saltada', '✓ tests::suma']})
        self.assertEqual(testrun.results(testrun.parse('nada'))['ran'], False)


class Seguimiento(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        patcher = mock.patch.dict(os.environ, {'XDG_RUNTIME_DIR': self.dir})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.got = []
        self.new = threading.Event()
        self.f = testrun.Follower(self.emit, interval=.01, flush=0)
        self.log = testrun.log_path('%7')
        self.msg = {'event': 'cmd-start', 'session_id': 'cmd:%7', 'pane': '%7', 'at': '100.5',
                    'command': 'make test'}

    def emit(self, msg):
        self.got.append(msg)
        self.new.set()

    def wait(self):
        self.assertTrue(self.new.wait(3))
        self.new.clear()
        return self.got[-1]

    def write(self, text, mode='a'):
        with open(self.log, mode) as f:
            f.write(text)

    def test_el_archivo_sale_del_pane_y_de_nada_mas(self):
        self.assertEqual(self.log, os.path.join(self.dir, 'elyares-tests-7.log'))
        for pane in ('', None, '7', '%7/../../x', '%', '../etc/passwd'):
            self.assertEqual(testrun.log_path(pane), '')

    def test_va_contando_y_al_final_borra_el_archivo(self):
        self.write('', 'w')
        self.assertTrue(self.f.start(self.msg))
        self.write('\x1b[32m  ✓ uno\x1b[0m\r\n')
        got = self.wait()
        self.assertEqual((got['event'], got['results']['passed'], got['results']['lines']),
                         ('cmd-start', 1, ['✓ uno']))
        self.write('  ⨯ dos\r\n')
        self.assertEqual(self.wait()['results']['lines'], ['✗ dos', '✓ uno'])
        self.write('\n  Tests:    1 failed, 2 passed\n')
        done = {**self.msg, 'event': 'cmd-done', 'at': '103.0', 'exit_code': 1}
        self.assertTrue(self.f.finish(done))
        while self.wait()['event'] != 'cmd-done':
            pass
        last = self.got[-1]
        self.assertEqual((last['exit_code'], last['results']['passed'], last['results']['failed']),
                         (1, 2, 1))
        self.assertFalse(os.path.exists(self.log))
        self.assertEqual(self.f.live, {})

    def test_sin_cambios_no_repite(self):
        self.write('  ✓ uno\n', 'w')
        self.f.start(self.msg)
        self.wait()
        self.assertFalse(self.new.wait(.1))
        self.assertEqual(len(self.got), 1)

    def test_lo_que_no_son_pruebas_no_avisa_hasta_el_final(self):
        self.write('compilando...\n', 'w')
        self.f.start(self.msg)
        self.assertFalse(self.new.wait(.1))
        self.assertTrue(self.f.finish({**self.msg, 'event': 'cmd-done'}))
        self.assertEqual(self.wait()['results']['ran'], False)

    def test_un_final_que_llega_antes_que_su_principio(self):
        self.write('', 'w')
        self.f.finish({**self.msg, 'event': 'cmd-done', 'at': '100.6'})
        self.wait()
        # El comando acabó al instante: su principio llega tarde y ya no cuenta.
        self.assertFalse(self.f.start(self.msg))
        # El siguiente comando sí.
        self.assertTrue(self.f.start({**self.msg, 'at': '200.0'}))

    def test_sin_archivo_no_eran_pruebas_seguidas(self):
        self.assertFalse(self.f.finish({**self.msg, 'event': 'cmd-done'}))
        self.assertFalse(self.f.start({**self.msg, 'pane': ''}))
        self.assertEqual(self.got, [])

    def test_solo_se_lee_el_final_de_un_archivo_enorme(self):
        self.write('  ✓ vieja\n' + 'x' * 64 + '\n', 'w')
        with mock.patch.object(testrun, 'MAX_LOG', 32):
            self.write('  ✓ nueva\n')
            self.assertEqual(testrun.parse(testrun.read(self.log)).items, {'nueva': OK})
        self.assertEqual(testrun.read(os.path.join(self.dir, 'no-existe')), '')


if __name__ == '__main__':
    unittest.main()
