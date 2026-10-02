"""El reloj de coffe: foco, avisos de descanso y lo que dice la burbuja."""

import json
import unittest

from elyares import coffe
from elyares.coffe import Tracker

TOOLTIP = 'Pomodoro · 12:40 restantes\n\nArreglar el flaky\nelyares-mascota\n\n3 pomodoros hoy\n1 h 15 min'


def line(phase, tooltip=TOOLTIP):
    return json.dumps({'class': phase, 'tooltip': tooltip})


def kinds(msgs):
    return [m['event'] for m in msgs]


class Reloj(unittest.TestCase):
    def setUp(self):
        self.t = Tracker()

    def test_la_primera_linea_no_anuncia(self):
        msgs = self.t.step(line('focus'))
        self.assertEqual(kinds(msgs), ['source', 'focus'])
        self.assertEqual(msgs[0], {'event': 'source', 'name': 'coffe', 'ok': True, 'note': 'en foco',
                                   'tip': ['Quedan 12:40', 'Tarea: Arreglar el flaky',
                                           '3 pomodoros hoy · 1 h 15 min']})
        self.assertEqual(msgs[1], {'event': 'focus', 'on': True})

    def test_la_misma_linea_calla(self):
        self.t.step(line('focus'))
        self.assertEqual(self.t.step(line('focus')), [])

    def test_solo_cambia_el_reloj(self):
        self.t.step(line('focus'))
        msgs = self.t.step(line('focus', TOOLTIP.replace('12:40', '12:39')))
        self.assertEqual(kinds(msgs), ['source'])
        self.assertEqual(msgs[0]['tip'][0], 'Quedan 12:39')

    def test_descanso_y_vuelta(self):
        self.t.step(line('focus'))
        msgs = self.t.step(line('break', 'Descanso · 05:00'))
        self.assertEqual(kinds(msgs), ['source', 'focus', 'alert'])
        self.assertEqual(msgs[1]['on'], False)
        self.assertEqual((msgs[2]['message'], msgs[2]['tone'], msgs[2]['ttl']),
                         ('Descanso · 05:00', 'ok', coffe.NOTICE_SECS))
        msgs = self.t.step(line('idle', ''))
        self.assertEqual(kinds(msgs), ['source', 'alert'])
        self.assertEqual(msgs[1]['message'], 'Se acabó el descanso')

    def test_reloj_caido(self):
        self.t.step(line('focus'))
        msgs = self.t.step(line('off', 'no se pudo conectar\nmás'))
        self.assertEqual(kinds(msgs), ['source', 'focus'])
        self.assertEqual((msgs[0]['ok'], msgs[0]['why']), (False, 'no se pudo conectar'))
        self.assertEqual(msgs[1]['on'], False)

    def test_basura(self):
        self.assertEqual(self.t.step('no es json'), [])
        self.assertEqual(self.t.step('[]'), [])
        self.assertEqual(self.t.step('{}'), [])


class Burbuja(unittest.TestCase):
    def test_sin_tarea(self):
        tip = coffe._tip({'tooltip': 'Descanso · 04:10\n\n3 pomodoros hoy'})
        self.assertEqual(tip, ['Quedan 04:10', '3 pomodoros hoy'])

    def test_texto_escapado(self):
        tip = coffe._tip({'tooltip': 'Pomodoro · 01:00\n\nA &amp; B\nproj\n\nhoy'})
        self.assertEqual(tip[1], 'Tarea: A & B')

    def test_vacio(self):
        self.assertEqual(coffe._tip({}), [])


if __name__ == '__main__':
    unittest.main()
