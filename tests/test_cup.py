import unittest

import cairo

from elyares import cup, pomodoroview


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


if __name__ == '__main__':
    unittest.main()
