"""El vigilante de GitHub: avisos, resumen de la burbuja y la ficha de un PR en rojo."""

import json
import unittest
from unittest import mock

from elyares import github
from elyares.github import Watcher


def pr(n=1, checks=None):
    return {'url': f'https://github.com/o/r/pull/{n}', 'number': n, 'title': f'cambio {n}',
            'repo': 'r', 'slug': 'o/r', 'checks': checks}


def snap(prs=(), reviews=()):
    return {'prs': {p['url']: p for p in prs}, 'reviews': {p['url']: p for p in reviews}}


class Avisos(unittest.TestCase):
    def setUp(self):
        self.asked = []
        self.w = Watcher(failed_checks=lambda account, p: [('build', 77), ('lint', None)],
                         log_tail=lambda account, p, run: self.asked.append(run) or ['E fallo'])

    def test_la_primera_foto_no_anuncia(self):
        self.assertEqual(self.w.step('yo', snap([pr(checks='FAILURE')], [pr(2)])), [])

    def test_sin_respuesta_no_pierde_la_foto(self):
        self.w.step('yo', snap([pr(checks='PENDING')]))
        self.assertEqual(self.w.step('yo', None), [])
        msg, = self.w.step('yo', snap([pr(checks='SUCCESS')]))
        self.assertEqual(msg['tone'], 'ok')

    def test_checks_en_verde(self):
        self.w.step('yo', snap([pr(checks='PENDING')]))
        msg, = self.w.step('yo', snap([pr(checks='SUCCESS')]))
        self.assertEqual(msg['session_id'], 'gh:ci:https://github.com/o/r/pull/1')
        self.assertEqual((msg['name'], msg['message']), ('r', 'PR #1: checks en verde · cambio 1'))
        self.assertNotIn('actions', msg)

    def test_checks_en_rojo_llevan_ficha(self):
        self.w.step('yo', snap([pr(checks='PENDING')]))
        msg, = self.w.step('yo', snap([pr(checks='FAILURE')]))
        self.assertEqual((msg['tone'], msg['message']), ('', 'PR #1: checks en rojo · cambio 1'))
        self.assertEqual((msg['where'], msg['note'], msg['lines']),
                         ('build y 1 más', '2 checks caídos', ['E fallo']))
        self.assertEqual([a['label'] for a in msg['actions']], ['Reintentar', 'Abrir PR'])
        self.assertEqual(self.asked, [77])

    def test_un_pr_nuevo_y_uno_que_sigue_igual_callan(self):
        self.w.step('yo', snap([pr(checks='FAILURE')]))
        self.assertEqual(self.w.step('yo', snap([pr(checks='FAILURE'), pr(2, 'FAILURE')])), [])

    def test_revision_pedida(self):
        self.w.step('yo', snap())
        msg, = self.w.step('yo', snap(reviews=[pr(4)]))
        self.assertEqual((msg['tone'], msg['message']),
                         ('info', 'Te piden revisar el PR #4 · cambio 4'))
        self.assertEqual(self.w.step('yo', snap(reviews=[pr(4)])), [])

    def test_cada_cuenta_tiene_su_foto(self):
        self.w.step('a', snap([pr(checks='PENDING')]))
        self.assertEqual(self.w.step('b', snap([pr(checks='SUCCESS')])), [])


class Ficha(unittest.TestCase):
    def test_con_run_de_actions(self):
        card = github.card('ElYares', pr(), [('build', 77)], ['uno', 'dos'])
        self.assertEqual((card['where'], card['note'], card['lines']),
                         ('build', '1 check caído', ['uno', 'dos']))
        retry, open_ = card['actions']
        self.assertEqual(retry['cmd'][-3:], ['ElYares', '77', 'o/r'])
        self.assertEqual((retry['term'], retry['after']), (True, 'clear'))
        # El token se pide al pulsar: no viaja en la alerta.
        self.assertIn('gh auth token --user "$1"', retry['cmd'][2])
        self.assertEqual(open_, {'label': 'Abrir PR', 'url': pr()['url'], 'after': 'dismiss'})

    def test_sin_run_solo_abre_y_lista_los_demas(self):
        card = github.card('yo', pr(), [('ci/circle', None), ('deploy', None)], [])
        self.assertEqual(card['lines'], ['deploy'])
        self.assertEqual([a['label'] for a in card['actions']], ['Abrir PR'])

    def test_sin_saber_que_fallo(self):
        card = github.card('yo', pr(), [], [])
        self.assertEqual((card['where'], card['note'], card['lines']), ('', '', []))
        self.assertEqual(len(card['actions']), 1)

    def test_clean_log(self):
        log = ('build\tRun tests\t2026-10-01T10:00:00.1234567Z FAILED tests/test_x.py::test_a\n'
               'build\tRun tests\t2026-10-01T10:00:01.0000000Z ##[group]Run pytest\n'
               'build\tRun tests\t2026-10-01T10:00:01.5000000Z \n'
               'build\tRun tests\t2026-10-01T10:00:02.0000000Z ##[error]Process completed with exit code 1.\n')
        self.assertEqual(github.clean_log(log),
                         ['FAILED tests/test_x.py::test_a', 'Process completed with exit code 1.'])
        self.assertEqual(github.clean_log(None), [])

    def test_log_tail_se_queda_con_el_final(self):
        log = ''.join(f'job\tpaso\t2026-10-01T10:00:00.0Z linea {i}\n' for i in range(20))
        with mock.patch.object(github, '_gh', return_value=log) as gh:
            lines = github.log_tail('yo', pr(), 77, n=3)
        self.assertEqual(lines, ['linea 17', 'linea 18', 'linea 19'])
        self.assertEqual(gh.call_args.args, ('yo', 'run', 'view', '77', '--repo', 'o/r', '--log-failed'))


def rollup(nodes):
    return json.dumps({'data': {'repository': {'pullRequest': {'commits': {'nodes': [
        {'commit': {'statusCheckRollup': {'contexts': {'nodes': nodes}}}}]}}}}})


class Preguntas(unittest.TestCase):
    def test_failed_checks(self):
        nodes = [
            {'__typename': 'StatusContext', 'context': 'ci/circle', 'state': 'ERROR'},
            {'__typename': 'CheckRun', 'name': 'lint', 'conclusion': 'SUCCESS',
             'checkSuite': {'workflowRun': {'databaseId': 5}}},
            {'__typename': 'CheckRun', 'name': 'build', 'conclusion': 'FAILURE',
             'checkSuite': {'workflowRun': {'databaseId': 77}}},
            {'__typename': 'CheckRun', 'name': 'externo', 'conclusion': 'TIMED_OUT',
             'checkSuite': {'workflowRun': None}},
            {'__typename': 'CheckRun', 'name': 'saltado', 'conclusion': 'SKIPPED'},
            None,
        ]
        with mock.patch.object(github, '_gh', return_value=rollup(nodes)) as gh:
            checks = github.failed_checks('yo', pr(3))
        # Primero los de Actions: tienen log y se pueden reintentar.
        self.assertEqual(checks, [('build', 77), ('ci/circle', None), ('externo', None)])
        self.assertIn('number=3', gh.call_args.args)
        self.assertIn('owner=o', gh.call_args.args)

    def test_failed_checks_sin_respuesta(self):
        for out in (None, 'no es json', json.dumps({'data': {'repository': None}}),
                    json.dumps({'data': {'repository': {'pullRequest': {'commits': {'nodes': [
                        {'commit': {'statusCheckRollup': None}}]}}}}})):
            with mock.patch.object(github, '_gh', return_value=out):
                self.assertEqual(github.failed_checks('yo', pr()), [])

    def test_snapshot(self):
        node = {'number': 1, 'title': 't', 'url': 'u1', 'repository': {'nameWithOwner': 'o/r'}}
        data = {'data': {
            'viewer': {'pullRequests': {'nodes': [
                {**node, 'commits': {'nodes': [{'commit': {'statusCheckRollup': {'state': 'SUCCESS'}}}]}},
                {**node, 'url': 'u2', 'commits': {'nodes': [{'commit': {'statusCheckRollup': None}}]}}]}},
            'search': {'nodes': [{**node, 'url': 'u3'}, None]}}}
        with mock.patch.object(github, '_gh', return_value=json.dumps(data)):
            s = github.snapshot('yo')
        self.assertEqual({u: p['checks'] for u, p in s['prs'].items()}, {'u1': 'SUCCESS', 'u2': None})
        self.assertEqual(s['prs']['u1']['slug'], 'o/r')
        self.assertEqual(list(s['reviews']), ['u3'])
        with mock.patch.object(github, '_gh', return_value=None):
            self.assertIsNone(github.snapshot('yo'))


class Resumen(unittest.TestCase):
    def test_cuenta_los_checks(self):
        lines = github.summary({'a': snap([pr(1, 'SUCCESS'), pr(2, 'FAILURE'), pr(3)], [pr(9)]),
                                'b': snap([pr(1, 'SUCCESS'), pr(4, 'PENDING')]), 'c': None})
        self.assertEqual(lines, ['4 PRs abiertos: 1 en verde, 1 en rojo, 1 corriendo, 1 sin checks',
                                 '1 revisión pendiente', 'Cuentas: a, b · no respondió c'])

    def test_sin_nada(self):
        self.assertEqual(github.summary({'a': snap()}),
                         ['Sin PRs abiertos', 'Sin revisiones pendientes', 'Cuentas: a'])


if __name__ == '__main__':
    unittest.main()
