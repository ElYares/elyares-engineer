"""Los workflows sin pantalla: lo que se guarda, el borrador del editor y la
marcha de una ejecución."""

import json
import os
import tempfile
import unittest
from unittest import mock

from elyares import workflows
from elyares.workflows import Draft, Run, Step, Workflow


def chain(on_fail=workflows.STOP):
    return Workflow('revisar', '/x/proj', [Step('elyares-designer', 'propón'), Step('elyares-engineer', 'hazlo'),
                                           Step('elyares-reviewer', 'revísalo')], on_fail)


class Guardado(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        patcher = mock.patch.object(workflows.settings, 'path', lambda: os.path.join(self.dir.name, 'cfg', 's.json'))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_lo_guardado_vuelve_como_estaba(self):
        self.assertEqual(workflows.load(), [])          # sin archivo, ninguno
        workflows.save([chain(workflows.GO)])
        self.assertEqual(workflows.load(), [chain(workflows.GO)])
        self.assertEqual(os.stat(workflows.path()).st_mode & 0o777, 0o600)

    def test_lo_que_no_sirve_se_salta(self):
        os.makedirs(os.path.dirname(workflows.path()))
        with open(workflows.path(), 'w') as f:
            json.dump([{'name': '  '}, 'x', {'name': 'a', 'steps': [{'agent': 'otro', 'text': 'x'}, 3,
                                                                  {'agent': 'elyares-auditor', 'text': 'audita'}],
                                            'on_fail': 'explota'}], f)
        self.assertEqual(workflows.load(), [Workflow('a', '', [Step('elyares-auditor', 'audita')])])
        with open(workflows.path(), 'w') as f:
            f.write('{roto')
        self.assertEqual(workflows.load(), [])

    def test_si_no_se_puede_guardar_lo_dice(self):
        with mock.patch.object(workflows.os, 'replace', side_effect=PermissionError(13, 'no')):
            with self.assertRaises(OSError):
                workflows.save([chain()])


class Borrador(unittest.TestCase):
    def test_uno_nuevo_parte_del_proyecto_y_no_se_puede_lanzar_vacio(self):
        d = Draft(project='/x/proj')
        self.assertFalse(d.dirty)
        self.assertEqual(d.blocker([]), 'Añade al menos un paso para lanzarlo')
        d.add()
        self.assertTrue(d.dirty)
        self.assertEqual(d.blocker([]), 'Ponle un nombre para guardarlo')
        d.w.name = ' Revisar '
        self.assertEqual(d.name_problem([chain()]), 'Ya existe un workflow con ese nombre. Elige otro.')
        d.w.name = 'otro'
        self.assertEqual(d.blocker([chain()]), 'Escribe qué hace el paso 1')
        d.w.steps[0].text = 'hazlo'
        self.assertEqual(d.blocker([chain()]), '')
        d.w.project = ''                                # sin proyecto fijo también vale: donde estés
        self.assertEqual(d.blocker([chain()]), '')

    def test_los_pasos_se_ordenan_y_se_quitan(self):
        d = Draft(chain())
        self.assertEqual(d.move(0, -1), 0)              # el primero no sube
        self.assertEqual(d.move(2, 1), 2)               # ni el último baja
        self.assertEqual(d.move(2, -1), 1)
        self.assertEqual([s.agent for s in d.w.steps], ['elyares-designer', 'elyares-reviewer', 'elyares-engineer'])
        d.remove(0)
        self.assertEqual(len(d.w.steps), 2)
        d.remove(7)
        self.assertEqual(len(d.w.steps), 2)

    def test_editar_guarda_en_su_sitio_y_con_su_nombre_no_choca(self):
        first, second = chain(), Workflow('otro', '/x/proj', [Step(text='x')])
        d = Draft(first)
        self.assertEqual(d.name_problem([first, second]), '')
        d.w.name, d.w.steps[0].text = ' revisar bien ', '  propón dos  '
        found = d.store([first, second])
        self.assertEqual([w.name for w in found], ['revisar bien', 'otro'])
        self.assertEqual(found[0].steps[0].text, 'propón dos')
        self.assertEqual(first.name, 'revisar')         # el guardado no se toca hasta guardar
        d.kept()
        self.assertFalse(d.dirty)
        self.assertEqual(d.saved_as, 'revisar bien')
        # Uno nuevo va al final.
        new = Draft(project='/x/proj')
        new.w.name = 'tercero'
        self.assertEqual([w.name for w in new.store(found)], ['revisar bien', 'otro', 'tercero'])


class Marcha(unittest.TestCase):
    def setUp(self):
        self.now = 100.0

    def run_of(self, on_fail=workflows.STOP):
        return Run(chain(on_fail), clock=lambda: self.now)

    def test_cada_paso_recibe_lo_que_dejo_el_anterior(self):
        run = self.run_of()
        self.assertEqual(run.status(), 'Sin empezar.')
        self.assertEqual(run.prompt(0), 'propón' + workflows.RULE)
        run.begin(0)
        self.assertEqual(run.status(), 'Corriendo el paso 1 de 3…')
        self.now += 12
        self.assertEqual(run.seconds(0), 12)
        self.assertEqual(run.finish(True, 'un panel a la derecha'), 1)
        self.assertEqual((run.states[0], run.took[0]), (workflows.OK, 12))
        prompt = run.prompt(1)
        self.assertTrue(prompt.startswith('hazlo\n'))
        self.assertIn('paso 2 de 3 del workflow «revisar»', prompt)
        self.assertIn('paso 1 (elyares-designer):\n\nun panel a la derecha', prompt)
        run.begin(1)
        self.assertEqual(run.finish(True, 'hecho'), 2)
        run.begin(2)
        self.assertIsNone(run.finish(True, 'limpio'))
        self.assertTrue(run.done)
        self.assertEqual(run.status(), 'Terminó.')

    def test_si_un_paso_falla_para_o_sigue_segun_el_workflow(self):
        run = self.run_of()
        run.begin(0)
        self.assertIsNone(run.finish(False, why='falló: sin red'))
        self.assertEqual((run.failed, run.done), (0, False))
        self.assertEqual(run.status(), 'Se paró en el paso 1 de 3.')
        # Reintentarlo lo deja como si no hubiera fallado.
        run.begin(0)
        self.assertIsNone(run.failed)
        self.assertEqual(run.finish(True, 'ahora sí'), 1)

        run = self.run_of(workflows.GO)
        self.assertEqual(run.refuse(0, 'está ocupado con otro turno'), 1)
        self.assertEqual(run.why[0], 'no pudo empezar: está ocupado con otro turno')
        self.assertEqual(run.prompt(1), 'hazlo' + workflows.RULE)     # sin respuesta anterior, solo lo suyo
        run.begin(1)
        self.assertEqual(run.finish(True, 'hecho'), 2)
        run.begin(2)
        self.assertIsNone(run.finish(True, 'ok'))
        self.assertEqual(run.status(), 'Terminó, con 1 paso fallido.')

    def test_el_agente_avisa_si_su_paso_no_salio(self):
        self.assertIn('PASO FALLIDO:', workflows.RULE)
        self.assertEqual(workflows.verdict('Todo en orden.\n\nLa rama está al día.'), '')
        self.assertEqual(workflows.verdict('No abrí el PR.\n\nPASO FALLIDO: gh usa otra cuenta.'), 'gh usa otra cuenta')
        self.assertEqual(workflows.verdict('Revisé.\n\n**PASO FALLIDO:** develop va 3 commits atrás\n'),
                         'develop va 3 commits atrás')
        self.assertEqual(workflows.verdict('- `paso fallido: sin red`'), 'sin red')
        # Nombrar la marca a mitad de una respuesta larga no es avisar.
        self.assertEqual(workflows.verdict('Si fallara pondría PASO FALLIDO: x\n' + 'ok\n' * 6), '')
        self.assertEqual(workflows.verdict(''), '')

    def test_detenido_a_mano_no_sigue(self):
        run = self.run_of(workflows.GO)
        run.begin(0)
        run.stopped = True
        self.assertIsNone(run.finish(False, why='se quedó a medias: el turno se cortó'))
        self.assertEqual(run.status(), 'Lo detuviste.')


if __name__ == '__main__':
    unittest.main()
