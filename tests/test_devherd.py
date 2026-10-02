"""El vigilante de DevHerd Observe: qué avisa al comparar dos fotos."""

import unittest

from elyares import devherd
from elyares.devherd import Watcher


def issue(iid=1, count=1, level='error', **extra):
    return {'id': iid, 'event_count': count, 'level': level, 'title': 'Boom', 'project': 'api',
            'culprit': 'app.py:10', 'service': 'web', **extra}


def container(status='running', restarts=0, cid='c1', **extra):
    return {'container_id': cid, 'status': status, 'restart_count': restarts, 'project': 'api',
            'service': 'web', 'name': 'api-web-1', **extra}


def snap(issues=(), containers=()):
    return {'issues': list(issues), 'containers': list(containers)}


class WatcherCase(unittest.TestCase):
    def setUp(self):
        self.exits = {}
        self.events = {}
        self.w = Watcher(expected_up=True, exit_info=self.exits.get,
                         tail=lambda cid: [f'log de {cid}'],
                         last_event=lambda project, iid: self.events.get(iid))

    def step(self, *args, now=0, **kw):
        return self.w.step(snap(*args, **kw), now)


class Errores(WatcherCase):
    def test_la_primera_foto_no_anuncia(self):
        self.assertEqual(self.step([issue(count=5)], [container('exited')]), [])

    def test_error_otra_vez(self):
        self.step([issue(count=1)])
        self.events[1] = {'event_id': 'ev9', 'transaction': 'GET /api/x'}
        msg, = self.step([issue(count=3)])
        self.assertEqual(msg['session_id'], 'devherd:issue:1')
        self.assertEqual((msg['name'], msg['message']), ('api', 'Error otra vez (3): Boom'))
        self.assertEqual((msg['where'], msg['note'], msg['lines']),
                         ('app.py:10', 'web · 3 eventos', ['GET /api/x']))
        self.assertEqual([a['label'] for a in msg['actions']], ['Timeline', 'Abrir'])
        self.assertEqual(msg['actions'][0]['cmd'], ['devherd', 'observe', 'timeline', 'ev9'])

    def test_error_nuevo(self):
        self.step([])
        msg, = self.step([issue(iid=2, first_seen='t', last_seen='t')])
        self.assertEqual(msg['message'], 'Error nuevo: Boom')
        # Sin evento que mostrar no hay Timeline.
        self.assertEqual([a['label'] for a in msg['actions']], ['Abrir'])

    def test_sin_eventos_nuevos_o_sin_ser_error_calla(self):
        self.step([issue(count=2), issue(iid=2, level='warning')])
        self.assertEqual(self.step([issue(count=2), issue(iid=2, count=9, level='warning')]), [])


class Contenedores(WatcherCase):
    def test_reinicio_y_bucle(self):
        self.step(containers=[container()])
        msg, = self.step(containers=[container(restarts=1)], now=10)
        self.assertEqual((msg['session_id'], msg['message']), ('devherd:ct:api/web', 'web se reinició'))
        self.assertEqual((msg['where'], msg['note'], msg['lines']),
                         ('api-web-1', '1 reinicio', ['log de c1']))
        self.assertEqual(msg['actions'][0]['cmd'][:2], ['docker', 'logs'])
        msg, = self.step(containers=[container(restarts=3)], now=20)
        self.assertEqual(msg['message'], 'web reinicia en bucle (3 veces en 5 min)')
        # Fuera de los 5 min vuelve a ser un reinicio suelto.
        msg, = self.step(containers=[container(restarts=4)], now=20 + devherd.LOOP_SECS + 1)
        self.assertEqual(msg['message'], 'web se reinició')

    def test_caida_con_codigo_de_error(self):
        labels = {devherd.WORKDIR_LABEL: '/srv/api'}
        self.step(containers=[container(labels=labels)])
        self.exits['c1'] = (1, False)
        msg, = self.step(containers=[container('exited', labels=labels)])
        self.assertEqual(msg['message'], 'web se cayó (código 1)')
        self.assertEqual([a['label'] for a in msg['actions']], ['Logs', 'Levantar'])
        self.assertEqual(msg['actions'][1]['cmd'], ['devherd', 'up', '/srv/api'])
        # Al volver a correr, se quita el aviso.
        self.assertEqual(self.step(containers=[container(labels=labels)]),
                         [{'event': 'alert-clear', 'session_id': 'devherd:ct:api/web'}])

    def test_sin_memoria(self):
        self.step(containers=[container()])
        self.exits['c1'] = (137, True)
        msg, = self.step(containers=[container('exited')])
        self.assertEqual(msg['message'], 'web se cayó (sin memoria)')

    def test_parado_a_mano_no_es_caida(self):
        self.step(containers=[container()])
        self.exits['c1'] = (143, False)
        self.assertEqual(self.step(containers=[container('exited')]), [])

    def test_recreado_quita_el_aviso(self):
        self.step(containers=[container()])
        self.exits['c1'] = (1, False)
        self.step(containers=[container('exited')])
        self.assertEqual(self.step(containers=[container(cid='c2')]),
                         [{'event': 'alert-clear', 'session_id': 'devherd:ct:api/web'}])


class Colector(unittest.TestCase):
    def test_avisa_a_la_tercera_y_se_quita_al_volver(self):
        w = Watcher(expected_up=True)
        self.assertEqual([w.step(None, 0), w.step(None, 0)], [[], []])
        msg, = w.step(None, 0)
        self.assertEqual((msg['session_id'], msg['message']),
                         ('devherd:collector', 'Observe no responde'))
        self.assertEqual(msg['actions'][0]['label'], 'Iniciar')
        self.assertEqual(w.step(None, 0), [])
        self.assertEqual(w.step(snap(), 0), [{'event': 'alert-clear',
                                              'session_id': 'devherd:collector'}])

    def test_si_nunca_estuvo_arriba_no_avisa(self):
        w = Watcher(expected_up=False)
        self.assertEqual([w.step(None, 0) for _ in range(4)], [[]] * 4)


if __name__ == '__main__':
    unittest.main()
