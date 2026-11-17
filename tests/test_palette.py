import unittest

try:
    from elyares import palette
except ImportError:             # sin `gi` no hay GTK
    palette = None


@unittest.skipIf(palette is None, 'sin gi')
class Busqueda(unittest.TestCase):
    def test_sin_acentos_ni_mayusculas(self):
        self.assertTrue(palette.matches('sesion', 'Ir a Sesión'))
        self.assertTrue(palette.matches('AJUS', 'Ir a Ajustes'))

    def test_todas_las_palabras_deben_estar(self):
        self.assertTrue(palette.matches('ir term', 'Ir a Terminal'))
        self.assertFalse(palette.matches('ir editor', 'Ir a Terminal'))

    def test_sin_consulta_entra_todo(self):
        self.assertTrue(palette.matches('', 'Cualquiera'))
        self.assertTrue(palette.matches('   ', 'Cualquiera'))


if __name__ == '__main__':
    unittest.main()
