import unittest

from elyares import paint


class TitulosTecnicos(unittest.TestCase):
    def test_con_caps_el_titulo_va_en_mayusculas_y_chico(self):
        out = paint.markdown('## Empieza simple', head='#fff', caps=True)
        self.assertIn('EMPIEZA SIMPLE', out)
        self.assertIn('letter_spacing', out)

    def test_sin_caps_el_titulo_no_cambia(self):
        out = paint.markdown('## Empieza simple', head='#fff')
        self.assertIn('Empieza simple', out)
        self.assertNotIn('letter_spacing', out)


if __name__ == '__main__':
    unittest.main()
