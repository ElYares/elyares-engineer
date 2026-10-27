import unittest

from elyares import fonts


class Letra(unittest.TestCase):
    def tearDown(self):
        fonts.use(fonts.SYSTEM)
        fonts.use_tired(False)
        fonts.use_scale(125)

    def test_la_del_sistema_deja_todo_como_esta(self):
        self.assertEqual(fonts.pick('Sans Semi-Bold 11'), 'Sans Semi-Bold 11')
        self.assertEqual(fonts.css(), '')

    def test_una_elegida_cambia_familia_y_peso_y_deja_el_tamano(self):
        fonts.use('Caviar Dreams')
        self.assertEqual(fonts.pick('Sans Semi-Bold 11'), 'Caviar Dreams Regular 11')
        self.assertEqual(fonts.pick('Sans'), 'Caviar Dreams Regular')

    def test_cada_variante_es_una_opcion_con_su_estilo(self):
        fonts.use('Dunkin Bold Italic')
        self.assertEqual(fonts.pick('Sans Medium 9'), 'Dunkin Bold Italic 9')
        fonts.use('Comfortaa Light')
        self.assertEqual(fonts.pick('Sans Bold 15'), 'Comfortaa Light 15')
        self.assertIn('font-weight: 300', fonts.css())

    def test_el_codigo_no_cambia(self):
        fonts.use('Comfortaa')
        self.assertEqual(fonts.pick('JetBrainsMono Nerd Font 9'), 'JetBrainsMono Nerd Font 9')
        self.assertEqual(fonts.pick('Sansation 9'), 'Sansation 9')

    def test_una_familia_desconocida_vuelve_a_la_del_sistema(self):
        self.assertEqual(fonts.use('Papyrus'), fonts.SYSTEM)

    def test_el_css_de_los_widgets_lleva_la_familia(self):
        fonts.use('Garet')
        self.assertIn('font-family: "Garet"', fonts.css())
        fonts.use('Dunkin Sans Italic')
        self.assertIn('font-style: italic', fonts.css())

    def test_vista_cansada_agranda_y_engrosa(self):
        fonts.use_tired(True)
        self.assertEqual(fonts.pick('Sans 10'), 'Sans Medium 12.5')
        self.assertEqual(fonts.pick('Sans Semi-Bold 8'), 'Sans Semi-Bold 10')
        self.assertEqual(fonts.pick('JetBrainsMono Nerd Font 9'), 'JetBrainsMono Nerd Font 11.2')
        self.assertEqual(fonts.pick('Sans'), 'Sans')
        self.assertIn('font-size: 125%', fonts.css())

    def test_vista_cansada_con_letra_elegida(self):
        fonts.use('Garet')
        fonts.use_tired(True)
        self.assertEqual(fonts.pick('Sans Semi-Bold 8'), 'Garet Book 10')
        self.assertIn('font-family: "Garet"', fonts.css())

    def test_apagada_todo_vuelve_a_como_estaba(self):
        fonts.use_tired(True)
        fonts.use_tired(False)
        self.assertEqual(fonts.pick('Sans 10'), 'Sans 10')
        self.assertEqual(fonts.css(), '')

    def test_tres_niveles_de_tamano(self):
        self.assertEqual(fonts.TIRED_SCALES, (125, 150, 200))
        fonts.use_tired(True)
        for pct, size in ((125, '12.5'), (150, '15'), (200, '20')):
            self.assertEqual(fonts.use_scale(pct), pct)
            self.assertEqual(fonts.pick('Sans 10'), f'Sans Medium {size}')
            self.assertIn(f'font-size: {pct}%', fonts.css())

    def test_un_nivel_que_no_existe_deja_125(self):
        self.assertEqual(fonts.use_scale(300), 125)

    def test_el_vidrio_se_cierra_con_la_vista_cansada(self):
        self.assertEqual(fonts.glass(.5), .5)
        fonts.use_tired(True)
        self.assertEqual(fonts.glass(.5), fonts.TIRED_GLASS)
        self.assertEqual(fonts.glass(.95), .95)

    def test_lo_elegido_usa_la_tinta_del_tema_y_no_un_blanco_fijo(self):
        fonts.use_tired(True)
        old = fonts.TIRED_INK
        fonts.TIRED_INK = '#123456'
        try:
            self.assertIn('color: #123456', fonts.css())
        finally:
            fonts.TIRED_INK = old

    def test_el_foco_se_ve_en_los_campos_y_menus(self):
        fonts.use_tired(True)
        for selector in ('entry:focus-within', 'dropdown:focus-within', 'textview:focus-within', 'switch:focus-visible'):
            self.assertIn(selector, fonts.css())


if __name__ == '__main__':
    unittest.main()
