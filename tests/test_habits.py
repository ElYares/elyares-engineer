"""Los hábitos: casilla de hoy, racha y archivo roto. Todo en una carpeta temporal."""

import os
import tempfile
import unittest
from unittest import mock

from elyares import habits


class Habitos(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        patch = mock.patch.object(habits, 'PATH', os.path.join(self.dir.name, 'h', 'habits.json'))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.dir.cleanup)

    def test_agregar_marcar_y_quitar(self):
        self.assertTrue(habits.add('  Leer   20 min ')[0])
        self.assertEqual(habits.items('2026-11-17')[0]['name'], 'Leer 20 min')
        self.assertTrue(habits.toggle('Leer 20 min', '2026-11-17'))
        self.assertTrue(habits.items('2026-11-17')[0]['done_today'])
        self.assertFalse(habits.toggle('Leer 20 min', '2026-11-17'))        # otra vez lo desmarca
        self.assertTrue(habits.remove('leer 20 min')[0])
        self.assertEqual(habits.items(), [])

    def test_no_agrega_vacios_ni_repetidos_ni_de_mas(self):
        self.assertFalse(habits.add('   ')[0])
        habits.add('Agua')
        self.assertFalse(habits.add('agua')[0])
        for i in range(habits.MAX_HABITS):
            habits.add(f'h{i}')
        self.assertFalse(habits.add('uno más')[0])

    def test_la_racha_cuenta_dias_seguidos_y_sobrevive_a_hoy_sin_marcar(self):
        self.assertEqual(habits.streak(['2026-11-15', '2026-11-16', '2026-11-17'], '2026-11-17'), 3)
        self.assertEqual(habits.streak(['2026-11-15', '2026-11-16'], '2026-11-17'), 2)     # hoy aún sin marcar
        self.assertEqual(habits.streak(['2026-11-10', '2026-11-12'], '2026-11-17'), 0)     # se rompió
        self.assertEqual(habits.streak([], '2026-11-17'), 0)

    def test_un_archivo_roto_es_una_lista_vacia(self):
        os.makedirs(os.path.dirname(habits.PATH))
        with open(habits.PATH, 'w') as fh:
            fh.write('{no es json')
        self.assertEqual(habits.load(), [])
        self.assertTrue(habits.add('Agua')[0])                            # y se puede volver a escribir


if __name__ == '__main__':
    unittest.main()
