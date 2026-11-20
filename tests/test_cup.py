import unittest

import cairo

from elyares import cup, pomodoro, pomodoroview


def status(phase='idle', progress=0.0, parked=False, task='', running=None):
    return dict(phase=phase, progress=progress, parked=parked, task=task,
                running=phase != 'idle' if running is None else running)


class Taza(unittest.TestCase):
    def test_en_foco_el_cafe_baja_y_en_descanso_sube(self):
        self.assertEqual(cup.state_of(status('focus', .25)), 'vaciando')
        self.assertAlmostEqual(cup.level_of(status('focus', .25)), .75)
        for phase in ('break', 'short_break', 'long_break', 'break-long'):
            self.assertEqual(cup.state_of(status(phase, .4)), 'llenando')
            self.assertAlmostEqual(cup.level_of(status(phase, .4)), .4)

    def test_parado_depende_de_si_hay_algo_en_el_refri(self):
        self.assertEqual((cup.state_of(status()), cup.level_of(status())), ('vacia', 0.0))
        self.assertEqual((cup.state_of(status(parked=True)), cup.level_of(status(parked=True))), ('refri', .55))
        self.assertEqual((cup.state_of(None), cup.level_of(None)), ('vacia', 0.0))

    def test_el_nivel_no_sale_de_cero_a_uno(self):
        self.assertEqual(cup.level_of(status('focus', 1.7)), 0.0)
        self.assertEqual(cup.level_of(status('break', -.3)), 0.0)

    def test_dibuja_todos_los_estados_sin_error(self):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 200)
        cr = cairo.Context(surface)
        for state in ('vacia', 'vaciando', 'repaso', 'llenando', 'refri'):
            for level in (0.0, .5, 1.0, 3.0):
                cup.draw(cr, 0, 0, 200, state, level, now=1.3, alpha=.8)
        self.assertNotEqual(bytes(surface.get_data()), bytes(200 * 200 * 4))


class TareasDelProyecto(unittest.TestCase):
    TASKS = [dict(id='1', title='a', repo='/r/uno'), dict(id='2', title='b', repo='/r/dos'),
             dict(id='3', title='c', repo='')]

    def test_solo_las_del_proyecto_abierto(self):
        self.assertEqual([t['id'] for t in pomodoroview.project_tasks(self.TASKS, '/r/dos')], ['2'])

    def test_sin_proyecto_no_hay_tareas(self):
        self.assertEqual(pomodoroview.project_tasks(self.TASKS, ''), [])

    def test_botones_segun_el_reloj(self):
        self.assertEqual(pomodoroview.buttons_for(None), [])
        self.assertEqual(pomodoroview.buttons_for(status()), [])
        keys = [k for k, _ in pomodoroview.buttons_for(status('focus', task='x'))]
        self.assertEqual(keys, ['pause', 'void', 'done'])
        self.assertEqual([k for k, _ in pomodoroview.buttons_for(status(parked=True))], ['resume'])


class BotonesEnFilas(unittest.TestCase):
    ALL = [('resume', 'Sacar del refri'), ('pause', 'Al refri'), ('void', 'Tirar'), ('done', 'Hecha')]

    def test_los_cuatro_botones_en_un_panel_angosto_pasan_a_una_segunda_fila(self):
        placed = pomodoroview.button_rows(self.ALL, 290)
        self.assertEqual({row for *_r, row, _w in [(p[0], p[3], p[4]) for p in placed]}, {0, 1})
        for key, label, x, row, bw in placed:
            self.assertLessEqual(x + bw, 290, key)                  # ninguno se sale
        self.assertEqual(placed[0][2], 0)                           # cada fila empieza en el borde

    def test_con_sitio_de_sobra_todos_van_en_una_fila(self):
        self.assertEqual({p[3] for p in pomodoroview.button_rows(self.ALL, 600)}, {0})

    def test_un_boton_mas_ancho_que_el_sitio_se_queda_solo_en_su_fila(self):
        placed = pomodoroview.button_rows([('a', 'x' * 80), ('b', 'Hecha')], 100)
        self.assertEqual([p[3] for p in placed], [0, 1])

    def test_el_bloque_de_arriba_crece_con_las_filas_y_sin_botones_es_la_taza(self):
        self.assertEqual(pomodoroview.header_height([], 290), pomodoroview.PM_CUP)
        one = pomodoroview.header_height([('done', 'Hecha')], 290)
        two = pomodoroview.header_height(self.ALL, 290)
        self.assertGreater(two, one)


class DescripcionDeLaTarea(unittest.TestCase):
    def setUp(self):
        import os
        import sqlite3
        import tempfile
        from unittest import mock
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        db = os.path.join(self.dir.name, 'coffe.db')
        con = sqlite3.connect(db)
        con.executescript('''CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE tasks (id INTEGER PRIMARY KEY, project_id INTEGER, title TEXT, notes TEXT,
                                state TEXT, estimate_pomodoros INTEGER, vault_note TEXT);
            INSERT INTO projects VALUES (1, 'elyares-engineer');
            INSERT INTO tasks VALUES (1, 1, 'Con notas largas de verdad', 'Hay que probar el panel.', 'pending', 2, NULL);
            INSERT INTO tasks VALUES (2, 1, 'Con nota del vault', NULL, 'pending', 1, 'hu.md');
            INSERT INTO tasks VALUES (3, 1, 'Sin nada', '', 'pending', NULL, NULL);
            INSERT INTO tasks VALUES (4, 1, 'Archivada', '', 'archived', NULL, NULL);''')
        con.commit()
        con.close()
        with open(os.path.join(self.dir.name, 'hu.md'), 'w') as f:
            f.write('---\nid: HU-1\n---\n\n# t\n\n## Historia\n\nComo **Yared** quiero algo\npara ver.\n\n## Criterios\n\n- otro\n')
        for patch in (mock.patch.object(pomodoro, 'DB', db), mock.patch.object(pomodoro, 'VAULT', self.dir.name)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_las_notas_de_coffe_mandan(self):
        info = pomodoro.task_info(1)
        self.assertEqual((info['title'], info['project'], info['estimate'], info['text']),
                         ('Con notas largas de verdad', 'elyares-engineer', 2, 'Hay que probar el panel.'))

    def test_sin_notas_sale_la_historia_de_la_nota_del_vault(self):
        self.assertEqual(pomodoro.task_info(2)['text'], 'Como Yared quiero algo para ver.')

    def test_los_pasos_numerados_corridos_pasan_cada_uno_a_su_linea(self):
        self.assertEqual(pomodoro.format_description('Probar. 1) Abrir el panel. 2) Pulsar la i. 3) Cerrar.'),
                         'Probar.\n1) Abrir el panel.\n2) Pulsar la i.\n3) Cerrar.')
        self.assertEqual(pomodoro.format_description('Una linea\n\n  otra  \n'), 'Una linea\notra')   # lo que ya viene en líneas se queda
        self.assertEqual(pomodoro.format_description('Sin pasos, 3 veces seguidas.'), 'Sin pasos, 3 veces seguidas.')

    def test_la_burbuja_crece_con_la_descripcion_hasta_lo_que_deja_la_pantalla(self):
        short = pomodoroview.detail_height(dict(text='una linea'))
        long = pomodoroview.detail_height(dict(text='\n'.join(f'paso {i}' for i in range(8))))
        self.assertGreater(long, short)
        view = pomodoroview.detail_view_max(900, 200)
        self.assertEqual(pomodoroview.detail_height(dict(text='x'), text_h=5000, view_max=view),
                         pomodoroview.DETAIL_HEAD + view + 10)                   # lo que sobra se ve con la rueda
        self.assertEqual(pomodoroview.detail_height(dict(text='x'), text_h=40, view_max=view),
                         pomodoroview.DETAIL_HEAD + 40 + 10)                     # lo medido manda sobre la estimación

    def test_el_alto_visible_sigue_a_la_pantalla_con_su_minimo_y_su_tope(self):
        line = pomodoroview.DETAIL_LINE
        self.assertEqual(pomodoroview.detail_view_max(0, 0), 12 * line)                        # sin pantalla conocida
        self.assertEqual(pomodoroview.detail_view_max(300, 280), pomodoroview.DETAIL_MIN_LINES * line)   # casi sin sitio
        self.assertEqual(pomodoroview.detail_view_max(4000, 0), pomodoroview.DETAIL_MAX_LINES * line)   # pantalla enorme
        self.assertLess(pomodoroview.detail_view_max(700, 300), pomodoroview.detail_view_max(1200, 300))

    def test_sin_nada_la_descripcion_queda_vacia_y_una_tarea_que_no_existe_es_none(self):
        self.assertEqual(pomodoro.task_info(3)['text'], '')
        self.assertIsNone(pomodoro.task_info(99))

    def test_los_titulos_salen_completos_y_sin_las_archivadas(self):
        self.assertEqual(pomodoro.read_titles(), {'1': 'Con notas largas de verdad', '2': 'Con nota del vault', '3': 'Sin nada'})

    def test_sin_base_de_coffe_no_hay_titulos_ni_error(self):
        from unittest import mock
        with mock.patch.object(pomodoro, 'DB', '/no/existe.db'):
            self.assertEqual(pomodoro.read_titles(), {})
            self.assertIsNone(pomodoro.task_info(1))


class ListaDeTareas(unittest.TestCase):
    def test_las_del_proyecto_abierto_no_se_pierden_tras_las_primeras_doce_de_otros(self):
        from unittest import mock
        text = '\n'.join([f'  {i}  pendiente —            alta    t{i}  [0] otro / p' for i in range(1, 30)]
                         + ['  304  pendiente —            media   Test panel  [0/1] personal / elyares-engineer'])
        watch = pomodoro.Watcher()
        with mock.patch.object(pomodoro, 'snapshot', return_value=None), \
                mock.patch.object(pomodoro, 'read_titles', return_value={}), \
                mock.patch.object(pomodoro, 'run', side_effect=lambda *a: (True, text if a[:1] == ('task',) else
                                                                           '[1] personal\n  [2] elyares-engineer  ← /r/eng')):
            watch._fetch(True)
        self.assertEqual(len(watch.read()[1]), pomodoro.MAX_TASKS)            # la ventana, como antes
        mine = pomodoroview.project_tasks(watch.read(None)[1], '/r/eng')
        self.assertEqual([t['id'] for t in mine], ['304'])


if __name__ == '__main__':
    unittest.main()
