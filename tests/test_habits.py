"""Los hábitos: casilla de hoy, racha y archivo roto. Todo en una carpeta temporal."""

import json
import os
import tempfile
import unittest
from unittest import mock

from elyares import habits


class Habitos(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        for attr, name in (('PATH', 'h/habits.json'), ('LIST_PATH', 'c/habitos.md'), ('SETTINGS', 'c/settings.json')):
            patch = mock.patch.object(habits, attr, os.path.join(self.dir.name, name))
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

    def test_la_lista_es_tu_md_con_guiones_numeros_y_casillas(self):
        os.makedirs(os.path.dirname(habits.LIST_PATH))
        with open(habits.LIST_PATH, 'w') as fh:
            fh.write('# Mis hábitos\n\n<!-- nota -->\nTexto suelto\n- Leer 20 min\n* [ ] Caminar\n'
                     '1. Estirar\n  - [x] agua\n- AGUA\n- \n')
        self.assertEqual(habits.names(), ['Leer 20 min', 'Caminar', 'Estirar', 'agua'])        # sin repetidos ni vacíos

    def test_agregar_y_quitar_escriben_en_tu_md_y_el_historial_se_queda(self):
        habits.add('Leer')
        habits.toggle('Leer', '2026-11-17')
        with open(habits.LIST_PATH) as fh:
            self.assertIn('- Leer\n', fh.read())
        self.assertTrue(habits.remove('leer')[0])
        self.assertEqual(habits.names(), [])
        habits.add('Leer')                                                 # al volver, su racha sigue ahí
        self.assertTrue(habits.items('2026-11-17')[0]['done_today'])
        self.assertFalse(habits.remove('no existe')[0])

    def test_editar_el_md_a_mano_se_ve_sin_reiniciar(self):
        habits.add('Uno')
        with open(habits.LIST_PATH, 'a') as fh:
            fh.write('- Dos\n')
        self.assertEqual(habits.names(), ['Uno', 'Dos'])

    def test_la_lista_puede_vivir_en_otra_ruta_por_el_ajuste(self):
        os.makedirs(os.path.dirname(habits.SETTINGS))
        mine = os.path.join(self.dir.name, 'vault', 'habitos.md')
        with open(habits.SETTINGS, 'w') as fh:
            json.dump({'habits_file': mine}, fh)
        habits.add('Meditar')
        with open(mine) as fh:
            self.assertIn('- Meditar', fh.read())

    def test_el_historial_de_antes_crea_la_lista_la_primera_vez(self):
        habits.save([dict(name='Agua', done=[])])
        self.assertEqual(habits.names(), ['Agua'])

    def use_list(self, path):
        os.makedirs(os.path.dirname(habits.SETTINGS), exist_ok=True)
        with open(habits.SETTINGS, 'w') as fh:
            json.dump({'habits_file': path}, fh)

    def test_leer_la_lista_no_crea_nada(self):
        """`items()` se llama al pintar: no escribe en tu vault ni crea carpetas."""
        self.assertEqual(habits.items(), [])
        self.assertFalse(os.path.exists(habits.LIST_PATH))
        self.assertTrue(habits.add('Agua')[0])                             # escribir sí la crea
        self.assertTrue(os.path.exists(habits.LIST_PATH))

    def test_una_lista_que_no_se_puede_leer_es_vacia_y_dice_por_que(self):
        self.use_list(self.dir.name)                                       # una carpeta, no un archivo
        self.assertEqual(habits.items(), [])
        self.assertIn('No se pudo leer', habits.last_error())
        self.assertFalse(habits.add('Agua')[0])
        self.assertFalse(habits.remove('Agua')[0])
        latin = os.path.join(self.dir.name, 'latin.md')
        with open(latin, 'wb') as fh:
            fh.write('- Caf\xe9 sin az\xfacar\n'.encode('latin-1'))
        self.use_list(latin)
        self.assertEqual(habits.items(), [])
        self.assertTrue(habits.last_error())

    def test_una_casilla_sin_texto_no_es_un_habito(self):
        self.assertEqual(habits.parse_list('- [x]\n- [ ] \n- []\n-  Leer\n- [ ] Caminar'), ['Leer', 'Caminar'])

    def test_corregir_mayusculas_en_la_lista_no_rompe_la_racha(self):
        habits.add('leer')
        habits.toggle('leer', '2026-11-17')
        with open(habits.LIST_PATH, 'w') as fh:
            fh.write('- Leer\n')
        self.assertTrue(habits.items('2026-11-17')[0]['done_today'])
        habits.toggle('Leer', '2026-11-18')
        self.assertEqual(len(habits.load()), 1)                            # la misma entrada, no otra

    def test_quitar_no_deja_la_nota_a_medias(self):
        habits.add('Uno')
        habits.add('Dos')
        with mock.patch.object(habits.os, 'replace', side_effect=OSError(28, 'No space left on device')):
            self.assertFalse(habits.remove('Uno')[0])
        self.assertEqual(habits.names(), ['Uno', 'Dos'])                   # la nota quedó entera

    def test_editar_sin_editor_lo_dice(self):
        with mock.patch.object(habits.subprocess, 'Popen', side_effect=OSError):
            ok, path = habits.edit()
        self.assertFalse(ok)
        self.assertEqual(path, habits.LIST_PATH)
        self.assertTrue(os.path.exists(path))                              # editar sí la crea, para abrirla a mano

    def test_respeta_xdg_config_home(self):
        import importlib
        with mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': self.dir.name}):
            fresh = importlib.reload(habits)
            self.assertEqual(fresh.SETTINGS, os.path.join(self.dir.name, 'elyares-engineer', 'settings.json'))
            from elyares import settings
            self.assertEqual(fresh.SETTINGS, settings.path())
        importlib.reload(habits)


if __name__ == '__main__':
    unittest.main()
