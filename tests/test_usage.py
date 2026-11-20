import json
import os
import tempfile
import unittest
from datetime import datetime

from elyares import usage

CLAUDEBAR = json.dumps({
    'error': None, 'plan': 'Max 5x',
    'windows': [
        {'id': 'session', 'label': 'Session', 'group': None, 'used_pct': 12, 'reset_at_unix': 1000},
        {'id': 'weekly', 'label': 'Weekly', 'group': None, 'used_pct': 14, 'reset_at_unix': 2000},
        {'id': 'model_0', 'label': 'Weekly', 'group': 'Fable', 'used_pct': 3, 'reset_at_unix': 2000}]})


def at(day, hour=12):
    return datetime(2026, 11, day, hour).timestamp()


class Leer(unittest.TestCase):
    def test_sesion_semana_y_modelos(self):
        got = usage.parse(CLAUDEBAR)
        self.assertEqual(got['session'], (12.0, 1000.0))
        self.assertEqual(got['weekly'], (14.0, 2000.0))
        self.assertEqual(got['models'], [('Fable', 3.0)])
        self.assertEqual(got['plan'], 'Max 5x')

    def test_salida_rota_o_con_error_es_none(self):
        for bad in ('', 'no json', '[]', json.dumps({'error': 'sin sesión', 'windows': []}),
                    json.dumps({'error': None, 'windows': []})):
            self.assertIsNone(usage.parse(bad))


class Falta(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(usage.left(10_000 + 2 * 3600 + 12 * 60, 10_000), '2 h 12 min')
        self.assertEqual(usage.left(10_000 + 86400 + 10 * 3600, 10_000), '1 d 10 h')
        self.assertEqual(usage.left(10_000 + 45 * 60, 10_000), '45 min')
        self.assertEqual(usage.left(10_000 - 5, 10_000), 'ya')
        self.assertEqual(usage.left(0, 10_000), '—')


class Dias(unittest.TestCase):
    def test_el_gasto_de_un_dia_es_lo_que_subio_la_semana(self):
        samples = [(at(18, 9), 0, 10), (at(18, 20), 0, 16), (at(19, 9), 0, 20)]
        got = dict(usage.daily(samples, now=at(19, 15)))
        self.assertEqual(got[datetime(2026, 11, 18).date()], 6.0)
        self.assertEqual(got[datetime(2026, 11, 19).date()], 4.0)

    def test_un_reinicio_de_la_semana_no_resta(self):
        samples = [(at(18, 9), 0, 90), (at(18, 20), 0, 95), (at(19, 9), 0, 2)]
        got = dict(usage.daily(samples, now=at(19, 15)))
        self.assertEqual(got[datetime(2026, 11, 19).date()], 0.0)

    def test_siempre_son_siete_dias_y_el_ultimo_es_hoy(self):
        got = usage.daily([], now=at(19))
        self.assertEqual(len(got), 7)
        self.assertEqual(got[-1][0], datetime(2026, 11, 19).date())


class Guardar(unittest.TestCase):
    def test_guarda_una_muestra_y_no_otra_antes_de_tiempo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'sub', 'usage.jsonl')
            data = usage.parse(CLAUDEBAR)
            self.assertTrue(usage.record(data, now=1_000_000, path=path))
            self.assertFalse(usage.record(data, now=1_000_100, path=path))
            self.assertTrue(usage.record(data, now=1_000_000 + usage.SAMPLE_EVERY, path=path))
            self.assertEqual([s[2] for s in usage.load(path)], [14.0, 14.0])

    def test_una_linea_rota_no_tumba_la_historia(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'u.jsonl')
            with open(path, 'w') as fh:
                fh.write('basura\n{"t": 5, "s": 1, "w": 2}\n')
            self.assertEqual(usage.load(path), [(5.0, 1.0, 2.0)])

    def test_sin_datos_no_guarda(self):
        self.assertFalse(usage.record(None))


if __name__ == '__main__':
    unittest.main()
